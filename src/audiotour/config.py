"""Repo paths and credentials."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
TOURS_DIR = REPO_ROOT / "tours"

load_dotenv(REPO_ROOT / ".env")


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


@dataclass(frozen=True)
class Tour:
    slug: str
    tours_dir: Path = TOURS_DIR  # tests point this at a temporary directory

    @property
    def root(self) -> Path:
        return self.tours_dir / self.slug

    @property
    def draft(self) -> Path:
        return self.root / "source" / "working-draft.md"

    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def settings(self) -> dict:
        """``tour.toml``: model, voices, render, mastering and SFX settings."""
        return _toml(self.root / "tour.toml")

    @property
    def info(self) -> dict:
        """The ``[tour]`` table: title, short_name, theme_color, artist, year.

        ``[book]`` (the audiobook name) is still read, with a note to rename it.
        """
        s = self.settings
        if "tour" in s:
            return s["tour"]
        if "book" in s:
            if self.slug not in _warned:
                _warned.add(self.slug)
                print(f"note: tours/{self.slug}/tour.toml: rename [book] to [tour]; [book] will stop working",
                      file=sys.stderr)
            return s["book"]
        return {}

    @property
    def title(self) -> str:
        return self.info.get("title", self.slug)

    @property
    def overrides(self) -> dict:
        """``overrides.toml``: spoken-text replacements and chunk retakes."""
        return _toml(self.root / "overrides.toml")


_warned: set[str] = set()


def _toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def tour(slug: str) -> Tour:
    t = Tour(slug)
    if not t.root.is_dir():
        known = ", ".join(sorted(p.name for p in TOURS_DIR.iterdir() if p.is_dir()))
        raise SystemExit(f"No tour '{slug}' under {TOURS_DIR}. Known: {known}")
    return t


# Deprecated audiobook-era names, kept so older code still runs. Use Tour, tour and TOURS_DIR.
Book = Tour
book = tour
BOOKS_DIR = TOURS_DIR
