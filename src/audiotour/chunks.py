"""Plan how a track is rendered: spoken-text overrides, then chunks and pauses.

A chunk is a run of whole paragraphs sent as one TTS request, so a retake
re-renders one chunk rather than a chapter. Pauses and changes of voice always
split chunks, and pauses become local silence. Chunk sizes are balanced: the fewest chunks that keep
each one under ``max_chars``, with the sizes as even as the paragraphs allow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .script import Pause, Text, Track

SEPARATOR = "\n\n"

NUMBER_WORDS = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
    "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen Twenty"
).split()


@dataclass
class Chunk:
    index: int  # 1-based within the track; 0 is the spoken title
    paragraphs: list[int]  # 0-based indexes into Track.paragraphs (empty for the title)
    texts: list[str] = field(repr=False)
    voice: str = "narrator"  # a [voices.<name>] entry in tour.toml

    @property
    def name(self) -> str:
        return "title" if self.index == 0 else f"chunk-{self.index:02d}"

    @property
    def text(self) -> str:
        return SEPARATOR.join(self.texts)

    @property
    def offsets(self) -> list[int]:
        """Character offset of each paragraph within ``text``."""
        out, pos = [], 0
        for t in self.texts:
            out.append(pos)
            pos += len(t) + len(SEPARATOR)
        return out


@dataclass
class Gap:
    seconds: float


Item = Chunk | Gap


def spoken_title(track: Track, with_label: bool = True) -> str:
    """'Chapter 1' + title -> 'Chapter One. The Quiet After the Guns.', or just the title."""
    if not with_label:
        return f"{track.title}."
    label = track.label
    head, _, number = label.rpartition(" ")
    if number.isdigit() and int(number) < len(NUMBER_WORDS):
        label = f"{head} {NUMBER_WORDS[int(number)]}"
    return f"{label}. {track.title}."


def apply_overrides(track: Track, replacements: list[dict]) -> list[str]:
    """Spoken text for each paragraph after ``[[replace]]`` rules for this track.

    A rule whose ``find`` text no longer appears is an error, so a script edit
    can't silently orphan a respelling or audio tag.
    """
    texts = list(track.paragraphs)
    for rule in replacements:
        if rule.get("track", "*") not in ("*", track.id):
            continue
        hits = [i for i, t in enumerate(texts) if rule["find"] in t]
        if not hits:
            raise SystemExit(f"Override not found in {track.id}: {rule['find']!r}")
        for i in hits:
            texts[i] = texts[i].replace(rule["find"], rule["with"])
    return texts


def balanced_groups(lengths: list[int], max_chars: int) -> list[list[int]]:
    """Split paragraph indexes into the fewest contiguous groups under ``max_chars``,
    minimising the largest group. A paragraph longer than the limit gets its own group."""
    if not lengths:
        return []
    sep = len(SEPARATOR)

    def size(i: int, j: int) -> int:  # chars of paragraphs i..j-1 joined
        return sum(lengths[i:j]) + sep * (j - i - 1)

    n = len(lengths)
    for k in range(max(1, math.ceil(size(0, n) / max_chars)), n + 1):
        # best[j][g]: (largest group, cuts) for the first j paragraphs in g groups
        best: dict[tuple[int, int], tuple[int, list[int]]] = {(0, 0): (0, [])}
        for g in range(1, k + 1):
            for j in range(g, n + 1):
                options = [
                    (max(best[i, g - 1][0], size(i, j)), best[i, g - 1][1] + [i])
                    for i in range(g - 1, j)
                    if (i, g - 1) in best
                ]
                if options:
                    best[j, g] = min(options)
        largest, cuts = best[n, k]
        if largest <= max_chars or k == n:
            bounds = cuts[1:] + [n]
            starts = cuts
            return [list(range(a, b)) for a, b in zip(starts, bounds)]
    raise AssertionError("unreachable")


def plan_track(
    track: Track,
    replacements: list[dict],
    max_chars: int,
    announce_title: bool,
    voices: dict[int, str] | None = None,
    title_label: bool = True,
) -> list[Item]:
    """``voices`` maps 0-based paragraph indexes to a voice; the rest (and the title) are the narrator's."""
    texts = apply_overrides(track, replacements)
    voices = voices or {}
    items: list[Item] = []
    if announce_title:
        items.append(Chunk(0, [], [spoken_title(track, title_label)]))
    run: list[int] = []  # paragraph indexes since the last pause or change of voice
    para = chunks = 0

    def flush() -> None:
        nonlocal chunks
        for group in balanced_groups([len(texts[i]) for i in run], max_chars):
            idx = [run[g] for g in group]
            chunks += 1
            items.append(Chunk(chunks, idx, [texts[i] for i in idx], voices.get(idx[0], "narrator")))
        run.clear()

    for seg in track.segments:
        if isinstance(seg, Text):
            voice = voices.get(para, "narrator")
            if run and voices.get(run[-1], "narrator") != voice:
                flush()
            run.append(para)
            para += 1
        elif isinstance(seg, Pause):
            flush()
            items.append(Gap(seg.seconds))
    flush()
    return items


def context(items: list[Item], position: int, limit: int) -> tuple[str | None, str | None]:
    """Neighbouring spoken text (whole paragraphs, up to ``limit`` chars each side)
    passed as previous_text / next_text so chunks join smoothly. The title gets none."""
    body = [x for x in items if isinstance(x, Chunk) and x.index > 0]
    me = items[position]
    if not isinstance(me, Chunk) or me.index == 0:
        return None, None
    k = body.index(me)

    def gather(paragraphs: list[str]) -> list[str]:
        taken: list[str] = []
        for p in paragraphs:
            if taken and sum(map(len, taken)) + len(p) > limit:
                break
            taken.append(p)
        return taken

    before = gather([t for c in body[:k] for t in c.texts][::-1])[::-1]
    after = gather([t for c in body[k + 1:] for t in c.texts])
    return SEPARATOR.join(before) or None, SEPARATOR.join(after) or None
