# Script format

The contract between whoever writes a book's script and the render pipeline. A draft that
follows it parses with no surprises. Nothing gets spoken by accident, and no track or pause is
silently skipped.

To use it:

1. Paste the prompt below into the chat or tool that writes the script, after the request for
   the story itself.
2. Save the result as `books/<slug>/source/working-draft.md`.
3. Run `uv run audiobook check <slug>`. It lists every line that breaks the contract and exits
   non-zero on errors. `render` and `master` refuse a draft that has errors.

- **Errors** mean the parse is wrong: a track heading the parser can't read, a bracketed cue
  or list that would be read aloud, or no tracks at all. Fix them in the draft.
- **Warnings** are style the narrator may trip on, such as digits or symbols. Gate Pā rendered
  fine with years written as digits, so treat warnings as things to listen for, not blockers.

The parser (`src/audiobook/script.py`) also accepts an en dash or a hyphen where the contract
says em dash, since models often swap them. The prompt still asks for the em dash.
`tests/test_script.py` checks that the example in the prompt passes with no errors or warnings,
so the prompt can't drift from the parser.

## Prompt

````markdown
Output the finished audiobook script as one Markdown document in exactly the format below.
A program reads it: anything that breaks these rules is either spoken aloud by mistake or
silently dropped, so follow them exactly.

## Structure

1. The first line is `# <Book title>`.
2. Material before, between or after the tracks (subtitle, narrator notes, sources,
   pronunciation guide, audio notes) is never spoken. Put each piece under its own `## `
   heading that does NOT start with `Script:`.
3. Each track is one section whose heading line is exactly:
   `## Script: <Label> — <Title>`
   - <Label> is a word plus a number written in digits, such as `Chapter 1`, `Scene 2` or
     `Workshop 1`, or a single word for an unnumbered track, such as `Introduction` or
     `Afterword`. Number each kind of track 1, 2, 3, ... in order.
   - The separator is a space, an em dash (—, U+2014), then a space. Never a hyphen (-) or
     an en dash (–).
   - <Title> is the plain title: no timings, brackets or final punctuation.
   - The player announces each track as "<Label in words>. <Title>." (for example
     "Scene Two. The bay and its people."), so don't repeat the label or title as the first
     line of the narration.
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
# Old Tom and the Bargain of Twofold Bay

Audiobook script · about 2,000 spoken words

## Narrator notes

Confirm the pronunciation of Thaua and beowa with a Thaua source before recording.

## Script: Scene 1 — The splash

*About 130 words, about 1 minute.*

A tail rises out of the sea and comes down hard. Slap.

Why would anyone row toward a killer whale?

[PAUSE — 3 SECONDS]

These people were not running away from it. They were answering it.

## Script: Scene 2 — The bay and its people

Twofold Bay is on the south coast of New South Wales, beside the town of Eden.

## Pronunciation

| Word | Guide | Source | Confirmed |
| --- | --- | --- | --- |
| Thaua | ... | ... | no |
```

## Before you reply, check

- Every track heading matches `## Script: <Label> — <Title>`, with an em dash.
- Every pause is its own paragraph matching `[PAUSE — N SECONDS]`, with an em dash.
- No script section contains digits, lists, sub-headings, blockquotes or bracketed cues.
- Return the whole document in one Markdown code block, with nothing before or after it.
````
