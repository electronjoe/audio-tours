"""Local audio helpers (ffmpeg / ffprobe). Nothing here costs credits."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def run(args: list[str]) -> str:
    """Run ffmpeg/ffprobe quietly; return stderr (where ffmpeg prints its reports)."""
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{args[0]} failed:\n{r.stderr[-2000:]}")
    return r.stdout + r.stderr


def duration(path: Path) -> float:
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(out.strip())


def silences(path: Path, noise_db: float = -45, min_seconds: float = 0.05) -> list[tuple[float, float]]:
    """(start, end) of each stretch quieter than ``noise_db`` lasting ``min_seconds``."""
    out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
               f"silencedetect=noise={noise_db}dB:d={min_seconds}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    ends += [duration(path)] * (len(starts) - len(ends))  # silence running to the end
    return list(zip(starts, ends))


def speech_bounds(path: Path) -> tuple[float, float]:
    """Where speech starts and ends, ignoring leading and trailing silence."""
    length = duration(path)
    quiet = silences(path)
    start = quiet[0][1] if quiet and quiet[0][0] <= 0.01 else 0.0
    end = quiet[-1][0] if quiet and quiet[-1][1] >= length - 0.06 else length
    return start, end


def loudness(path: Path, prefilter: str = "") -> float:
    """Integrated loudness in LUFS (EBU R128), after ``prefilter`` (an ffmpeg chain ending in a comma)."""
    out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"{prefilter}ebur128", "-f", "null", "-"])
    summary = out[out.rfind("Summary:"):]
    m = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    if not m or m.group(1) == "-inf":
        raise SystemExit(f"Could not measure loudness of {path}")
    return float(m.group(1))
