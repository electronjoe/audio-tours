# Script format

The contract between whoever writes a tour's script and the render pipeline. A draft that
follows it parses with no surprises. Nothing gets spoken by accident, and no track or pause is
silently skipped.

To use it:

1. Paste the prompt below into the chat or tool that writes the script, after the request for
   the story itself.
2. Save the result as `tours/<slug>/source/working-draft.md`.
3. Run `uv run tour check <slug>`. It lists every line that breaks the contract and exits
   non-zero on errors. `render` and `master` refuse a draft that has errors.

- **Errors** mean the parse is wrong: a track heading the parser can't read, a bracketed cue
  or list that would be read aloud, a speaker label that isn't in the cast, a cast voice or
  sound cue that `tour.toml` doesn't define, or no tracks at all. Fix them in the draft, or add
  the missing `[voices.<key>]` or `[sfx.<name>]` to `tour.toml` (`6-sound.md`).
- **Warnings** are style the narrator may trip on, such as digits or symbols. Narration usually
  renders fine with years written as digits, so treat warnings as things to listen for, not
  blockers.

The parser (`src/audiotour/script.py`) also accepts an en dash or a hyphen where the contract
says em dash, since models often swap them. The prompt still asks for the em dash.
`tests/test_script.py` checks that the example in the prompt passes with no errors or warnings,
so the prompt can't drift from the parser.

## What the pipeline does with it

- **Speakers.** Each `## Cast` entry, `- NAME → voices.<key>: note`, maps a label to a
  `[voices.<key>]` in `tour.toml`. A paragraph starting `NAME:` is spoken by that voice, with
  the label stripped. Unlabelled paragraphs, and `NARRATOR:` ones, are the narrator's. Each
  change of speaker starts a new TTS chunk, with the neighbouring text of both speakers sent as
  context, and the master joins speakers with a short gap (`[master] speaker_gap`, default
  0.7 s) instead of the narrator's paragraph gap.
- **One-shot effects.** `[SFX — splash]` plays `[sfx.splash]` in the gap where it stands.
  The gap grows to `sfx_gap` (default 0.5 s), the effect, then `sfx_gap` again. A cue between
  two paragraphs of one chunk cuts the chunk's audio at the paragraph break. It doesn't split the
  chunk, so adding a cue to a rendered script costs nothing.
- **Beds.** `[SFX — river, under]` fades the bed in over 1.5 s before the next speech.
  `[SFX — river, stop]` fades it out over 3 s from the end of the speech before it. A bed with
  no `stop` fades out after the last speech. A `loop = true` effect repeats to fill the span.
  The bed sits at `level_db` relative to the voice in the gaps and is pushed a further
  `duck_db` down under speech by a sidechain compressor keyed on the voice. Both are set per
  effect in `tour.toml` and default to −9.
- **Retired.** The pre-005 `[tracks.<id>.voices]` paragraph-number map and
  `[[tracks.<id>.beds]]` are no longer read. `tour check` reports them, and `render` and
  `master` refuse to run while they're there. Use labels and cues instead.

## Prompt

````markdown
Output the finished audio tour script as one Markdown document in exactly the format below.
A program reads it: anything that breaks these rules is either spoken aloud by mistake or
silently dropped, so follow them exactly.

## Structure

1. The first line is `# <Tour title>`.
2. Material before, between or after the tracks (subtitle, narrator notes, sources,
   pronunciation guide, audio notes) is never spoken. Put each piece under its own `## `
   heading that does NOT start with `Script:`.
3. Each track is one section whose heading line is exactly:
   `## Script: <Label> — <Title>`
   - Each track is one stop of the tour. <Label> is `Stop` and the stop number in digits,
     such as `Stop 1`, numbered 1, 2, 3, ... in the order the stops play.
   - The separator is a space, an em dash (—, U+2014), then a space. Never a hyphen (-) or
     an en dash (–).
   - <Title> is the plain title: no timings, brackets or final punctuation.
   - The narrator announces each track's title before it (for example "The bay and its
     people."), so don't repeat the label or title as the first line of the narration.
4. Optionally, the line straight after a track heading may be a length note in italics that
   starts with "About", e.g. `*About 210 words, about 1.5 minutes.*` It is not spoken. Don't
   start any other italic paragraph with "About".
5. A track ends at the next `## ` heading.

## Cast

If anyone other than the narrator speaks, list them before the first track in a section
headed exactly `## Cast`. It is never spoken. One line per speaker:
`- NAME → voices.<key>: <one-line character note>`, for example
`- PLATYPUS → voices.platypus: a cheerful, quick young platypus, light Australian accent`.
NAME is in capitals. <key> is lower case and names the voice the producer will design from
the note. The narrator needs no entry.

## Inside a script section, only these are allowed

- Paragraphs of narration, separated by one blank line. Every word is spoken exactly as written.
- Guest paragraphs: a paragraph that starts with a cast NAME, a colon and a space, e.g.
  `PLATYPUS: A minute? I'm on my dinner break.` The label is not spoken and holds only to the
  end of its paragraph, so label every paragraph of a long speech. Paragraphs without a label
  are the narrator's. Never start a paragraph with any other capitalised word and a colon.
- Pause markers, each on its own line with a blank line before and after:
  `[PAUSE — 3 SECONDS]`
  Use an em dash, a whole or decimal number, and the word SECONDS. Use pauses for thinking time
  after a question to the listener. Default length: 3 seconds.
- Sound cues, each on its own line with a blank line before and after:
  - `[SFX — splash]` plays a short effect once, in the gap between the paragraphs around it.
  - `[SFX — river, under]` starts a background sound under the speech that follows.
  - `[SFX — river, stop]` fades that background sound out. Without it, it runs to the end
    of the track.
  The name is lower case, one word or words joined by hyphens. Use 2–4 cues per track, never
  in the middle of a key sentence, and nothing that could alarm a driver (no sirens, horns,
  brakes, crashes or phone sounds). Describe each named sound in `## Audio notes`.

Not allowed inside a script section: sub-headings (`###`), bulleted or numbered lists,
tables, blockquotes (`>`), links, footnotes, horizontal rules, timestamps, and any other cue
or stage direction in brackets or parentheses, e.g. "(pause)", "[slowly]", "(laughs)". Bold and
italics are stripped and don't change the delivery, so they are pointless there.

## Write for the ear

- Write numbers, years, dates, measurements and money as words, exactly as they should be
  spoken: "nineteen thirty", "the seventeenth of September", "seven metres",
  "twenty twenty-two". No digits in narration.
- Spell out what a narrator would have to interpret: "for example" not "e.g.", "about" not
  "~", "per cent" not "%", "and" not "&".
- Spell names and non-English words correctly, with their proper diacritics (such as
  macrons). Never put phonetic respellings in the narration. List pronunciations in a
  separate `## Pronunciation` section instead (word, guide, source, and whether a fluent
  speaker has confirmed it).
- Sound effects go in the script as cues (above). Describe each one in a separate
  `## Audio notes` section: the name, one-shot or background, and what it should sound like.

## Example

```
# Hobart to the Falls

Audio tour script · two stops

## Narrator notes

Confirm the pronunciation of Tyenna before recording.

## Cast

- PLATYPUS → voices.platypus: a cheerful, quick young platypus, light Australian accent

## Script: Stop 1 — The Bridge over the Derwent

*About 40 words, about 20 seconds.*

Up ahead, the road crosses the River Derwent.

How do you think people crossed it before there was a bridge?

[PAUSE — 3 SECONDS]

Keep your answer in mind. We will find out soon.

## Script: Stop 2 — The Town by the River

[SFX — river, under]

New Norfolk sits beside the same river, further upstream. Excuse me, platypus?

PLATYPUS: Shh. I'm diving.

[SFX — splash]

[SFX — river, stop]

Then we will leave you to your dinner.

## Audio notes

- river: background. A gentle shallow river over stones, no music, no voices.
- splash: once. A small animal slipping into calm water.

## Pronunciation

| Word | Guide | Source | Confirmed |
| --- | --- | --- | --- |
| Tyenna | ... | ... | no |
```

## Before you reply, check

- Every track heading matches `## Script: <Label> — <Title>`, with an em dash.
- Every pause is its own paragraph matching `[PAUSE — N SECONDS]`, and every sound cue is its
  own paragraph matching `[SFX — name]`, `[SFX — name, under]` or `[SFX — name, stop]`, all
  with an em dash.
- Every speaker label is a NAME listed under `## Cast`, and every `under` has a matching
  `stop` or runs to the end of its track on purpose.
- No script section contains digits, lists, sub-headings, blockquotes or other bracketed cues.
- Return the whole document in one Markdown code block, with nothing before or after it.
````
