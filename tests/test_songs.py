"""Song tables (tasks/006): field checks, the Spotify check against recorded responses, publish.

The responses in tests/fixtures/spotify/ were fetched once from the free, account-less
endpoints; these tests never go online.
"""

import json

import pytest

from audiotour import publish, songs
from audiotour.config import REPO_ROOT, Tour

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "spotify"
TID = "4uLU6hMCjMI75M1A2tKUQC"
LINK = f"https://open.spotify.com/track/{TID}"
OEMBED = (FIXTURES / f"oembed-{TID}.json").read_text()
PAGE = (FIXTURES / f"track-{TID}.html").read_text()

DRAFT = """\
# Demo

## Script: Stop 1 — The Hill

A story about the hill. Our song is Never Gonna Give You Up, by Rick Astley.

## Script: Stop 2 — The Bridge

A story about the bridge.
"""

TOML = """\
[tour]
title = "Demo"

[stops.stop-1]
lat = -42.88
lon = 147.33

[stops.stop-1.song]
title = "{title}"
artist = "Rick Astley"
spotify = "{link}"
length = "{length}"
why = "A test song."

[stops.stop-2]
lat = -42.89
lon = 147.34
"""


def make_tour(tmp_path, title="Never Gonna Give You Up", link=LINK + "?si=abc123", length="3:34"):
    root = tmp_path / "tours" / "demo"
    (root / "source").mkdir(parents=True)
    (root / "source" / "working-draft.md").write_text(DRAFT)
    (root / "tour.toml").write_text(TOML.format(title=title, link=link, length=length))
    return Tour("demo", tmp_path / "tours")


class Spotify:
    """Recorded responses, by URL, and a count of what was asked."""

    def __init__(self, offline=False, page=True):
        self.calls, self.offline, self.page = [], offline, page

    def __call__(self, url):
        self.calls.append(url)
        if self.offline:
            raise songs.Offline("no network")
        if url == songs.OEMBED.format(link=LINK):
            return 200, OEMBED
        if url == LINK:
            if not self.page:
                raise songs.Offline("timeout")
            return 200, PAGE
        return 404, "Not Found"


def messages(problems):
    return [("error" if p.error else "warning", p.message) for p in problems]


def test_seconds():
    assert songs.seconds("3:42") == 222
    assert songs.seconds("12:05") == 725
    assert songs.seconds(214) == 214
    for bad in ("3.42", "3:7", "0:00", "", "three", True, -5):
        with pytest.raises(ValueError):
            songs.seconds(bad)


def test_track_links():
    assert songs.track_id(LINK) == TID
    assert songs.canonical(f"https://open.spotify.com/intl-de/track/{TID}?si=x") == LINK
    assert songs.track_id(f"https://open.spotify.com/album/{TID}") is None
    assert songs.track_id(f"spotify:track:{TID}") is None


def test_field_problems():
    assert songs.field_problems({"title": "a", "artist": "b", "spotify": LINK, "length": "1:00", "why": "c"}) == []
    bad = songs.field_problems({"title": "a", "spotify": "https://example.com", "length": "90s", "lenght": 1})
    assert "missing artist" in bad and "missing why" in bad
    assert any("not a track link" in m for m in bad)
    assert any("m:ss" in m for m in bad)
    assert any("unknown field 'lenght'" in m for m in bad)


def test_page_facts_from_the_recorded_track_page():
    assert songs.page_facts(PAGE) == ("Rick Astley", 214)
    assert songs.page_facts("<html><head></head></html>") == (None, None)


def test_titles():
    assert songs.same_title("never gonna give you up!", "Never Gonna Give You Up") == "same"
    assert songs.same_title("Rock & Roll", "Rock and Roll") == "same"
    assert songs.same_title("Here Comes the Sun", "Here Comes The Sun - Remastered 2009") == "version"
    assert songs.same_title("Waltzing Matilda", "Waltzing Matilda (Live)") == "version"
    assert songs.same_title("Waltzing Matilda", "Never Gonna Give You Up") == "different"


def test_check_passes_a_correct_song(tmp_path):
    tour = make_tour(tmp_path)
    spotify = Spotify()
    assert messages(songs.check(tour, spotify)) == []
    assert spotify.calls == [songs.OEMBED.format(link=LINK), LINK]  # the ?si= tag is dropped
    cached = json.loads((tour.root / "cache" / "spotify" / f"{TID}.json").read_text())
    assert cached == {"title": "Never Gonna Give You Up", "artist": "Rick Astley", "seconds": 214}
    # The second check is answered from the cache.
    assert messages(songs.check(tour, spotify)) == [] and len(spotify.calls) == 2


def test_check_rejects_a_title_that_does_not_match(tmp_path):
    tour = make_tour(tmp_path, title="Waltzing Matilda")
    problems = songs.check(tour, Spotify())
    errors = [m for kind, m in messages(problems) if kind == "error"]
    assert errors == ["[stops.stop-1.song]: the link is 'Never Gonna Give You Up' on Spotify, not 'Waltzing Matilda'"]
    assert problems[0].line == 8  # the [stops.stop-1.song] line in tour.toml
    # The script names the artist but not this title.
    assert ("warning", "[stops.stop-1.song]: the stop-1 script never names the title ('Waltzing Matilda'); "
                       "the song segment should") in messages(problems)


def test_check_does_not_need_a_version_note_spoken(tmp_path):
    tour = make_tour(tmp_path, title="Never Gonna Give You Up (version 2)")
    assert not [m for _, m in messages(songs.check(tour, Spotify(offline=True))) if "never names" in m]
    assert songs.base_title("Song Of Australia (version 2)") == "Song Of Australia"
    assert songs.base_title("Here Comes the Sun - Remastered 2009") == "Here Comes the Sun"
    assert songs.base_title("Waltzing Matilda") == "Waltzing Matilda"


def test_check_rejects_a_wrong_length_and_says_the_right_one(tmp_path):
    tour = make_tour(tmp_path, length="3:42")
    assert messages(songs.check(tour, Spotify())) == [
        ("error", "[stops.stop-1.song]: length = '3:42', but Spotify says 3:34; write length = \"3:34\"")]
    assert messages(songs.check(make_tour(tmp_path / "b", length="3:35"), Spotify())) == []  # within 2 s


def test_check_rejects_an_unknown_track(tmp_path):
    tour = make_tour(tmp_path, link="https://open.spotify.com/track/0000000000000000000000")
    assert messages(songs.check(tour, Spotify())) == [
        ("error", "[stops.stop-1.song]: Spotify has no track https://open.spotify.com/track/0000000000000000000000")]


def test_offline_warns_instead_of_failing(tmp_path):
    tour = make_tour(tmp_path)
    spotify = Spotify(offline=True)
    problems = songs.check(tour, spotify)
    assert [p.error for p in problems] == [False]
    assert "link not verified, Spotify unreachable (no network)" in problems[0].message
    assert not (tour.root / "cache").exists()
    assert [p.error for p in songs.check(tour, Spotify(), online=False)] == [False]  # --offline


def test_title_checked_even_if_the_track_page_fails(tmp_path):
    tour = make_tour(tmp_path)
    problems = songs.check(tour, Spotify(page=False))
    assert messages(problems) == [("warning", "[stops.stop-1.song]: couldn't read the length from Spotify's "
                                              "track page; check length = '3:34' by hand")]
    assert not (tour.root / "cache" / "spotify" / f"{TID}.json").exists()  # retried next time


def test_no_songs_no_network(tmp_path):
    tour = make_tour(tmp_path)
    toml = (tour.root / "tour.toml").read_text()
    (tour.root / "tour.toml").write_text(toml.split("[stops.stop-1.song]")[0] + "[stops.stop-2]\nlat = 1\nlon = 2\n")
    spotify = Spotify()
    assert songs.check(tour, spotify) == [] and spotify.calls == []


def test_publish_copies_the_song(tmp_path):
    tour = make_tour(tmp_path)
    publish.publish(tour, tmp_path / "site")
    stops = json.loads((tmp_path / "site" / "demo" / "tour.json").read_text())["stops"]
    assert stops[0]["song"] == {"title": "Never Gonna Give You Up", "artist": "Rick Astley",
                                "spotify": LINK, "length": 214, "why": "A test song."}
    assert "song" not in stops[1]


def test_publish_refuses_a_broken_song(tmp_path):
    tour = make_tour(tmp_path, length="soon")
    with pytest.raises(SystemExit, match=r"\[stops.stop-1.song\]: length"):
        publish.publish(tour, tmp_path / "site")


def test_report_prints_tour_toml_lines(tmp_path, capsys):
    tour = make_tour(tmp_path, title="Waltzing Matilda")
    assert songs.report(tour, online=False) == (0, 2)
    out = capsys.readouterr().out.splitlines()
    assert all(line.startswith(f"{tour.root / 'tour.toml'}:8: warning: [stops.stop-1.song]: ") for line in out)
