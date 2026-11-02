# 5. Writing the scripts

Goal: `tours/<slug>/source/working-draft.md`, one `## Script:` section per stop, which passes
`uv run tour check <slug>`. The format the parser accepts is `docs/script-format.md`. This
document covers the content.

## Voice and audience

- **One primary narrator** carries the tour: warm, curious, documentary. Keep it consistent from
  stop to stop.
- **Write for adults and children together.** Use concrete pictures ("like making a path across
  a bowl of porridge"), short sentences, and one idea at a time. Never baby-talk. An adult
  should hear at least one thing they didn't know at each stop.
- **Story first, facts inside the story.** Open on a person, a creature or a problem ("Imagine
  being given this job."). Facts arrive because the story needs them.
- **Ask questions and leave room to answer.** Ask 1–2 questions per stop with a
  `[PAUSE — 3 SECONDS]` after each, or set a challenge to discuss after the stop ends.
- **Be honest about hard history.** Convict labour, dispossession and extinction are told
  plainly and appropriately for children, without lingering on gore.

## Titles

Chapter titles were a highlight of the Hobart tour. Keep their pattern: a concrete noun plus a
surprising twist, e.g. "The Road That Tried to Sink", "The Cargo That Must Not Hatch". A title
never gives away the answer. The player reads the title aloud before the story, so the story's
first line mustn't repeat it.

## Shape of a stop (about 3 minutes, about 330–400 words)

1. **Hook** (1–3 short lines): a scene, a question, or "Imagine...".
2. **Story** with a turn: something goes wrong, someone has an ingenious idea, a surprise.
3. **Side fact or look-out**: wildlife, industry or national context, ideally visible or audible
   right now. Passengers may look; never direct the driver.
4. **Close**: a question or challenge for the car, or a link to what's coming.
5. **Optional song segment** (+30–60 s, about 70–140 words, task 006). Name the **song and
   artist** clearly. Say **why it's here** (it was written about this valley, the artist grew
   up down the road, it was the anthem of this protest). Tell **one gripping thing** about it:
   how it came to be, the record it broke, the trouble it caused. End by inviting the passengers
   to tap the button on the screen. Keep it as lively as the story, never a list of
   facts about the song.

## Guests and interviews (task 005)

The narrator stays the host and interviews a guest at a few stops per tour.

- **Experts** are roles, not real named living people: "a river scientist", "a forester who has
  climbed these trees". Never put a synthetic voice in the mouth of a real living person.
- **Figures from history** speak only words they actually said or wrote, introduced as such
  ("In her own words, from a letter home in eighteen fifty..."). The narrator can paraphrase
  around them.
- **Animals** may speak in the first person, playfully and clearly as make-believe ("If a
  platypus could talk, it might say..."). Everything they say must still be true.
- A guest moment lasts 30–90 seconds of back and forth. The narrator asks short questions, and
  the guest answers in character with real facts.
- List each guest under `## Cast` with a short character note (personality, pace, accent if
  relevant), which is what the voice is designed from: `- PLATYPUS → voices.platypus: a
  cheerful, quick young platypus`. Avoid caricatured accents. Each guest paragraph starts with
  its label, `PLATYPUS: ...`; the narrator's paragraphs have none (`docs/script-format.md`).
- Keep turns short, usually one paragraph. Each turn is its own TTS request, so a retake of
  one line re-renders only that line, and a speaker change gets a short hand-off gap.
- A custom voice slot is scarce (the plan holds 3, all in use), so reuse a guest voice across
  tours where it fits, or ask before designing a new one (6-sound.md).
- Example: Hobart stop 6 in `tours/hobart/source/working-draft.md`, where the narrator
  interviews a platypus. It was first tried as its own draft, `source/stop-6-platypus.md`.
  That is cheap: `tour check|render|master <slug>
  <stop> --draft <file>.md` builds into `build/<file>/` and never touches the published stops,
  and lines that keep their text and neighbours come from the cache.

## Sound in the script

Mark SFX with cues on their own line at moments that help the story: the creak of a hop kiln,
rain on a forest canopy, a steam whistle in the distance (`docs/script-format.md`).

- `[SFX — splash]`: a one-shot, played in the gap between the paragraphs around it. The gap
  grows by the effect's length, so put it on a beat, after the line it answers.
- `[SFX — river, under]` … `[SFX — river, stop]`: a bed under the speech in between, ducked
  under the voice. Without `stop`, it fades out after the track's last speech.

Use 2–4 per stop, never over a key sentence, and never anything alarming to a driver (README
house rules). Describe each named sound in `## Audio notes` (one-shot or bed, and what it should
sound like), which is where `6-sound.md` takes its `[sfx.<name>]` prompt from. Adding or moving a
cue doesn't re-render any speech.

## Rules checklist before `tour check`

- [ ] Every claim traces to a confirmed item in the research notes.
- [ ] Numbers, years and units are written as words. No digits in the narration.
- [ ] No "look left/right now", nothing aimed at the driver, nothing about the screen except the
      song button (passengers).
- [ ] Each stop fits its time budget (word count ÷ about 110 per minute, plus pauses and the
      song segment).
- [ ] Each title follows the pattern and doesn't spoil the story.
- [ ] Guests follow the rules above and are listed in `## Cast`. Songs are named, explained and
      verified.
- [ ] Every SFX cue is described in `## Audio notes`, and `tour check` finds its
      `[sfx.<name>]` and every cast voice in `tour.toml`.
- [ ] Every unusual name is in `## Pronunciation`.
- [ ] No family names or personal details anywhere in the committed draft.
