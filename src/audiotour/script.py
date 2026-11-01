"""Parse a working-draft markdown file into narratable tracks.

A track starts at a heading of the form ``## Script: <Label> — <Title>`` and
runs until the next ``## `` heading. Inside a track, the italic metadata line
(``*About 490 words...*``) is dropped and ``[PAUSE — N SECONDS]`` markers become
explicit pause segments so silence is inserted locally instead of paid for.
The em dash may also be an en dash or a hyphen. ``docs/script-format.md`` is the
full contract, and ``check`` reports anything that breaks it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DASH = r"(?:—|–|--?)"  # writers (and models) swap em dashes for en dashes or hyphens
TRACK_HEADING = re.compile(rf"^## Script:\s*(?P<label>.+?)\s+{DASH}\s+(?P<title>.+?)\s*$")
PAUSE = re.compile(rf"\[PAUSE\s*{DASH}\s*(?P<seconds>\d+(?:\.\d+)?)\s+SECONDS?\]", re.IGNORECASE)
METADATA_LINE = re.compile(r"^\*About .+\*$")


@dataclass
class Text:
    text: str
    line: int = field(default=0, compare=False)  # where the paragraph starts in the draft


@dataclass
class Pause:
    seconds: float
    line: int = field(default=0, compare=False)


Segment = Text | Pause


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
        if pause:
            current.segments.append(Pause(float(pause.group("seconds")), start))
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


def check(markdown: str) -> list[Problem]:
    """Everything in a draft that breaks the script contract, in line order."""
    problems = [
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
        for seg in t.segments:
            if isinstance(seg, Pause):
                continue
            p = seg.text
            if NOT_PROSE.match(p):
                problems.append(Problem(seg.line, f"heading, list, table, quote or rule inside a track would be spoken: {p[:60]}"))
                continue
            if BRACKET.search(p):
                problems.append(Problem(seg.line, f"bracketed text would be spoken; a pause is its own paragraph, '[PAUSE — 3 SECONDS]': {p[:60]}"))
                continue
            if DIGIT.search(p):
                problems.append(Problem(seg.line, f"digits: write numbers as they should be spoken: {p[:60]}", error=False))
            if SYMBOL.search(p):
                problems.append(Problem(seg.line, f"symbol or abbreviation: spell it out: {p[:60]}", error=False))
    return sorted(problems, key=lambda p: p.line)


def check_file(path: Path) -> list[Problem]:
    return check(path.read_text(encoding="utf-8"))


QUOTES = ('"', "\u201c")  # straight or curly opening double quote


def check_voices(track: Track, voices: dict[int, str]) -> list[Problem]:
    """Warnings where a voice map (0-based paragraph -> voice) disagrees with the quoting.

    The script contract has no speaker labels, so a second voice's lines are its quoted
    paragraphs. A mismatch usually means a script edit shifted the paragraph numbers.
    """
    if not voices:
        return []
    texts = [s for s in track.segments if isinstance(s, Text)]
    problems = []
    for i, seg in enumerate(texts):
        quoted = seg.text.startswith(QUOTES)
        voice = voices.get(i, "narrator")
        if voice != "narrator" and not quoted:
            problems.append(Problem(seg.line, f"paragraph {i + 1} is {voice}'s but isn't quoted: {seg.text[:60]}", error=False))
        elif voice == "narrator" and quoted:
            problems.append(Problem(seg.line, f"paragraph {i + 1} is quoted but is the narrator's: {seg.text[:60]}", error=False))
    return problems
