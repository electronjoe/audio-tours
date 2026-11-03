"""A tour's base map from OpenStreetMap (task 010).

``tour map <slug>`` makes one Overpass query for the area around the route and stops (cached
for good in ``tours/<slug>/cache/overpass/``), assembles water, parks, roads, rivers, the
coastline and town names, clips them to the area, projects them to metres around its centre
(the player's projection), simplifies them and writes ``site/<slug>/map.json``, which the
player draws under the route (``site/player/map.js``). The file is written whole or not at all.

Coordinates in map.json are whole metres from ``origin``: x east, y south (as on screen), in
flat arrays ``[x0, y0, x1, y1, ...]``. Polygons are lists of rings, closed implicitly; outer
rings run clockwise on screen and holes anticlockwise, so each class draws as one path with
``fill-rule: nonzero``.

The data is © OpenStreetMap contributors under the ODbL 1.0; map.json says so, and the map
on screen shows the attribution.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import time
from collections.abc import Callable
from pathlib import Path

from . import config

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "audio-tours map tool (https://github.com/electronjoe/audio-tours)"
M = 111320  # metres per degree, as the player's along() uses
MARGIN = 5000  # metres around the route and stops, or MARGIN_FRAC of the larger side if more
MARGIN_FRAC = 0.15
TOLERANCE = 25  # metres, Douglas-Peucker: the map is never shown closer than a few km wide
MIN_AREA = 50_000  # square metres (0.05 km²): smaller rings are dropped
MIN_LENGTH = 300  # metres: shorter roads and rivers are dropped
WARN_BYTES = 300_000
RETRY_WAIT = 30  # seconds before the one retry
ROAD_RANK = {"motorway": 1, "trunk": 1, "primary": 2, "secondary": 3}
PLACE_RANK = {"city": 1, "town": 2, "village": 3}
ATTRIBUTION = "© OpenStreetMap contributors"

QUERY = """[out:json][timeout:180][bbox:{s},{w},{n},{e}];
(
  wr["natural"="water"];
  wr["waterway"="riverbank"];
  way["natural"="coastline"];
  wr["boundary"="national_park"];
  wr["leisure"="nature_reserve"];
  wr["leisure"="park"];
  way["highway"~"^(motorway|trunk|primary|secondary)$"];
  way["waterway"="river"];
  node["place"~"^(city|town|village)$"];
);
out geom;"""

Pt = tuple[float, float]  # (x, y) in metres, y north, until written


# --- area ------------------------------------------------------------------------------


class Area:
    """The box drawn, ``[south, west, north, east]`` in degrees, with the projection to metres
    around its centre."""

    def __init__(self, bbox: list[float]):
        self.bbox = bbox
        s, w, n, e = bbox
        self.lat0, self.lon0 = round((s + n) / 2, 5), round((w + e) / 2, 5)
        self.k = math.cos(math.radians(self.lat0))
        x0, y0 = self.xy(s, w)
        x1, y1 = self.xy(n, e)
        self.box = (x0, y0, x1, y1)  # metres, y north

    @classmethod
    def around(cls, points: list[tuple[float, float]]) -> Area:
        """The route and stops' bounding box plus MARGIN, or MARGIN_FRAC of its larger side."""
        if not points:
            raise SystemExit("no route or stops to draw a map around; run `tour route` first")
        s, n = min(p[0] for p in points), max(p[0] for p in points)
        w, e = min(p[1] for p in points), max(p[1] for p in points)
        k = math.cos(math.radians((s + n) / 2))
        margin = max(MARGIN, MARGIN_FRAC * max((n - s) * M, (e - w) * M * k))
        dlat, dlon = margin / M, margin / (M * k)
        return cls([round(s - dlat, 4), round(w - dlon, 4), round(n + dlat, 4), round(e + dlon, 4)])

    def xy(self, lat: float, lon: float) -> Pt:
        return ((lon - self.lon0) * M * self.k, (lat - self.lat0) * M)

    @property
    def km(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return (x1 - x0) / 1000, (y1 - y0) / 1000

    def query(self) -> str:
        s, w, n, e = self.bbox
        return QUERY.format(s=s, w=w, n=n, e=e)


def tour_points(tour: config.Tour) -> list[tuple[float, float]]:
    route_file = tour.root / "route.json"
    route = json.loads(route_file.read_text()) if route_file.exists() else {}
    pts = [tuple(p) for leg in ("outbound", "return") for p in route.get(leg, [])]
    pts += [(s["lat"], s["lon"]) for s in tour.settings.get("stops", {}).values()]
    return pts


# --- fetch -------------------------------------------------------------------------------


class Busy(Exception):
    """Overpass timed out or was too busy: worth one retry."""


def http_post(query: str) -> dict:
    import httpx

    try:
        r = httpx.post(OVERPASS_URL, data={"data": query}, timeout=200, headers={"User-Agent": USER_AGENT})
    except httpx.TimeoutException as err:
        raise Busy("timed out") from err
    except httpx.HTTPError as err:
        raise SystemExit(f"Overpass: {err}") from err
    if r.status_code in (429, 504):
        raise Busy(f"HTTP {r.status_code}")
    if r.status_code != 200:
        raise SystemExit(f"Overpass: HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    remark = data.get("remark", "")
    if "timed out" in remark or "out of memory" in remark:
        raise Busy(remark)
    return data


def fetch(area: Area, cache_dir: Path, refresh: bool = False,
          post: Callable[[str], dict] = http_post, wait: float = RETRY_WAIT) -> tuple[dict, bool]:
    """Overpass's answer for the area, from ``cache_dir`` when we have it (for good: only
    ``refresh`` asks again). A timeout or a busy server is retried once. Returns (data, cached)."""
    query = area.query()
    path = cache_dir / f"{hashlib.sha256(query.encode()).hexdigest()[:16]}.json.gz"
    if path.exists() and not refresh:
        return json.loads(gzip.decompress(path.read_bytes())), True
    for attempt in (1, 2):
        try:
            data = post(query)
            break
        except Busy as err:
            if attempt == 2:
                w, h = area.km
                raise SystemExit(
                    f"Overpass didn't answer twice ({err}) for an area of {w:.0f} × {h:.0f} km.\n"
                    "Try again later. If it keeps failing on a large area, split the query into one per"
                    " feature type (task 010, Decisions).") from err
            print(f"Overpass: {err}; trying once more in {wait:.0f} s")
            time.sleep(wait)
    if "elements" not in data:
        raise SystemExit(f"Overpass: no elements in the answer: {str(data)[:300]}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps({"query": query, **data}).encode()))
    return data, False


# --- geometry --------------------------------------------------------------------------


def join(parts: list[list], directed: bool = False) -> tuple[list[list], list[list]]:
    """Join ways that share end points into chains. Returns (closed rings, open chains); a
    ring's first point is repeated at its end. ``directed`` never reverses a way (the
    coastline's direction says which side is land)."""
    todo = {i: list(p) for i, p in enumerate(parts) if len(p) >= 2}
    ends: dict = {}
    for i, p in todo.items():
        for q in (p[0], p[-1]):
            ends.setdefault(q, set()).add(i)

    def pop(i: int) -> list:
        p = todo.pop(i)
        for q in (p[0], p[-1]):
            ends[q].discard(i)
        return p

    rings, chains = [], []
    while todo:
        cur = pop(min(todo))
        for forward in (True, False):  # grow at the end, then at the start
            while cur[0] != cur[-1]:
                tip = cur[-1] if forward else cur[0]
                found = None
                for i in sorted(ends.get(tip, ())):
                    p = todo[i]
                    if (p[0] if forward else p[-1]) == tip:
                        found = pop(i)
                        break
                    if not directed and found is None:
                        found = i
                if isinstance(found, int):
                    found = pop(found)[::-1]
                if found is None:
                    break
                cur = cur + found[1:] if forward else found[:-1] + cur
        (rings if cur[0] == cur[-1] and len(cur) >= 4 else chains).append(cur)
    return rings, chains


def clip_ring(ring: list[Pt], box: tuple[float, float, float, float]) -> list[Pt]:
    """Sutherland-Hodgman: the ring (without its repeated end) cut to the box. Pieces of a
    concave ring stay joined along the box's edge, which fills the same."""
    x0, y0, x1, y1 = box
    edges = [(lambda p: p[0] >= x0, lambda a, b: _at_x(a, b, x0)), (lambda p: p[0] <= x1, lambda a, b: _at_x(a, b, x1)),
             (lambda p: p[1] >= y0, lambda a, b: _at_y(a, b, y0)), (lambda p: p[1] <= y1, lambda a, b: _at_y(a, b, y1))]
    out = ring
    for inside, cut in edges:
        pts, out = out, []
        for i, b in enumerate(pts):
            a = pts[i - 1]
            if inside(b):
                if not inside(a):
                    out.append(cut(a, b))
                out.append(b)
            elif inside(a):
                out.append(cut(a, b))
        if not out:
            break
    return out


def _at_x(a: Pt, b: Pt, x: float) -> Pt:
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _at_y(a: Pt, b: Pt, y: float) -> Pt:
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def clip_line(line: list[Pt], box: tuple[float, float, float, float]) -> list[list[Pt]]:
    """The pieces of a line inside the box (Liang-Barsky on each segment)."""
    x0, y0, x1, y1 = box
    pieces: list[list[Pt]] = []
    cur: list[Pt] = []
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t0, t1, keep = 0.0, 1.0, True
        for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
            if p == 0:
                if q < 0:
                    keep = False
                    break
                continue
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
        if not keep or t0 > t1:
            if cur:
                pieces.append(cur)
                cur = []
            continue
        pa = (a[0] + t0 * dx, a[1] + t0 * dy)
        pb = (a[0] + t1 * dx, a[1] + t1 * dy)
        if not cur:
            cur = [pa]
        cur.append(pb)
        if t1 < 1:
            pieces.append(cur)
            cur = []
    if cur:
        pieces.append(cur)
    return [p for p in pieces if len(p) >= 2]


def simplify(pts: list[Pt], tol: float = TOLERANCE) -> list[Pt]:
    """Douglas-Peucker, keeping both ends."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        far, at = 0.0, None
        for k in range(i + 1, j):
            d = _off(pts[k], pts[i], pts[j])
            if d > far:
                far, at = d, k
        if at is not None and far > tol:
            keep[at] = True
            stack += [(i, at), (at, j)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_ring(ring: list[Pt], tol: float = TOLERANCE) -> list[Pt]:
    """Douglas-Peucker on a ring (no repeated end): split at the point furthest from the first,
    simplify both halves. Fewer than 3 points left means the ring is gone."""
    if len(ring) < 4:
        return list(ring)
    far = max(range(len(ring)), key=lambda k: (ring[k][0] - ring[0][0]) ** 2 + (ring[k][1] - ring[0][1]) ** 2)
    a = simplify(ring[: far + 1], tol)
    b = simplify(ring[far:] + [ring[0]], tol)
    return a[:-1] + b[:-1]


def _off(p: Pt, a: Pt, b: Pt) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    if not L:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def signed_area(ring: list[Pt]) -> float:
    """Shoelace, y north: positive anticlockwise."""
    return sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring))) / 2


def length(line: list[Pt]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:]))


def flat(pts: list[Pt]) -> list[int]:
    """Whole metres, y south, repeated points dropped."""
    out: list[int] = []
    for x, y in pts:
        p = [round(x), -round(y)]
        if out[-2:] != p:
            out += p
    return out


def land(rings: list[list[Pt]], chains: list[list[Pt]], box: tuple[float, float, float, float]) -> list[list[Pt]] | None:
    """Land polygons from the coastline (land is on its left), in metres, y north: closed rings
    (islands) clipped to the box, and open chains clipped to it and closed along its edge,
    walking anticlockwise from each chain's end to the next chain's start. None if a clipped
    chain ends inside the box (data missing): the coastline is then drawn as a line."""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    P = 2 * (W + H)
    corners = [(0.0, (x0, y0)), (W, (x1, y0)), (W + H, (x1, y1)), (2 * W + H, (x0, y1))]

    def perim(p: Pt) -> float | None:
        """Where p is on the box's edge, anticlockwise from the bottom-left corner."""
        d = {"b": abs(p[1] - y0), "r": abs(p[0] - x1), "t": abs(p[1] - y1), "l": abs(p[0] - x0)}
        edge = min(d, key=d.get)
        if d[edge] > 1:
            return None
        return {"b": p[0] - x0, "r": W + p[1] - y0, "t": W + H + x1 - p[0], "l": 2 * W + H + y1 - p[1]}[edge]

    out = [r for r in (clip_ring(ring[:-1], box) for ring in rings) if len(r) >= 3]
    pieces = []
    for chain in chains:
        for piece in clip_line(chain, box):
            a, b = perim(piece[0]), perim(piece[-1])
            if a is None or b is None:
                return None
            pieces.append((simplify(piece), a, b))
    used: set[int] = set()
    for i in range(len(pieces)):
        if i in used:
            continue
        used.add(i)
        ring, t = list(pieces[i][0]), pieces[i][2]
        while True:
            j = min((k for k in range(len(pieces)) if k not in used or k == i),
                    key=lambda k: (pieces[k][1] - t) % P)
            gap = (pieces[j][1] - t) % P
            ring += [c for _, c in sorted(((c - t) % P, xy) for c, xy in corners if 0 < (c - t) % P < gap)]
            if j == i:
                break
            used.add(j)
            ring += pieces[j][0]
            t = pieces[j][2]
        out.append(ring)
    return out


# --- assembly ----------------------------------------------------------------------------


def kind(tags: dict) -> str | None:
    if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
        return "water"
    if tags.get("boundary") == "national_park" or tags.get("leisure") in ("nature_reserve", "park"):
        return "green"
    if tags.get("natural") == "coastline":
        return "coast"
    if tags.get("highway") in ROAD_RANK:
        return "road"
    if tags.get("waterway") == "river":
        return "river"
    return None


def _geom(g: list | None) -> list[tuple[float, float]]:
    return [(p["lat"], p["lon"]) for p in g or [] if p]


def areas(elements: list[dict]) -> dict[str, list[tuple[list, list]]]:
    """Water and green as (outer rings, inner rings) per feature, in degrees, ends repeated:
    closed ways, and multipolygon relations with their member ways joined into rings."""
    out: dict[str, list[tuple[list, list]]] = {"water": [], "green": []}
    for el in elements:
        k = kind(el.get("tags", {}))
        if k not in out:
            continue
        if el["type"] == "way":
            g = _geom(el.get("geometry"))
            if len(g) >= 4 and g[0] == g[-1]:
                out[k].append(([g], []))
        elif el["type"] == "relation":
            members = [m for m in el.get("members", []) if m.get("type") == "way"]
            outer, _ = join([_geom(m.get("geometry")) for m in members if m.get("role") in ("outer", "")])
            inner, _ = join([_geom(m.get("geometry")) for m in members if m.get("role") == "inner"])
            if outer:
                out[k].append((outer, inner))
    return out


def lines(elements: list[dict]) -> dict[str, list]:
    """Roads (by rank), rivers and the coastline as lines in degrees."""
    out: dict[str, list] = {"coast": [], "river": [], 1: [], 2: [], 3: []}
    for el in elements:
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        k = kind(tags)
        g = _geom(el.get("geometry"))
        if k == "road":
            out[ROAD_RANK[tags["highway"]]].append(g)
        elif k in ("coast", "river"):
            out[k].append(g)
    return out


def build(data: dict, area: Area) -> tuple[dict, dict[str, int]]:
    """map.json's content from Overpass's answer, and counts for the report."""
    els = data["elements"]
    box = area.box
    proj = lambda g: [area.xy(lat, lon) for lat, lon in g]  # noqa: E731
    counts: dict[str, int] = {}

    def polys(features: list[tuple[list, list]]) -> list[list[int]]:
        rings = []
        for outer, inner in features:
            for ring, is_outer in [(r, True) for r in outer] + [(r, False) for r in inner]:
                r = simplify_ring(clip_ring(proj(ring[:-1]), box))
                if len(r) < 3 or abs(signed_area(r)) < MIN_AREA:
                    continue
                # Clockwise on screen (y south) is anticlockwise here (y north) for outers.
                if (signed_area(r) > 0) != is_outer:
                    r.reverse()
                rings.append(flat(r))
        return rings

    def polylines(parts: list[list], directed: bool = False) -> list[list[int]]:
        rings, chains = join(parts, directed)
        out = []
        for line in rings + chains:
            for piece in clip_line(proj(line), box):
                if length(piece) >= MIN_LENGTH:
                    out.append(flat(simplify(piece)))
        return out

    def coast(parts: list[list]) -> dict:
        """Land polygons when the coastline closes along the box's edge (the sea is the rest),
        else the coastline as lines; nothing without a coastline."""
        if not parts:
            return {}
        rings, chains = join(parts, directed=True)
        shapes = land([proj(r) for r in rings], [proj(c) for c in chains], box)
        if shapes is None:
            print("note: the coastline doesn't cross the whole area; drawn as a line, not a sea fill")
            return {"coast": polylines(parts, directed=True)}
        out = []
        for r in shapes:
            r = simplify_ring(r)
            if len(r) >= 3 and abs(signed_area(r)) >= MIN_AREA:
                out.append(flat(r if signed_area(r) > 0 else r[::-1]))
        return {"land": out}

    a, ln = areas(els), lines(els)
    content = {
        "version": 1,
        "origin": [area.lat0, area.lon0],
        "bbox": area.bbox,
        "extent": [round(box[0]), -round(box[3]), round(box[2]), -round(box[1])],
        "attribution": ATTRIBUTION,
        "license": "ODbL-1.0",
        "water": polys(a["water"]),
        "green": polys(a["green"]),
        **coast(ln["coast"]),
        "roads": [{"rank": r, "pts": p} for r in (1, 2, 3) for p in polylines(ln[r])],
        "rivers": polylines(ln["river"]),
        "places": places(els, area),
    }
    for k in ("land", "coast", "water", "green", "roads", "rivers", "places"):
        if k in content:
            counts[k] = len(content[k])
    return content, counts


def places(elements: list[dict], area: Area) -> list[dict]:
    x0, y0, x1, y1 = area.box
    out = []
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] != "node" or tags.get("place") not in PLACE_RANK or not tags.get("name"):
            continue
        x, y = area.xy(el["lat"], el["lon"])
        if x0 <= x <= x1 and y0 <= y <= y1:
            out.append({"name": tags["name"], "at": [round(x), -round(y)], "rank": PLACE_RANK[tags["place"]]})
    return sorted(out, key=lambda p: (p["rank"], p["name"]))


# --- write ---------------------------------------------------------------------------------


def write(content: dict, path: Path) -> int:
    """Write map.json whole: a temporary file renamed into place. Returns its size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path.stat().st_size


def link_tour_json(path: Path) -> bool:
    """Add ``"map": "map.json"`` to an already published tour.json (publish adds it too)."""
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    if data.get("map") == "map.json":
        return False
    data["map"] = "map.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return True


def make(tour: config.Tour, site_dir: Path, refresh: bool = False,
         post: Callable[[str], dict] = http_post, wait: float = RETRY_WAIT) -> list[str]:
    """Fetch (or reuse), build and write site/<slug>/map.json. Returns the report's lines."""
    area = Area.around(tour_points(tour))
    w, h = area.km
    lines_ = [f"area: {w:.0f} × {h:.0f} km around the route and stops ({', '.join(map(str, area.bbox))})"]
    data, cached = fetch(area, tour.root / "cache" / "overpass", refresh, post, wait)
    lines_.append(f"overpass: {len(data['elements'])} elements ({'cached' if cached else 'fetched'})")
    content, counts = build(data, area)
    out = site_dir / tour.slug / "map.json"
    size = write(content, out)
    lines_.append(", ".join(f"{v} {k}" for k, v in counts.items()))
    lines_.append(f"  -> {config.show(out)} ({size / 1000:.0f} KB)")
    if size > WARN_BYTES:
        lines_.append(f"warning: map.json is over {WARN_BYTES // 1000} KB; the phone saves it with the audio")
    if link_tour_json(site_dir / tour.slug / "tour.json"):
        lines_.append(f"  -> {config.show(site_dir / tour.slug / 'tour.json')}: added \"map\"")
    return lines_
