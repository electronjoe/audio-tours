import pytest

from audiotour.chunks import (
    Chunk,
    Gap,
    apply_overrides,
    balanced_groups,
    context,
    plan_track,
    spoken_title,
)
from audiotour.config import TOURS_DIR
from audiotour.script import Cue, Pause, Text, Track, load_tracks


def track(*segments) -> Track:
    return Track("ch03", "Chapter 3", "A Different Kind of Strength", list(segments))


def test_spoken_title():
    assert spoken_title(track()) == "Chapter Three. A Different Kind of Strength."
    assert spoken_title(Track("afterword", "Afterword", "How We Know")) == "Afterword. How We Know."


def test_balanced_groups_are_even_and_under_limit():
    assert balanced_groups([500, 500, 500, 500], 1500) == [[0, 1], [2, 3]]
    assert balanced_groups([100, 100], 1500) == [[0, 1]]
    assert balanced_groups([2000, 10], 1500) == [[0], [1]]


def test_pauses_split_chunks_and_titles_come_first():
    items = plan_track(track(Text("a"), Text("b"), Pause(4), Text("c")), [], 1500, True)
    assert [type(x) for x in items] == [Chunk, Chunk, Gap, Chunk]
    assert [x.name for x in items if isinstance(x, Chunk)] == ["title", "chunk-01", "chunk-02"]
    assert items[1].text == "a\n\nb" and items[1].paragraphs == [0, 1] and items[1].offsets == [0, 3]
    assert items[3].paragraphs == [2]


def test_overrides_apply_and_unmatched_rules_fail():
    t = track(Text("Let's find out."))
    rule = {"track": "ch03", "find": "Let's", "with": "[warmly] Let's"}
    assert apply_overrides(t, [rule]) == ["[warmly] Let's find out."]
    assert apply_overrides(t, [{**rule, "track": "ch01"}]) == ["Let's find out."]
    with pytest.raises(SystemExit):
        apply_overrides(t, [{"find": "missing", "with": "x"}])


def test_context_uses_neighbouring_paragraphs():
    items = plan_track(track(Text("a" * 10), Text("b" * 10), Text("c" * 10)), [], 12, True)
    assert context(items, 0, 600) == (None, None)  # the title stands alone
    assert context(items, 2, 600) == ("a" * 10, "c" * 10)
    assert context(items, 1, 600) == (None, "b" * 10 + "\n\n" + "c" * 10)


def test_stop1_plan():
    ch01 = load_tracks(TOURS_DIR / "hobart" / "source" / "working-draft.md")[0]
    chunks = [x for x in plan_track(ch01, [], 1500, False) if isinstance(x, Chunk)]
    assert len(chunks) == 2
    assert all(800 <= len(c.text) <= 1500 for c in chunks)
    assert [p for c in chunks for p in c.paragraphs] == list(range(len(ch01.paragraphs)))


def test_changes_of_speaker_split_chunks_and_cues_do_not():
    t = track(Text("a"), Text("b", voice="kiki"), Cue("splash"), Text("c", voice="kiki"), Text("d"),
              Cue("rain", "under"), Text("e"), Pause(3), Text("f"))
    chunks = [x for x in plan_track(t, [], 1500, True) if isinstance(x, Chunk)]
    assert [(c.paragraphs, c.voice) for c in chunks] == [
        ([], "narrator"), ([0], "narrator"), ([1, 2], "kiki"), ([3, 4], "narrator"), ([5], "narrator"),
    ]


def test_hobart_stop6_interviews_the_platypus():
    """Stop 6 alternates narrator and platypus chunks over a river bed; the other stops are
    one narrator with no cues, so their chunks (and cache keys) are as before."""
    for t in load_tracks(TOURS_DIR / "hobart" / "source" / "working-draft.md"):
        voices = {seg.voice for seg in t.segments if isinstance(seg, Text)}
        cues = [(c.sfx, c.mode) for c in t.segments if isinstance(c, Cue)]
        if t.id == "stop-6":
            assert voices == {"narrator", "platypus"}
            assert cues == [("river", "under"), ("splash", "once"), ("river", "stop")]
            chunks = [x for x in plan_track(t, [], 1500, False) if isinstance(x, Chunk)]
            assert [c.voice for c in chunks[:3]] == ["narrator", "platypus", "narrator"]
        else:
            assert voices == {"narrator"} and cues == []


def test_title_without_label():
    assert spoken_title(track(), with_label=False) == "A Different Kind of Strength."
    items = plan_track(track(Text("a")), [], 1500, True, title_label=False)
    assert items[0].text == "A Different Kind of Strength."
