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
  or list that would be read aloud, or no tracks at all. Fix them in the draft.
- **Warnings** are style the narrator may trip on, such as digits or symbols. Narration usually
  renders fine with years written as digits, so treat warnings as things to listen for, not
  blockers.

The parser (`src/audiotour/script.py`) also accepts an en dash or a hyphen where the contract
says em dash, since models often swap them. The prompt still asks for the em dash.
`tests/test_script.py` checks that the example in the prompt passes with no errors or warnings,
so the prompt can't drift from the parser.

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

## Inside a script section, only two things are allowed

- Paragraphs of narration, separated by one blank line. Every word is spoken exactly as written.
- Pause markers, each on its own line with a blank line before and after:
  `[PAUSE — 3 SECONDS]`
  Use an em dash, a whole or decimal number, and the word SECONDS. Use pauses for thinking time
  after a question to the listener. Default length: 3 seconds.

Not allowed inside a script section: sub-headings (`###`), bulleted or numbered lists,
tables, blockquotes (`>`), links, footnotes, horizontal rules, timestamps, speaker labels,
and any cue or stage direction in brackets or parentheses, e.g. "(pause)", "[slowly]",
"[SFX: waves]". Bold and italics are stripped and don't change the delivery, so they are
pointless there.

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
- Sound-effect and music ideas go in a separate `## Audio notes` section that names the
  track and paragraph, never in the narration.

## Example

```
# Hobart to the Falls

Audio tour script · two stops

## Narrator notes

Confirm the pronunciation of Tyenna before recording.

## Script: Stop 1 — The Bridge over the Derwent

*About 40 words, about 20 seconds.*

Up ahead, the road crosses the River Derwent.

How do you think people crossed it before there was a bridge?

[PAUSE — 3 SECONDS]

Keep your answer in mind. We will find out soon.

## Script: Stop 2 — The Town by the River

New Norfolk sits beside the same river, further upstream.

## Pronunciation

| Word | Guide | Source | Confirmed |
| --- | --- | --- | --- |
| Tyenna | ... | ... | no |
```

## Before you reply, check

- Every track heading matches `## Script: <Label> — <Title>`, with an em dash.
- Every pause is its own paragraph matching `[PAUSE — N SECONDS]`, with an em dash.
- No script section contains digits, lists, sub-headings, blockquotes or bracketed cues.
- Return the whole document in one Markdown code block, with nothing before or after it.
````
