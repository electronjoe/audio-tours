# Making a tour: process

How a tour goes from "we're driving from A to B on Saturday" to audio on the phone. Each stage
has its own document. The pipeline commands are in the top-level `README.md`, and the script
format the parser accepts is in [5-scripts.md](5-scripts.md#the-format-contract).

| Stage | Document | Output |
| --- | --- | --- |
| 0. Start | this page | `uv run tour new <slug> --title "..."`: `tour.toml`, `plan.md`, `source/research.md` and an empty draft, from [templates/](templates/) |
| 1. Route | [1-route.md](1-route.md) | `tours/<slug>/route.json`, legs and timings |
| 2. Stops | [2-stops.md](2-stops.md) | `[stops.*]` in `tour.toml`, with trigger points and time budgets |
| 3. Research | [3-research.md](3-research.md) | `source/research.md` (gitignored): a broad pool of facts with sources |
| 4. Topics | [4-topics.md](4-topics.md) | A plan: which story, side facts, song, guest and SFX go at each stop |
| 5. Scripts | [5-scripts.md](5-scripts.md) | `source/working-draft.md`, which passes `uv run tour check` |
| 6. Sound | [6-sound.md](6-sound.md) | Voices, SFX and songs in `tour.toml`; rendered and mastered audio |
| 7. Publish and test | top-level README | A simulated drive passes, then the real trip |

After the trip, write what worked and what didn't into the tour's `plan.md`. Turn anything
general into a task in `tasks/` or an edit to these documents.

## House rules

- **Driver safety first.** Nothing in the audio may sound like a hazard or an alert: no sirens,
  horns, screeching tyres, crashes, phone ringtones or indicator clicks. While driving, never
  say "look left now" or ask anyone to read the screen. Songs and buttons are for passengers.
- **True and sourced.** Every fact traces to a source in the research notes. Dramatisation is
  allowed only where it is clearly framed as dramatisation (see 5-scripts.md).
- **Two audiences at once.** Adults should learn something surprising, and children should be
  able to follow along and take part. Neither should feel talked down to.
- **Privacy.** The repo and the site are public. Family names, ages, home addresses and travel
  dates go in gitignored files only (`source/research.*`). Committed files say "the family" or
  "the passengers".
- **Spend deliberately.** Every paid call goes through `spend.Guard`. Check
  `uv run tour account` before a full render. Hobart is test-only (`[tour] test_only = true`):
  no new paid content there, only test renders of a pipeline change.

## What the Hobart trial taught us (2026-11-02)

Keep:

- **Chapter titles.** "The Road That Tried to Sink", "The Hunter with an Electric Face". They
  are intriguing and concrete, and they set up a question.
- **Captivating historical stories** with a real arc, not lists of facts.
- **Educational questions with thinking pauses**, aimed at both children and adults.
- About 3 minutes per stop, a chime before each, and no stop interrupting another.

Change:

- **Research far more broadly before choosing** (3-research.md): wildlife you are likely to
  see, the national and state picture (primary industries, major news and controversies),
  music, food, landscape. Then downselect into the stops (4-topics.md).
- **Music.** 2–4 songs per tour, tied to the places, with a spoken song segment and a Spotify
  button (6-sound.md, task 006).
- **More sound effects.** They should feel like part of the place (6-sound.md).
- **More voices.** Keep the primary narrator, and have them interview guests now and then:
  experts, figures from history, even animals (5-scripts.md, task 005).
