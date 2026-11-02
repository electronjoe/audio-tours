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


DRAFT = "working-draft.md"


@dataclass(frozen=True)
class Tour:
    slug: str
    tours_dir: Path = TOURS_DIR  # tests point this at a temporary directory
    draft_name: str = DRAFT  # another file in source/ for an excerpt or trial, e.g. stop-6-platypus.md

    @property
    def root(self) -> Path:
        return self.tours_dir / self.slug

    @property
    def draft(self) -> Path:
        return self.root / "source" / self.draft_name

    @property
    def build(self) -> Path:
        """Renders and masters. Another draft builds into its own subfolder, so it can never
        overwrite the tour's published stops."""
        base = self.root / "build"
        return base if self.draft_name == DRAFT else base / Path(self.draft_name).stem

    @property
    def sfx_dir(self) -> Path:
        """Generated sound effects, shared by every draft of the tour."""
        return self.root / "build" / "sfx"

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


def show(path: Path) -> str:
    """A path relative to the repo for messages, or as given if it's elsewhere (tests)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def tour(slug: str, draft: str | None = None) -> Tour:
    t = Tour(slug, draft_name=draft or DRAFT)
    if not t.root.is_dir():
        known = ", ".join(sorted(p.name for p in TOURS_DIR.iterdir() if p.is_dir()))
        raise SystemExit(f"No tour '{slug}' under {TOURS_DIR}. Known: {known}")
    if draft and not t.draft.exists():
        raise SystemExit(f"No draft {t.draft}")
    return t


# Deprecated audiobook-era names, kept so older code still runs. Use Tour, tour and TOURS_DIR.
Book = Tour
book = tour
BOOKS_DIR = TOURS_DIR
