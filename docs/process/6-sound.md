# 6. Sound: voices, effects and songs

## Voices

- **The narrator.** Design with `uv run tour design` (paid previews), listen to 2–3 rounds, and
  pick one. Record the choice in `tour.toml` under `[voices.narrator]`: the voice id, its
  source, the date, and why it was picked. Hobart's narrator was chosen for "more gravitas,
  similar pacing". It can be reused across tours to keep a series voice.
- **Guests.** Each `## Cast` entry names a `[voices.<key>]`. Design one voice per entry from its
  character note (`tour design`, about 130 credits a round). Guests should sound clearly
  different from the narrator (pitch, pace, texture), so a listener in a noisy car can tell who
  is speaking. Record each voice the same way as the narrator's: `name`, `voice_id`, `source`
  and a comment with the date and why it was chosen (Hobart's `[voices.platypus]`).
- **Voice slots.** The plan holds at most 3 custom voices and all 3 are in use
  (Tour-Tasmania-Narrator, Tour-Platypus, Postcards-Guide). A designed preview can't be used for
  TTS until it is saved into a slot. Ask before deleting any voice, and never delete
  Postcards-Guide. A premade library voice (`tour voices`) needs no slot.
- **Cost.** A guest costs no more than the narrator: its lines replace narrator lines at the
  same rate (about 0.22 credits per character). Each turn is its own chunk, so retaking one
  line costs a few credits.
- **Listen in the car.** Phone speaker or car Bluetooth, with road noise. Headphones flatter
  quiet voices.

## Sound effects

Each `[SFX — name]` cue in the script names an `[sfx.<name>]` in `tour.toml`; `tour check`
reports any that are missing. `uv run tour sfx <slug> [name ...]` generates `variants` takes
(about 5.5 credits per second each) into `build/sfx/`, and the master uses the `chosen` one.

```toml
[sfx.river]
prompt = "Gentle shallow river flowing over stones in quiet forest, no music, no voices"
duration = 15      # seconds; a bed is looped to fill its span, so 10-15 s is enough
loop = true        # beds: ask for a seamless loop
level_db = -9      # relative to the voice: a bed's level in the gaps, a one-shot's level
duck_db = -9       # beds: the extra reduction under speech (sidechain compressor)
variants = 1
chosen = 1
```

Optional per bed: `fade_in` (default 1.5 s, before the next speech) and `fade_out` (default
3 s, after the last speech). In `[master]`, `speaker_gap` (0.7 s) is the hand-off between
speakers and `sfx_gap` (0.5 s) the space either side of a one-shot. `tour master` prints each
bed's measured level under speech and in the gaps, relative to the voice.

- **Use them to make a place real**, not as decoration: the birds of this forest, this river,
  a hop kiln's fan, a distant steam train for a railway story, rain for a flood story.
- Use 2–4 per stop: a short ambience at the opening, and one or two one-shot effects on story
  beats. One-shot effects play in gaps, not over words.
- **Beds under speech** should sit about 18–23 dB below the voice. The defaults (−9, −9) give
  about −20. Hobart's river uses `duck_db = -13`, about −23 under speech, which reproduces
  the lab 005 excerpt the user chose. Check on a phone speaker that every word stays clear.
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
- **Record** the song in `tour.toml`:
  ```toml
  [stops.stop-3.song]
  title = "..."
  artist = "..."
  spotify = "https://open.spotify.com/track/<id>"
  length = "3:42"   # m:ss, as Spotify shows it
  why = "One line for the screen: why this song is here."
  ```
  The player shows `title`, `artist` and `why` after the stop ends, and uses `length` to decide
  whether there is room to play the song before the next stop (task 006).
- **Verify** with `uv run tour check <tour>`. It asks Spotify (free, no account) for each link's
  title (oEmbed) and length (the track page's `music:duration` tag), and fails if the title
  isn't `title` or the length is more than 2 s off `length`; it prints the right length. A
  version note on Spotify's title ("- Remastered 2011", "(Live)") is a warning. It also warns
  if Spotify credits another artist, or if the stop's script doesn't name the song and the
  artist. Answers are cached in `tours/<slug>/cache/spotify/`; offline (or with `--offline`)
  the links aren't verified and check warns. Choose the original recording, not a cover or a
  karaoke version, unless the cover is the point.
