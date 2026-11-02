"""Offline mixing and mastering of a rendered track into one finished MP3.

Timeline: head silence, the chapter sting, the spoken title, then the speech.
Each chunk is trimmed to its speech (from the TTS timestamps). Chunks of the
same speaker are joined with the narrator's own median paragraph gap, so a chunk
join sounds like any other paragraph break; a change of speaker gets the
shorter ``speaker_gap``. Pauses become exact silence.

Sound cues come from the script (``[SFX — name]``, ``[SFX — name, under]``,
``[SFX — name, stop]``). A one-shot lengthens the gap it sits in by its own
length plus ``sfx_gap`` either side; a cue between two paragraphs of one chunk
cuts the chunk at the paragraph break, so no re-render is needed. A bed fades
in before the speech after its ``under`` cue and out after the speech before
its ``stop``, at ``level_db`` relative to the voice in the gaps, and is ducked
a further ``duck_db`` under speech by a sidechain compressor keyed on the voice.
Then the whole mix is loudness-normalised (two-pass loudnorm) and encoded with
ID3 tags.
"""

from __future__ import annotations

import itertools
import json
import re
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import audio, config
from .chunks import Chunk
from .render import find_track, plan
from .script import Cue, Pause, Text, load_tracks

LEAD = 0.15  # seconds kept before the first spoken character of a chunk
TAIL = 0.5  # seconds kept after the last one (breath and decay)
FORMAT = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
SPEAKER_GAP = 0.35  # speech to speech at a change of speaker
SFX_GAP = 0.5  # speech to a one-shot, and the one-shot to the next speech
SFX_LEVEL_DB = -9.0  # an effect's level relative to the voice (a bed's, in the gaps)
DUCK_DB = -9.0  # a bed's extra reduction under speech
DUCK_RATIO = 4  # sidechain compressor ratio; the threshold is set from duck_db
BED_FADE_IN, BED_FADE_OUT = 1.5, 3.0


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

    def add_ducked(self, path: Path, chain: str, key: Path, compressor: str, loop: bool = False) -> None:
        """``path`` through ``chain``, then pushed down by a sidechain keyed on ``key``."""
        n = len(self.inputs)
        self.inputs.append((["-stream_loop", "-1"] if loop else []) + ["-i", str(path)])
        self.inputs.append(["-i", str(key)])
        self.chains += [f"[{n}:a]{chain}[b{n}]", f"[{n + 1}:a]{FORMAT}[k{n}]",
                        f"[b{n}][k{n}]{compressor}[a{n}]"]
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


def sfx_file(tour: config.Tour, name: str, variant: int | None = None) -> Path:
    d = tour.settings["sfx"][name]
    path = tour.sfx_dir / f"{name}-{variant or d.get('chosen', 1)}.mp3"
    if not path.exists():
        raise SystemExit(f"Missing {config.show(path)}; run `tour sfx {tour.slug} {name}`")
    return path


def compressor(voice_lufs: float, duck_db: float) -> str:
    """A sidechain compressor that takes about ``duck_db`` off the bed while the voice speaks.

    Above the threshold the gain falls by (level - threshold) * (1 - 1/ratio), so putting
    the threshold |duck_db| / (1 - 1/ratio) below the voice's loudness gives about
    ``duck_db`` at speaking level. Attack and release are the lab 005 reference's.
    """
    threshold = voice_lufs + duck_db / (1 - 1 / DUCK_RATIO)
    return (f"sidechaincompress=threshold={10 ** (threshold / 20):.5f}:ratio={DUCK_RATIO}"
            ":attack=30:release=450:makeup=1")


def check_manifest(tour: config.Tour, track, items: list[dict]) -> None:
    """The render must match the script as it is now, or the cues land in the wrong place."""
    have = [(it["name"], it["paragraphs"], it["voice"], it["chars"]) for it in items if it["kind"] == "speech"]
    want = [(c.name, c.paragraphs, c.voice, len(c.text)) for c in plan(tour, track) if isinstance(c, Chunk)]
    if have != want:
        raise SystemExit(f"{config.show(tour.build / track.id)}/manifest.json is older than the "
                         f"script; run `tour render {tour.slug} {track.id}` again (cached chunks cost nothing)")


@dataclass
class Piece:
    """A stretch of one chunk's audio, from paragraph ``lo`` to ``hi`` (indexes into the chunk)."""

    item: dict
    lo: int
    hi: int


def master_track(tour: config.Tour, track_id: str) -> Path:
    track, number = find_track(tour, track_id)
    work = tour.build / track.id
    manifest_path = work / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No render for {track.id}; run `tour render {tour.slug} {track.id}` first")
    manifest = json.loads(manifest_path.read_text())
    m = tour.settings.get("master", {})
    sfx_defs = tour.settings.get("sfx", {})
    cues = tour.settings.get("tracks", {}).get(track.id, {})
    items = manifest["items"]
    check_manifest(tour, track, items)
    gap = paragraph_gap(items)
    speaker_gap = m.get("speaker_gap", SPEAKER_GAP)
    sfx_gap = m.get("sfx_gap", SFX_GAP)

    # --- timeline -------------------------------------------------------------
    t = m.get("head_seconds", 0.5)
    sting = None
    if m.get("sting") and cues.get("sting", True):
        sting_path = sfx_file(tour, m["sting"])
        sting = (sting_path, t)
        t += audio.duration(sting_path) + m.get("sting_gap", 0.6)

    voice: list[tuple[Path, float, float, float]] = []  # file, trim start, trim end, place
    paragraphs: dict[int, list[float]] = {}  # 0-based paragraph -> absolute [start, end]
    shots: list[tuple[str, float]] = []  # one-shot sfx name, start
    beds: list[tuple[Cue, int]] = []  # under/stop cue, the paragraph after it
    timeline: list[dict] = []
    where = {p: (it, k) for it in items if it["kind"] == "speech" for k, p in enumerate(it["paragraphs"])}
    state = {"end": None, "voice": None}  # last speech end (absolute) and its voice

    def place(piece: Piece, pending: list) -> None:
        it, lo, hi = piece.item, piece.lo, piece.hi
        times = it["times"] if it["paragraphs"] else [it["speech"]]
        s0, s1 = times[lo][0], times[hi][1]
        trim0 = max(0.0, s0 - LEAD) if lo == 0 else max(s0 - LEAD, times[lo - 1][1])
        trim1 = min(it["duration"], s1 + TAIL) if hi == len(times) - 1 else min(s1 + TAIL, times[hi + 1][0])
        at = t if state["end"] is None else state["end"]
        if pending:  # pauses and one-shots, in script order, make the gap
            for kind, value in pending:
                if kind == "pause":
                    at += value
                else:
                    at += sfx_gap
                    shots.append((value, at))
                    at += audio.duration(sfx_file(tour, value)) + sfx_gap
        elif state["end"] is not None:
            at += speaker_gap if it["voice"] != state["voice"] else gap
        offset = at - s0  # file time -> timeline
        voice.append((work / it["file"], trim0, trim1, offset + trim0))
        for p, (a, b) in zip(it["paragraphs"][lo:hi + 1], times[lo:hi + 1]):
            paragraphs[p] = [offset + a, offset + b]
        name = it["name"] if (lo, hi) == (0, len(times) - 1) else f"{it['name']} ¶{it['paragraphs'][lo] + 1}-{it['paragraphs'][hi] + 1}"
        timeline.append({"part": name, "voice": it["voice"], "speech": [round(at, 2), round(offset + s1, 2)]})
        state["end"], state["voice"] = offset + s1, it["voice"]

    pending: list[tuple[str, float | str]] = []
    title = next((it for it in items if it["kind"] == "speech" and it["name"] == "title"), None)
    if title:
        place(Piece(title, 0, 0), [])
        pending.append(("pause", m.get("title_gap", 1.2)))
    current: Piece | None = None
    held: list[tuple[str, float | str]] = []  # what comes before ``current``
    para = 0
    for seg in track.segments:
        if isinstance(seg, Text):
            it, k = where[para]
            if current and current.item is it and k == current.hi + 1 and not pending:
                current.hi = k
            else:
                if current:
                    place(current, held)
                current, held, pending = Piece(it, k, k), pending, []
            para += 1
        elif isinstance(seg, Pause):
            pending.append(("pause", seg.seconds))
            timeline.append({"pause": seg.seconds, "after_paragraph": para})
        elif seg.mode == "once":
            pending.append(("sfx", seg.sfx))
        else:
            beds.append((seg, para))
    if current:
        place(current, held)
    end = state["end"]
    for kind, value in pending:  # pauses and one-shots after the last speech still play
        if kind == "pause":
            end += value
        else:
            shots.append((value, end + sfx_gap))
            end += sfx_gap + audio.duration(sfx_file(tour, value))
    total = end + m.get("tail_seconds", 2.5)

    # beds: (sfx, start, fade-out start)
    spans: list[tuple[str, float, float]] = []
    running: dict[str, float] = {}
    for cue, p in beds:
        if cue.mode == "under":
            fade_in = sfx_defs[cue.sfx].get("fade_in", BED_FADE_IN)
            running[cue.sfx] = paragraphs[p][0] - fade_in if p in paragraphs else end
        elif cue.sfx in running:
            start = running.pop(cue.sfx)
            spans.append((cue.sfx, start, max(start, paragraphs[p - 1][1]) if p else start))
    spans += [(name, start, state["end"]) for name, start in running.items()]  # still running at the end
    for name, start, fade_at in spans:
        total = max(total, fade_at + sfx_defs[name].get("fade_out", BED_FADE_OUT))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- narration loudness, so effects sit at a level relative to it ----
        g = Graph()
        for path, a, b, at in voice:
            g.add(path, f"atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{FORMAT},{delay(at)}")
        voice_wav = tmp / "voice.wav"
        audio.run(["ffmpeg", "-hide_banner", "-y"] + g.args(total) + ["-c:a", "pcm_f32le", str(voice_wav)])
        voice_lufs = audio.loudness(voice_wav)

        # --- full mix ------------------------------------------------------------
        if sting:
            path, at = sting
            gain = voice_lufs + m.get("sting_level_db", -8) - audio.loudness(path)
            g.add(path, f"{FORMAT},volume={gain:.2f}dB,{delay(at)}")
            timeline.insert(0, {"sfx": path.name, "at": round(at, 2), "gain_db": round(gain, 1)})
        for name, at in shots:
            path = sfx_file(tour, name)
            gain = voice_lufs + sfx_defs[name].get("level_db", SFX_LEVEL_DB) - audio.loudness(path)
            g.add(path, f"{FORMAT},volume={gain:.2f}dB,{delay(at)}")
            timeline.append({"sfx": path.name, "at": round(at, 2), "gain_db": round(gain, 1)})
        reports = []
        for name, start, fade_at in spans:
            d = sfx_defs[name]
            path = sfx_file(tour, name)
            fade_out = d.get("fade_out", BED_FADE_OUT)
            span = fade_at + fade_out - start
            fade_in = min(d.get("fade_in", BED_FADE_IN), span)
            gain = voice_lufs + d.get("level_db", SFX_LEVEL_DB) - audio.loudness(path)
            loop = d.get("loop", False)
            chain = (
                f"{'' if loop else 'apad,'}atrim=duration={span:.3f},asetpts=PTS-STARTPTS,{FORMAT},"
                f"afade=t=in:d={fade_in:.3f},afade=t=out:st={span - fade_out:.3f}:d={fade_out:.3f},"
                f"volume={gain:.2f}dB,{delay(start)},apad=whole_dur={total:.3f},atrim=duration={total:.3f}"
            )
            duck = compressor(voice_lufs, d.get("duck_db", DUCK_DB))
            g.add_ducked(path, chain, voice_wav, duck, loop=loop)  # a loop repeats to fill the span
            stem = Graph()
            stem.add_ducked(path, chain, voice_wav, duck, loop=loop)
            stem_wav = tmp / f"bed-{len(reports)}.wav"
            audio.run(["ffmpeg", "-hide_banner", "-y"] + stem.args(total) + ["-c:a", "pcm_f32le", str(stem_wav)])
            levels = bed_levels(stem_wav, voice, start + fade_in, fade_at)
            reports.append(f"{name} {levels[0] - voice_lufs:+.1f} dB under speech, {levels[1] - voice_lufs:+.1f} dB in gaps")
            timeline.append({"sfx": path.name, "from": round(start, 2), "fade_out_at": round(fade_at, 2),
                             "to": round(fade_at + fade_out, 2), "gain_db": round(gain, 1),
                             "under_speech_db": round(levels[0] - voice_lufs, 1),
                             "in_gaps_db": round(levels[1] - voice_lufs, 1)})
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
        out = tour.build / f"{track.id}.mp3"
        info = tour.info
        tags = {
            "title": f"{track.label}: {track.title}",
            "track": f"{number}/{len(load_tracks(tour.draft))}",
            "album": info.get("title", tour.slug),
            "artist": info.get("artist", ""),
            "album_artist": info.get("artist", ""),
            "genre": "Audio tour",
            "date": str(info.get("year", "")),
        }
        meta = [a for k, v in tags.items() if v for a in ("-metadata", f"{k}={v}")]
        audio.run(["ffmpeg", "-hide_banner", "-y", "-i", str(mix_wav), "-af", loudnorm,
                   "-c:a", "libmp3lame", "-b:a", m.get("bitrate", "192k"), "-id3v2_version", "3",
                   *meta, str(out)])

    (work / "timeline.json").write_text(json.dumps({
        "voice_lufs_premaster": voice_lufs,
        "paragraph_gap": round(gap, 3),
        "speaker_gap": speaker_gap,
        "paragraphs": {p + 1: [round(a, 2), round(b, 2)] for p, (a, b) in sorted(paragraphs.items())},
        "events": timeline,
    }, indent=2, ensure_ascii=False) + "\n")
    final = audio.loudness(out)
    print(f"{track.id}: {audio.duration(out) / 60:.1f} min, {final:.1f} LUFS, paragraph gap {gap:.2f} s")
    for r in reports:
        print(f"  bed {r}")
    print(f"  -> {config.show(out)}")
    return out


def bed_levels(stem: Path, voice: list[tuple[Path, float, float, float]], lo: float, hi: float) -> tuple[float, float]:
    """A bed's mean RMS level (dBFS) under speech and in the gaps, while it is fully up."""
    def rms(a: float, b: float) -> float | None:
        if b - a < 0.3:
            return None
        out = audio.run(["ffmpeg", "-hide_banner", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(stem),
                         "-af", "astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"])
        found = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", out)
        return float(found[-1]) if found and found[-1] != "-inf" else None

    spans = sorted((at + LEAD, at + b - a - TAIL) for _, a, b, at in voice)
    inside = [rms(max(a, lo) + 0.3, min(b, hi)) for a, b in spans if b > lo and a < hi]
    gaps = [rms(b1 + 0.1, a2) for (_, b1), (a2, _) in itertools.pairwise(spans) if lo < b1 and a2 < hi]
    def avg(xs: list[float | None]) -> float:
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else float("nan")

    return avg(inside), avg(gaps)


def chapters_metadata(title: str, chapters: list[tuple[str, float]]) -> str:
    """An ffmetadata file: the tour title and one chapter per (title, duration) in order."""
    def esc(s: str) -> str:
        return "".join("\\" + c if c in "=;#\\\n" else c for c in s)

    lines = [";FFMETADATA1", f"title={esc(title)}"]
    t = 0.0
    for name, length in chapters:
        start, t = t, t + length
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(start * 1000)}",
                  f"END={round(t * 1000)}", f"title={esc(name)}"]
    return "\n".join(lines) + "\n"


def combine_tour(tour: config.Tour) -> Path:
    """Join every mastered track, in tour order, into one MP3 with chapter markers.

    The tracks are already mastered to the same loudness and format, so they are
    stream-copied (no second encode). Each track's own head and tail silence
    makes the gap between chapters.
    """
    tracks = load_tracks(tour.draft)
    files = [tour.build / f"{t.id}.mp3" for t in tracks]
    missing = [t.id for t, f in zip(tracks, files) if not f.exists()]
    if missing:
        raise SystemExit(f"Not mastered yet: {', '.join(missing)}; run `tour master {tour.slug} <track>`")
    info = tour.info
    title = info.get("title", tour.slug)
    chapters = [(f"{t.label}: {t.title}", audio.duration(f)) for t, f in zip(tracks, files)]
    out = tour.build / f"{tour.slug}-complete.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "list.txt").write_text("".join(f"file '{f}'\n" for f in files))
        (tmp / "meta.txt").write_text(chapters_metadata(title, chapters))
        tags = {"album": title, "artist": info.get("artist", ""), "album_artist": info.get("artist", ""),
                "genre": "Audio tour", "date": str(info.get("year", "")), "track": "1/1"}
        meta = [a for k, v in tags.items() if v for a in ("-metadata", f"{k}={v}")]
        audio.run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                   "-i", str(tmp / "meta.txt"), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                   "-c", "copy", "-id3v2_version", "3", *meta, str(out)])
    total = audio.duration(out)
    print(f"{tour.slug}: {len(files)} tracks, {total / 60:.1f} min, {len(chapters)} chapter markers")
    print(f"  -> {out.relative_to(config.REPO_ROOT)}")
    return out
