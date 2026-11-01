"""Write a tour's web bundle: ``site/<slug>/tour.json`` plus its mastered audio.

Audio files get a content hash in their name, so a re-master is a new URL and
phones that downloaded the old one fetch the new one instead of a stale cache.
"""

from __future__ import annotations

import hashlib
import json
import shutil

from . import audio, config
from .script import load_tracks

SITE_DIR = config.REPO_ROOT / "site"


def publish(book: config.Book) -> None:
    out = SITE_DIR / book.slug
    audio_dir = out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    stops_cfg = book.settings.get("stops", {})
    tracks = {t.id: t for t in load_tracks(book.draft)}
    stops, keep = [], set()
    for n, (sid, s) in enumerate(stops_cfg.items(), 1):
        t = tracks.get(sid)
        if t is None:
            raise SystemExit(f"[stops.{sid}] has no '## Script:' track in the draft")
        stop = {"id": sid, "n": n, "title": t.title, "lat": s["lat"], "lon": s["lon"],
                "radius": s.get("radius", 400), "place": s.get("place", ""),
                "strict": s.get("strict", False)}
        mp3 = book.build / f"{sid}.mp3"
        if mp3.exists():
            digest = hashlib.sha256(mp3.read_bytes()).hexdigest()[:8]
            name = f"{sid}-{digest}.mp3"
            shutil.copyfile(mp3, audio_dir / name)
            keep.add(name)
            stop |= {"audio": f"audio/{name}", "bytes": mp3.stat().st_size,
                     "duration": round(audio.duration(mp3), 1)}
        else:
            print(f"  {sid}: not mastered yet; published without audio")
        stops.append(stop)
    for old in audio_dir.glob("*.mp3"):
        if old.name not in keep:
            old.unlink()
    route_file = book.root / "route.json"
    tour = {"slug": book.slug, "title": book.settings.get("book", {}).get("title", book.slug),
            "lookahead": book.settings.get("player", {}).get("lookahead", 2), "stops": stops, "route": json.loads(route_file.read_text()) if route_file.exists() else {}}
    (out / "tour.json").write_text(json.dumps(tour, ensure_ascii=False, indent=1) + "\n")
    total = sum(s.get("bytes", 0) for s in stops)
    print(f"{book.slug}: {len(stops)} stops, {len(keep)} with audio, {total / 1e6:.1f} MB")
    print(f"  -> {out.relative_to(config.REPO_ROOT)}/tour.json")
