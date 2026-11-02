"""Parse a working-draft markdown file into narratable tracks.

A track starts at a heading of the form ``## Script: <Label> — <Title>`` and
runs until the next ``## `` heading. Inside a track, the italic metadata line
(``*About 490 words...*``) is dropped and ``[PAUSE — N SECONDS]`` markers become
explicit pause segments so silence is inserted locally instead of paid for.

A ``## Cast`` section (never spoken) lists the guest speakers, one per line:
``- PLATYPUS → voices.platypus: a cheerful young platypus``. A paragraph that
starts with ``PLATYPUS:`` is then spoken by ``[voices.platypus]``; the label is
stripped and holds only to the end of its paragraph. Unlabelled paragraphs are
the narrator's (``NARRATOR:`` may also be written). Sound cues sit on their own
line: ``[SFX — splash]`` plays a one-shot in the gap there, ``[SFX — river,
under]`` starts a bed under the following speech and ``[SFX — river, stop]``
fades it out.

The em dash may also be an en dash or a hyphen. ``docs/script-format.md`` is the
full contract, and ``check`` reports anything that breaks it.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

DASH = r"(?:—|–|--?)"  # writers (and models) swap em dashes for en dashes or hyphens
TRACK_HEADING = re.compile(rf"^## Script:\s*(?P<label>.+?)\s+{DASH}\s+(?P<title>.+?)\s*$")
PAUSE = re.compile(rf"\[PAUSE\s*{DASH}\s*(?P<seconds>\d+(?:\.\d+)?)\s+SECONDS?\]", re.IGNORECASE)
METADATA_LINE = re.compile(r"^\*About .+\*$")
SFX_CUE = re.compile(rf"\[SFX\s*{DASH}\s*(?P<name>[^,\]]*?)\s*(?:,\s*(?P<mode>[^\]]*?)\s*)?\]", re.IGNORECASE)
SFX_MODES = ("once", "under", "stop")  # once is a cue with no mode
CAST_HEADING = re.compile(r"^##\s+Cast\s*$", re.IGNORECASE)
CAST_LINE = re.compile(
    r"^[-*]\s+(?P<name>[A-Z][A-Z0-9' -]*?)\s*(?:→|->)\s*voices\.(?P<voice>[A-Za-z0-9_-]+)\s*(?::\s*(?P<note>.*))?$"
)
# A capitalised word or two at the start of a paragraph, then a colon: a speaker label if
# it names the cast, an error otherwise (it would be spoken).
LABEL = re.compile(r"^(?P<name>[A-Z][A-Z0-9'-]+(?: [A-Z0-9'-]+)*):\s*(?P<text>.*)$", re.DOTALL)
NARRATOR = "NARRATOR"  # always in the cast, as [voices.narrator]


@dataclass
class Text:
    text: str
    line: int = field(default=0, compare=False)  # where the paragraph starts in the draft
    voice: str = "narrator"  # a [voices.<key>] entry in tour.toml
    label: str | None = field(default=None, compare=False)  # the NAME: it was written with


@dataclass
class Pause:
    seconds: float
    line: int = field(default=0, compare=False)


@dataclass
class Cue:
    """A sound effect at this point: a one-shot in the gap, or a bed starting or stopping."""

    sfx: str  # an [sfx.<name>] entry in tour.toml
    mode: str = "once"  # once | under | stop
    line: int = field(default=0, compare=False)


Segment = Text | Pause | Cue


@dataclass
class CastMember:
    name: str  # the label, in capitals
    voice: str  # the [voices.<key>] it speaks with
    note: str
    line: int = 0


def parse_cast(markdown: str) -> tuple[dict[str, CastMember], list[Problem]]:
    """Every ``## Cast`` section's entries by name, and any lines that don't parse."""
    cast: dict[str, CastMember] = {}
    problems: list[Problem] = []
    inside = False
    last: CastMember | None = None
    for n, raw in enumerate(markdown.splitlines(), 1):
        line = raw.strip()
        if raw.startswith("## "):
            inside = bool(CAST_HEADING.match(raw.rstrip()))
            continue
        if not inside or not line:
            continue
        if raw[:1].isspace() and last is not None:  # a note wrapped onto the next line
            last.note = f"{last.note} {line}".strip()
            continue
        last = None
        m = CAST_LINE.match(line)
        if not m:
            problems.append(Problem(n, f"cast line isn't '- NAME → voices.<key>: note': {line[:60]}"))
            continue
        member = CastMember(m["name"], m["voice"], (m["note"] or "").strip(), n)
        if member.name in cast:
            problems.append(Problem(n, f"{member.name} is already in the cast on line {cast[member.name].line}"))
            continue
        cast[member.name] = last = member
    problems += [Problem(m.line, f"{m.name} has no character note", error=False) for m in cast.values() if not m.note]
    cast.setdefault(NARRATOR, CastMember(NARRATOR, "narrator", "the narrator"))
    return cast, problems


@dataclass
class Track:
    id: str
    label: str
    title: str
    segments: list[Segment] = field(default_factory=list)
    line: int = field(default=0, compare=False)

    @property
    def paragraphs(self) -> list[str]:
        return [s.text for s in self.segments if isinstance(s, Text)]

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.paragraphs)

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)

    @property
    def pause_seconds(self) -> float:
        return sum(s.seconds for s in self.segments if isinstance(s, Pause))


def track_id(label: str) -> str:
    """'Chapter 1' -> 'ch01', 'Workshop 2' -> 'ws02', 'Afterword' -> 'afterword'."""
    m = re.fullmatch(r"(Chapter|Workshop)\s+(\d+)", label)
    if m:
        prefix = {"Chapter": "ch", "Workshop": "ws"}[m.group(1)]
        return f"{prefix}{int(m.group(2)):02d}"
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def clean(paragraph: str) -> str:
    """Strip markdown emphasis and escapes so only spoken text remains."""
    text = paragraph.replace("\\[", "[").replace("\\]", "]")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    return text.strip()


def parse_tracks(markdown: str) -> list[Track]:
    cast, _ = parse_cast(markdown)
    tracks: list[Track] = []
    current: Track | None = None
    buffer: list[str] = []
    start = 0

    def flush_paragraph() -> None:
        if current is None or not buffer:
            buffer.clear()
            return
        paragraph = clean(" ".join(buffer))
        buffer.clear()
        if not paragraph or METADATA_LINE.match(paragraph):
            return
        pause = PAUSE.fullmatch(paragraph)
        cue = SFX_CUE.fullmatch(paragraph)
        label = LABEL.match(paragraph)
        if pause:
            current.segments.append(Pause(float(pause.group("seconds")), start))
        elif cue:
            mode = (cue["mode"] or "once").lower()
            current.segments.append(Cue(cue["name"], mode, start))
        elif label and label["name"] in cast:
            member = cast[label["name"]]
            current.segments.append(Text(label["text"].strip(), start, member.voice, member.name))
        else:
            current.segments.append(Text(paragraph, start))

    for n, raw in enumerate(markdown.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("## "):
            flush_paragraph()
            heading = TRACK_HEADING.match(line)
            if heading:
                label = heading.group("label")
                current = Track(track_id(label), label, heading.group("title"), line=n)
                tracks.append(current)
            else:
                current = None
        elif not line.strip():
            flush_paragraph()
        elif current is not None:
            if METADATA_LINE.match(line.strip()):
                continue
            if not buffer:
                start = n
            buffer.append(line.strip())
    flush_paragraph()
    return tracks


def load_tracks(path: Path) -> list[Track]:
    return parse_tracks(path.read_text(encoding="utf-8"))


# --- Checking a draft against docs/script-format.md ---------------------------------

SCRIPT_HEADING = re.compile(r"^##\s+Script\b", re.IGNORECASE)
NOT_PROSE = re.compile(r"^(?:#|>|\||[-*+]\s|\d{1,2}[.)]\s|-{3,}|_{3,})")
BRACKET = re.compile(r"[\[\]]")
DIGIT = re.compile(r"\d")
SYMBOL = re.compile(r"[%&~@#/]|\b(?:e\.g|i\.e|etc)\.")


@dataclass
class Problem:
    line: int  # 0 when it's about the whole draft
    message: str
    error: bool = True  # errors mean the parse is wrong; warnings are style the narrator may trip on


def check(
    markdown: str, voices: Collection[str] | None = None, sfx: Collection[str] | None = None
) -> list[Problem]:
    """Everything in a draft that breaks the script contract, in line order.

    ``voices`` and ``sfx`` are the ``[voices.*]`` and ``[sfx.*]`` keys in tour.toml; when
    given, cast entries and SFX cues that name anything else are errors.
    """
    cast, problems = parse_cast(markdown)
    for member in cast.values():
        if voices is not None and member.voice not in voices:
            problems.append(Problem(member.line, f"{member.name} speaks with voices.{member.voice}, "
                                                 f"but tour.toml has no [voices.{member.voice}]"))
    problems += [
        Problem(n, f"not a track heading ('## Script: <Label> — <Title>'), so the track is skipped: {raw.strip()}")
        for n, raw in enumerate(markdown.splitlines(), 1)
        if SCRIPT_HEADING.match(raw) and not TRACK_HEADING.match(raw.rstrip())
    ]
    tracks = parse_tracks(markdown)
    if not tracks:
        headings = [line.strip() for line in markdown.splitlines() if line.startswith("## ")]
        found = f"; the first '## ' heading is '{headings[0]}'" if headings else ""
        problems.append(Problem(0, f"no tracks: no heading of the form '## Script: <Label> — <Title>'{found}"))
    seen: dict[str, int] = {}
    for t in tracks:
        if t.id in seen:
            problems.append(Problem(t.line, f"track id '{t.id}' repeats the track on line {seen[t.id]}"))
        seen.setdefault(t.id, t.line)
        if not t.paragraphs:
            problems.append(Problem(t.line, f"track '{t.id}' has no narration"))
        problems += _check_cues(t, sfx)
        for seg in t.segments:
            if not isinstance(seg, Text):
                continue
            if seg.label and not seg.text:
                problems.append(Problem(seg.line, f"{seg.label}: has nothing to say"))
                continue
            p = seg.text
            label = LABEL.match(p)
            if label and seg.label is None:
                problems.append(Problem(seg.line, f"'{label['name']}:' isn't in the ## Cast, so it would be spoken; "
                                                  f"add it to the cast or rewrite the line: {p[:60]}"))
                continue
            first = p.split(":", 1)[0] if ":" in p[:40] else ""
            if first and first != first.upper() and first.upper() in cast:
                problems.append(Problem(seg.line, f"'{first}:' looks like a speaker label; labels are in capitals, "
                                                  f"'{first.upper()}:': {p[:60]}", error=False))
            if NOT_PROSE.match(p):
                problems.append(Problem(seg.line, f"heading, list, table, quote or rule inside a track would be spoken: {p[:60]}"))
                continue
            if BRACKET.search(p):
                problems.append(Problem(seg.line, "bracketed text would be spoken; a pause or sound cue is its own "
                                                  f"paragraph, '[PAUSE — 3 SECONDS]' or '[SFX — name]': {p[:60]}"))
                continue
            if DIGIT.search(p):
                problems.append(Problem(seg.line, f"digits: write numbers as they should be spoken: {p[:60]}", error=False))
            if SYMBOL.search(p):
                problems.append(Problem(seg.line, f"symbol or abbreviation: spell it out: {p[:60]}", error=False))
    return sorted(problems, key=lambda p: p.line)


def _check_cues(track: Track, sfx: Collection[str] | None) -> list[Problem]:
    """Unknown effects or modes, a stop with no bed running, a bed started twice or with
    no speech after it."""
    problems = []
    running: dict[str, int] = {}  # bed -> line it started on
    for k, seg in enumerate(track.segments):
        if not isinstance(seg, Cue):
            continue
        if not seg.sfx:
            problems.append(Problem(seg.line, "sound cue has no name: '[SFX — name]'"))
            continue
        if sfx is not None and seg.sfx not in sfx:
            problems.append(Problem(seg.line, f"[SFX — {seg.sfx}]: tour.toml has no [sfx.{seg.sfx}]"))
        if seg.mode not in SFX_MODES:
            problems.append(Problem(seg.line, f"[SFX — {seg.sfx}, {seg.mode}]: the mode is 'under', 'stop' "
                                              "or nothing (a one-shot)"))
        elif seg.mode == "under":
            if seg.sfx in running:
                problems.append(Problem(seg.line, f"[SFX — {seg.sfx}, under]: it's already running from line "
                                                  f"{running[seg.sfx]}"))
            elif not any(isinstance(x, Text) for x in track.segments[k + 1:]):
                problems.append(Problem(seg.line, f"[SFX — {seg.sfx}, under]: no speech after it to go under"))
            running[seg.sfx] = seg.line
        elif seg.mode == "stop" and running.pop(seg.sfx, None) is None:
            problems.append(Problem(seg.line, f"[SFX — {seg.sfx}, stop]: no '[SFX — {seg.sfx}, under]' "
                                              "is running"))
    return problems


def check_file(path: Path, settings: dict | None = None) -> list[Problem]:
    """``check`` a draft file; with tour.toml's ``settings``, also check cast and SFX names."""
    if settings is None:
        return check(path.read_text(encoding="utf-8"))
    return check(path.read_text(encoding="utf-8"), settings.get("voices", {}), settings.get("sfx", {}))
