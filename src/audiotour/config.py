"""Repo paths and credentials."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOKS_DIR = REPO_ROOT / "tours"

load_dotenv(REPO_ROOT / ".env")


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


@dataclass(frozen=True)
class Book:
    slug: str

    @property
    def root(self) -> Path:
        return BOOKS_DIR / self.slug

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
    def overrides(self) -> dict:
        """``overrides.toml``: spoken-text replacements and chunk retakes."""
        return _toml(self.root / "overrides.toml")


def _toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def book(slug: str) -> Book:
    b = Book(slug)
    if not b.root.is_dir():
        known = ", ".join(sorted(p.name for p in BOOKS_DIR.iterdir() if p.is_dir()))
        raise SystemExit(f"No book '{slug}' under {BOOKS_DIR}. Known: {known}")
    return b
