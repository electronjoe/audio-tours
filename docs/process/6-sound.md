# 6. Sound: voices, effects and songs

## Voices

- **The narrator.** Design with `uv run tour design` (paid previews), listen to 2–3 rounds, and
  pick one. Record the choice in `tour.toml` under `[voices.narrator]`: the voice id, its
  source, the date, and why it was picked. Hobart's narrator was chosen for "more gravitas,
  similar pacing". It can be reused across tours to keep a series voice.
- **Guests** (task 005). Design one voice per cast entry from its character note. Guests should
  sound clearly different from the narrator (pitch, pace, texture), so a listener in a noisy car
  can tell who is speaking. Record each voice the same way as the narrator's.
- **Listen in the car.** Phone speaker or car Bluetooth, with road noise. Headphones flatter
  quiet voices.

## Sound effects

ElevenLabs SFX is already wired in: `[sfx.<key>]` in `tour.toml`, then `uv run tour sfx <slug>`,
which generates `variants` takes and keeps the `chosen` one.

- **Use them to make a place real**, not as decoration: the birds of this forest, this river,
  a hop kiln's fan, a distant steam train for a railway story, rain for a flood story.
- Use 2–4 per stop: a short ambience at the opening, and one or two one-shot effects on story
  beats. Keep beds under speech at about −18 dB relative to the voice (ducked). One-shot effects
  play in gaps, not over words.
- **Never** use sirens, horns, brakes or screeching tyres, crashes, ringtones, notification
  sounds or indicator clicks. Nothing a driver might react to.
- Write prompts that are concrete and short, e.g. "Two green rosellas calling in eucalyptus
  forest, light breeze, no music". Ask for "no music" and "no voices" explicitly.
- The chime before every stop stays.
- Optional: ElevenLabs can also generate original music. A short original theme (5–10 s) for
  the tour opening and close is fair game. Real songs are never embedded, only linked (below).

## Songs (task 006)

- **Choose** 2–4 songs per tour from the research (3-research.md, Music), each with a genuine tie
  to the place or the stop's theme. Prefer songs the family might not know, plus at least one
  they will.
- **Write** a song segment into the stop's script (5-scripts.md): the song and artist, why it's
  here, one gripping fact, and the button cue.
- **Link.** Use `https://open.spotify.com/track/<id>`. On Android it opens the Spotify app at
  that track. Find the track on open.spotify.com (search). Never write an ID from memory.
- **Verify.** `curl -s "https://open.spotify.com/oembed?url=<link>"` should return the right
  title. Choose the original recording, not a cover or a karaoke version, unless the cover is
  the point.
- **Record** the song in `tour.toml` as `[stops.<id>.song]`: title, artist, spotify, why
  (one line for the screen).
