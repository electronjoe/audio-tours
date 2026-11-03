# 011: Play now on a slow link: stop the old story at once, show Loading…

Status: done (deployed 2026-11-03; needs a check on a slow link) · Priority: high · Raised: 2026-11-03 (cruise ship Wi-Fi)

## Why

> When I went to All Stories and clicked on for example stop 8 Start - it took me to the audio
> playing page but at first it continued to play the prior audio - for at least ten seconds
> before stopping that and starting the new audio. [...] I think it should stop immediately
> even while loading? Also maybe we need some sort of visual (minimal) notification that audio
> is fetching because that took some time?

## Now (before)

`play()` (`site/player/app.js`) set `S.current` to the new stop and rendered it, then awaited
`audioBlob()`, which downloads the whole MP3 (about 3 MB) into the cache before anything
touches the audio element. Until then the old story kept playing under the new one's title.
Two Play nows in a row raced: each load set `audio.src` when it landed, so the first tap's
audio could play under the second tap's title. Skip during a load didn't stop it landing.

## Change

- **`halt()`** (app.js:79) pauses the element and bumps a counter, `plays`. `play()` calls it
  first, so the old story stops at the tap. A load that finishes after a newer `play()`, Skip
  or Start over sees a stale ticket and is dropped.
- **`S.loading`** is the stop whose audio is still arriving. While it's set, the car screen's
  ring says **Loading…** in place of the pause button (which would wake the old story), the
  ring's track breathes, and the map card says Loading… in place of the time left. Both fade
  in after half a second (`.wait` in style.css), so a saved story, there in a blink, never
  flashes them. The pause button and the media-session play handler do nothing while loading.
- Not done: streaming a story that isn't saved instead of fetching it whole first. On the
  drive, Download for offline makes it moot; raise it again if slow links matter beyond the
  ship.

## Acceptance

- [x] Play now while a story plays silences it at once, before the new audio arrives.
- [x] A story whose audio is still arriving shows Loading…, with no pause button.
- [x] A load overtaken by a newer Play now is dropped; the newer story's own audio plays.
- [x] Skip during a load leaves nothing playing when the audio lands.
- [x] A saved story starts without showing Loading….
- [x] `tests/player_drive.py` "Slow link" covers the above by holding `.mp3` requests (it fails
      five of its seven checks on the old engine).
- [ ] Checked on a slow link on the phone.
