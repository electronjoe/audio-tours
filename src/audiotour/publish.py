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
        stop |= nav_field(sid, s) | text_fields(sid, s)
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
    data["route"] |= route_end(tour)
    if (out / "map.json").exists():
        data["map"] = "map.json"  # the base map from `tour map` (task 010)
    (out / "tour.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    total = sum(s.get("bytes", 0) for s in stops)
    print(f"{tour.slug}: {len(stops)} stops, {len(keep)} with audio, {total / 1e6:.1f} MB")
    print(f"  -> {out.relative_to(site_dir.parent)}/tour.json")
    write_pages(tour, site_dir)
    write_index(site_dir)


def _point(value, where: str) -> list[float]:
    """A ``[lat, lon]`` pair from tour.toml, checked, so a typo fails at publish, not in Maps."""
    if (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
            and -90 <= value[0] <= 90 and -180 <= value[1] <= 180):
        return [float(v) for v in value]
    raise SystemExit(f"{where} = {value!r}; expected [lat, lon] in degrees")


def nav_field(sid: str, s: dict) -> dict:
    """A stop's ``nav`` for the Navigate link (task 003): ``[lat, lon]``, ``false`` (not a
    waypoint), or nothing (the player uses the trigger point)."""
    if "nav" not in s:
        return {}
    if s["nav"] is False:
        return {"nav": False}
    return {"nav": _point(s["nav"], f"[stops.{sid}] nav")}


LABEL_MAX, TEASER_MAX = 20, 90  # characters: a pin label beside a pin; one line on its card


def text_fields(sid: str, s: dict) -> dict:
    """A stop's optional ``label`` (the map pin's) and ``teaser`` (the pin card's line), task
    009: plain one-line strings, checked here so a long label fails at publish, not on a pin."""
    out = {}
    for key, most in (("label", LABEL_MAX), ("teaser", TEASER_MAX)):
        if key not in s:
            continue
        v = s[key]
        if not isinstance(v, str) or not v.strip() or "\n" in v or len(v.strip()) > most:
            raise SystemExit(f"[stops.{sid}] {key} = {v!r}; expected one line of 1 to {most} characters")
        out[key] = v.strip()
    return out


def route_end(tour: config.Tour) -> dict:
    """``[route] end`` from tour.toml: where the Navigate links finish (task 003)."""
    route = tour.settings.get("route", {})
    return {"end": _point(route["end"], "[route] end")} if "end" in route else {}


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


FALLBACK_KMH = 80  # trip time without OSRM's seconds, as `tour plan-check` assumes


def trip(route: dict) -> tuple[float, float]:
    """The drive's length in metres (outbound then return) and its time in seconds: OSRM's
    ``seconds`` when every leg has them, else FALLBACK_KMH. The player's setup screen agrees."""
    from .route import metres

    legs = [route.get(k) or [] for k in ("outbound", "return")]
    m = sum(metres(tuple(a), tuple(b)) for leg in legs for a, b in zip(leg, leg[1:]))
    times = route.get("seconds") or {}
    timed = times and all(times.values())
    return m, sum(v[-1] for v in times.values()) if timed else m / (FALLBACK_KMH / 3.6)


def about(seconds: float) -> str:
    """"about 1 h 50 min", to the nearest 5 minutes."""
    mins = max(5, round(seconds / 300) * 5)
    h, m = divmod(mins, 60)
    return "about " + (f"{h} h" + (f" {m} min" if m else "") if h else f"{m} min")


def tour_card(slug: str, data: dict) -> str:
    """One row in the tour list: the title, then mode, story count, length and driving time."""
    stops = data.get("stops", [])
    facts = [data.get("mode", "drive").capitalize(), f"{len(stops)} stor{'y' if len(stops) == 1 else 'ies'}"]
    metres, seconds = trip(data.get("route", {}))
    if metres:
        facts += [f"{round(metres / 1000)} km", about(seconds)]
    return (f'<li><a class="row" href="{html.escape(slug)}/"><b>{html.escape(data.get("title", slug))}</b>'
            f'<small>{" · ".join(facts)}</small></a></li>')


def write_index(site_dir: Path = SITE_DIR) -> None:
    tours = [(p.parent.name, _read_json(p)) for p in published(site_dir)]
    tours.sort(key=lambda t: (t[1].get("title", t[0]).lower(), t[0]))
    cards = "\n".join(tour_card(slug, data) for slug, data in tours) or "<li>No tours published yet.</li>"
    (site_dir / "index.html").write_text(_template("home.html").substitute(tours=cards))
    print(f"  -> {(site_dir / 'index.html').relative_to(site_dir.parent)} ({len(tours)} tours)")


def _template(name: str) -> Template:
    return Template((PLAYER_DIR / name).read_text())


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}
