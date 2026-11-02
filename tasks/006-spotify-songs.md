# 006: Song moments with Spotify links

Status: todo · Priority: medium · Raised: 2026-11-02 (Hobart road test)

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
- While the tour page is in the background, Chrome on Android stops delivering GPS. Show the
  button only if the next trigger is far enough away for the song to finish (song length plus
  1 minute, at the current speed). Otherwise show "Save for later", which keeps it in the stop
  card. After a song, the next fix triggers normally (lookahead 2 covers a stop crossed while
  in the background, but the one jumped over is marked skipped).
- Optional: a "Drive soundtrack" list under More with every song in the tour.

## Acceptance

- [ ] On an Android phone, the button opens Spotify at the right song, and coming back to the
      tab resumes GPS triggering.
- [ ] `tour check` rejects a song link whose oEmbed title doesn't match `title`.
- [ ] A stop with a song has a spoken song segment that names the song and the artist and says
      why it is there.
- [ ] `tests/player_drive.py` checks that the song card appears after the stop ends and clears
      when the next stop starts.
