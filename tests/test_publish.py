import json
import re
import shutil

import pytest

from audiotour import config, publish
from audiotour.config import REPO_ROOT, Tour

SITE = REPO_ROOT / "site"

DRAFT = """\
# Demo Walk

## Script: Stop 1 — The Corner

A short story about the corner.

## Script: Stop 2 — The Bridge

A short story about the bridge.
"""

TOML = """\
[{table}]
title = '{title}'

[player]
mode = "walk"

[stops.stop-1]
lat = -42.88
lon = 147.33

[stops.stop-2]
lat = -42.89
lon = 147.34
radius = 60
"""


def make_tour(tours, slug="demo", title="Demo Walk", table="tour"):
    root = tours / slug
    (root / "source").mkdir(parents=True)
    (root / "source" / "working-draft.md").write_text(DRAFT)
    (root / "tour.toml").write_text(TOML.format(table=table, title=title))
    return Tour(slug, tours)


def test_hobart_pages_match_committed(tmp_path):
    """The committed page and manifest are what the templates produce: edit site/player/, then publish."""
    for data in SITE.glob("*/tour.json"):  # every published tour, for the tour list
        (tmp_path / data.parent.name).mkdir()
        shutil.copyfile(data, tmp_path / data.parent.name / "tour.json")
    publish.pages(tmp_path, config.TOURS_DIR)
    for name in ("index.html", "manifest.webmanifest"):
        assert (tmp_path / "hobart" / name).read_text() == (SITE / "hobart" / name).read_text(), name
    assert (tmp_path / "index.html").read_text() == (SITE / "index.html").read_text()


def test_second_tour_needs_no_hand_written_files(tmp_path):
    site, tours = tmp_path / "site", tmp_path / "tours"
    (site / "hobart").mkdir(parents=True)
    shutil.copyfile(SITE / "hobart" / "tour.json", site / "hobart" / "tour.json")
    (site / "lab").mkdir()  # a folder without tour.json is not a tour
    publish.publish(make_tour(tours), site)

    data = json.loads((site / "demo" / "tour.json").read_text())
    assert list(data)[:4] == ["schema", "slug", "title", "mode"]
    assert (data["schema"], data["title"], data["mode"]) == (1, "Demo Walk", "walk")
    assert [s["id"] for s in data["stops"]] == ["stop-1", "stop-2"]
    assert "audio" not in data["stops"][0]

    page = (site / "demo" / "index.html").read_text()
    assert "<title>Demo Walk</title>" in page and "${" not in page
    v = publish.player_version()
    assert all(f'<script src="../player/{js}?v={v}"></script>' in page for js in ("app.js", "map.js", "view.js"))
    manifest = json.loads((site / "demo" / "manifest.webmanifest").read_text())
    assert manifest["name"] == manifest["short_name"] == "Demo Walk"
    assert manifest["theme_color"] == publish.DEFAULT_THEME

    index = (site / "index.html").read_text()
    rows = re.findall(r'<a class="row" href="([^"]+)">', index)
    assert rows == ["demo/", "hobart/"]  # sorted by title
    assert "<small>Walk · 2 stories</small>" in index  # no route: no length or time
    assert re.search(r"<small>Drive · 8 stories · \d+ km · about (\d+ h)?( ?\d+ min)?</small>", index)


def test_trip_length_and_time():
    route = {"outbound": [[-42.0, 147.0], [-42.0, 147.1]], "return": [[-42.0, 147.1], [-42.0, 147.0]]}
    m, secs = publish.trip(route)
    assert 16400 < m < 16600 and secs == pytest.approx(m / (80 / 3.6))  # 80 km/h without OSRM times
    route["seconds"] = {"outbound": [0, 600], "return": [0, 660]}
    assert publish.trip(route)[1] == 1260
    assert [publish.about(s) for s in (60, 1260, 3600, 6600)] == ["about 5 min", "about 20 min", "about 1 h", "about 1 h 50 min"]


def test_titles_are_escaped(tmp_path):
    site, tours = tmp_path / "site", tmp_path / "tours"
    publish.publish(make_tour(tours, title='Rocks & "Ropes" <1>'), site)
    page = (site / "demo" / "index.html").read_text()
    assert "<title>Rocks &amp; &quot;Ropes&quot; &lt;1&gt;</title>" in page
    assert json.loads((site / "demo" / "manifest.webmanifest").read_text())["name"] == 'Rocks & "Ropes" <1>'
    assert "Rocks &amp; &quot;Ropes&quot; &lt;1&gt;" in (site / "index.html").read_text()


def test_book_table_is_still_read(tmp_path, capsys):
    tour = make_tour(tmp_path, table="book", title="Old Name")
    assert tour.title == "Old Name"
    assert "rename [book] to [tour]" in capsys.readouterr().err
    assert config.Book is config.Tour and config.book is config.tour and config.BOOKS_DIR == config.TOURS_DIR


def test_tour_table_wins_quietly(tmp_path, capsys):
    tour = make_tour(tmp_path, title="New Name")
    assert tour.info["title"] == "New Name"
    assert capsys.readouterr().err == ""


def test_publish_keeps_published_audio_without_a_build(tmp_path):
    """A fresh clone has no build/: republishing must not delete committed audio."""
    site, tours = tmp_path / "site", tmp_path / "tours"
    tour = make_tour(tours)
    publish.publish(tour, site)
    data = json.loads((site / "demo" / "tour.json").read_text())
    (site / "demo" / "audio" / "stop-1-0123abcd.mp3").write_bytes(b"mp3")
    (site / "demo" / "audio" / "stop-2-stale000.mp3").write_bytes(b"old")
    data["stops"][0] |= {"audio": "audio/stop-1-0123abcd.mp3", "bytes": 3, "duration": 1.5}
    (site / "demo" / "tour.json").write_text(json.dumps(data))
    publish.publish(tour, site)
    stops = json.loads((site / "demo" / "tour.json").read_text())["stops"]
    assert (stops[0]["audio"], stops[0]["duration"]) == ("audio/stop-1-0123abcd.mp3", 1.5)
    assert "audio" not in stops[1]
    assert sorted(p.name for p in (site / "demo" / "audio").iterdir()) == ["stop-1-0123abcd.mp3"]


def test_unknown_mode_is_refused(tmp_path):
    tour = make_tour(tmp_path / "tours")
    (tour.root / "tour.toml").write_text((tour.root / "tour.toml").read_text().replace('"walk"', '"cycle"'))
    with pytest.raises(SystemExit, match="mode"):
        publish.publish(tour, tmp_path / "site")


def test_player_reads_the_published_schema():
    app = (SITE / "player" / "app.js").read_text()
    assert re.search(r"^const SCHEMA = (\d+);", app, re.MULTILINE).group(1) == str(publish.SCHEMA)
    assert "schema !== SCHEMA" in app


def test_label_and_teaser_are_copied_and_checked(tmp_path):
    tour = make_tour(tmp_path / "tours")
    toml = (tour.root / "tour.toml").read_text()
    toml = toml.replace("lon = 147.33\n", 'lon = 147.33\nlabel = " The Corner "\nteaser = "Why the corner is round."\n')
    (tour.root / "tour.toml").write_text(toml)
    publish.publish(tour, tmp_path / "site")
    stops = json.loads((tmp_path / "site" / "demo" / "tour.json").read_text())["stops"]
    assert (stops[0]["label"], stops[0]["teaser"]) == ("The Corner", "Why the corner is round.")
    assert "label" not in stops[1] and "teaser" not in stops[1]
    for bad in ('label = "A label far too long for a pin"', "label = 3", 'teaser = ""'):
        (tour.root / "tour.toml").write_text(toml.replace('lon = 147.34\n', f"lon = 147.34\n{bad}\n"))
        with pytest.raises(SystemExit, match=r"\[stops.stop-2\]"):
            publish.publish(tour, tmp_path / "site")
