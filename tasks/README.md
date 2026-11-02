# Tasks

One Markdown file per task, numbered in the order they were raised. Keep each file current:
update `Status` and tick acceptance boxes as work lands, and add what you learned on the road
to the file, not just to a commit message.

Statuses: `todo`, `doing`, `blocked` (say on what), `done`.

| # | Task | Status | Source |
| --- | --- | --- | --- |
| 001 | [Start tour waits for GPS; never auto-plays](001-start-waits-for-gps.md) | done | Hobart road test |
| 002 | [Reusable player, separate from per-tour content](002-reusable-player.md) | done | Hobart road test |
| 003 | [Google Maps route from each stop onward](003-maps-route-from-stop.md) | todo | Hobart road test |
| 004 | [Process and rule documents](004-process-docs.md) | doing | Hobart road test |
| 005 | [Script format v2: cast, guest voices, inline sound effects](005-script-format-v2.md) | doing (built; needs a listen) | Hobart road test |
| 006 | [Song moments with Spotify links](006-spotify-songs.md) | doing | Hobart road test |
| 007 | [Walking tours (trails and city walks)](007-walking-tours.md) | todo | Hobart road test |

## Template

```markdown
# NNN: <Title>

Status: todo · Priority: high | medium | low · Raised: YYYY-MM-DD (<where>)

## Why
What happened or what was asked, quoted where possible.

## Now
How it works today, with file:line pointers.

## Change
What to build, and the decisions already made.

## Acceptance
- [ ] Checkable outcomes, including the test that proves it.

## Open questions
Anything to settle before or during the work.
```
