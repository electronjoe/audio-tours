# audio-tours

GPS-triggered audio tours: the pipeline is in `src/audiotour/`, the web player in `site/player/`,
and per-tour content in `tours/<slug>/` (see `README.md`).

- Making or revising a tour: follow `docs/process/` in order (route, stops, research,
  topics, scripts, sound). Its house rules (driver safety, sourced facts, both audiences,
  privacy) are requirements.
- Work items live in `tasks/`, one Markdown file per task, indexed in `tasks/README.md`. Update
  a task's status and acceptance boxes as work lands.
- The repo and the site are public. Never commit family names, ages or addresses. Keep them in
  `tours/*/source/research.*`, which is gitignored.
- Paid ElevenLabs calls go only through `spend.Guard`. Check `uv run tour account` before
  large renders.
- Player changes: run `uv run --with playwright python tests/player_drive.py hobart`.
