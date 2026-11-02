# 005: Script format v2: cast, guest voices, inline sound effects

Status: doing · Priority: high · Raised: 2026-11-02 (Hobart road test)

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
  `uv run tour account` before rendering a full tour. Answered by the test below: the guest
  costs nothing extra, the SFX about 100 credits per stop.
- Custom-voice limit: the account holds 3 of 3 custom voices (the Hobart narrator and two from
  another project). A designed guest voice can't be saved until a slot is freed or the plan
  is upgraded. That's the user's decision.

## Test results (2026-11-02)

One stop 6 excerpt: the narrator interviews a platypus (11 turns, 688 spoken characters), with
a river bed ducked under the speech and a splash one-shot. It's written in the syntax proposed
above (`lab/005-excerpt.md`) and rendered two ways by the throwaway `lab/voices_005.py`. Every
paid call went through `spend.Guard`, and each is logged in `ledger.jsonl` as `lab-005 …`.
Both versions open with the chime and the stop's cached title.

- **A, stitched:** one eleven_v4 with-timestamps request per turn, with neighbouring turns as
  `previous_text`/`next_text`. Each turn is trimmed to its speech and joined with 0.6 s gaps.
  Output: `build/lab-005/stop-6-excerpt-A-stitched.mp3`, 73 s.
- **B, dialogue:** one `POST /v1/text-to-dialogue/with-timestamps` request with
  `model_id = eleven_v4`, which the endpoint accepts. It's kept as one take, cut once in the
  silence before the splash. Output: `build/lab-005/stop-6-excerpt-B-dialogue.mp3`, 64 s.
  Hand-offs between speakers are 0.25–0.35 s, which is why it runs shorter.

**Credits actually used.** The account went from 22,159 to 22,686 credits used, a total of
527. No other worktree spent anything in that window.

| Item | Credits | Source |
| --- | --- | --- |
| River bed, 15 s, loop, 1 take | 82 | `character-cost` header |
| Splash, 2 s, 1 take | 11 | header |
| Platypus Voice Design, 1 round (3 previews, 131-character preview text) | ~131 | account delta (the endpoint sends no cost header) |
| A: 11 TTS requests, 688 characters | 152 | headers |
| B: 1 dialogue request, 688 characters | 151 | header |

The two methods cost the same: about 0.22 credits per character on this payg plan, whether as
TTS or dialogue. Sound effects cost about 5.5 credits per second. Voice Design came to about
1 credit per character of preview text, charged once per round, not per preview.

**The designed platypus voice wasn't used.** Saving it failed because the account is at its
3/3 custom-voice limit, and TTS rejects an unsaved preview id with a 404. Both versions use
the premade **Charlie** (young, Australian, energetic) instead. The three design previews are
in `build/lab-005/platypus-design-{1,2,3}.mp3` for listening.

**Ducking.** The bed sits 9 dB below the voice and is pushed down by a sidechain compressor
keyed on the voice (ratio 4). Measured against the voice, it comes out at about −18.5 to
−19.5 dB under speech and about −13.5 dB in the gaps. That matches `6-sound.md`. Listen to
both versions on a phone speaker before settling the levels.

**Extrapolation.**

| | Per stop | Per 8-stop tour |
| --- | --- | --- |
| Plain narration (about 2,200 characters) | ~480 | ~3,900 |
| Guest moment, either method | +0, because the guest's lines replace narrator lines | +0 |
| SFX: one 15 s bed and 1–3 one-shots of 2 s, 1 take | +95–115 | +750–920 |
| SFX with 2 takes each | +190–230 | +1,500–1,850 |
| Guest voice design, 1–3 guests × 1–2 rounds | one-off | +130–800 |
| **Total** | | **~4,800–6,500** |

Add about 20% for retakes. With about 42k credits left this period, the targets in
`docs/process/4-topics.md` (1–3 guests, 2–4 SFX per stop) are affordable, so they're
unchanged.

### Recommendation

**Method.** Make **A, per-speaker TTS,** the default, and keep **B** as an option for a
single interview block if it sounds clearly better in the car. The cost doesn't decide it, so
these points do:

- A fits the existing pipeline. `chunks.plan_track` already splits chunks when the voice
  changes, and caching, `spend.Guard`, manifests and per-paragraph timestamps carry over.
- With A, editing or retaking one line re-renders only that line, a few credits. With B,
  changing any line re-renders the whole exchange, about 150–250 credits per interview.
- B sounds more like a real conversation: tight hand-offs, and voices that react to each
  other. Its limits:
  - At most 2,000 characters per request.
  - Only 100 characters of outside context, so the join to the narrator's chunks either side
    may shift tone.
  - Its `voice_segments` are back to back with no gaps, so cue points have to be found by
    silence detection.
  - A seed doesn't guarantee the same take twice.
- To get some of B's flow into A, shorten the gap at a speaker change to about 0.35 s. Keep
  the narrator's own paragraph gap within a turn.
- Confirm by listening to both files in the car. If B wins clearly, add a per-track switch
  such as `[tracks.<id>] dialogue = true` that renders consecutive labelled turns as one
  dialogue request.

**Syntax.** Keep the proposal above. It parsed without ambiguity in the lab. Refinements for
the real parser:

- A `NAME:` label counts only when NAME is listed in `## Cast`. Any other capitalised word
  followed by a colon is an error, never spoken. The label is stripped before TTS.
- A one-shot cue on its own line plays in the gap between the paragraphs around it, and that
  gap is lengthened by the effect's length. This works the same for both methods.
- An `under` bed fades in about 1.5 s before the next speech. A `stop` fades it out over about
  3 s across the next gap.
- SFX entries gain `level_db` (bed level in the gaps, relative to the voice, default −9) and
  `duck_db` (extra reduction under speech, default about −9, done with a sidechain
  compressor).
- Retire the existing `[tracks.<id>.voices]` paragraph map and `check_voices` quoting check
  once labels exist.
