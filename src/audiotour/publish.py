"""Write a tour's web bundle under ``site/``.

``publish`` writes ``site/<slug>/tour.json`` (format: docs/tour-json.md) and the mastered
audio, then the pages. ``pages`` rewrites only the pages, for every published tour:
``site/<slug>/index.html`` and ``manifest.webmanifest`` from the templates in
``site/player/``, and the tour list ``site/index.html``. Nothing under ``site/`` is
hand-written except the player itself (``site/player/``, ``site/sw.js``).

Audio files get a content hash in their name, so a re-master is a new URL and
phones that downloaded the old one fetch the new one instead of a stale cache.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from string import Template

from . import audio, config, songs
from .script import load_tracks

SITE_DIR = config.REPO_ROOT / "site"
PLAYER_DIR = SITE_DIR / "player"  # the templates; tests publish elsewhere but use these
SCHEMA = 1  # tour.json format version; bump only for changes an older player would misread
MODES = ("drive", "walk")
DEFAULT_THEME = "#14532d"


def publish(tour: config.Tour, site_dir: Path = SITE_DIR) -> None:
    out = site_dir / tour.slug
    audio_dir = out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    previous = {s["id"]: s for s in _read_json(out / "tour.json").get("stops", [])}
    stops_cfg = tour.settings.get("stops", {})
    player = tour.settings.get("player", {})
    mode = player.get("mode", "drive")
    if mode not in MODES:
        raise SystemExit(f"[player] mode = {mode!r}; expected one of {', '.join(MODES)}")
    tracks = {t.id: t for t in load_tracks(tour.draft)}
    stops, keep = [], set()
    for n, (sid, s) in enumerate(stops_cfg.items(), 1):
        t = tracks.get(sid)
        if t is None:
            raise SystemExit(f"[stops.{sid}] has no '## Script:' track in the draft")
        stop = {"id": sid, "n": n, "title": t.title, "lat": s["lat"], "lon": s["lon"],
                "radius": s.get("radius", 400), "place": s.get("place", ""),
                "strict": s.get("strict", False)}
        if "song" in s:
            stop["song"] = songs.to_json(sid, s["song"])  # tasks/006
        mp3 = tour.build / f"{sid}.mp3"
        old = previous.get(sid, {})
        if mp3.exists():
            digest = hashlib.sha256(mp3.read_bytes()).hexdigest()[:8]
            name = f"{sid}-{digest}.mp3"
            shutil.copyfile(mp3, audio_dir / name)
            keep.add(name)
            stop |= {"audio": f"audio/{name}", "bytes": mp3.stat().st_size,
                     "duration": round(audio.duration(mp3), 1)}
        elif old.get("audio") and (out / old["audio"]).exists():
            # No local build (a fresh clone or worktree): keep what is already published
            # rather than deleting committed audio.
            print(f"  {sid}: no build/{sid}.mp3; keeping the published {old['audio']}")
            keep.add(Path(old["audio"]).name)
            stop |= {k: old[k] for k in ("audio", "bytes", "duration") if k in old}
        else:
            print(f"  {sid}: not mastered yet; published without audio")
        stops.append(stop)
    for stale in audio_dir.glob("*.mp3"):
        if stale.name not in keep:
            stale.unlink()
    route_file = tour.root / "route.json"
    data = {"schema": SCHEMA, "slug": tour.slug, "title": tour.title, "mode": mode,
            "lookahead": player.get("lookahead", 2), "stops": stops,
            "route": json.loads(route_file.read_text()) if route_file.exists() else {}}
    (out / "tour.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    total = sum(s.get("bytes", 0) for s in stops)
    print(f"{tour.slug}: {len(stops)} stops, {len(keep)} with audio, {total / 1e6:.1f} MB")
    print(f"  -> {out.relative_to(site_dir.parent)}/tour.json")
    write_pages(tour, site_dir)
    write_index(site_dir)


def pages(site_dir: Path = SITE_DIR, tours_dir: Path = config.TOURS_DIR) -> None:
    """Rewrite every published tour's page and manifest, and the tour list. No audio needed."""
    for path in published(site_dir):
        write_pages(config.Tour(path.parent.name, tours_dir), site_dir)
    write_index(site_dir)


def published(site_dir: Path) -> list[Path]:
    """Every ``site/<slug>/tour.json``; other folders (the player, lab pages) are skipped."""
    return sorted(site_dir.glob("*/tour.json"))


def page_fields(tour: config.Tour, site_dir: Path) -> dict[str, str]:
    """Title, short name and theme colour from ``[tour]``, else the published title."""
    info = tour.info if tour.root.is_dir() else {}
    title = info.get("title") or _read_json(site_dir / tour.slug / "tour.json").get("title", tour.slug)
    theme = info.get("theme_color", DEFAULT_THEME)
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", theme):
        raise SystemExit(f"tours/{tour.slug}/tour.toml: theme_color {theme!r} is not a #hex colour")
    return {"title": title, "short_name": info.get("short_name", title), "theme_color": theme}


def write_pages(tour: config.Tour, site_dir: Path = SITE_DIR) -> None:
    out = site_dir / tour.slug
    out.mkdir(parents=True, exist_ok=True)
    f = page_fields(tour, site_dir)
    page = _template("tour.html").substitute(
        title=html.escape(f["title"]), theme_color=html.escape(f["theme_color"]))
    manifest = _template("tour.webmanifest").substitute(
        {k: json.dumps(v, ensure_ascii=False) for k, v in
         {"name": f["title"], "short_name": f["short_name"], "theme_color": f["theme_color"]}.items()})
    (out / "index.html").write_text(page)
    (out / "manifest.webmanifest").write_text(manifest)
    print(f"  -> {out.relative_to(site_dir.parent)}/index.html, manifest.webmanifest")


def tour_card(slug: str, data: dict) -> str:
    """One entry in the tour list: title, then mode, stop count and total minutes."""
    stops = data.get("stops", [])
    facts = [data.get("mode", "drive").capitalize(), f"{len(stops)} stop{'s' if len(stops) != 1 else ''}"]
    seconds = sum(s.get("duration", 0) for s in stops)
    if seconds:
        facts.append(f"{round(seconds / 60)} min")
    return (f'<a class="card" href="{html.escape(slug)}/"><div class="title">{html.escape(data.get("title", slug))}'
            f'</div><div class="sub">{" · ".join(facts)}</div></a>')


def write_index(site_dir: Path = SITE_DIR) -> None:
    tours = [(p.parent.name, _read_json(p)) for p in published(site_dir)]
    tours.sort(key=lambda t: (t[1].get("title", t[0]).lower(), t[0]))
    cards = "\n".join(tour_card(slug, data) for slug, data in tours) or "<p>No tours published yet.</p>"
    (site_dir / "index.html").write_text(_template("home.html").substitute(tours=cards))
    print(f"  -> {(site_dir / 'index.html').relative_to(site_dir.parent)} ({len(tours)} tours)")


def _template(name: str) -> Template:
    return Template((PLAYER_DIR / name).read_text())


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}
