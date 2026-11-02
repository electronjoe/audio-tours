"""Cost guard for every paid ElevenLabs call.

Each paid call is described by a request dict. The guard:

1. hashes the request; if ``cache/<hash>`` exists it is reused and nothing is spent
2. otherwise refuses requests over ``max_chars`` and asks for confirmation
   (unless ``assume_yes``)
3. makes the call and records its cost in ``ledger.jsonl``. The cost comes from
   the response's ``character-cost`` header. The account usage counter lags by
   minutes, so its before/after delta is logged for reference only
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from . import eleven
from .config import Tour


def request_key(request: dict) -> str:
    blob = json.dumps(request, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def credits_used() -> int | None:
    """The account usage counter, or None if it can't be read (e.g. rate-limited). It's for
    reference only, so it must never stop a call or lose a result that was already paid for."""
    try:
        return int(eleven.subscription().get("character_count", 0))
    except (SystemExit, httpx.HTTPError):
        return None


@dataclass
class Guard:
    tour: Tour
    max_chars: int = 2000
    assume_yes: bool = False

    @property
    def cache_dir(self) -> Path:
        return self.tour.root / "cache"

    @property
    def ledger(self) -> Path:
        return self.tour.root / "ledger.jsonl"

    def approve(self, label: str, chars: int) -> None:
        if chars > self.max_chars:
            raise SystemExit(
                f"{label}: {chars:,} chars exceeds --max-chars {self.max_chars:,}; refusing."
            )
        print(f"{label}: {chars:,} chars to send.")
        if not self.assume_yes and input("Proceed? [y/N] ").strip().lower() != "y":
            raise SystemExit("Cancelled; nothing spent.")

    def run(
        self,
        label: str,
        request: dict,
        chars: int,
        call: Callable[[], tuple[bytes, dict]],
        suffix: str = ".mp3",
    ) -> tuple[Path, bool]:
        """Return (cached file, was_cached). ``call`` returns (payload bytes, metadata)."""
        key = request_key(request)
        path = self.cache_dir / f"{key}{suffix}"
        if path.exists():
            print(f"{label}: cached ({path.name}), 0 credits.")
            return path, True
        self.approve(label, chars)
        before = credits_used()
        started = time.time()
        payload, meta = call()
        after = credits_used()
        # The account counter lags by minutes, so a delta can mis-attribute earlier calls'
        # cost; record it separately and leave the cost unknown without a header.
        credits = int(meta["character-cost"]) if "character-cost" in meta else None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entry = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "label": label,
            "key": key,
            "chars": chars,
            "credits": credits,
            "account_delta": None if before is None or after is None else after - before,
            "seconds": round(time.time() - started, 1),
            "request": request,
            "meta": meta,
        }
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        cost = "unknown (no cost header)" if credits is None else f"{credits:,} credits"
        print(f"{label}: done, {cost} for {chars:,} chars.")
        return path, False


def read_ledger(tour: Tour) -> list[dict]:
    path = tour.root / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
