"""Route tools (task 008): `tour route` from recorded OSRM responses, and `tour plan-check`.

Nothing here calls OSRM: tests/fixtures/osrm/ holds responses recorded on 2026-11-02.
"""

import gzip
import json
import tomllib

import pytest

from audiotour import config, route
from audiotour.config import REPO_ROOT, Tour

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "osrm"
SHORT = [(-42.68044, 146.78524), (-42.68181, 146.71655)]  # Hobart stop 4 -> Mount Field
VIA = [(-42.68181, 146.71655), (-42.6812, 146.72986), (-42.68044, 146.78524)]  # back, via stop 6


def recorded(name: str) -> dict:
    path = FIXTURES / name
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text())


def offline_get(*names: str):
    """A stand-in for http_get that answers only the recorded URLs."""
    answers = {d["url"]: d for d in map(recorded, names)}

    def get(url: str) -> dict:
        assert url in answers, f"unrecorded request: {url}"
        return answers[url]
    return get


def no_network(url: str) -> dict:
    raise AssertionError(f"tried the network: {url}")


# --- tour route ------------------------------------------------------------------------


def test_leg_keeps_a_vertex_every_300_m_along_the_road():
    data = recorded("short.json")
    leg = route.leg_from_osrm("outbound", data)
    full = [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]]
    assert leg.points[0] == (round(full[0][0], 5), round(full[0][1], 5))
    assert leg.points[-1] == (round(full[-1][0], 5), round(full[-1][1], 5))
    assert 20 <= len(leg.points) <= 30  # 7.4 km of road
    # Every kept point is an OSRM vertex, and the gaps along the road are >= 300 m but the last.
    rounded = [(round(a, 5), round(b, 5)) for a, b in full]
    idx = [rounded.index(p) for p in leg.points]
    assert idx == sorted(idx)
    along = [sum(route.metres(full[i], full[i + 1]) for i in range(a, b)) for a, b in zip(idx, idx[1:])]
    assert all(x >= 300 for x in along[:-1])
    assert all(x < 300 + max(route.metres(full[i], full[i + 1]) for i in range(len(full) - 1)) for x in along)


def test_seconds_rise_to_the_legs_duration():
    for name in ("short.json", "via.json"):
        data = recorded(name)
        leg = route.leg_from_osrm("x", data)
        assert leg.seconds[0] == 0
        assert leg.seconds == sorted(leg.seconds)
        assert leg.seconds[-1] == pytest.approx(data["routes"][0]["duration"], abs=0.2)
        assert len(leg.seconds) == len(leg.points)


def test_annotations_that_dont_line_up_are_spread_by_length():
    data = recorded("via.json")
    data["routes"][0]["legs"][1]["annotation"]["duration"].pop()
    leg = route.leg_from_osrm("x", data)
    assert leg.seconds[-1] == pytest.approx(data["routes"][0]["duration"], abs=0.2)


def demo_tour(tmp_path, toml: str, draft: str = "") -> Tour:
    root = tmp_path / "demo"
    (root / "source").mkdir(parents=True)
    (root / "tour.toml").write_text(toml)
    (root / "source" / config.DRAFT).write_text(draft)
    return Tour("demo", tours_dir=tmp_path)


def legs_toml(out=SHORT, ret=VIA) -> str:
    def pts(p):
        return "[" + ", ".join(f"[{a}, {b}]" for a, b in p) + "]"
    return f"[route]\nend = [-42.88, 147.33]\n\n[route.outbound]\npoints = {pts(out)}\n\n[route.return]\npoints = {pts(ret)}\n"


def test_build_writes_legs_and_seconds_then_reuses_the_cache(tmp_path):
    tour = demo_tour(tmp_path, legs_toml())
    content, legs = route.build(tour, get=offline_get("short.json", "via.json"), pause=0)
    assert list(content) == ["outbound", "return", "seconds"]
    assert content["seconds"]["return"][-1] == pytest.approx(525, abs=0.2)
    assert [leg.name for leg in legs] == ["outbound", "return"]
    table = route.leg_table(legs)
    assert table[1].split() == ["outbound", "7.4", "8.1", str(len(content["outbound"]))]
    assert table[3].startswith("total")
    # The second run comes from tours/demo/cache/osrm/ without asking OSRM.
    again, _ = route.build(tour, get=no_network, pause=0)
    assert again == content
    out = tmp_path / "scratch" / "route.json"
    route.write(content, out)
    assert json.loads(out.read_text()) == content


def test_build_needs_route_legs(tmp_path):
    tour = demo_tour(tmp_path, "[route]\nend = [-42.88, 147.33]\n")
    with pytest.raises(SystemExit, match=r"\[route.outbound\]"):
        route.build(tour, get=no_network)


def test_osrm_refusal_stops_with_its_message(tmp_path):
    tour = demo_tour(tmp_path, legs_toml())
    with pytest.raises(SystemExit, match="NoRoute"):
        route.build(tour, get=lambda url: {"code": "NoRoute", "message": "Impossible route"})
    assert not (tour.root / "cache" / "osrm").exists()


def test_hobart_legs_rebuild_the_committed_route():
    """The recorded Hobart responses, thinned, closely match tours/hobart/route.json (made on
    2026-11-02 the same way). Close means: at least 94% of the points identical and no point
    of either more than 150 m from the other's line. The differences are a street choice in
    New Norfolk where OpenStreetMap has changed since."""
    legs = route.legs_config(config.tour("hobart"))
    names = {"outbound": "hobart-outbound.json.gz", "return": "hobart-return.json.gz"}
    built = {}
    for name, cfg in legs.items():
        data = recorded(names[name])
        assert data["url"] == route.osrm_url(cfg["points"]), "tour.toml's legs changed; record again"
        built[name] = [list(p) for p in route.leg_from_osrm(name, data).points]
    committed = json.loads((REPO_ROOT / "tours" / "hobart" / "route.json").read_text())
    for name in ("outbound", "return"):
        a, b = [tuple(p) for p in built[name]], [tuple(p) for p in committed[name]]
        assert len(set(a) & set(b)) >= 0.94 * max(len(a), len(b))
        assert max(route._far(a, b), route._far(b, a)) <= 150
    lines = route.compare(built, committed)
    assert lines[0].startswith("outbound: 212 vs 212 points")


# --- tour plan-check -------------------------------------------------------------------

# A straight road north and back: 30 km each way, a point every 300 m, 20 m/s.
STEP_DEG = 300 / 111195
N = 100


def straight(seconds: bool = True) -> dict:
    out = [[round(-42.0 + i * STEP_DEG, 6), 147.0] for i in range(N + 1)]
    r = {"outbound": out, "return": out[::-1]}
    if seconds:
        r["seconds"] = {"outbound": [i * 15.0 for i in range(N + 1)], "return": [i * 15.0 for i in range(N + 1)]}
    return r


def at_km(km: float) -> float:
    return round(-42.0 + km * 1000 / 111195, 6)


def words(n: int) -> str:
    return " ".join(["word"] * n)


def plan(tmp_path, stops: str, draft: str = "", extra: str = "", seconds: bool = True):
    tour = demo_tour(tmp_path, extra + stops, draft)
    rows, findings, trip = route.check(tour, straight(seconds), site_dir=tmp_path / "site")
    return rows, findings, trip


def errors(findings):
    return [f for f in findings if f.level == "error"]


def stop(sid: str, km: float, radius: int = 500, more: str = "") -> str:
    return f"[stops.{sid}]\nlat = {at_km(km)}\nlon = 147.0\nradius = {radius}\n{more}\n"


# Stop 4 is on the way back at km 25; the road out crosses its zone on the way to stop 3.
OUT_AND_BACK = stop("stop-1", 3) + stop("stop-2", 12) + stop("stop-3", 28, 300) + stop("stop-4", 25)


def draft(**lengths: int) -> str:
    return "# Demo\n\n" + "".join(f"## Script: Stop {sid.split('-')[1]} — Title\n\n{words(n)}\n\n"
                                  for sid, n in lengths.items())


SHORT_DRAFT = draft(**{"stop-1": 130, "stop-2": 130, "stop-3": 130, "stop-4": 130})


def test_a_sound_plan_passes_and_notes_the_strict_stop(tmp_path):
    stops = OUT_AND_BACK.replace(stop("stop-4", 25), stop("stop-4", 25, more="strict = true"))
    rows, findings, trip = plan(tmp_path, stops, SHORT_DRAFT)
    assert errors(findings) == []
    assert [r.sid for r in rows] == ["stop-1", "stop-2", "stop-3", "stop-4"]
    assert rows[0].km == pytest.approx(2.5, abs=0.05)  # zone entry, not the centre
    assert rows[3].km == pytest.approx(34.5, abs=0.05)  # on the way back
    assert rows[0].road == pytest.approx(9000 / 20, abs=2)  # km 2.5 to km 11.5 at 20 m/s
    assert rows[0].source == "draft" and rows[0].audio == pytest.approx(60 + 0.5 + 2.5 + 1.2 + 0.5, abs=0.5)
    assert any(f.sid == "stop-4" and "is needed" in f.message for f in findings)
    assert trip.timed


def test_a_return_zone_on_the_outbound_road_needs_strict(tmp_path):
    _, findings, _ = plan(tmp_path, OUT_AND_BACK, SHORT_DRAFT)
    [e] = errors(findings)
    assert e.sid == "stop-4" and "set strict = true" in e.message and "stop-3" in e.message


def test_strict_is_not_needed_outside_the_lookahead(tmp_path):
    _, findings, _ = plan(tmp_path, OUT_AND_BACK, SHORT_DRAFT, extra="[player]\nlookahead = 1\n\n")
    assert errors(findings) == []


def test_a_zone_crossed_before_its_own_trigger_plays_early(tmp_path):
    # The way back runs on a parallel road 330 m east. Stop 2 is on it, but its 500 m zone
    # also reaches the road out, where stop 2 is already the next stop.
    r = straight()
    r["return"] = [[lat, 147.004] for lat, _ in r["return"]]
    stops = stop("stop-1", 3) + stop("stop-2", 25).replace("lon = 147.0\n", "lon = 147.004\n")
    tour = demo_tour(tmp_path, stops, draft(**{"stop-1": 130, "stop-2": 130}))
    rows, findings, _ = route.check(tour, r, site_dir=tmp_path)
    assert rows[1].km > 30  # placed on the way back
    [w] = [f for f in findings if f.level == "warning"]
    assert w.sid == "stop-2" and "it will play there" in w.message


def test_a_trigger_off_the_road_is_an_error(tmp_path):
    stops = stop("stop-1", 3) + "[stops.stop-2]\nlat = -41.97\nlon = 147.01\nradius = 900\n"  # ~800 m east
    _, findings, _ = plan(tmp_path, stops, draft(**{"stop-1": 130, "stop-2": 130}))
    [e] = errors(findings)
    assert e.sid == "stop-2" and "not on the route" in e.message


def test_a_stop_behind_the_one_before_it_is_found_on_the_way_back(tmp_path):
    # Stop 2 lies behind stop 1 on the way out, and the way back passes it only after stop 1's
    # own zone, so it is found there, on the return.
    stops = stop("stop-1", 12) + stop("stop-2", 3)
    rows, _, _ = plan(tmp_path, stops, draft(**{"stop-1": 130, "stop-2": 130}))
    assert rows[1].km == pytest.approx(56.5, abs=0.05)


def test_too_little_road_for_the_audio_is_an_error(tmp_path):
    long = draft(**{"stop-1": 1300, "stop-2": 130})  # ~10 min on 450 s of road
    _, findings, _ = plan(tmp_path, stop("stop-1", 3) + stop("stop-2", 12), long)
    msgs = [f.message for f in errors(findings) if f.sid == "stop-1"]
    assert msgs and "doesn't cover its audio" in msgs[0]


def test_too_little_quiet_is_a_warning(tmp_path):
    # ~397 s of audio on 450 s of road: it fits, with 53 s of quiet.
    _, findings, _ = plan(tmp_path, stop("stop-1", 3) + stop("stop-2", 12),
                          draft(**{"stop-1": 850, "stop-2": 130}))
    assert errors(findings) == []
    assert any(f.level == "warning" and f.sid == "stop-1" and "quiet" in f.message for f in findings)


def test_a_song_stop_budgets_the_song_and_a_margin(tmp_path):
    song = '\n[stops.stop-2.song]\ntitle = "River Song"\nartist = "A Band"\nlength = "{}"\n'
    base = stop("stop-1", 3) + stop("stop-2", 12) + stop("stop-3", 28, 300)
    text = draft(**{"stop-1": 130, "stop-2": 130, "stop-3": 130})
    # Road from stop 2 (km 11.5) to stop 3 (km 27.7): 810 s.
    rows, findings, _ = plan(tmp_path / "a", base + song.format("9:00"), text)
    assert rows[1].song == 540
    assert rows[1].need == pytest.approx(rows[1].audio + 540 + 60 + 60)  # + an unwritten segment
    assert errors(findings) == []
    assert any("doesn't name the song" in f.message for f in findings)
    _, findings, _ = plan(tmp_path / "b", base + song.format("11:00"), text)
    [e] = errors(findings)
    assert e.sid == "stop-2" and "the song and a 60 s margin" in e.message
    # A script that names the song has its segment already.
    named = text.replace("## Script: Stop 2 — Title\n\n", "## Script: Stop 2 — Title\n\nNow River Song. ")
    rows, findings, _ = plan(tmp_path / "c", base + song.format("9:00"), named)
    assert rows[1].need == pytest.approx(rows[1].audio + 540 + 60)
    assert not any("doesn't name the song" in f.message for f in findings)
    _, findings, _ = plan(tmp_path / "d", base + song.format("about four minutes"), text)
    assert any(f.level == "error" and "song length" in f.message for f in findings)


@pytest.mark.parametrize("value, seconds", [("3:42", 222), ("1:02:03", 3723), (200, 200),
                                            (" 4:05 ", 245), ("3m42", None), (None, None), (True, None)])
def test_song_lengths(value, seconds):
    assert route.song_seconds({"length": value}) == seconds


def test_radii_follow_2_stops_md(tmp_path):
    _, findings, _ = plan(tmp_path / "a", stop("stop-1", 3, 200) + stop("stop-2", 12, 1200),
                          draft(**{"stop-1": 130, "stop-2": 130}))
    assert {f.sid for f in errors(findings)} == {"stop-1", "stop-2"}
    walk = "[player]\nmode = \"walk\"\n\n"
    _, findings, _ = plan(tmp_path / "b", stop("stop-1", 3, 60) + stop("stop-2", 12, 300),
                          draft(**{"stop-1": 13, "stop-2": 13}), extra=walk)
    [e] = errors(findings)
    assert e.sid == "stop-2" and "25-80 m" in e.message


def test_without_seconds_road_time_assumes_80_kmh(tmp_path):
    rows, findings, trip = plan(tmp_path, stop("stop-1", 3) + stop("stop-2", 12),
                                draft(**{"stop-1": 130, "stop-2": 130}), seconds=False)
    assert not trip.timed
    assert rows[0].road == pytest.approx(9000 / (80 / 3.6), abs=2)
    assert any(f.level == "note" and "80 km/h" in f.message for f in findings)


def test_a_wait_at_the_end_of_a_leg_counts_as_road_time(tmp_path):
    # Parked at the end of the road out, then just after on the way back (like Hobart 5 and 6).
    stops = stop("stop-1", 29.5, 300) + stop("stop-2", 28, 300, more="strict = true")
    text = draft(**{"stop-1": 650, "stop-2": 130})  # ~5 min while parked
    _, findings, _ = plan(tmp_path / "a", stops, text)
    assert any(f.sid == "stop-1" and "doesn't cover" in f.message for f in errors(findings))
    extra = "[route.outbound]\npoints = [[0, 0], [0, 1]]\nwait = 20\n\n"
    rows, findings, _ = plan(tmp_path / "b", stops, text, extra=extra)
    assert errors(findings) == []
    assert rows[0].road > 20 * 60


def test_published_lengths_are_used_and_a_changed_draft_is_flagged(tmp_path):
    site = tmp_path / "site" / "demo"
    site.mkdir(parents=True)
    (site / "tour.json").write_text(json.dumps({"stops": [{"id": "stop-1", "duration": 30.0}]}))
    rows, findings, _ = plan(tmp_path, stop("stop-1", 3) + stop("stop-2", 12),
                             draft(**{"stop-1": 130, "stop-2": 130}))
    assert (rows[0].audio, rows[0].source) == (30.0, "published")
    assert (rows[1].source) == "draft"
    assert any(f.sid == "stop-1" and "has the script changed" in f.message for f in findings)


def test_hobart_plan_has_no_errors():
    tour = config.tour("hobart")
    data = json.loads((tour.root / "route.json").read_text())
    rows, findings, _ = route.check(tour, data)
    assert errors(findings) == [], findings
    assert [r.sid for r in rows] == list(tomllib.loads(tour.root.joinpath("tour.toml").read_text())["stops"])
    assert all(r.road and r.need and r.road > r.need for r in rows)
    assert any(f.sid == "stop-6" and "is needed" in f.message for f in findings)
