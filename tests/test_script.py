import re

from audiotour.config import BOOKS_DIR, REPO_ROOT
from audiotour.script import Pause, Text, check, check_file, parse_tracks, load_tracks

SAMPLE = """\
## Locked configuration

Not narrated.

## Script: Chapter 3 — A Different Kind of Strength

*About 950 words, roughly 7 minutes.*

First paragraph,
wrapped across lines.

**\\[PAUSE — 4 SECONDS\\]**

Here's what happened.

## Script: Afterword — How We Know

Last track.

## Invention register

Not narrated either.
"""


def test_parse_sample():
    tracks = parse_tracks(SAMPLE)
    assert [t.id for t in tracks] == ["ch03", "afterword"]
    ch3 = tracks[0]
    assert ch3.title == "A Different Kind of Strength"
    assert ch3.segments == [
        Text("First paragraph, wrapped across lines."),
        Pause(4.0),
        Text("Here's what happened."),
    ]
    assert tracks[1].paragraphs == ["Last track."]



def test_dash_variants():
    tracks = parse_tracks(
        "## Script: Scene 1 - The Splash\n\nSlap.\n\n[PAUSE - 3 SECONDS]\n\n"
        "## Script: Scene 2 – The Bay\n\n[PAUSE – 2.5 SECONDS]\n\nEden.\n"
    )
    assert [(t.id, t.title) for t in tracks] == [("scene-1", "The Splash"), ("scene-2", "The Bay")]
    assert tracks[0].segments == [Text("Slap."), Pause(3.0)]
    assert tracks[1].segments == [Pause(2.5), Text("Eden.")]


def test_check_sample_is_clean():
    assert check(SAMPLE) == []


def test_check_finds_problems():
    draft = """\
## Script: Scene 1 · The splash (0:00–1:05)

## Script: Scene 2 — The bay

Fine.

*[pause]*

### A sub-heading

- a list item

In 1930, Tom died & was found.

## Script: Scene 2 — Again

More.
"""
    problems = [(p.line, p.error, p.message.split(":")[0]) for p in check(draft)]
    assert problems == [
        (1, True, "not a track heading ('## Script"),
        (7, True, "bracketed text would be spoken; a pause is its own paragraph, '[PAUSE — 3 SECONDS]'"),
        (9, True, "heading, list, table, quote or rule inside a track would be spoken"),
        (11, True, "heading, list, table, quote or rule inside a track would be spoken"),
        (13, False, "digits"),
        (13, False, "symbol or abbreviation"),
        (15, True, "track id 'scene-2' repeats the track on line 3"),
    ]


def test_check_no_tracks_names_the_first_heading():
    [problem] = check("# Old Tom\n\n## Scene 1 · The splash\n\nSlap.\n")
    assert problem.error and "'## Scene 1 · The splash'" in problem.message



def test_script_format_example_is_clean():
    """The example in the prompt must pass the checker, so the contract can't drift."""
    doc = (REPO_ROOT / "docs" / "script-format.md").read_text(encoding="utf-8")
    [example] = re.findall(r"^```\n(.*?)^```$", doc, re.MULTILINE | re.DOTALL)
    assert [t.id for t in parse_tracks(example)] == ["scene-1", "scene-2"]
    assert check(example) == []


def test_check_voices_flags_unquoted_and_misassigned_paragraphs():
    from audiotour.script import Text, Track, check_voices

    t = Track("episode-1", "Episode 1", "T", [Text("Hello."), Text('"Hi," said Kiki.'), Text('"Bye."')])
    assert check_voices(t, {}) == []
    assert check_voices(t, {1: "kiki", 2: "kiki"}) == []
    problems = check_voices(t, {0: "kiki", 1: "kiki"})
    assert [(p.error, p.message[:12]) for p in problems] == [(False, "paragraph 1 "), (False, "paragraph 3 ")]
