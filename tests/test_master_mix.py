"""Master a two-speaker track with a one-shot and a ducked bed, from synthetic audio.

Speech is tone bursts (one second per paragraph), so the timings are exact and no
paid call is involved.
"""

import json
import shutil

import pytest

from audiotour import audio
from audiotour.chunks import Chunk
from audiotour.config import Tour
from audiotour.master import SFX_GAP, SPEAKER_GAP, master_track
from audiotour.render import plan

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

DRAFT = """\
# Test

## Cast

- KIKI → voices.kiki: a test guest

## Script: Stop 1 — Test

[SFX — rain, under]

A one.

A two.

[SFX — pop]

A three.

KIKI: B one.

[SFX — rain, stop]

A four.
"""

TOML = """\
[narration]
model_id = "m"
output_format = "mp3_44100_128"

[voices.narrator]
voice_id = "n"

[voices.kiki]
voice_id = "k"

[sfx.rain]
prompt = "rain"
loop = true

[sfx.pop]
prompt = "pop"
duration = 0.5
"""

LEAD, PARA, BREAK, TRAIL = 0.1, 1.0, 0.5, 0.3


def tones(path, n: int, freq: int) -> None:
    """``n`` one-second tones with half-second breaks, as a chunk's speech."""
    parts = "".join(f"sine=f={freq}:d={PARA},volume=0.1[t{i}];anullsrc=d={BREAK}[s{i}];" for i in range(n))
    order = "".join(f"[t{i}][s{i}]" for i in range(n))
    graph = (f"anullsrc=d={LEAD}[lead];{parts}[lead]{order}concat=n={2 * n + 1}:v=0:a=1,"
             f"atrim=duration={LEAD + n * (PARA + BREAK) - BREAK + TRAIL}")
    audio.run(["ffmpeg", "-hide_banner", "-y", "-filter_complex", graph, "-ar", "44100", str(path)])


def test_master_places_cues_and_ducks_the_bed(tmp_path):
    tour = Tour("demo", tours_dir=tmp_path)
    (tour.root / "source").mkdir(parents=True)
    tour.draft.write_text(DRAFT)
    (tour.root / "tour.toml").write_text(TOML)
    tour.sfx_dir.mkdir(parents=True)
    audio.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=4:a=0.1", str(tour.sfx_dir / "rain-1.mp3")])
    audio.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=1000:d=0.5", str(tour.sfx_dir / "pop-1.mp3")])

    from audiotour.render import find_track
    track, _ = find_track(tour, "stop-1")
    work = tour.build / "stop-1"
    work.mkdir(parents=True)
    items = []
    for c in (x for x in plan(tour, track) if isinstance(x, Chunk)):
        n = len(c.texts)
        tones(work / f"{c.name}.wav", n, 300 if c.voice == "narrator" else 600)
        times = [[LEAD + k * (PARA + BREAK), LEAD + k * (PARA + BREAK) + PARA] for k in range(n)]
        items.append({"kind": "speech", "name": c.name, "voice": c.voice, "file": f"{c.name}.wav",
                      "duration": LEAD + n * (PARA + BREAK) - BREAK + TRAIL, "paragraphs": c.paragraphs,
                      "times": times, "speech": [times[0][0], times[-1][1]], "gaps": [BREAK] * (n - 1),
                      "chars": len(c.text)})
    (work / "manifest.json").write_text(json.dumps({"items": items}))

    out = master_track(tour, "stop-1")
    assert out == tour.build / "stop-1.mp3"
    timeline = json.loads((work / "timeline.json").read_text())
    parts = [e for e in timeline["events"] if "part" in e]
    assert [p["part"] for p in parts] == ["title", "chunk-01 ¶1-2", "chunk-01 ¶3-3", "chunk-02", "chunk-03"]
    para = {int(k): v for k, v in timeline["paragraphs"].items()}

    # inside one piece the chunk keeps its own break; the cue cuts chunk-01 there
    assert para[2][0] - para[1][1] == pytest.approx(BREAK, abs=0.02)
    [pop] = [e for e in timeline["events"] if e.get("sfx") == "pop-1.mp3"]
    assert pop["at"] == pytest.approx(para[2][1] + SFX_GAP, abs=0.02)
    assert para[3][0] == pytest.approx(pop["at"] + audio.duration(tour.sfx_dir / "pop-1.mp3") + SFX_GAP, abs=0.02)
    # a change of speaker, either way, gets the short gap
    assert para[4][0] - para[3][1] == pytest.approx(SPEAKER_GAP, abs=0.02)
    assert para[5][0] - para[4][1] == pytest.approx(SPEAKER_GAP, abs=0.02)

    [bed] = [e for e in timeline["events"] if e.get("sfx") == "rain-1.mp3"]
    assert bed["from"] == pytest.approx(para[1][0] - 1.5, abs=0.02)
    assert bed["fade_out_at"] == pytest.approx(para[4][1], abs=0.02)
    assert bed["under_speech_db"] < bed["in_gaps_db"] - 4  # ducked under the voice
