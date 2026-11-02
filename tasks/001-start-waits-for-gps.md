# 001: Start tour waits for GPS; never auto-plays

Status: done · Priority: high · Raised: 2026-11-02 (Hobart road test)

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

- [x] With a stop left in `pending` from a previous session, tapping Start plays nothing. The
      Now card offers Resume, and tapping it plays that stop.
- [x] Saved state older than 8 hours shows the Start from the beginning / Continue choice.
- [x] A fallback (coarse) fix inside a stop's zone does not trigger it. A precise fix does.
- [x] The event log shows why each stop started.
- [x] `tests/player_drive.py` is updated: the reload check expects Resume, not auto-play, and
      new checks cover "Start plays nothing" and "coarse fix ignored".

## Notes from the 2–3 Nov 2026 round

- **Since 002, the markup lives in one template, `site/player/tour.html`.** Edit it, then run
  `uv run tour pages`, which needs no audio build. `test_hobart_pages_match_committed` fails if
  the committed pages weren't regenerated. The element ids, element order and `../player/`
  paths are unchanged, so the `player_drive.py` selectors still hold. `start()`, `save()` and
  `load()` in `app.js` weren't touched. `savedAt` and the event log belong in localStorage,
  not `tour.json`.
- **GPS after a gap (phone test, task 006):** Chrome sends no fixes while the page is hidden.
  The first fixes after a return arrive 4–7 s later at ±26–54 m, can jump around for about
  5 s, and may be 1–1.5 km from the last fix. That supports gating on accuracy right after a
  gap. 006 specifies a `catch-up` trigger cause for stops passed while away, so the event log
  here should leave room for it.

## As built (2 Nov 2026)

All in `site/player/app.js` (with markup in `tour.html` and styles in `style.css`). The
catch-up from 006 landed in the same change, because both are about which fix may trigger a stop.

- **Start** (`start()`) arms GPS, takes the wake lock and unlocks audio. It never plays a stop.
  `load()` puts saved `pending` stops into `S.resume`, not the queue, so a GPS trigger can't
  play a leftover story either. The Now card shows **▶ Resume: N. Title**. Resume restarts the
  stop from its beginning (the position isn't saved). If another stop starts first, the offer
  is dropped and the stop is marked skipped, so it is still playable from its card.
- **Stale progress:** `save()` writes `savedAt`. If progress (cursor, statuses or pending) is
  older than 8 h, or was saved before `savedAt` existed, the Start button is replaced by
  **Start from the beginning** and **Continue (next: stop N)**. Continue keeps the Resume offer.
- **Accuracy gate:** fallback fixes are tagged `coarse`. They move the dot and the distances but
  never trigger. After Start and after every gap (page hidden, or no fix for 20 s), the first
  fix used must be ±50 m or better. If none that good arrives within 30 s of the first fix
  back, the normal 150 m gate applies again (forest, city canyons). The status chip says
  "GPS settling (±N m)" meanwhile.
- **Event log:** the last 30 events go in localStorage under `tour:<slug>:log`, not
  `tour.json`, and show newest first under **More → Event log**. Events: `play` and `queued`
  with a cause (`gps` with distance from the centre and accuracy, `manual`, `resume`,
  `catch-up`), `missed` (cause `catch-up`, with the jump), `ignored` (`coarse-ignored`,
  `settling`, `inaccurate`; at most once a minute per stop, and only for a fix inside an armed
  zone), `back` (gap length, jump, accuracy), `start` and `reset`.
- **Play now** on the Next stop card is green only within 2 km of the zone.
- `tests/player_drive.py`: the reload check expects Resume. New checks cover Start playing
  nothing, stale progress (both buttons), a coarse fix ignored and a precise one triggering,
  the event log (data and the More panel), and the hidden gap from 006. The screenshot path can
  be redirected with `$PLAYER_TEST_SHOT`.
- Not yet tried on the road. The next drive should open the Event log after Start and after
  coming back from Spotify or a locked screen.
