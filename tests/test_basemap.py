"""Task 010: `tour map`, the base map from OpenStreetMap.

Nothing here calls Overpass. tests/fixtures/overpass/hobart-waterfront.json.gz is the answer
recorded for Hobart on 2026-11-03, trimmed to Hobart's waterfront and the Derwent (its bbox)
and to the fields basemap reads; the other tests build small areas by hand.
"""

import gzip
import json
import math

import pytest

from audiotour import basemap, publish
from audiotour.config import REPO_ROOT, Tour

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "overpass" / "hobart-waterfront.json.gz"
BOX = [-43.0, 147.0, -42.9, 147.1]  # about 8.2 x 11.1 km


def recorded() -> dict:
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def pairs(flat: list[int]) -> list[tuple[int, int]]:
    return list(zip(flat[::2], flat[1::2]))


def screen_area(ring: list[int]) -> float:
    """Shoelace on screen (y south): positive clockwise, as the eye sees it."""
    p = pairs(ring)
    return -sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p))) / 2


def filled(rings: list[list[int]], x: float, y: float) -> bool:
    """Whether (x, y) on screen is filled under the nonzero rule, as the player draws a class."""
    w = 0
    for ring in rings:
        p = pairs(ring)
        for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1]):
            if (y0 <= y) != (y1 <= y):
                cross = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if cross > x:
                    w += 1 if y1 > y0 else -1
    return w != 0


def way(tags: dict, pts: list[tuple[float, float]], i: int = 1) -> dict:
    return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in pts]}


def at(area: basemap.Area, lat: float, lon: float) -> tuple[float, float]:
    x, y = area.xy(lat, lon)
    return x, -y


# --- assembly -------------------------------------------------------------------------------


def test_multipolygon_members_join_into_rings_with_a_hole():
    """A lake as a relation: its outer ring in three ways, one drawn backwards, and an island."""
    sq = [(-42.96, 147.03), (-42.96, 147.07), (-42.94, 147.07), (-42.94, 147.03)]
    isle = [(-42.955, 147.045), (-42.945, 147.045), (-42.945, 147.055), (-42.955, 147.055), (-42.955, 147.045)]
    g = lambda pts: [{"lat": a, "lon": b} for a, b in pts]  # noqa: E731
    rel = {"type": "relation", "id": 9, "tags": {"type": "multipolygon", "natural": "water"}, "members": [
        {"type": "way", "role": "outer", "geometry": g([sq[0], sq[1]])},
        {"type": "way", "role": "outer", "geometry": g([sq[2], sq[1]])},  # backwards
        {"type": "way", "role": "outer", "geometry": g([sq[2], sq[3], sq[0]])},
        {"type": "way", "role": "inner", "geometry": g(isle)},
    ]}
    area = basemap.Area(BOX)
    content, _ = basemap.build({"elements": [rel]}, area)
    outer, hole = content["water"]
    assert screen_area(outer) > 0 > screen_area(hole), "outer clockwise on screen, the hole anticlockwise"
    assert abs(screen_area(outer)) == pytest.approx(3.27e3 * 2.22e3, rel=0.02)
    assert filled(content["water"], *at(area, -42.95, 147.04))  # water
    assert not filled(content["water"], *at(area, -42.95, 147.05))  # the island


def test_rings_and_lines_are_clipped_to_the_area():
    area = basemap.Area(BOX)
    big = [(-43.05, 146.95), (-43.05, 147.05), (-42.95, 147.05), (-42.95, 146.95), (-43.05, 146.95)]
    road = [(-42.95, 146.9), (-42.95, 147.2)]  # crosses the whole area west to east
    content, _ = basemap.build({"elements": [way({"leisure": "park"}, big), way({"highway": "primary"}, road, 2)]}, area)
    x0, y0, x1, y1 = content["extent"]
    (park,), (r,) = content["green"], content["roads"]
    assert all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in pairs(park) + pairs(r["pts"]))
    assert r["rank"] == 2 and pairs(r["pts"])[0][0] == x0 and pairs(r["pts"])[-1][0] == x1
    assert abs(screen_area(park)) == pytest.approx((x1 - x0) / 2 * (y1 - y0) / 2, rel=0.02)  # a quarter of it


def test_small_polygons_and_short_roads_are_dropped():
    area = basemap.Area(BOX)
    pond = [(-42.95, 147.05), (-42.95, 147.052), (-42.948, 147.052), (-42.948, 147.05), (-42.95, 147.05)]  # 160 x 220 m
    lane = [(-42.95, 147.05), (-42.95, 147.053)]  # 245 m
    content, _ = basemap.build({"elements": [way({"natural": "water"}, pond), way({"highway": "secondary"}, lane, 2)]}, area)
    assert content["water"] == [] and content["roads"] == []


def test_simplify_keeps_rings_closed_and_ends_fixed():
    circle = [(1000 * math.cos(t / 200 * 2 * math.pi), 1000 * math.sin(t / 200 * 2 * math.pi)) for t in range(200)]
    r = basemap.simplify_ring(circle)
    assert 8 <= len(r) < 40 and r[0] == circle[0]
    assert basemap.signed_area(r) == pytest.approx(math.pi * 1e6, rel=0.03)
    line = [(x, 10 * math.sin(x / 30)) for x in range(0, 3000, 10)]
    s = basemap.simplify(line)
    assert s[0] == line[0] and s[-1] == line[-1] and len(s) == 2  # wiggles of 10 m are under 25 m


# --- the coastline ---------------------------------------------------------------------------


def test_coastline_closes_along_the_edge_with_land_on_its_left():
    """A coastline running north up the middle: land is on its left (west)."""
    area = basemap.Area(BOX)
    north = [(-43.1, 147.05), (-42.8, 147.05)]
    content, _ = basemap.build({"elements": [way({"natural": "coastline"}, north)]}, area)
    assert "coast" not in content
    (land,) = content["land"]
    x0, y0, x1, y1 = content["extent"]
    assert screen_area(land) == pytest.approx((x1 - x0) * (y1 - y0) / 2, rel=0.01)
    assert filled(content["land"], *at(area, -42.95, 147.02))
    assert not filled(content["land"], *at(area, -42.95, 147.08))  # sea
    content, _ = basemap.build({"elements": [way({"natural": "coastline"}, north[::-1])]}, area)
    assert filled(content["land"], *at(area, -42.95, 147.08))  # southward: land to the east


def test_an_estuary_and_an_island():
    """Sea coming in from the south edge as a U, in two ways, and an island in it."""
    area = basemap.Area(BOX)
    west = [(-43.1, 147.04), (-42.93, 147.04), (-42.93, 147.05)]  # up the west shore, land on the left
    east = [(-42.93, 147.05), (-42.93, 147.06), (-43.1, 147.06)]  # and back down the east shore
    isle = [(-42.98, 147.048), (-42.98, 147.052), (-42.97, 147.052), (-42.97, 147.048), (-42.98, 147.048)]  # anticlockwise
    els = [way({"natural": "coastline"}, east, 1), way({"natural": "coastline"}, west, 2), way({"natural": "coastline"}, isle, 3)]
    content, _ = basemap.build({"elements": els}, area)
    land = content["land"]
    assert len(land) == 2 and all(screen_area(r) > 0 for r in land)
    assert not filled(land, *at(area, -42.96, 147.045))  # in the estuary
    assert filled(land, *at(area, -42.975, 147.05))  # on the island
    assert filled(land, *at(area, -42.92, 147.05))  # north of the estuary's head
    assert filled(land, *at(area, -42.96, 147.02)) and filled(land, *at(area, -42.96, 147.08))


def test_a_coastline_that_stops_inside_the_area_is_drawn_as_a_line():
    area = basemap.Area(BOX)
    content, _ = basemap.build({"elements": [way({"natural": "coastline"}, [(-43.1, 147.05), (-42.95, 147.05)])]}, area)
    assert "land" not in content and len(content["coast"]) == 1


def test_recorded_hobart_waterfront():
    fx = recorded()
    area = basemap.Area(fx["bbox"])
    content, counts = basemap.build(fx, area)
    assert list(content)[:6] == ["version", "origin", "bbox", "extent", "attribution", "license"]
    assert (content["version"], content["attribution"], content["license"]) == (1, "© OpenStreetMap contributors", "ODbL-1.0")
    for k in ("land", "green", "water"):
        assert all(len(r) >= 6 and len(r) % 2 == 0 and all(isinstance(v, int) for v in r) for r in content[k]), k
        assert all(r[:2] != r[-2:] for r in content[k]), f"{k}: rings close implicitly, without a repeated end"
    assert all(screen_area(r) > 0 for r in content["land"])
    assert all(r["rank"] in (1, 2, 3) and len(r["pts"]) >= 4 for r in content["roads"])
    assert {r["rank"] for r in content["roads"]} == {1, 2, 3}
    assert [p["name"] for p in content["places"]] == ["Hobart"] and content["places"][0]["rank"] == 1
    # The Derwent between Hobart and Bellerive is sea; the city and Bellerive are land.
    land = content["land"]
    assert not filled(land, *at(area, -42.884, 147.350))
    assert filled(land, *at(area, -42.882, 147.325))
    assert filled(land, *at(area, -42.875, 147.372))
    x0, y0, x1, y1 = content["extent"]
    sea = 1 - sum(screen_area(r) for r in land) / ((x1 - x0) * (y1 - y0))
    assert 0.15 < sea < 0.6
    # The two nature reserves are multipolygon relations: their rings assemble.
    assert counts["green"] >= 2 and len(json.dumps(content)) < 20_000


# --- fetch, cache, write ---------------------------------------------------------------------


def hobart_like(tmp_path) -> Tour:
    root = tmp_path / "tours" / "demo"
    root.mkdir(parents=True)
    (root / "tour.toml").write_text('[tour]\ntitle = "Demo"\n\n[stops.stop-1]\nlat = -42.88\nlon = 147.33\n')
    (root / "route.json").write_text(json.dumps({"outbound": [[-42.88, 147.33], [-42.86, 147.30]], "return": []}))
    return Tour("demo", tmp_path / "tours")


def test_area_has_a_margin_of_5_km_or_15_percent():
    a = basemap.Area.around([(-42.88, 147.33), (-42.86, 147.30)])
    w, h = a.km
    assert w == pytest.approx(2.45 + 10, abs=0.1) and h == pytest.approx(2.2 + 10, abs=0.1)
    b = basemap.Area.around([(-42.8, 146.7), (-42.8, 147.3)])  # 49 km wide: 15 % is 7.4 km
    assert b.km[0] == pytest.approx(49.1 * 1.3, abs=0.2)


def test_fetch_retries_once_then_stops_and_keeps_the_old_map(tmp_path):
    tour, site = hobart_like(tmp_path), tmp_path / "site"
    old = site / "demo" / "map.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"version": 1, "old": true}\n')
    calls = []

    def busy(query: str) -> dict:
        calls.append(query)
        raise basemap.Busy("HTTP 429")

    with pytest.raises(SystemExit, match=r"(?s)didn't answer twice \(HTTP 429\) for an area of 12 × 12 km.*Try again later"):
        basemap.make(tour, site, post=busy, wait=0)
    assert len(calls) == 2 and "[timeout:180]" in calls[0]
    assert old.read_text() == '{"version": 1, "old": true}\n'
    assert not list((tour.root / "cache").rglob("*.gz"))


def test_a_busy_server_then_an_answer_is_cached_for_good(tmp_path):
    tour, site = hobart_like(tmp_path), tmp_path / "site"
    fx, calls = recorded(), []

    def flaky(query: str) -> dict:
        calls.append(query)
        if len(calls) == 1:
            raise basemap.Busy("timed out")
        return {"elements": fx["elements"]}

    basemap.make(tour, site, post=flaky, wait=0)
    first = (site / "demo" / "map.json").read_bytes()
    assert len(calls) == 2
    lines = basemap.make(tour, site, post=lambda q: pytest.fail("asked Overpass again"), wait=0)
    assert any("(cached)" in line for line in lines)
    assert (site / "demo" / "map.json").read_bytes() == first
    basemap.make(tour, site, refresh=True, post=flaky, wait=0)
    assert len(calls) == 3


def test_a_failed_write_leaves_the_old_map(tmp_path):
    out = tmp_path / "site" / "demo" / "map.json"
    out.parent.mkdir(parents=True)
    out.write_text("old\n")
    with pytest.raises(TypeError):
        basemap.write({"version": 1, "water": [object()]}, out)
    assert out.read_text() == "old\n" and [p.name for p in out.parent.iterdir()] == ["map.json"]


def test_user_agent_names_the_project_and_429_is_busy(monkeypatch):
    import httpx

    seen = {}

    def post(url, data, timeout, headers):
        seen.update(url=url, headers=headers, data=data)
        return httpx.Response(429, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(basemap.Busy, match="429"):
        basemap.http_post("[out:json];")
    assert seen["url"] == "https://overpass-api.de/api/interpreter"
    assert "audio-tours" in seen["headers"]["User-Agent"] and "github.com" in seen["headers"]["User-Agent"]


def test_make_links_the_map_from_a_published_tour_json(tmp_path):
    tour, site = hobart_like(tmp_path), tmp_path / "site"
    (site / "demo").mkdir(parents=True)
    (site / "demo" / "tour.json").write_text(json.dumps({"schema": 1, "slug": "demo"}))
    basemap.make(tour, site, post=lambda q: {"elements": []}, wait=0)
    assert json.loads((site / "demo" / "tour.json").read_text())["map"] == "map.json"


def test_publish_adds_map_only_when_the_file_exists(tmp_path):
    from test_publish import make_tour

    site, tours = tmp_path / "site", tmp_path / "tours"
    tour = make_tour(tours)
    publish.publish(tour, site)
    assert "map" not in json.loads((site / "demo" / "tour.json").read_text())
    (site / "demo" / "map.json").write_text("{}\n")
    publish.publish(tour, site)
    assert json.loads((site / "demo" / "tour.json").read_text())["map"] == "map.json"
