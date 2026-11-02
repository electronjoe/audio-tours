"""Paid rendering: narration chunks and sound effects, every call through ``spend.Guard``.

Narration uses the with-timestamps endpoint so each chunk comes back with
per-character timing. That gives paragraph start/end times, which the mixer
uses to place sound effects and to join chunks with natural gaps.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from . import audio, config, eleven
from .chunks import Chunk, Gap, context, plan_track
from .script import Track, check_file, load_tracks
from .spend import Guard, read_ledger, request_key

DEFAULT_MAX_CHUNK = 1500
DEFAULT_CONTEXT = 600


def find_track(tour: config.Tour, track_id: str) -> tuple[Track, int]:
    """The track and its 1-based position in the tour. Refuses a draft that fails the check."""
    errors = [p for p in check_file(tour.draft, tour.settings) if p.error]
    if errors:
        raise SystemExit(
            f"{tour.draft} has {len(errors)} script error(s); see `tour check {tour.slug}`"
        )
    tracks = load_tracks(tour.draft)
    for n, t in enumerate(tracks, 1):
        if t.id == track_id:
            if retired(tour, t):
                raise SystemExit(retired(tour, t)[0])
            return t, n
    raise SystemExit(f"No track {track_id}; known: {', '.join(t.id for t in tracks)}")


def retired(tour: config.Tour, track: Track) -> list[str]:
    """The pre-005 paragraph-number maps in tour.toml are gone; say what replaced them."""
    t = tour.settings.get("tracks", {}).get(track.id, {})
    out = []
    if "voices" in t:
        out.append(f"[tracks.{track.id}.voices] in tour.toml is retired: label the guest's paragraphs "
                   "('NAME: ...') and list NAME under '## Cast' (docs/script-format.md)")
    if "beds" in t:
        out.append(f"[[tracks.{track.id}.beds]] in tour.toml is retired: put '[SFX — name, under]' and "
                   "'[SFX — name, stop]' cues in the script (docs/script-format.md)")
    return out


def plan(tour: config.Tour, track: Track) -> list[Chunk | Gap]:
    render = tour.settings.get("render", {})
    return plan_track(
        track,
        tour.overrides.get("replace", []),
        render.get("max_chunk_chars", DEFAULT_MAX_CHUNK),
        render.get("announce_titles", True),
        render.get("title_label", True),
    )


def tts_request(tour: config.Tour, track_id: str, items: list, position: int) -> dict:
    s = tour.settings
    chunk = items[position]
    prev, nxt = context(items, position, s.get("render", {}).get("context_chars", DEFAULT_CONTEXT))
    request = {
        "kind": "tts-timestamps",
        "text": chunk.text,
        "voice_id": s["voices"][chunk.voice]["voice_id"],
        "model_id": s["narration"]["model_id"],
        "output_format": s["narration"]["output_format"],
        "previous_text": prev,
        "next_text": nxt,
    }
    if s["narration"].get("voice_settings"):
        request["voice_settings"] = s["narration"]["voice_settings"]
    take = tour.overrides.get("takes", {}).get(track_id, {}).get(chunk.name, 1)
    if take > 1:  # a retake is a new request, so it gets a new cache key
        request["take"] = take
    return request


def paragraph_times(chunk: Chunk, alignment: dict | None, length: float) -> list[list[float]]:
    """[start, end] seconds of each paragraph in the chunk's audio.

    Falls back to spreading time by character count if the alignment doesn't
    match the text we sent (it should, for the non-normalised alignment).
    """
    text = chunk.text
    spans = [(o, o + len(t)) for o, t in zip(chunk.offsets, chunk.texts)]
    if alignment and "".join(alignment["characters"]) == text:
        starts = alignment["character_start_times_seconds"]
        ends = alignment["character_end_times_seconds"]
        return [[round(starts[a], 3), round(ends[b - 1], 3)] for a, b in spans]
    print(f"  warning: {chunk.name} alignment doesn't match its text; estimating paragraph times")
    per_char = length / max(1, len(text))
    return [[round(a * per_char, 3), round(b * per_char, 3)] for a, b in spans]


def refine(times: list[list[float]], mp3: Path) -> tuple[list[list[float]], list[float], list[float]]:
    """Snap paragraph times to the audio's real silences.

    The alignment's separator characters absorb the pauses, so a paragraph's last
    character "ends" when the next one starts. The longest silence near each
    boundary is the actual paragraph break. Returns (times, speech bounds, gaps).
    """
    speech = list(audio.speech_bounds(mp3))
    quiet = audio.silences(mp3, min_seconds=0.15)
    times = [list(t) for t in times]
    gaps = []
    for k in range(len(times) - 1):
        lo, hi = times[k][1] - 1.0, times[k + 1][0] + 0.3
        near = [(b - a, a, b) for a, b in quiet if a < hi and b > lo]
        if near:
            _, a, b = max(near)
            times[k][1], times[k + 1][0] = round(a, 3), round(b, 3)
            gaps.append(round(b - a, 3))
    times[0][0], times[-1][1] = round(speech[0], 3), round(speech[1], 3)
    return times, [round(x, 3) for x in speech], gaps


def render_track(tour: config.Tour, track_id: str, guard: Guard, dry_run: bool) -> Path | None:
    track, number = find_track(tour, track_id)
    items = plan(tour, track)
    requests = {i: tts_request(tour, track.id, items, i) for i, x in enumerate(items) if isinstance(x, Chunk)}

    print(f"{track.id}: {track.label} — {track.title}")
    todo = 0
    for i, x in enumerate(items):
        if isinstance(x, Gap):
            print(f"  pause      {x.seconds:g} s (local silence)")
            continue
        cached = (guard.cache_dir / f"{request_key(requests[i])}.json").exists()
        todo += 0 if cached else len(x.text)
        where = "title" if x.index == 0 else f"paragraphs {x.paragraphs[0] + 1}-{x.paragraphs[-1] + 1}"
        take = requests[i].get("take", 1)
        print(f"  {x.name:<10} {x.voice:<9} {len(x.text):>5} chars  {where:<16} {'cached' if cached else 'to render'}"
              f"{f'  (take {take})' if take > 1 else ''}")
    print(f"  to send: {todo:,} chars (~{round(todo * 0.22):,} credits at the measured v4 rate)")
    if dry_run:
        return None

    if todo:
        guard.approve(f"render {track.id}", todo)
    guard.assume_yes = True  # the track was approved as a whole above
    out_dir = tour.build / track.id
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_items = []
    for i, x in enumerate(items):
        if isinstance(x, Gap):
            manifest_items.append({"kind": "pause", "seconds": x.seconds})
            continue
        req = requests[i]
        call = lambda req=req: _call_tts(req)
        path, _ = guard.run(f"{track.id} {x.name}", req, len(x.text), call, suffix=".json")
        result = json.loads(path.read_text())
        mp3 = out_dir / f"{x.name}.mp3"
        mp3.write_bytes(base64.b64decode(result["audio_base64"]))
        length = audio.duration(mp3)
        times, speech, gaps = refine(paragraph_times(x, result.get("alignment"), length), mp3)
        manifest_items.append({
            "kind": "speech",
            "name": x.name,
            "voice": x.voice,
            "file": mp3.name,
            "duration": round(length, 3),
            "paragraphs": x.paragraphs,
            "times": times,
            "speech": speech,
            "gaps": gaps,
            "chars": len(x.text),
            "request_id": _request_id(tour, req),
        })
    manifest = {
        "track": track.id,
        "number": number,
        "label": track.label,
        "title": track.title,
        "items": manifest_items,
    }
    path = _manifest(tour, track.id)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"  -> {path.relative_to(config.REPO_ROOT)}")
    return path


def _call_tts(req: dict) -> tuple[bytes, dict]:
    result, meta = eleven.tts_with_timestamps(
        req["text"], req["voice_id"], req["model_id"],
        previous_text=req["previous_text"], next_text=req["next_text"],
        voice_settings=req.get("voice_settings"), output_format=req["output_format"],
    )
    return json.dumps(result).encode(), meta


def _request_id(tour: config.Tour, request: dict) -> str | None:
    """The API request-id for a cached request, from the ledger (for stitching later)."""
    key = request_key(request)
    for e in reversed(read_ledger(tour)):
        if e["key"] == key:
            return e.get("meta", {}).get("request-id")
    return None


def _manifest(tour: config.Tour, track_id: str) -> Path:
    return tour.build / track_id / "manifest.json"


# --- Sound effects --------------------------------------------------------------


def sfx_requests(tour: config.Tour, names: list[str]) -> list[tuple[str, int, dict]]:
    defs = tour.settings.get("sfx", {})
    unknown = [n for n in names if n not in defs]
    if unknown:
        raise SystemExit(f"No [sfx.{unknown[0]}] in tour.toml; known: {', '.join(defs)}")
    out = []
    for name in names or list(defs):
        d = defs[name]
        for variant in range(1, d.get("variants", 1) + 1):
            out.append((name, variant, {
                "kind": "sfx",
                "text": d["prompt"],
                "model_id": d.get("model_id", "eleven_text_to_sound_v2"),
                "duration_seconds": d.get("duration"),
                "loop": d.get("loop", False),
                "prompt_influence": d.get("prompt_influence"),
                "variant": variant,  # not sent; makes each variant its own cache entry
            }))
    return out


def generate_sfx(tour: config.Tour, names: list[str], guard: Guard, max_seconds: float) -> None:
    requests = sfx_requests(tour, names)
    todo = [(n, v, r) for n, v, r in requests if not (guard.cache_dir / f"{request_key(r)}.mp3").exists()]
    seconds = sum(r["duration_seconds"] or 0 for _, _, r in todo)
    for name, variant, r in requests:
        state = "to render" if (name, variant, r) in todo else "cached"
        print(f"  {name}-{variant:<3} {r['duration_seconds'] or 'auto':>5} s  loop={r['loop']!s:<5} {state}")
    if todo:
        print(f"  to generate: {len(todo)} clips, {seconds:g} s"
              f" (~{round(seconds * 5.5):,} credits at the measured 5.5/s)")
        if seconds > max_seconds:
            raise SystemExit(f"{seconds:g} s exceeds --max-seconds {max_seconds:g}; refusing.")
        guard.approve("sound effects", sum(len(r["text"]) for _, _, r in todo))
        guard.assume_yes = True
    out_dir = tour.sfx_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, variant, r in requests:
        call = lambda r=r: eleven.sound_effect(
            r["text"], r["model_id"], r["duration_seconds"], r["loop"], r["prompt_influence"]
        )
        path, _ = guard.run(f"sfx {name}-{variant}", r, len(r["text"]), call)
        out = out_dir / f"{name}-{variant}.mp3"
        shutil.copyfile(path, out)
        print(f"  -> {out.relative_to(config.REPO_ROOT)}  ({audio.duration(out):.1f} s)")
