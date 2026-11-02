"""EXPERIMENTAL lab for task 005: one guest-voice excerpt rendered two ways.

    uv run python lab/voices_005.py sfx            # PAID: river bed + splash (one take each)
    uv run python lab/voices_005.py design         # PAID: Voice Design for the platypus, saves preview 1
    uv run python lab/voices_005.py a              # PAID: method A, one TTS request per speaker turn
    uv run python lab/voices_005.py b [--model M]  # PAID: method B, one text-to-dialogue request
    uv run python lab/voices_005.py master a|b     # offline: mix and master into build/lab-005/

Reads lab/005-excerpt.md (the syntax proposed in task 005). Every paid call goes through
spend.Guard with the hobart book, so the cache and ledger are the tour's own. Throwaway code:
the real feature belongs in script.py / render.py / master.py.

Findings baked in (2026-11-02): `design` can't save while the account is at its custom-voice
limit (3/3), and an unsaved preview id is a 404 for TTS, so the test fell back to the premade
Charlie, recorded in build/lab-005/platypus-voice.json. eleven_v4 works with text-to-dialogue.
"""

from __future__ import annotations

import base64
import itertools
import json
import re
import sys
import tempfile
from pathlib import Path

from audiotour import audio, config, eleven
from audiotour.spend import Guard

BOOK = config.book("hobart")
EXCERPT = Path(__file__).with_name("005-excerpt.md")
OUT = BOOK.build / "lab-005"
MODEL = "eleven_v4"
FORMAT = "mp3_44100_128"
CONTEXT = 600
VOICES = {"narrator": "ShIjYUEv1pABubDlTWxD"}  # platypus is added by `design` (voice.json)
VOICE_FILE = OUT / "platypus-voice.json"

DESIGN = {
    "name": "lab-005-platypus",
    "description": (
        "A cheerful, quick, slightly cheeky young platypus character in a children's nature "
        "audio tour. Young adult voice, light natural Australian accent, bright and higher "
        "pitched, fast and playful, clear diction. Not a caricature."
    ),
    "text": "A minute? I'm on my dinner break. Make it quick. No zapping! I just listen. "
            "It's like a secret message that says: dinner, this way.",
}
SFX = {  # same request shape as render.sfx_requests, so tour.toml can adopt them cached
    "river": {"prompt": "Gentle shallow river flowing over stones in quiet Tasmanian forest, "
                        "soft distant birds, steady, no music, no voices", "duration": 15, "loop": True},
    "splash": {"prompt": "A small animal slipping into calm river water, one soft splash, close, "
                         "no music, no voices", "duration": 2, "loop": False},
}

CUE = re.compile(r"^\[SFX\s*—\s*(?P<name>[a-z0-9-]+)(?:,\s*(?P<mode>under|stop))?\]$")
PAUSE = re.compile(r"^\[PAUSE\s*—\s*(?P<s>[\d.]+)\s+SECONDS\]$")
LABEL = re.compile(r"^(?P<name>[A-Z][A-Z ]+):\s+(?P<text>.+)$", re.DOTALL)


def parse() -> list[tuple]:
    """('say', voice, text) | ('sfx', name, 'once'|'under'|'stop') | ('pause', seconds)."""
    body = EXCERPT.read_text().split("## Script:", 1)[1].split("\n## ", 1)[0].split("\n", 1)[1]
    out = []
    for para in (" ".join(p.split()) for p in body.split("\n\n") if p.strip()):
        if m := CUE.match(para):
            out.append(("sfx", m["name"], m["mode"] or "once"))
        elif m := PAUSE.match(para):
            out.append(("pause", float(m["s"])))
        elif m := LABEL.match(para):
            out.append(("say", m["name"].lower(), m["text"]))
        else:
            out.append(("say", "narrator", para))
    return out


def voices() -> dict[str, str]:
    v = dict(VOICES)
    if VOICE_FILE.exists():
        v["platypus"] = json.loads(VOICE_FILE.read_text())["voice_id"]
    return v


def guard() -> Guard:
    return Guard(BOOK, max_chars=2000, assume_yes=True)  # approved for this test by the user


# --- paid steps -----------------------------------------------------------------


def cmd_sfx() -> None:
    (OUT / "sfx").mkdir(parents=True, exist_ok=True)
    for name, d in SFX.items():
        req = {"kind": "sfx", "text": d["prompt"], "model_id": "eleven_text_to_sound_v2",
               "duration_seconds": d["duration"], "loop": d["loop"], "prompt_influence": None,
               "variant": 1}
        path, _ = guard().run(f"lab-005 sfx {name}", req, len(d["prompt"]), lambda d=d: eleven.sound_effect(
            d["prompt"], duration_seconds=d["duration"], loop=d["loop"]))
        (OUT / "sfx" / f"{name}.mp3").write_bytes(path.read_bytes())


def cmd_design() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    req = {"kind": "design", "description": DESIGN["description"], "text": DESIGN["text"],
           "model_id": "eleven_ttv_v3", "seed": None}

    def call() -> tuple[bytes, dict]:
        result, meta = eleven.design_voice(DESIGN["description"], DESIGN["text"])
        return json.dumps(result).encode(), meta

    path, _ = guard().run(f"lab-005 {DESIGN['name']}", req, len(DESIGN["text"]), call, suffix=".json")
    previews = json.loads(path.read_text())["previews"]
    for i, p in enumerate(previews, 1):
        (OUT / f"platypus-design-{i}.mp3").write_bytes(base64.b64decode(p["audio_base_64"]))
    if not VOICE_FILE.exists():  # take preview 1, as agreed (saving is free)
        v = eleven.save_designed_voice(
            "Tour-Tasmania-Platypus", DESIGN["description"], previews[0]["generated_voice_id"],
            labels={"tour": "hobart", "role": "platypus", "series": "audio-tours"},
            not_selected=[p["generated_voice_id"] for p in previews[1:]])
        VOICE_FILE.write_text(json.dumps({"voice_id": v["voice_id"], "preview": 1}, indent=2))
    print(f"platypus voice: {voices()['platypus']}")


def context(turns: list[tuple[str, str]], k: int) -> tuple[str | None, str | None]:
    def gather(texts: list[str]) -> list[str]:
        taken: list[str] = []
        for t in texts:
            if taken and sum(map(len, taken)) + len(t) > CONTEXT:
                break
            taken.append(t)
        return taken
    before = gather([t for _, t in turns[:k]][::-1])[::-1]
    after = gather([t for _, t in turns[k + 1:]])
    return "\n\n".join(before) or None, "\n\n".join(after) or None


def cmd_a() -> None:
    v, turns = voices(), [(s[1], s[2]) for s in parse() if s[0] == "say"]
    (OUT / "A").mkdir(parents=True, exist_ok=True)
    for k, (voice, text) in enumerate(turns):
        prev, nxt = context(turns, k)
        req = {"kind": "tts-timestamps", "text": text, "voice_id": v[voice], "model_id": MODEL,
               "output_format": FORMAT, "previous_text": prev, "next_text": nxt}

        def call(req=req) -> tuple[bytes, dict]:
            result, meta = eleven.tts_with_timestamps(
                req["text"], req["voice_id"], req["model_id"], previous_text=req["previous_text"],
                next_text=req["next_text"], output_format=FORMAT)
            return json.dumps(result).encode(), meta

        path, _ = guard().run(f"lab-005 A turn-{k + 1:02d} {voice}", req, len(text), call, suffix=".json")
        (OUT / "A" / f"turn-{k + 1:02d}.mp3").write_bytes(base64.b64decode(json.loads(path.read_text())["audio_base64"]))


def dialogue(inputs: list[dict], model: str) -> tuple[bytes, dict]:
    with eleven._client(timeout=300) as c:
        r = c.post("/v1/text-to-dialogue/with-timestamps", params={"output_format": FORMAT},
                   json={"inputs": inputs, "model_id": model})
        return r.content, eleven._cost_headers(r)


def cmd_b(model: str) -> None:
    v = voices()
    inputs = [{"text": s[2], "voice_id": v[s[1]]} for s in parse() if s[0] == "say"]
    req = {"kind": "dialogue-timestamps", "inputs": inputs, "model_id": model, "output_format": FORMAT}
    chars = sum(len(i["text"]) for i in inputs)
    path, _ = guard().run(f"lab-005 B dialogue {model}", req, chars, lambda: dialogue(inputs, model), suffix=".json")
    (OUT / "B").mkdir(parents=True, exist_ok=True)
    result = json.loads(path.read_text())
    (OUT / "B" / f"dialogue-{model}.mp3").write_bytes(base64.b64decode(result["audio_base64"]))
    (OUT / "B" / f"segments-{model}.json").write_text(json.dumps(result["voice_segments"], indent=1))


# --- offline mix ------------------------------------------------------------------

HEAD, STING_GAP, TITLE_GAP, TURN_GAP, SFX_PAD, TAIL = 0.3, 0.4, 1.2, 0.6, 0.35, 1.5
LEAD, TRAIL = 0.1, 0.35
BED_GAP_DB, STING_DB, SPLASH_DB = -9, -6, -8  # relative to the voice's loudness


def clips_a() -> list[tuple]:
    """('clip', file, trim0, trim1) | ('gap', s) | ('sfx', name, mode) after the title."""
    out, k = [], 0
    for s in parse():
        if s[0] == "say":
            k += 1
            f = OUT / "A" / f"turn-{k:02d}.mp3"
            a, b = audio.speech_bounds(f)
            out.append(("clip", f, max(0, a - LEAD), min(audio.duration(f), b + TRAIL)))
        else:
            out.append(s)
    return out


def clips_b(model: str) -> list[tuple]:
    """The dialogue stays one take; it is only cut at a one-shot cue (in the silence
    between the two turns) so the splash gets its own gap, as in method A."""
    f = OUT / "B" / f"dialogue-{model}.mp3"
    segs = json.loads((OUT / "B" / f"segments-{model}.json").read_text())
    turn_end: dict[int, float] = {}
    turn_start: dict[int, float] = {}
    for s in segs:
        i = s["dialogue_input_index"]
        turn_start[i] = min(turn_start.get(i, 1e9), s["start_time_seconds"])
        turn_end[i] = max(turn_end.get(i, 0), s["end_time_seconds"])
    quiet = audio.silences(f, min_seconds=0.12)
    a0, b0 = audio.speech_bounds(f)
    out, k, cut = [], 0, max(0, a0 - LEAD)
    for s in parse():
        if s[0] == "say":
            k += 1
        elif s[0] == "sfx" and s[2] == "once":
            lo, hi = turn_end[k - 1] - 0.4, turn_start[k] + 0.4
            near = [(y - x, x, y) for x, y in quiet if x < hi and y > lo]
            _, x, y = max(near) if near else (0, turn_end[k - 1], turn_start[k])
            out.append(("clip", f, cut, x + TRAIL))
            out.append(s)
            cut = y - LEAD
        elif s[0] == "sfx":
            at = turn_start[k] - 0.5 if s[2] == "under" else turn_end[k - 1] + 0.3
            out.append(("bedmark", s[1], s[2], at))
        else:
            out.append(s)
    out.insert(len(out) - sum(1 for x in out if x[0] == "pause"), ("clip", f, cut, min(audio.duration(f), b0 + TRAIL)))
    return out


def duck_report(bed: Path, spans: list[tuple[float, float]], start: float, end: float, voice_lufs: float) -> str:
    """Mean bed level (RMS dBFS) inside speech and in the gaps, while the bed is fully up."""
    def rms(a: float, b: float) -> float | None:
        if b - a < 0.3:
            return None
        out = audio.run(["ffmpeg", "-hide_banner", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(bed),
                         "-af", "astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"])
        m = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", out)
        return float(m[-1]) if m and m[-1] != "-inf" else None
    lo, hi = start + 1.5, end - 3
    inside = [rms(max(a, lo) + 0.3, min(b, hi)) for a, b in spans if b > lo and a < hi]
    gaps = [rms(b1 + 0.1, a2) for (_, b1), (a2, _) in itertools.pairwise(spans) if lo < b1 and a2 < hi]
    inside, gaps = [x for x in inside if x is not None], [x for x in gaps if x is not None]
    avg = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    return f"under speech {avg(inside) - voice_lufs:+.1f} dB, in gaps {avg(gaps) - voice_lufs:+.1f} dB"


def master(method: str, model: str) -> Path:
    items = clips_a() if method == "a" else clips_b(model)
    chime, splash, river = BOOK.build / "sfx" / "chime-1.mp3", OUT / "sfx" / "splash.mp3", OUT / "sfx" / "river.mp3"
    title = BOOK.build / "stop-6" / "title.mp3"  # the stop's cached title, shared by both

    voice, t = [], HEAD + audio.duration(chime) + STING_GAP
    voice.append((title, 0.0, 2.487 + TRAIL, t))
    t += 2.487 + TITLE_GAP
    events, cues, prev = [], {}, "title"
    for it in items:
        if it[0] == "clip":
            _, f, a, b = it
            t += TURN_GAP if prev == "clip" else 0  # B's clips are cut only at one-shot cues
            voice.append((f, a, b, t))
            t += b - a
            prev = "clip"
            if cues.get("under") == "next":
                cues["under"] = t - (b - a)
        elif it[0] == "sfx" and it[2] == "once":
            t += SFX_PAD
            events.append(("splash", t))
            t += audio.duration(splash) + SFX_PAD
            prev = "sfx"
        elif it[0] == "sfx":  # method A: a bed starts at the next clip, stops after the last one
            cues[it[2]] = "next" if it[2] == "under" else t
        elif it[0] == "bedmark":  # method B: a time inside the dialogue file, mapped below
            cues[it[2]] = "next" if it[2] == "under" else ("file", it[3])
        elif it[0] == "pause":
            t += it[1]
    total = t + TAIL
    stop = cues["stop"]
    if isinstance(stop, tuple):  # file time -> timeline, via the clip that contains it
        stop = next(place + stop[1] - a for f, a, b, place in voice[1:] if a <= stop[1] <= b)
    bed_from, bed_to = cues["under"] - 1.5, stop + 1.5

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
        ins, chains = [], []
        for n, (f, a, b, place) in enumerate(voice):
            ins += ["-i", str(f)]
            chains.append(f"[{n}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{fmt},adelay={round(place*1000)}:all=1[v{n}]")
        mix = "".join(f"[v{n}]" for n in range(len(voice)))
        voice_wav = tmp / "voice.wav"
        audio.run(["ffmpeg", "-hide_banner", "-y", *ins, "-filter_complex",
                   ";".join(chains) + f";{mix}amix=inputs={len(voice)}:normalize=0,apad=whole_dur={total:.3f},atrim=duration={total:.3f}[out]",
                   "-map", "[out]", "-c:a", "pcm_f32le", str(voice_wav)])
        vl = audio.loudness(voice_wav)
        g_chime = vl + STING_DB - audio.loudness(chime)
        g_splash = vl + SPLASH_DB - audio.loudness(splash)
        g_bed = vl + BED_GAP_DB - audio.loudness(river)
        span = bed_to - bed_from
        graph = (
            f"[0:a]{fmt},asplit[v][key];"
            f"[1:a]{fmt},volume={g_chime:.2f}dB,adelay={round(HEAD*1000)}:all=1[c];"
            + "".join(f"[2:a]{fmt},volume={g_splash:.2f}dB,adelay={round(at*1000)}:all=1[s];" for _, at in events)
            + f"[3:a]atrim=duration={span:.3f},asetpts=PTS-STARTPTS,{fmt},afade=t=in:d=1.5,"
            f"afade=t=out:st={span-3:.3f}:d=3,volume={g_bed:.2f}dB,adelay={round(bed_from*1000)}:all=1,"
            f"apad=whole_dur={total:.3f},atrim=duration={total:.3f}[bed];"
            # duck the bed under the voice: about -6 to -8 dB more while someone speaks
            f"[bed][key]sidechaincompress=threshold=0.015:ratio=4:attack=30:release=450:makeup=1,asplit[duck][stem];"
            f"[v][c][s][duck]amix=inputs=4:normalize=0,apad=whole_dur={total:.3f},atrim=duration={total:.3f}[out]"
        )
        mix_wav = tmp / "mix.wav"
        audio.run(["ffmpeg", "-hide_banner", "-y", "-i", str(voice_wav), "-i", str(chime), "-i", str(splash),
                   "-stream_loop", "-1", "-i", str(river), "-filter_complex", graph, "-map", "[out]",
                   "-c:a", "pcm_f32le", str(mix_wav), "-map", "[stem]", "-c:a", "pcm_f32le", str(tmp / "bed.wav")])
        spans = [(p, p + b - a) for _, a, b, p in voice[1:]]
        print(f"  voice {vl:.1f} LUFS; bed vs voice: {duck_report(tmp / 'bed.wav', spans, bed_from, bed_to, vl)}")
        target = "I=-16:TP=-1.5:LRA=11"
        rep = audio.run(["ffmpeg", "-hide_banner", "-i", str(mix_wav), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"])
        m = json.loads(rep[rep.rfind("{"):rep.rfind("}") + 1])
        ln = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=44100")
        name = "A-stitched" if method == "a" else f"B-dialogue{'' if model == MODEL else '-' + model.split('_')[-1]}"
        out = OUT / f"stop-6-excerpt-{name}.mp3"
        audio.run(["ffmpeg", "-hide_banner", "-y", "-i", str(mix_wav), "-af", ln, "-c:a", "libmp3lame", "-b:a", "128k",
                   "-id3v2_version", "3", "-metadata", f"title=Lab 005 excerpt {name}",
                   "-metadata", "album=Audio Tours lab", str(out)])
    print(f"{out.relative_to(config.REPO_ROOT)}: {audio.duration(out):.1f} s, {audio.loudness(out):.1f} LUFS, "
          f"bed {bed_from:.1f}-{bed_to:.1f} s, splash at {events[0][1]:.1f} s")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    model = args[args.index("--model") + 1] if "--model" in args else MODEL
    {"sfx": cmd_sfx, "design": cmd_design, "a": cmd_a, "b": lambda: cmd_b(model),
     "master": lambda: master(args[1], model), "parse": lambda: print(*parse(), sep="\n")}[args[0]]()
