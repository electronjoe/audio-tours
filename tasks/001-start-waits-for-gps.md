# 001: Start tour waits for GPS; never auto-plays

Status: todo · Priority: high · Raised: 2026-11-02 (Hobart road test)

## Why

> When I start a tour, I don't want the first audio track to actually start immediately (as it
> does), I want it to begin waiting for the location trigger instead.

On the road (Android, Chrome), tapping **Start tour** well short of Granton started stop 1
straight away. Nothing else was tapped.

## Now

GPS alone shouldn't have done it: stop 1's zone is about 12 km from central Hobart. There are
two plausible causes, and neither has been confirmed:

1. **Leftover queued story (most likely).** `save()` persists the playing stop and the queue as
   `pending` (`site/player/app.js`, `save`/`load`). `start()` then deliberately resumes it:
   `if (S.queue.length && !S.current) playNext(); // resume after a reload`. If stop 1 was
   played or queued on this phone during earlier testing (a simulated drive, **Play now** or
   **Start here**) and never finished, the next Start plays it immediately.
   `tests/player_drive.py` asserts this resume behaviour ("a reload mid-story resumes that story
   after Start"), so it is by design, but the design is wrong for a fresh trip.
2. **A bad network fix.** When there is no satellite fix, `startGPS` falls back to
   `getCurrentPosition({enableHighAccuracy: false})` and feeds the result to `onFix`, which
   triggers stops. A Wi-Fi or cell location can be kilometres off while still reporting an
   accuracy under `MAX_ACCURACY` (150 m), for example a phone hotspot or a router that has
   moved.

## Change

- **Start never plays audio.** It arms GPS, takes the wake lock and unlocks audio, and nothing
  else.
- **Saved progress is offered, not resumed.** If saved state exists, the Now card shows
  "Resume: <stop title>" as a button the user can tap. Store `savedAt` in the saved state. If
  it is older than about 8 hours, show two buttons instead of Start: **Start from the
  beginning** (clears status, cursor and queue) and **Continue (next: stop N)**.
- **Coarse fixes never trigger.** Fixes from the low-accuracy fallback update the display
  (distances, the map dot) but are tagged `coarse` and skipped by the trigger loop in `onFix`.
- **Trigger log.** Keep the last 30 trigger and play events (time, cause: `gps` with distance
  and accuracy, `manual`, `resume`, `coarse-ignored`) in localStorage and show them under
  **More → Event log**. The next oddity on the road can then be diagnosed instead of guessed
  at.
- Keep **▶ Play now** on the Next stop card, but make it a secondary (non-green) button
  until the stop is within about 2 km, so it is less tempting than Start.

## Acceptance

- [ ] With a stop left in `pending` from a previous session, tapping Start plays nothing. The
      Now card offers Resume, and tapping it plays that stop.
- [ ] Saved state older than 8 hours shows the Start from the beginning / Continue choice.
- [ ] A fallback (coarse) fix inside a stop's zone does not trigger it. A precise fix does.
- [ ] The event log shows why each stop started.
- [ ] `tests/player_drive.py` is updated: the reload check expects Resume, not auto-play, and
      new checks cover "Start plays nothing" and "coarse fix ignored".
