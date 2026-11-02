"""Task 003: the Navigate from here links.

The player builds them (``navLink`` in site/player/app.js); these tests run that block under
Node with made-up tours. Publish copies ``nav`` and ``[route] end`` into tour.json.
"""

import json
import re
import shutil
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from audiotour import publish
from audiotour.config import REPO_ROOT, Tour

APP = REPO_ROOT / "site" / "player" / "app.js"
NODE = shutil.which("node")


def nav_links(tour: dict) -> list[dict | None]:
    """navLink(tour, i) for every stop, computed by the player's own code."""
    if not NODE:
        pytest.skip("node is not installed")
    block = re.search(r"^// --- navigate from here.*?^// --- end navigate from here", APP.read_text(),
                      re.MULTILINE | re.DOTALL)
    assert block, "app.js: the navigate block's marker comments are missing"
    js = block.group(0) + f"\nconst t = {json.dumps(tour)};\nconsole.log(JSON.stringify(t.stops.map((_, i) => navLink(t, i))));"
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def parts(url: str) -> tuple[list[str], str, str]:
    """(waypoints, destination, travelmode) from a Maps directions URL."""
    u = urlsplit(url)
    assert (u.scheme, u.netloc, u.path) == ("https", "www.google.com", "/maps/dir/")
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert q["api"] == "1" and "origin" not in q
    return (q["waypoints"].split("|") if "waypoints" in q else []), q["destination"], q["travelmode"]


def stops(n: int, extra: dict | None = None) -> list[dict]:
    return [{"id": f"stop-{k}", "lat": round(-42.0 - k / 100, 5), "lon": round(147.0 + k / 100, 5), **(extra or {}).get(k, {})}
            for k in range(1, n + 1)]


def test_this_stop_and_every_later_one_then_the_end():
    links = nav_links({"mode": "drive", "stops": stops(3), "route": {"end": [-42.9, 147.3]}})
    assert parts(links[0]["url"]) == (["-42.01,147.01", "-42.02,147.02", "-42.03,147.03"], "-42.9,147.3", "driving")
    assert parts(links[2]["url"]) == (["-42.03,147.03"], "-42.9,147.3", "driving")
    assert {l["label"] for l in links} == {"Navigate from here"}


def test_nav_points_override_or_drop_a_stop():
    s = stops(3, {1: {"nav": [-41.5, 146.5]}, 2: {"nav": False}})
    links = nav_links({"mode": "walk", "stops": s, "route": {}})
    assert parts(links[0]["url"]) == (["-41.5,146.5"], "-42.03,147.03", "walking")  # no end: the last stop
    assert parts(links[1]["url"]) == ([], "-42.03,147.03", "walking")


def test_only_adjacent_repeats_are_dropped():
    s = stops(4)
    s[1] |= {"lat": s[0]["lat"], "lon": s[0]["lon"]}  # stop 2 shares stop 1's point
    s[3] |= {"lat": s[0]["lat"], "lon": s[0]["lon"]}  # stop 4 too: an out-and-back
    links = nav_links({"stops": s, "route": {"end": [s[3]["lat"], s[3]["lon"]]}})
    assert parts(links[0]["url"]) == (["-42.01,147.01", "-42.03,147.03"], "-42.01,147.01", "driving")


def test_no_points_no_link():
    assert nav_links({"stops": stops(2, {2: {"nav": False}}), "route": {}})[1] is None


def test_more_than_ten_points_are_cut_to_ten():
    links = nav_links({"mode": "drive", "stops": stops(12), "route": {"end": [-42.9, 147.3]}})
    waypoints, dest, _ = parts(links[0]["url"])  # 12 stops + the end = 13 points
    assert len(waypoints) == 9 and waypoints[0] == "-42.01,147.01" and dest == "-42.1,147.1"  # stop 10
    assert links[0]["label"] == "Navigate (next 10 stops)"
    assert "%7C" in links[0]["url"] and "|" not in links[0]["url"]
    waypoints, dest, _ = parts(links[3]["url"])  # stops 4-12 + the end = exactly 10: no cut
    assert len(waypoints) == 9 and dest == "-42.9,147.3" and links[3]["label"] == "Navigate from here"


def test_hobart_stop_6_goes_back_through_new_norfolk_to_hobart():
    tour = json.loads((REPO_ROOT / "site" / "hobart" / "tour.json").read_text())
    s = {x["id"]: x for x in tour["stops"]}
    link = nav_links(tour)[5]
    waypoints, dest, mode = parts(link["url"])
    assert waypoints == [f"{s[k]['lat']},{s[k]['lon']}" for k in ("stop-6", "stop-7", "stop-8")]
    assert "New Norfolk" in s["stop-8"]["place"]
    assert dest == ",".join(map(str, tour["route"]["end"])) and tour["route"]["end"] == tour["route"]["return"][-1]
    assert mode == "driving"


TOML = """\
[route]
end = [-42.9, 147.3]

[stops.stop-1]
lat = -42.88
lon = 147.33
nav = [-42.87, 147.32]

[stops.stop-2]
lat = -42.89
lon = 147.34
nav = false
"""
DRAFT = "## Script: Stop 1 — One\n\nText.\n\n## Script: Stop 2 — Two\n\nText.\n"


def make_tour(tours, toml=TOML):
    (tours / "demo" / "source").mkdir(parents=True)
    (tours / "demo" / "source" / "working-draft.md").write_text(DRAFT)
    (tours / "demo" / "tour.toml").write_text(toml)
    return Tour("demo", tours)


def test_publish_copies_nav_and_route_end(tmp_path):
    publish.publish(make_tour(tmp_path / "tours"), tmp_path / "site")
    data = json.loads((tmp_path / "site" / "demo" / "tour.json").read_text())
    assert [s.get("nav", "absent") for s in data["stops"]] == [[-42.87, 147.32], False]
    assert data["route"] == {"end": [-42.9, 147.3]}


def test_publish_leaves_them_out_when_unset(tmp_path):
    toml = "\n".join(l for l in TOML.splitlines() if not l.startswith(("nav", "end", "[route]")))
    publish.publish(make_tour(tmp_path / "tours", toml), tmp_path / "site")
    data = json.loads((tmp_path / "site" / "demo" / "tour.json").read_text())
    assert all("nav" not in s for s in data["stops"]) and data["route"] == {}


@pytest.mark.parametrize("bad", ["nav = true", "nav = [147.3, -42.9, 0]", 'nav = "-42.8,147.3"', "nav = [-142.0, 147.0]"])
def test_publish_refuses_a_bad_nav(tmp_path, bad):
    with pytest.raises(SystemExit, match=r"\[stops.stop-1\] nav"):
        publish.publish(make_tour(tmp_path / "tours", TOML.replace("nav = [-42.87, 147.32]", bad)), tmp_path / "site")
