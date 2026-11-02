"""``tour new <slug>``: start a tour from the templates in ``docs/process/templates/``.

It writes ``tour.toml``, ``plan.md`` and, in ``source/``, the research notes (gitignored) and an
empty working draft. It never overwrites: an existing tour folder is refused.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from string import Template

from .config import REPO_ROOT, TOURS_DIR, show

TEMPLATES = REPO_ROOT / "docs" / "process" / "templates"
# template -> path inside the new tour folder
FILES = {
    "tour.toml": "tour.toml",
    "plan.md": "plan.md",
    "research.md": "source/research.md",
    "working-draft.md": "source/working-draft.md",
}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RESERVED = {"player", "lab"}  # folders under site/ that a published tour would collide with


def create(slug: str, title: str, tours_dir: Path = TOURS_DIR, today: date | None = None) -> list[Path]:
    """Write the new tour's files and return their paths."""
    if not SLUG.fullmatch(slug):
        raise SystemExit(f"Slug {slug!r}: use lower-case letters, digits and single hyphens, e.g. 'bruny-island'.")
    if slug in RESERVED:
        raise SystemExit(f"Slug {slug!r} is taken by site/{slug}/; pick another.")
    root = tours_dir / slug
    if root.exists():
        raise SystemExit(f"{show(root)} already exists; nothing written.")
    today = today or date.today()
    values = {
        "slug": slug,
        "title": title,
        "title_toml": json.dumps(title, ensure_ascii=False),  # a JSON string is a valid TOML string
        "date": today.isoformat(),
        "year": today.year,
    }
    written = []
    for name, rel in FILES.items():
        out = root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(Template((TEMPLATES / name).read_text()).substitute(values))
        written.append(out)
    return written
