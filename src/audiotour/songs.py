"""Song moments (tasks/006): the ``[stops.<id>.song]`` table in tour.toml.

```toml
[stops.stop-3.song]
title = "..."
artist = "..."
spotify = "https://open.spotify.com/track/<id>"
length = "3:42"   # m:ss, or whole seconds
why = "One line for the screen: why this song is here."
```

``tour check`` verifies each link against Spotify (``check``): the oEmbed title must match
``title``, and the track page's ``music:duration`` meta tag must match ``length``. Neither
needs an account. Answers are cached in ``tours/<slug>/cache/spotify/``, so only the first
check of a link goes online. Offline, the links aren't verified and check warns instead.
``publish`` copies each song into tour.json (``to_json``), with ``length`` in seconds.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from . import config
from .script import Problem, load_tracks

FIELDS = ("title", "artist", "spotify", "length", "why")
TRACK_URL = re.compile(
    r"^https://open\.spotify\.com/(?:intl-[A-Za-z-]+/)?track/(?P<id>[A-Za-z0-9]{22})/?(?:\?.*)?$")
LENGTH = re.compile(r"^(?P<m>\d+):(?P<s>[0-5]\d)$")
LENGTH_SLACK = 2  # seconds of difference from Spotify's duration allowed (it rounds)
OEMBED = "https://open.spotify.com/oembed?url={link}"
TIMEOUT = 10  # seconds per request
USER_AGENT = "audio-tours song check"


class Offline(Exception):
    """Spotify couldn't be reached: no network, a timeout, or a server error."""


@dataclass
class Facts:
    """What Spotify says about a track."""

    title: str
    artist: str | None = None  # from the track page; None if it couldn't be read
    seconds: int | None = None


Fetch = Callable[[str], tuple[int, str]]  # url -> (HTTP status, body); raises Offline


def songs(settings: dict) -> dict[str, dict]:
    """Every stop's song table, by stop id, in stop order."""
    return {sid: s["song"] for sid, s in settings.get("stops", {}).items() if "song" in s}


def seconds(length: str | int) -> int:
    """``"3:42"`` (or a whole number of seconds) as seconds. Raises ValueError otherwise."""
    if isinstance(length, int) and not isinstance(length, bool) and length > 0:
        return length
    m = LENGTH.match(str(length).strip()) if isinstance(length, str) else None
    if not m or not int(m["m"]) * 60 + int(m["s"]):
        raise ValueError(f"length = {length!r}: write it as \"m:ss\", e.g. \"3:42\"")
    return int(m["m"]) * 60 + int(m["s"])


def mmss(secs: int) -> str:
    return f"{secs // 60}:{secs % 60:02d}"


def track_id(link: str) -> str | None:
    m = TRACK_URL.match(str(link).strip())
    return m["id"] if m else None


def canonical(link: str) -> str:
    """The plain track link, without ``intl-xx/`` or a ``?si=`` share tag."""
    return f"https://open.spotify.com/track/{track_id(link)}"


def field_problems(song: dict) -> list[str]:
    """What's wrong with a song table on its own, without going online."""
    if not isinstance(song, dict):
        return ["song must be a table: [stops.<id>.song] with " + ", ".join(FIELDS)]
    out = [f"missing {f}" for f in FIELDS if not str(song.get(f, "")).strip()]
    out += [f"unknown field {f!r} (expected {', '.join(FIELDS)})" for f in song if f not in FIELDS]
    if song.get("spotify") and not track_id(song["spotify"]):
        out.append(f"spotify = {song['spotify']!r} is not a track link (https://open.spotify.com/track/<id>)")
    if song.get("length"):
        try:
            seconds(song["length"])
        except ValueError as e:
            out.append(str(e))
    return out


def to_json(sid: str, song: dict) -> dict:
    """The song as tour.json carries it (docs/tour-json.md). Refuses an invalid table."""
    bad = field_problems(song)
    if bad:
        raise SystemExit(f"[stops.{sid}.song]: {'; '.join(bad)}. Run `uv run tour check`.")
    return {"title": song["title"].strip(), "artist": song["artist"].strip(),
            "spotify": canonical(song["spotify"]), "length": seconds(song["length"]),
            "why": song["why"].strip()}


# --- Asking Spotify -------------------------------------------------------------------

def http_get(url: str) -> tuple[int, str]:
    try:
        r = httpx.get(url, timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError as e:
        raise Offline(str(e) or type(e).__name__) from e
    if r.status_code >= 500 or r.status_code == 429:
        raise Offline(f"HTTP {r.status_code}")
    return r.status_code, r.text


def page_facts(page: str) -> tuple[str | None, int | None]:
    """The artist and duration (s) from a track page's ``music:`` meta tags."""

    def meta(name: str) -> str | None:
        for tag in re.findall(r"<meta\b[^>]*>", page):
            if re.search(rf"""(?:name|property)=["']{re.escape(name)}["']""", tag):
                m = re.search(r"""content=["']([^"']*)["']""", tag)
                return html.unescape(m[1]) if m else None
        return None

    duration = meta("music:duration")
    return meta("music:musician_description"), int(duration) if duration and duration.isdigit() else None


def lookup(link: str, cache_dir: Path | None = None, fetch: Fetch = http_get) -> Facts | None:
    """What Spotify says about a track link; None if it has no such track. Raises Offline.

    A complete answer is cached in ``cache_dir`` (a track's title and length don't change).
    """
    tid = track_id(link)
    cached = cache_dir / f"{tid}.json" if cache_dir else None
    if cached and cached.exists():
        return Facts(**json.loads(cached.read_text()))
    url = canonical(link)
    status, body = fetch(OEMBED.format(link=url))
    if status in (400, 404):
        return None
    if status != 200:
        raise Offline(f"oEmbed: HTTP {status}")
    facts = Facts(json.loads(body)["title"])
    try:
        status, page = fetch(url)
        if status == 200:
            facts.artist, facts.seconds = page_facts(page)
    except Offline:
        pass  # the title is verified; the length can't be, this time
    if cached and facts.seconds:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(asdict(facts), ensure_ascii=False) + "\n")
    return facts


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def same_title(ours: str, theirs: str) -> str:
    """``"same"``, ``"version"`` (Spotify adds a note such as "- Remastered 2011" or
    "(Live)"), or ``"different"``. Case, accents and punctuation don't count."""
    if _plain(ours) == _plain(theirs):
        return "same"
    m = re.match(r"^(.*?)\s*(?:\s[-–—]\s.*|\(.*\)|\[.*\])$", theirs.strip())
    if m and m[1] and _plain(m[1]) == _plain(ours):
        return "version"
    return "different"


# --- tour check -----------------------------------------------------------------------

def check(tour: config.Tour, fetch: Fetch = http_get, online: bool = True) -> list[Problem]:
    """Every song table's problems. ``line`` is the line in tour.toml (0 if not found)."""
    table = songs(tour.settings)
    if not table:
        return []
    toml_lines = (tour.root / "tour.toml").read_text(encoding="utf-8").splitlines()
    spoken = {}
    if tour.draft.exists():
        spoken = {t.id: _plain(" ".join(t.paragraphs)) for t in load_tracks(tour.draft)}
    problems: list[Problem] = []
    offline: str | None = None if online else "not checked online"
    for sid, song in table.items():
        line = _line_of(toml_lines, sid)
        where = f"[stops.{sid}.song]"
        bad = field_problems(song)
        problems += [Problem(line, f"{where}: {msg}") for msg in bad]
        if bad:
            continue
        # The stop's script should name the song and the artist (docs/process/5-scripts.md).
        for f in ("title", "artist"):
            if sid in spoken and _plain(song[f]) not in spoken[sid]:
                problems.append(Problem(line, f"{where}: the {sid} script never names the {f} "
                                              f"({song[f]!r}); the song segment should", error=False))
        if offline is None:
            try:
                facts = lookup(song["spotify"], tour.root / "cache" / "spotify", fetch)
            except Offline as e:
                offline = str(e)
        if offline is not None:
            problems.append(Problem(line, f"{where}: link not verified, Spotify unreachable ({offline}); "
                                          "run check again online", error=False))
            continue
        problems += _compare(line, where, song, facts)
    return problems


def _compare(line: int, where: str, song: dict, facts: Facts | None) -> list[Problem]:
    if facts is None:
        return [Problem(line, f"{where}: Spotify has no track {song['spotify']}")]
    out = []
    match = same_title(song["title"], facts.title)
    if match == "different":
        out.append(Problem(line, f"{where}: the link is {facts.title!r} on Spotify, not {song['title']!r}"))
    elif match == "version":
        out.append(Problem(line, f"{where}: Spotify calls it {facts.title!r}; fine if that's the "
                                 "recording you mean", error=False))
    if facts.artist and _plain(song["artist"]) not in _plain(facts.artist) \
            and _plain(facts.artist) not in _plain(song["artist"]):
        out.append(Problem(line, f"{where}: Spotify credits {facts.artist!r}, not {song['artist']!r}; "
                                 "is it a cover?", error=False))
    if facts.seconds is None:
        out.append(Problem(line, f"{where}: couldn't read the length from Spotify's track page; "
                                 f"check length = {song['length']!r} by hand", error=False))
    elif abs(seconds(song["length"]) - facts.seconds) > LENGTH_SLACK:
        out.append(Problem(line, f"{where}: length = {song['length']!r}, but Spotify says "
                                 f"{mmss(facts.seconds)}; write length = \"{mmss(facts.seconds)}\""))
    return out


def _line_of(lines: list[str], sid: str) -> int:
    for pattern in (rf"^\s*\[stops\.{re.escape(sid)}\.song\]", rf"^\s*\[stops\.{re.escape(sid)}\]"):
        for n, text in enumerate(lines, 1):
            if re.match(pattern, text):
                return n
    return 0


def report(tour: config.Tour, online: bool = True) -> tuple[int, int]:
    """Print the song problems for ``tour check``; return (errors, warnings)."""
    problems = check(tour, online=online)
    path = config.show(tour.root / "tour.toml")
    for p in problems:
        where = f"{path}:{p.line}" if p.line else path
        print(f"{where}: {'error' if p.error else 'warning'}: {p.message}")
    errors = sum(p.error for p in problems)
    return errors, len(problems) - errors
