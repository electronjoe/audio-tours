import re

from audiotour.config import REPO_ROOT
from audiotour.script import (
    Cue,
    Pause,
    Text,
    check,
    parse_cast,
    parse_tracks,
)

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
        (7, True, "bracketed text would be spoken; a pause or sound cue is its own paragraph, '[PAUSE — 3 SECONDS]' or '[SFX — name]'"),
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
    doc = (REPO_ROOT / "docs" / "process" / "5-scripts.md").read_text(encoding="utf-8")
    [example] = re.findall(r"^```\n(.*?)^```$", doc, re.MULTILINE | re.DOTALL)
    assert [t.id for t in parse_tracks(example)] == ["stop-1", "stop-2"]
    assert check(example) == []


CAST_DRAFT = """\
# Interview

## Cast

- PLATYPUS → voices.platypus: a cheerful young platypus,
  quick and a little cheeky.
- OLD MINER -> voices.miner: a gravelly storyteller

## Script: Stop 1 — The River

[SFX — river, under]

Excuse me, platypus?

**PLATYPUS:** A minute? I'm on my dinner break.

[SFX — splash]

NARRATOR: Then how do you find dinner?

OLD MINER: Gold, mostly.

And the second paragraph of a long speech needs no label? It does.

[SFX — river, stop]

[PAUSE — 3 SECONDS]
"""


def test_cast_labels_and_cues_parse():
    cast, problems = parse_cast(CAST_DRAFT)
    assert problems == []
    assert cast["PLATYPUS"].voice == "platypus"
    assert cast["PLATYPUS"].note == "a cheerful young platypus, quick and a little cheeky."
    assert cast["OLD MINER"].voice == "miner"
    [t] = parse_tracks(CAST_DRAFT)
    assert t.segments == [
        Cue("river", "under"),
        Text("Excuse me, platypus?"),
        Text("A minute? I'm on my dinner break.", voice="platypus"),
        Cue("splash"),
        Text("Then how do you find dinner?"),
        Text("Gold, mostly.", voice="miner"),
        Text("And the second paragraph of a long speech needs no label? It does."),
        Cue("river", "stop"),
        Pause(3.0),
    ]
    assert t.char_count == sum(len(p) for p in t.paragraphs)  # labels aren't spoken, or counted
    assert check(CAST_DRAFT, voices={"narrator", "platypus", "miner"}, sfx={"river", "splash"}) == []


def test_check_reports_unknown_cast_voices_and_sfx():
    problems = [(p.line, p.message) for p in check(CAST_DRAFT, voices={"narrator", "platypus"}, sfx={"river"})]
    assert problems == [
        (7, "OLD MINER speaks with voices.miner, but tour.toml has no [voices.miner]"),
        (17, "[SFX — splash]: tour.toml has no [sfx.splash]"),
    ]


def test_check_rejects_bad_labels_and_cues():
    draft = """\
## Cast

- PLATYPUS → voices.platypus: a platypus
- not a cast line

## Script: Stop 1 — The River

KOALA: I'm not in the cast.

Platypus: lower-case labels are only a warning.

PLATYPUS:

[SFX — river, stop]

[SFX — rain, loud]

[SFX — rain, under]

Speech.

[SFX — rain, under]

[SFX — ]

[SFX — wind, under]
"""
    problems = [(p.line, p.error, p.message.split(":")[0]) for p in check(draft)]
    assert problems == [
        (4, True, "cast line isn't '- NAME → voices.<key>"),
        (8, True, "'KOALA"),
        (10, False, "'Platypus"),
        (12, True, "PLATYPUS"),
        (14, True, "[SFX — river, stop]"),
        (16, True, "[SFX — rain, loud]"),
        (22, True, "[SFX — rain, under]"),
        (24, True, "sound cue has no name"),
        (26, True, "[SFX — wind, under]"),
    ]
