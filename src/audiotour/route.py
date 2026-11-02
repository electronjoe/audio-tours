"""Route and stop tools (docs/process/1-route.md, 2-stops.md; task 008).

``tour route <slug>`` asks OSRM for each leg in ``[route.<leg>]`` of ``tour.toml`` and writes
``route.json``: ``{"outbound": [[lat, lon], ...], "return": [...], "seconds": {...}}``. Each
leg keeps one OSRM vertex every ``SPACING`` metres along the road (and always the last), which
is how Hobart's first route.json was made. ``seconds`` holds OSRM's cumulative driving time at
each kept point, so ``plan-check`` can time the road between triggers offline.

``tour plan-check <slug>`` is offline. It places every stop's trigger on the route in sequence
and checks the rules in 2-stops.md: on the route, enough road time for the audio (and a song),
radius ranges, and ``strict`` where a later stop's zone is on the road to an earlier one.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .script import load_tracks

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"
SPACING = 300  # metres between kept route points
STEP = 20  # metres between samples when plan-check walks the route
ON_ROUTE = 100  # metres; a trigger further from the route is "not on the route". Generous,
# because 300 m chords cut curves: Hobart stop 6 is 1 m from OSRM's road but 71 m from route.json.
SONG_MARGIN = 60  # seconds: back from Spotify, a usable fix and some buffer (task 006)
QUIET = 60  # seconds of quiet wanted between stops (2-stops.md, Spacing)
SONG_SEGMENT = 60  # seconds budgeted for a song segment the script doesn't have yet
FALLBACK_KMH = 80  # planning speed when route.json has no "seconds" (2-stops.md)
RADII = {"drive": (300, 1000), "walk": (25, 80)}  # 2-stops.md
STALE = 0.15  # warn when a published length and the draft estimate differ by more

Point = tuple[float, float]


def metres(a: Point, b: Point) -> float:
    """Great-circle distance in metres (the player's formula)."""
    r = math.pi / 180
    h = (math.sin((b[0] - a[0]) * r / 2) ** 2
         + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


# --- tour route ------------------------------------------------------------------------


def legs_config(tour: config.Tour) -> dict[str, dict]:
    """``[route.<leg>]`` tables that have ``points``, in file order. Other ``[route]`` keys
    (``end``, task 003) are not legs."""
    route = tour.settings.get("route", {})
    legs = {k: v for k, v in route.items() if isinstance(v, dict) and "points" in v}
    for name, leg in legs.items():
        pts = leg["points"]
        if len(pts) < 2 or any(len(p) != 2 for p in pts):
            raise SystemExit(f"[route.{name}] points: need at least two [lat, lon] pairs")
    return legs


def osrm_url(points: list) -> str:
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    return f"{OSRM_URL}{coords}?overview=full&geometries=geojson&annotations=duration,distance&steps=false"


def http_get(url: str) -> dict:
    import httpx

    r = httpx.get(url, timeout=60, headers={"User-Agent": "audio-tours route tool"})
    r.raise_for_status()
    return r.json()


def fetch(url: str, cache_dir: Path, refresh: bool = False,
          get: Callable[[str], dict] = http_get) -> tuple[dict, bool]:
    """OSRM's answer for ``url``, from ``cache_dir`` when we have it. Returns (data, cached)."""
    path = cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text()), True
    data = get(url)
    if data.get("code") != "Ok":
        raise SystemExit(f"OSRM: {data.get('code')}: {data.get('message', '')}\n  {url}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": url, **data}))
    return data, False


@dataclass
class Leg:
    name: str
    points: list[Point]  # simplified
    seconds: list[float]  # cumulative OSRM time at each point
    distance: float  # OSRM metres
    duration: float  # OSRM seconds
    snaps: list[float] = field(default_factory=list)  # metres from each input point to the road


def leg_from_osrm(name: str, data: dict, spacing: float = SPACING) -> Leg:
    """Thin OSRM's full geometry to one vertex every ``spacing`` metres along the road."""
    route = data["routes"][0]
    full = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    durations = segment_seconds(full, route["legs"])
    elapsed = [0.0]
    for d in durations:
        elapsed.append(elapsed[-1] + d)
    keep, since = [0], 0.0
    for i in range(1, len(full)):
        since += metres(full[i - 1], full[i])
        if since >= spacing:
            keep.append(i)
            since = 0.0
    if keep[-1] != len(full) - 1:
        keep.append(len(full) - 1)
    return Leg(name, [(round(full[i][0], 5), round(full[i][1], 5)) for i in keep],
               [round(elapsed[i], 1) for i in keep], route["distance"], route["duration"],
               [w.get("distance", 0.0) for w in data.get("waypoints", [])])


def segment_seconds(full: list[Point], legs: list[dict]) -> list[float]:
    """Seconds per geometry segment. OSRM's annotations leave out turn penalties, so each
    leg's are scaled up to the leg's ``duration``. If they don't line up with the geometry one
    to one, each leg's time is spread over the whole geometry by length instead."""
    out = []
    for leg in legs:
        ann = leg.get("annotation", {}).get("duration", [])
        total = sum(ann)
        out += [d * leg["duration"] / total for d in ann] if total else ann
    if len(out) == len(full) - 1:
        return out
    lengths = [metres(full[i], full[i + 1]) for i in range(len(full) - 1)]
    whole = sum(lengths) or 1.0
    time_ = sum(leg["duration"] for leg in legs)
    return [time_ * x / whole for x in lengths]


def build(tour: config.Tour, refresh: bool = False, spacing: float = SPACING,
          get: Callable[[str], dict] = http_get, pause: float = 1.0) -> tuple[dict, list[Leg]]:
    """Fetch (or reuse) every leg and return route.json's content and the legs."""
    legs_cfg = legs_config(tour)
    if not legs_cfg:
        raise SystemExit(
            f"{config.show(tour.root / 'tour.toml')}: no [route.<leg>] tables with points.\n"
            "Add e.g.\n  [route.outbound]\n  points = [[start_lat, start_lon], [end_lat, end_lon]]\n"
            "  [route.return]\n  points = [[end_lat, end_lon], [start_lat, start_lon]]")
    cache_dir = tour.root / "cache" / "osrm"
    legs, fetched = [], False
    for name, cfg in legs_cfg.items():
        if fetched and pause:
            time.sleep(pause)  # the public OSRM server asks for at most one request a second
        data, cached = fetch(osrm_url(cfg["points"]), cache_dir, refresh, get)
        fetched = not cached
        legs.append(leg_from_osrm(name, data, spacing))
    content: dict = {leg.name: [list(p) for p in leg.points] for leg in legs}
    content["seconds"] = {leg.name: leg.seconds for leg in legs}
    return content, legs


def leg_table(legs: list[Leg]) -> list[str]:
    lines = [f"{'leg':<12} {'km':>6} {'min':>6} {'points':>7}"]
    for leg in legs:
        lines.append(f"{leg.name:<12} {leg.distance / 1000:>6.1f} {leg.duration / 60:>6.1f} {len(leg.points):>7}")
    if len(legs) > 1:
        lines.append(f"{'total':<12} {sum(x.distance for x in legs) / 1000:>6.1f}"
                     f" {sum(x.duration for x in legs) / 60:>6.1f} {sum(len(x.points) for x in legs):>7}")
    for leg in legs:
        for n, d in enumerate(leg.snaps):
            if d > 50:
                lines.append(f"note: {leg.name} point {n + 1} is {d:.0f} m from the nearest road")
    unknown = [leg.name for leg in legs if leg.name not in ("outbound", "return")]
    if unknown:
        lines.append(f"note: the player draws and simulates only outbound and return, not {', '.join(unknown)}")
    return lines


def write(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content) + "\n")


def compare(a: dict, b: dict) -> list[str]:
    """How closely two routes match, leg by leg: points in common, and the furthest any point
    of either lies from the other's line (a symmetric Hausdorff distance, in metres)."""
    lines = []
    for name in [k for k in a if k != "seconds" and k in b]:
        pa, pb = [tuple(p) for p in a[name]], [tuple(p) for p in b[name]]
        shared = len(set(pa) & set(pb))
        far = max(_far(pa, pb), _far(pb, pa))
        la, lb = _length(pa), _length(pb)
        lines.append(f"{name}: {len(pa)} vs {len(pb)} points, {shared} identical; "
                     f"{la / 1000:.1f} vs {lb / 1000:.1f} km; furthest apart {far:.0f} m")
    return lines


def _length(pts: list[Point]) -> float:
    return sum(metres(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _far(pa: list[Point], pb: list[Point]) -> float:
    dense = _densify(pb)
    return max(min(metres(p, q) for q in dense) for p in pa)


def _densify(pts: list[Point], step: float = STEP) -> list[Point]:
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, math.ceil(metres(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


# --- tour plan-check -------------------------------------------------------------------


@dataclass
class Trip:
    """The whole trip, legs end to end, sampled about every ``STEP`` metres."""
    pts: list[Point] = field(default_factory=list)
    km: list[float] = field(default_factory=list)  # along the trip
    t: list[float] = field(default_factory=list)  # seconds from the start, with waits between legs
    leg: list[str] = field(default_factory=list)
    timed: bool = True  # False: times come from FALLBACK_KMH


def trip(route: dict, waits: dict[str, float]) -> Trip:
    """Sample route.json's legs in order. Times come from its ``seconds`` (OSRM), else from
    FALLBACK_KMH; ``waits`` adds minutes parked at the end of a leg."""
    legs = [k for k, v in route.items() if k not in ("seconds", "end") and isinstance(v, list) and v]
    times = route.get("seconds") or {}
    out = Trip(timed=all(len(times.get(k, [])) == len(route[k]) for k in legs))
    dist = clock = 0.0
    for name in legs:
        pts = [tuple(x) for x in route[name]]
        secs = times[name] if out.timed else None
        if out.pts:
            dist += metres(out.pts[-1], pts[0])
        samples = [(pts[0], dist, secs[0] if secs else None)]  # (point, metres, OSRM seconds)
        start_dist = dist
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            seg = metres(a, b)
            n = max(1, math.ceil(seg / STEP))
            for k in range(1, n + 1):
                f = k / n
                samples.append(((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), dist + seg * f,
                                secs[i - 1] + (secs[i] - secs[i - 1]) * f if secs else None))
            dist += seg
        for pt, d, s in samples:
            out.pts.append(pt)
            out.km.append(d / 1000)
            out.t.append(clock + (s if s is not None else (d - start_dist) / (FALLBACK_KMH / 3.6)))
            out.leg.append(name)
        clock = out.t[-1] + waits.get(name, 0.0) * 60
    return out


@dataclass
class Placed:
    sid: str
    cfg: dict
    at: int | None = None  # sample nearest the trigger
    entry: int | None = None  # first sample inside the zone, on the way to `at`
    off: float = 0.0  # metres from the trigger point to the route


@dataclass
class Finding:
    level: str  # "error", "warning" or "note"
    sid: str
    message: str


def runs(d: list[float], radius: float) -> list[tuple[int, int]]:
    """(first, last) sample index of each stretch of road inside the zone."""
    out, start = [], None
    for i, x in enumerate(d):
        if x <= radius and start is None:
            start = i
        elif x > radius and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(d) - 1))
    return out


def place(path: Trip, stops: dict[str, dict]) -> tuple[list[Placed], dict[str, list[float]]]:
    """Find each trigger on the route, in sequence: the first stretch inside its zone, after
    the stop before it, that passes within ON_ROUTE of the trigger point."""
    placed, dists, after = [], {}, 0
    for sid, s in stops.items():
        c = (s["lat"], s["lon"])
        d = [metres(c, q) for q in path.pts]
        dists[sid] = d
        r = max(s.get("radius", 400), ON_ROUTE)
        p = Placed(sid, s)
        for a, b in runs(d, r):
            if b < after:
                continue
            lo = max(a, after)
            best = min(range(lo, b + 1), key=d.__getitem__)
            if d[best] <= ON_ROUTE:
                p.at, p.off = best, d[best]
                inside = [i for i in range(a, best + 1) if d[i] <= s.get("radius", 400)]
                p.entry = max(inside[0] if inside else best, after)
                after = best
                break
        else:
            p.off = min(d[after:] or d)
        placed.append(p)
    return placed, dists


def song_seconds(song: dict) -> float | None:
    """``length`` as "3:42", "1:02:03" or a number of seconds; None if unreadable."""
    v = song.get("length")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"\d+(:\d{1,2}){0,2}", v.strip()):
        total = 0.0
        for part in v.strip().split(":"):
            total = total * 60 + int(part)
        return total
    return None


def published(tour: config.Tour, site_dir: Path) -> dict[str, float]:
    path = site_dir / tour.slug / "tour.json"
    if not path.exists():
        return {}
    return {s["id"]: s["duration"] for s in json.loads(path.read_text()).get("stops", []) if "duration" in s}


def draft_seconds(tour: config.Tour) -> dict[str, tuple[float, str]]:
    """Each track's estimated length (as in `tour estimate`, plus the mastering's head, sting,
    title and tail), with its text for finding a song segment."""
    from .cli import WORDS_PER_MINUTE

    if not tour.draft.exists():
        return {}
    s = tour.settings
    m, r = s.get("master", {}), s.get("render", {})
    sting = s.get("sfx", {}).get(m.get("sting", ""), {}) if m.get("sting") else {}
    fixed = (m.get("head_seconds", 0.5) + m.get("tail_seconds", 2.5)
             + (sting.get("duration", 0) + m.get("sting_gap", 0.6) if sting else 0))
    out = {}
    for t in load_tracks(tour.draft):
        title = (len(t.title.split()) / WORDS_PER_MINUTE * 60 + m.get("title_gap", 1.2)
                 if r.get("announce_titles", True) else 0)
        talk = t.word_count / WORDS_PER_MINUTE * 60 + t.pause_seconds
        out[t.id] = (talk + title + fixed, " ".join(t.paragraphs))
    return out


def audio_seconds(tour: config.Tour, site_dir: Path) -> dict[str, tuple[float, str]]:
    """Each stop's audio length and where it came from: the mastered build, else the published
    tour.json, else the draft estimate."""
    from . import audio

    pub, draft = published(tour, site_dir), draft_seconds(tour)
    out = {}
    for sid in tour.settings.get("stops", {}):
        mp3 = tour.build / f"{sid}.mp3"
        if mp3.exists():
            out[sid] = (audio.duration(mp3), "built")
        elif sid in pub:
            out[sid] = (pub[sid], "published")
        elif sid in draft:
            out[sid] = (draft[sid][0], "draft")
    return out


@dataclass
class Row:
    sid: str
    km: float | None
    off: float
    audio: float | None
    source: str
    song: float | None
    need: float | None
    road: float | None
    to: str


def check(tour: config.Tour, route: dict, site_dir: Path | None = None) -> tuple[list[Row], list[Finding], Trip]:
    site_dir = site_dir or config.REPO_ROOT / "site"
    s = tour.settings
    stops: dict[str, dict] = s.get("stops", {})
    mode = s.get("player", {}).get("mode", "drive")
    lookahead = s.get("player", {}).get("lookahead", 2)
    waits = {k: float(v.get("wait", 0)) for k, v in s.get("route", {}).items()
             if isinstance(v, dict) and "wait" in v}
    path = trip(route, waits)
    if not path.pts:
        raise SystemExit("route.json has no legs")
    placed, dists = place(path, stops)
    lengths, draft = audio_seconds(tour, site_dir), draft_seconds(tour)
    findings: list[Finding] = []
    if not path.timed:
        findings.append(Finding("note", "", f"route.json has no \"seconds\"; road times assume {FALLBACK_KMH} km/h."
                                " Run `tour route` to time the legs with OSRM."))

    # On the route, in sequence.
    for p in placed:
        if p.at is None:
            findings.append(Finding("error", p.sid, f"trigger is not on the route after the stop before it"
                                    f" (nearest {p.off:.0f} m; allowed {ON_ROUTE} m)"))

    # Radii.
    lo, hi = RADII.get(mode, RADII["drive"])
    for sid, cfg in stops.items():
        r = cfg.get("radius", 400)
        if not lo <= r <= hi:
            findings.append(Finding("error", sid, f"radius {r} m is outside {lo}-{hi} m for a {mode} tour"))

    # Road time between triggers.
    rows = []
    for n, p in enumerate(placed):
        length, source = lengths.get(p.sid, (None, "none"))
        song_cfg = p.cfg.get("song")
        song = None
        need = length
        if length is None:
            findings.append(Finding("warning", p.sid, "no audio and no draft track; nothing to budget"))
        if p.sid in draft and source == "published":
            est = draft[p.sid][0]
            if abs(est - length) > STALE * length:
                findings.append(Finding("warning", p.sid, f"published audio is {length:.0f} s but the draft"
                                        f" reads as ~{est:.0f} s; has the script changed since mastering?"))
        if isinstance(song_cfg, dict):
            song = song_seconds(song_cfg)
            if song is None:
                findings.append(Finding("error", p.sid, f"song length {song_cfg.get('length')!r}: give it as \"m:ss\""))
            elif need is not None:
                need += song + SONG_MARGIN
                text = draft.get(p.sid, (0, ""))[1].lower()
                title = str(song_cfg.get("title", "")).lower()
                if source == "draft" and (not title or title not in text):
                    need += SONG_SEGMENT
                    findings.append(Finding("warning", p.sid, f"the script doesn't name the song yet;"
                                            f" budgeting {SONG_SEGMENT} s for its segment"))
        nxt = next((q for q in placed[n + 1:] if q.entry is not None), None)
        road, to = None, ""
        if p.entry is not None:
            end = nxt.entry if nxt else len(path.pts) - 1
            road, to = path.t[end] - path.t[p.entry], nxt.sid if nxt else "end of route"
        rows.append(Row(p.sid, path.km[p.entry] if p.entry is not None else None, p.off,
                        length, source, song, need, road, to))
        if road is None or need is None:
            continue
        what = "its audio" + (", the song and a 60 s margin" if song else "")
        if road < need:
            findings.append(Finding("error", p.sid, f"{road:.0f} s of road to {to} doesn't cover {what}"
                                    f" ({need:.0f} s); move a trigger or shorten the stop"))
        elif not song and road < need + QUIET and nxt:
            findings.append(Finding("warning", p.sid, f"only {road - need:.0f} s of quiet before {to}"
                                    f" (about {QUIET} s wanted)"))

    findings += strict_findings(placed, dists, path, stops, lookahead)
    return rows, findings, path


def strict_findings(placed: list[Placed], dists: dict[str, list[float]], path: Trip,
                    stops: dict[str, dict], lookahead: int) -> list[Finding]:
    """Replay the player's ``armed()`` wherever the road crosses a stop's zone before its own
    trigger: a stop armed there would play early, on the road to an earlier stop."""
    out = []
    order = [p.sid for p in placed]
    entries = {p.sid: p.entry for p in placed}
    for j, p in enumerate(placed):
        if p.entry is None:
            continue
        radius = p.cfg.get("radius", 400)
        needed = False
        for a, b in runs(dists[p.sid], radius):
            if a >= p.entry or (a <= p.entry <= b):
                continue
            # Stops whose trigger comes before this point have been handled.
            cursor = next((k for k, sid in enumerate(order)
                           if entries[sid] is None or entries[sid] >= a), len(order))
            if cursor == j:
                out.append(Finding("warning", p.sid, f"the road also crosses its zone at km {path.km[a]:.1f},"
                                   f" before its trigger at km {path.km[p.entry]:.1f}; it will play there"))
                continue
            plain = j - cursor < lookahead
            if not plain:
                continue
            needed = True
            if not stops[p.sid].get("strict", False):
                out.append(Finding("error", p.sid, f"its zone is on the road to {order[cursor]}"
                                   f" (km {path.km[a]:.1f}, {path.leg[a]}) while it is armed;"
                                   " set strict = true"))
        if stops[p.sid].get("strict", False):
            if needed:
                out.append(Finding("note", p.sid, "strict = true is needed (its zone is on the road to an"
                                   " earlier stop) and is set"))
            else:
                out.append(Finding("note", p.sid, "strict = true is set but no earlier road crosses its zone"))
    return out


def report(rows: list[Row], findings: list[Finding], path: Trip) -> list[str]:
    lines = [f"{'stop':<10} {'km':>6} {'off m':>6} {'audio s':>8} {'from':<10} {'song s':>7}"
             f" {'need s':>7} {'road s':>7} {'spare':>6}  to"]

    def f(v: float | None, w: int, p: int = 0) -> str:
        return f"{v:>{w}.{p}f}" if v is not None else f"{'-':>{w}}"

    for r in rows:
        spare = r.road - r.need if r.road is not None and r.need is not None else None
        lines.append(f"{r.sid:<10} {f(r.km, 6, 1)} {f(r.off, 6)} {f(r.audio, 8)} {r.source:<10} {f(r.song, 7)}"
                     f" {f(r.need, 7)} {f(r.road, 7)} {f(spare, 6)}  {r.to}")
    lines.append(f"route {path.km[-1]:.1f} km, {path.t[-1] / 60:.0f} min including waits"
                 + ("" if path.timed else f" (at {FALLBACK_KMH} km/h)"))
    for x in findings:
        lines.append(f"{x.level}: {x.sid + ': ' if x.sid else ''}{x.message}")
    errors = sum(x.level == "error" for x in findings)
    warnings = sum(x.level == "warning" for x in findings)
    lines.append(f"{len(rows)} stops, {errors} errors, {warnings} warnings")
    return lines
