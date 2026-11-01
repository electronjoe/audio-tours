"""Offline mixing and mastering of a rendered track into one finished MP3.

Timeline: head silence, the chapter sting, the spoken title, then the narration
chunks. Each chunk is trimmed to its speech (from the TTS timestamps) and
chunks are joined with the narrator's own median paragraph gap, so a chunk
join sounds like any other paragraph break. Pauses become exact silence.

Sound-effect beds are placed on paragraphs (``[[tracks.<id>.beds]]`` in
tour.toml) at a level relative to the narration's loudness, then the whole mix
is loudness-normalised (two-pass loudnorm) and encoded with ID3 tags.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import audio, config
from .render import find_track
from .script import load_tracks

LEAD = 0.15  # seconds kept before the first spoken character of a chunk
TAIL = 0.5  # seconds kept after the last one (breath and decay)
FORMAT = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"


@dataclass
class Graph:
    """Inputs and filter chains for one ffmpeg -filter_complex call."""

    inputs: list[list[str]] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    outs: list[str] = field(default_factory=list)

    def add(self, path: Path, chain: str, loop: bool = False) -> None:
        n = len(self.inputs)
        self.inputs.append((["-stream_loop", "-1"] if loop else []) + ["-i", str(path)])
        self.chains.append(f"[{n}:a]{chain}[a{n}]")
        self.outs.append(f"[a{n}]")

    def args(self, total: float) -> list[str]:
        mix = (
            f"{''.join(self.outs)}amix=inputs={len(self.outs)}:normalize=0:dropout_transition=0,"
            f"apad=whole_dur={total:.3f},atrim=duration={total:.3f}[out]"
        )
        flat = [a for i in self.inputs for a in i]
        return flat + ["-filter_complex", ";".join(self.chains + [mix]), "-map", "[out]"]


def delay(seconds: float) -> str:
    return f"adelay={round(seconds * 1000)}:all=1"


def paragraph_gap(items: list[dict]) -> float:
    """The narrator's median pause between paragraphs inside a chunk."""
    gaps = [g for it in items if it["kind"] == "speech" for g in it["gaps"]]
    return min(1.5, max(0.4, statistics.median(gaps))) if gaps else 0.8


def sfx_file(book: config.Book, name: str, variant: int | None = None) -> Path:
    d = book.settings["sfx"][name]
    path = book.build / "sfx" / f"{name}-{variant or d.get('chosen', 1)}.mp3"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(config.REPO_ROOT)}; run `tour sfx {book.slug} {name}`")
    return path


def master_track(book: config.Book, track_id: str) -> Path:
    track, number = find_track(book, track_id)
    work = book.build / track.id
    manifest_path = work / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No render for {track.id}; run `tour render {book.slug} {track.id}` first")
    manifest = json.loads(manifest_path.read_text())
    m = book.settings.get("master", {})
    cues = book.settings.get("tracks", {}).get(track.id, {})
    items = manifest["items"]
    gap = paragraph_gap(items)

    # --- timeline -------------------------------------------------------------
    t = m.get("head_seconds", 0.5)
    sting = None
    if m.get("sting") and cues.get("sting", True):
        sting_path = sfx_file(book, m["sting"])
        sting = (sting_path, t)
        t += audio.duration(sting_path) + m.get("sting_gap", 0.6)

    voice: list[tuple[Path, float, float, float]] = []  # file, trim start, trim end, place
    paragraphs: dict[int, list[float]] = {}  # 0-based paragraph -> absolute [start, end]
    next_speech = t
    pending_gap = 0.0
    timeline = []
    for it in items:
        if it["kind"] == "pause":
            pending_gap += it["seconds"]
            timeline.append({"pause": it["seconds"], "at": round(next_speech, 2)})
            continue
        if voice:  # previous speech end + gap
            next_speech += pending_gap or gap
        pending_gap = 0.0
        s0, s1 = it["speech"]
        trim0, trim1 = max(0.0, s0 - LEAD), min(it["duration"], s1 + TAIL)
        place = next_speech - (s0 - trim0)
        voice.append((work / it["file"], trim0, trim1, place))
        for p, (a, b) in zip(it["paragraphs"], it["times"]):
            paragraphs[p] = [place + a - trim0, place + b - trim0]
        timeline.append({"part": it["name"], "speech": [round(next_speech, 2), round(place + s1 - trim0, 2)]})
        next_speech = place + s1 - trim0
        if it["name"] == "title":
            pending_gap = m.get("title_gap", 1.2)
    total = next_speech + m.get("tail_seconds", 2.5)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- narration loudness, so effects sit at a level relative to it ----
        g = Graph()
        for path, a, b, place in voice:
            g.add(path, f"atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{FORMAT},{delay(place)}")
        voice_wav = tmp / "voice.wav"
        audio.run(["ffmpeg", "-hide_banner", "-y"] + g.args(total) + ["-c:a", "pcm_f32le", str(voice_wav)])
        voice_lufs = audio.loudness(voice_wav)

        # --- full mix ------------------------------------------------------------
        if sting:
            path, at = sting
            gain = voice_lufs + m.get("sting_level_db", -8) - audio.loudness(path)
            g.add(path, f"{FORMAT},volume={gain:.2f}dB,{delay(at)}")
            timeline.insert(0, {"sfx": path.name, "at": round(at, 2), "gain_db": round(gain, 1)})
        for bed in cues.get("beds", []):
            path = sfx_file(book, bed["sfx"], bed.get("variant"))
            start = paragraphs[bed["from_paragraph"] - 1][0] + bed.get("start_offset", 0.0)
            end = paragraphs[bed["to_paragraph"] - 1][1] + bed.get("end_offset", 0.5)
            span = end - start
            fade_in, fade_out = bed.get("fade_in", 1.5), min(bed.get("fade_out", 3.0), span)
            gain = voice_lufs + bed["level_db"] - audio.loudness(path)
            loop = book.settings["sfx"][bed["sfx"]].get("loop", False)
            chain = (
                f"{'' if loop else 'apad,'}atrim=duration={span:.3f},asetpts=PTS-STARTPTS,{FORMAT},"
                f"afade=t=in:d={fade_in},afade=t=out:st={span - fade_out:.3f}:d={fade_out},"
                f"volume={gain:.2f}dB,{delay(start)}"
            )
            g.add(path, chain, loop=loop)  # a loop repeats to fill the span; a one-shot pads with silence
            timeline.append({"sfx": path.name, "from": round(start, 2), "to": round(end, 2), "gain_db": round(gain, 1)})
        mix_wav = tmp / "mix.wav"
        audio.run(["ffmpeg", "-hide_banner", "-y"] + g.args(total) + ["-c:a", "pcm_f32le", str(mix_wav)])

        # --- two-pass loudness normalisation and MP3 export ----------------------
        target = f"I={m.get('target_lufs', -16)}:TP={m.get('true_peak', -1.5)}:LRA=11"
        report = audio.run(["ffmpeg", "-hide_banner", "-i", str(mix_wav), "-af",
                            f"loudnorm={target}:print_format=json", "-f", "null", "-"])
        measured = json.loads(report[report.rfind("{"):report.rfind("}") + 1])
        loudnorm = (
            f"loudnorm={target}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true,aresample=44100"
        )
        out = book.build / f"{track.id}.mp3"
        info = book.settings.get("book", {})
        tags = {
            "title": f"{track.label}: {track.title}",
            "track": f"{number}/{len(load_tracks(book.draft))}",
            "album": info.get("title", book.slug),
            "artist": info.get("artist", ""),
            "album_artist": info.get("artist", ""),
            "genre": "Audiobook",
            "date": str(info.get("year", "")),
        }
        meta = [a for k, v in tags.items() if v for a in ("-metadata", f"{k}={v}")]
        audio.run(["ffmpeg", "-hide_banner", "-y", "-i", str(mix_wav), "-af", loudnorm,
                   "-c:a", "libmp3lame", "-b:a", m.get("bitrate", "192k"), "-id3v2_version", "3",
                   *meta, str(out)])

    (work / "timeline.json").write_text(json.dumps({
        "voice_lufs_premaster": voice_lufs,
        "paragraph_gap": round(gap, 3),
        "paragraphs": {p + 1: [round(a, 2), round(b, 2)] for p, (a, b) in sorted(paragraphs.items())},
        "events": timeline,
    }, indent=2) + "\n")
    final = audio.loudness(out)
    print(f"{track.id}: {audio.duration(out) / 60:.1f} min, {final:.1f} LUFS, paragraph gap {gap:.2f} s")
    print(f"  -> {out.relative_to(config.REPO_ROOT)}")
    return out


def chapters_metadata(title: str, chapters: list[tuple[str, float]]) -> str:
    """An ffmetadata file: the book title and one chapter per (title, duration) in order."""
    def esc(s: str) -> str:
        return "".join("\\" + c if c in "=;#\\\n" else c for c in s)

    lines = [";FFMETADATA1", f"title={esc(title)}"]
    t = 0.0
    for name, length in chapters:
        start, t = t, t + length
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(start * 1000)}",
                  f"END={round(t * 1000)}", f"title={esc(name)}"]
    return "\n".join(lines) + "\n"


def combine_book(book: config.Book) -> Path:
    """Join every mastered track, in book order, into one MP3 with chapter markers.

    The tracks are already mastered to the same loudness and format, so they are
    stream-copied (no second encode). Each track's own head and tail silence
    makes the gap between chapters.
    """
    tracks = load_tracks(book.draft)
    files = [book.build / f"{t.id}.mp3" for t in tracks]
    missing = [t.id for t, f in zip(tracks, files) if not f.exists()]
    if missing:
        raise SystemExit(f"Not mastered yet: {', '.join(missing)}; run `tour master {book.slug} <track>`")
    info = book.settings.get("book", {})
    title = info.get("title", book.slug)
    chapters = [(f"{t.label}: {t.title}", audio.duration(f)) for t, f in zip(tracks, files)]
    out = book.build / f"{book.slug}-complete.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "list.txt").write_text("".join(f"file '{f}'\n" for f in files))
        (tmp / "meta.txt").write_text(chapters_metadata(title, chapters))
        tags = {"album": title, "artist": info.get("artist", ""), "album_artist": info.get("artist", ""),
                "genre": "Audiobook", "date": str(info.get("year", "")), "track": "1/1"}
        meta = [a for k, v in tags.items() if v for a in ("-metadata", f"{k}={v}")]
        audio.run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                   "-i", str(tmp / "meta.txt"), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                   "-c", "copy", "-id3v2_version", "3", *meta, str(out)])
    total = audio.duration(out)
    print(f"{book.slug}: {len(files)} tracks, {total / 60:.1f} min, {len(chapters)} chapter markers")
    print(f"  -> {out.relative_to(config.REPO_ROOT)}")
    return out
