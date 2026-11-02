# 006: Song moments with Spotify links

Status: doing (built: song table, `tour check` link and length check, publish, Now card with the room rule; needs songs in a tour and a phone test) · Priority: medium · Raised: 2026-11-02 (Hobart road test)

## Why

> Include music topics! Ideally with some Spotify links? To open the Spotify app to a song?
> That would be super cool. [A passenger] loves music, and having it be related to the drive
> somehow would be fantastic.

> The stop audio should mention (add extra time budget) what song it is recommending and why:
> any interesting history or facts linking the tour location and the song, or captivating
> information about the song. Engaging!

## Decisions (2026-11-02)

- The phones are Android with Chrome. A `https://open.spotify.com/track/<id>` link opens the
  Spotify app at that track.
- **A song button after a stop.** The narrator introduces the song at the end of the stop.
  When the stop's audio ends, the player shows a large **▶ Play on Spotify** button. Tapping it
  is optional.
- We never embed or play copyrighted music in our audio. We only link to it.

## Background GPS (measured 3 Nov 2026)

Measured with `site/lab/gps-probe/` (same `watchPosition` options as the player) on Android
Chrome 156, as a passenger at about 10 m/s, phone charging. Each hidden span lasted 1.3–2.3
minutes.

| Phase | Hidden | Fixes while hidden | Longest gap | First fix after return |
| --- | --- | --- | --- | --- |
| Page in front, screen on | 0 | (1 fix/s, 4–8 m) | 1 s | n/a |
| Spotify playing, page behind it | 2m17s | 0 | 2m23s | 6 s later, ±54 m, jumped 1.56 km |
| Screen locked | 1m38s | 0 | 1m45s | 6 s later, ±26 m, jumped 1.08 km |
| Spotify + our quiet audio loop | 2m11s | 0 | 2m18s | 7 s later, ±50 m |
| Screen locked + our quiet audio loop | 1m19s | 0 | 1m24s | 5 s later, ±35 m |

- **While the page is hidden, GPS is off.** This holds whether another app is in front or the
  screen is locked, and whether or not audio plays. With the loop playing and the screen locked,
  the page was never frozen and its timers kept running, yet no fix arrived. With no audio
  playing, Chrome froze the page 60–90 s after it was hidden. Audio stops the freeze but not the GPS
  cut-off, so the tour's own audio doesn't keep triggers working with the screen off either.
- **Spotify takes the audio focus.** Our loop was paused 1 s after switching to Spotify.
- **No errors, no restart needed.** `watchPosition` stops delivering while hidden and resumes by
  itself 4–7 s after the page is back in front. The first fixes are rough (±26–54 m) and settle
  under ±15 m within 5–10 s, sometimes after a few jumpy seconds (a 97 m backward step, then a
  144 m step).
- **What the player does today:** `onFix` triggers a stop only when a fix lands inside its zone.
  A zone crossed entirely while hidden stays armed. When a later stop triggers, `advanceTo()`
  silently marks the jumped-over stop skipped, and nothing tells the listener it was missed.
  Position-derived speed across a gap or a jumpy patch is meaningless (144 m in 1 s is about
  520 km/h).
- **Uncertain, but unlikely to change the rule:** the hidden spans were shorter than the planned
  3 minutes, but every hidden span got zero fixes. The phone was charging, and Android is
  usually more lenient then, not less. The user agent doesn't reveal the real Android version.
  Not tested: split-screen (the page stays visible, so GPS may continue) and the Spotify embed
  player inside the page (see Open questions).

## Change

**Content** (see `docs/process/4-topics.md`, `5-scripts.md` and `6-sound.md`):

- Choose 2–4 songs per tour, each tied to the place: an artist from there, a song about it,
  a song that was part of its history, or one that shares the stop's theme (rivers, trains,
  forests).
- Each song stop gets a **song segment** in its script: an extra **30–60 seconds** on top of the
  usual stop length. It names the song and the artist plainly, says why it belongs at this place,
  and tells one gripping thing about the song (how it was written, a record it broke, what it
  caused). It ends with a cue to the listener, e.g. "The button to play it is on your screen
  now." Budget that time when spacing the stops (`docs/process/2-stops.md`).
- `tour.toml` gets a song table per stop:
  ```toml
  [stops.stop-3.song]
  title = "..."
  artist = "..."
  spotify = "https://open.spotify.com/track/<id>"
  length = "3:42"   # used by the "room for the song" check below
  why = "One line for the screen: why this song is here."
  ```
- **Verify every link.** Don't trust a remembered track ID. Fetch
  `https://open.spotify.com/oembed?url=<link>` (no account needed) and check that the returned
  title matches. `tour check` does this when online and warns when offline.

**Player:**

- Publish copies `song` into `tour.json`.
- When a stop with a song ends, the Now card shows the song (title, artist, the `why` line) and
  **▶ Play on Spotify**. The card stays until the next stop starts. The song also appears in
  that stop's expanded card so it can be played later.
- **While Spotify plays, the tour is deaf** (no GPS, see above). The tour still must not miss
  a stop. Two rules handle this:
- **Only offer the song when there's room.** Show **▶ Play on Spotify** only if
  `time to next trigger > song length + 60 s`, otherwise show "Save for later", which keeps it
  in the stop card.
  - *Time to next trigger:* the straight-line distance from the current fix to the edge of the
    nearest armed zone (`metres − radius`), divided by the speed. Straight-line distance is never
    longer than the road distance, so the estimate errs toward "no room".
  - *Speed:* the higher of `coords.speed` and the median speed over the last 2 minutes, but at
    least 8 m/s. A stop at traffic lights then doesn't open a window that closes as soon as the
    lights change.
  - *The 60 s margin:* about 10 s from return to a usable fix (measured: 4–7 s to the first
    fix, under ±15 m within 10 s), plus about 30 s for the listener to notice the song has ended
    and switch back (unmeasured; Spotify may autoplay another song, so this is the soft part),
    plus 20 s of buffer for speed changes. The deadline is the zone's edge, so arriving a little
    late still triggers the stop inside the zone. The catch-up below covers worse cases.
  - *Song length* comes from a `length = "3:42"` field in the song table. oEmbed doesn't
    return the duration, but the track page does, and `tour check` verifies `length` against
    it (see Open questions).
  - *Content side* (`docs/process/2-stops.md`): place a song stop only where the road time to
    the next trigger at the planning speed covers the stop's audio, the song segment, the song
    and the 60 s margin. The player check is then only a guard for slow traffic or a fast
    driver.
- **Catch up on return.** A stop passed while the page was away is offered, not lost.
  - *Away* means the page was hidden, or no fix arrived for over 20 s.
  - *When to check:* on the first fix after being away with accuracy ±50 m or better. If it's
    worse, wait for the next; they come every second.
  - *Triggering:* stops whose zone contains the new fix trigger as usual.
  - *Passed while away:* an armed stop (in the lookahead window) whose centre lies within
    `radius + 10 % of the jump` of the straight segment from the last fix before the gap to this
    fix. The padding allows for curves on a 1–1.5 km jump. Mark it `missed` (shown like
    skipped) and show it in the Now card as "Passed while you were away: Stop N ▶ Play" until
    the next stop starts. Don't auto-play it, because it's behind the car.
  - *Speed after a gap:* don't derive speed from positions across a gap or in the first 10 s
    after it. Use `coords.speed` when the fix has it.
  - Event-log cause `catch-up` (see 001's trigger log).
  - **Built 2 Nov 2026 with 001** (`onFix`, `catchUp` and `along` in `site/player/app.js`).
    Two refinements to the rule above: a stop counts only if its centre projects strictly
    between the two fixes, so a zone still ahead of the car isn't marked missed; and the check
    repeats while it finds stops, so a gap over more stops than `lookahead` catches them all, in
    order. If none of the fixes back reaches ±50 m within 30 s, the normal 150 m gate applies.
    Playing one offer leaves any others; a GPS-triggered stop clears them all. Position-derived
    speed is never computed across a gap, in the 10 s after it, or between fixes more than 20 s
    apart. The last 2 minutes of used fixes and their speeds are in `S.track`, ready for the
    median speed the song button needs.
- Optional: a "Drive soundtrack" list under More with every song in the tour.

### As built (2 Nov 2026)

- **Song table and check** (`src/audiotour/songs.py`). `[stops.<id>.song]` takes exactly
  `title`, `artist`, `spotify`, `length` (`"m:ss"`, or whole seconds) and `why`; missing or
  unknown fields, a link that isn't a track and an unreadable length are errors.
  `uv run tour check <tour>` then asks Spotify about each link: the oEmbed title must match
  `title` (case, accents, punctuation and `&`/"and" don't count; a version note such as
  "- Remastered 2011" or "(Live)" is a warning), and the track page's `music:duration` must be
  within 2 s of `length` (an error that prints the right value). It warns if Spotify credits
  another artist (`music:musician_description`) or if the stop's script doesn't name the title
  and the artist. Offline, or with `--offline`, each link gets a warning instead and check
  doesn't fail. Answers are cached in `tours/<slug>/cache/spotify/<id>.json` (gitignored), so
  only the first check of a link goes online. Unit tests (`tests/test_songs.py`) use responses
  recorded once in `tests/fixtures/spotify/`.
- **`length` stays hand-entered**, though check could read it: `tour.toml` is hand-edited
  with comments, which a TOML rewrite would lose, and stop planning should be able to read
  `length` offline. Check verifies it and prints the right value to paste instead.
- **Publish** copies the song into the stop in `tour.json` (`docs/tour-json.md`), with the
  plain track link and `length` in seconds. It refuses a song table check would reject offline.
- **Player** (`site/player/app.js`, "songs" section). When a stop with a song ends (its audio
  `ended`, not a skip), `S.song` holds it and the Now card shows the title, artist, length and
  `why`. Below them is **▶ Play on Spotify** (a link, opening in a new tab, so a phone without
  the Spotify app doesn't lose the tour page) when `secondsToTrigger() > length + 60`, and
  otherwise "Save for later: the next stop comes before the song would end. It stays in stop
  N's card below." The check is rerun on every fix and every second, so the button can come and
  go as the speed or distance changes. Without a usable fix (none, coarse, or settling after a
  gap) there is no room; with no stop left armed there is always room. Any stop starting clears
  the card, as does Reset. Every stop with a song shows it in its expanded card, with its own
  Play link, whatever the room. The event log records each offer (`song`, with the room
  decision and the estimate) and each tap (`song-play`). The card isn't saved across a reload;
  the song is still in the stop's card.
- `tests/player_drive.py` serves a fixture copy of `tour.json` with a song on stop 1 (the
  committed tour has none). It checks that there is no card while the stop plays and that the
  song is in its expanded card; after the stop ends the card shows the song with
  ▶ Play on Spotify (12 km to the next zone at 10 m/s); at 50 m/s, and 2 km from the next zone,
  it says Save for later; back where there is room, Play returns; and the card clears when
  stop 2 starts.
- Fixed on the way: the Pause/Skip row stayed on screen after a stop ended, because
  `.controls { display: flex }` overrode its `hidden` attribute.
- Not built: the optional "Drive soundtrack" list.

## Acceptance

- [ ] On an Android phone, the button opens Spotify at the right song, and coming back to the
      tab resumes GPS triggering.
- [x] Measured whether GPS keeps working while Spotify plays or the screen is locked: it
      doesn't, even with audio playing (3 Nov 2026, above).
- [x] The button shows only when `time to next trigger > song length + 60 s`; otherwise "Save
      for later" (`tests/player_drive.py`, Song).
- [x] `tests/player_drive.py` simulates a hidden gap whose jump crosses a whole stop zone: that
      stop is offered as "Passed while you were away" and the next one still triggers.
- [x] `tour check` rejects a song link whose oEmbed title doesn't match `title`
      (`tests/test_songs.py`).
- [ ] A stop with a song has a spoken song segment that names the song and the artist and says
      why it is there. (Content: no tour has a song yet. `tour check` warns when a song stop's
      script doesn't name the song and the artist.)
- [x] `tests/player_drive.py` checks that the song card appears after the stop ends and clears
      when the next stop starts.

## Open questions

- ~~**Song length:** check whether the track page (`open.spotify.com/track/<id>`) carries a
  `music:duration` meta tag that `tour check` can read without an account.~~ **Answered 2 Nov
  2026: yes.** A plain GET of the track page, with no account or cookies, returns
  `<meta name="music:duration" content="214"/>` (seconds) and
  `<meta name="music:musician_description" content="Rick Astley"/>`, next to `og:title` and
  `og:type = music.song`. The page is about 280 kB. It's unofficial and could change, so check
  treats a page without the tag as a warning ("check the length by hand"), not an error. The
  author still enters `length` (see As built), and check verifies it.
- **Keep the page in front instead:** the Spotify embed player
  (`open.spotify.com/embed/track/<id>`) inside the tour page would keep GPS running. Without a
  Spotify login in Chrome it plays only a 30 s preview, so it would be a fallback, not the main
  path. It would also revisit the "only link" decision, although it is Spotify's own licensed
  player, not our audio. Android split-screen (Spotify and Chrome side by side) might also keep the page visible.
  Both are untested; a 2-minute probe run would settle either one.
