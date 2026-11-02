# 005: Script format v2: cast, guest voices, inline sound effects

Status: todo · Priority: high · Raised: 2026-11-02 (Hobart road test)

## Why

The feedback asks for more sound effects and more voices: a primary narrator who sometimes
interviews an expert, a figure from history or an animal. Today's script contract forbids both,
because it has no speaker labels and no bracketed cues (`docs/script-format.md`).

## Now

- Every track is one voice: `[voices.narrator]` in `tour.toml`, and `render.py` chunks the
  narration with surrounding context.
- The only sound effect is the chime sting before each stop (`[sfx.chime]`, `master.py`).
- `script.py` treats any bracketed text other than `[PAUSE — N SECONDS]` as an error.

## Change

**Script syntax** (the parser and `tour check` enforce it):

- A `## Cast` section (not spoken) lists the speakers. Each one maps to a `[voices.<key>]` in
  `tour.toml` and has a one-line character note, e.g.
  `- PLATYPUS → voices.platypus: a cheerful, fast-talking young platypus`.
- A paragraph that starts with `NAME:` (a cast name in capitals, then a colon) is spoken by that
  voice. Paragraphs without a label belong to the narrator. A label holds only until the end of
  its paragraph, so a long guest speech labels every paragraph. That keeps each paragraph
  readable on its own.
- Sound cues sit on their own line, like pauses:
  `[SFX — kookaburra]` plays `[sfx.kookaburra]` from `tour.toml` at that point.
  `[SFX — rain, under]` starts it as a bed under the following speech, ducked, until
  `[SFX — rain, stop]` or the end of the track.
- `tour check` reports cast names or SFX keys that don't match `tour.toml`.

**Pipeline:**

- **Render:** each speaker run is rendered with its voice. Keep using the per-chunk TTS path,
  so caching and `spend.Guard` keep working, and pass neighbouring text as context so the
  delivery flows. ElevenLabs' text-to-dialogue endpoint is an alternative to evaluate for
  back-and-forth exchanges. Compare the two on one interview before choosing.
- **SFX:** `tour sfx` already generates `[sfx.*]` entries. Each SFX entry gains `level_db` and
  `duck_db`.
- **Master:** assemble the speech runs with short gaps, insert one-shot SFX at their cue points,
  mix beds under speech with ducking, then normalise loudness as today.
- **Voice design:** `tour design` already exists. Record each chosen guest voice in `tour.toml`
  the way the narrator's is recorded (id, source, date, why it was chosen).

## Acceptance

- [ ] A test draft with two speakers, one one-shot SFX and one bed passes `tour check`. Bad
      cast or SFX names fail it.
- [ ] Rendered and mastered, it has both voices, the SFX at the right moments, and speech that
      stays intelligible over the bed (listen on phone speakers, not just headphones).
- [ ] `tests/test_script.py` covers the new syntax, and the prompt in `docs/script-format.md`
      is updated to match the parser.
- [ ] `ledger.jsonl` shows the extra credit cost per stop, so the cost of multi-voice is known.

## Open questions

- Credits: a guest voice and 2–4 SFX per stop costs more than a plain narrator. Check
  `uv run tour account` before rendering a full tour.
