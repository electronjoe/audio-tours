# 005: Script format v2: cast, guest voices, inline sound effects

Status: doing (built; waiting on a phone-speaker listen and the speaker-gap choice) · Priority: high · Raised: 2026-11-02 (Hobart road test)

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

- [x] A test draft with two speakers, one one-shot SFX and one bed passes `tour check`. Bad
      cast or SFX names fail it. (`tours/hobart/source/stop-6-platypus.md` with
      `tour check hobart --draft stop-6-platypus.md`, and `tests/test_script.py`.)
- [ ] Rendered and mastered, it has both voices, the SFX at the right moments, and speech that
      stays intelligible over the bed (listen on phone speakers, not just headphones). Built as
      `build/stop-6-platypus/stop-6.mp3`; the placement is checked by
      `tests/test_master_mix.py`. It still needs a listen.
- [x] `tests/test_script.py` covers the new syntax, and the prompt in `docs/script-format.md`
      is updated to match the parser.
- [x] `ledger.jsonl` shows the extra credit cost per stop, so the cost of multi-voice is known.
      (The `lab-005 …` entries. The real pipeline's proof render came entirely from them, at 0
      credits.)

## Open questions

- Credits: a guest voice and 2–4 SFX per stop costs more than a plain narrator. Check
  `uv run tour account` before rendering a full tour. Answered by the test below: the guest
  costs nothing extra, the SFX about 100 credits per stop.
- Custom-voice limit: the plan allows 3 custom voices. It now holds `Tour-Tasmania-Narrator`,
  `Tour-Platypus` and `Postcards-Guide` (keep that one), so it's full again. A second guest
  voice means a plan upgrade, or guests on premade voices.

## Test results (2026-11-02)

One stop 6 excerpt: the narrator interviews a platypus (11 turns, 688 spoken characters), with
a river bed ducked under the speech and a splash one-shot. It's written in the syntax proposed
above (`lab/005-excerpt.md`) and rendered two ways by the throwaway `lab/voices_005.py`. Every
paid call went through `spend.Guard`, and each is logged in `ledger.jsonl` as `lab-005 …`.
Both versions open with the chime and the stop's cached title.

- **A, stitched:** one eleven_v4 with-timestamps request per turn, with neighbouring turns as
  `previous_text`/`next_text`. Each turn is trimmed to its speech and joined with 0.6 s gaps.
  Output: `build/lab-005/stop-6-excerpt-A-stitched.mp3`, 75 s.
- **B, dialogue:** one `POST /v1/text-to-dialogue/with-timestamps` request with
  `model_id = eleven_v4`, which the endpoint accepts. It's kept as one take, cut once in the
  silence before the splash. Output: `build/lab-005/stop-6-excerpt-B-dialogue.mp3`, 65 s.
  Hand-offs between speakers are 0.25–0.35 s, which is why it runs shorter.

**Credits actually used.** The account went from 22,159 to 22,915 credits used, a total of
756: 527 for the first round with Charlie, then 229 to re-render with `Tour-Platypus`. No
other worktree spent anything in that window.

| Item | Credits | Source |
| --- | --- | --- |
| River bed, 15 s, loop, 1 take | 82 | `character-cost` header |
| Splash, 2 s, 1 take | 11 | header |
| Platypus Voice Design, 1 round (3 previews, 131-character preview text) | ~131 | account delta (the endpoint sends no cost header) |
| A with Charlie: 11 TTS requests, 688 characters | 152 | headers |
| B with Charlie: 1 dialogue request, 688 characters | 151 | header |
| Saving preview 1 as `Tour-Platypus` | 0 | free |
| A with `Tour-Platypus`: 5 platypus turns, 355 characters (the narrator turns were cached) | 78 | headers |
| B with `Tour-Platypus`: the whole dialogue again, 688 characters | 151 | header |

The two methods cost the same: about 0.22 credits per character on this payg plan, whether as
TTS or dialogue. Sound effects cost about 5.5 credits per second. Voice Design came to about
1 credit per character of preview text, charged once per round, not per preview.

**Guest voice.** At first the designed voice couldn't be saved: the account was at its 3/3
custom-voice limit, and TTS rejects an unsaved preview id with a 404. So the first renders used
the premade **Charlie** (young, Australian, energetic), kept as
`build/lab-005/stop-6-excerpt-{A-stitched,B-dialogue}-charlie.mp3`. After a slot was freed,
design preview 1 was saved as **`Tour-Platypus`** (`gDRccCpQyi22aTpudovx`, the preview's id
kept as the voice id, from Voice Design `eleven_ttv_v3` on 2026-11-02). Both excerpts were then
re-rendered with it. All three previews are in `build/lab-005/platypus-design-{1,2,3}.mp3`.

The re-render shows what a voice change costs. With A, only the guest's lines are re-rendered,
78 credits. With B, the whole exchange is re-rendered, 151 credits.

**Ducking.** The bed sits 9 dB below the voice and is pushed down by a sidechain compressor
keyed on the voice (ratio 4). Measured against the voice, it comes out at about −18.5 to
−19.5 dB under speech with Charlie, and about −21.5 dB with the louder `Tour-Platypus`. It's
about −13.5 dB in the gaps. That matches `6-sound.md`. Listen to
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
- **Decided (2026-11-03): A.** The user listened to the Tour-Platypus renders and chose
  `stop-6-excerpt-A-stitched.mp3` ("fantastic! I love this"). Build A, with the voice, sound
  bed and ducking used in that file as the reference. Leave the per-track dialogue switch out
  unless a later tour needs it.

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

## As built (2026-11-03)

Method A, per-speaker TTS, in the real pipeline. `lab/` is gone: the excerpt is now
`tours/hobart/source/stop-6-platypus.md`, and method B's code is in git history (fbd14b5,
`lab/voices_005.py`) if a later tour wants the dialogue endpoint.

- **Parser** (`script.py`). `## Cast` lines are `- NAME → voices.<key>: note` (`->` also
  works, and a note may wrap onto indented lines). `NARRATOR` is always in the cast. A
  paragraph starting `NAME:` is that voice's, with the label stripped. A capitalised `WORD:`
  that isn't in the cast is an error, and a lower-case `Platypus:` matching a cast name is a
  warning. `[SFX — name]`, `[SFX — name, under]` and `[SFX — name, stop]` become `Cue`
  segments. `tour check` reports cast voices and SFX missing from `tour.toml`, unknown modes,
  a `stop` with no bed running, a bed started twice, and an `under` with no speech after it.
- **Render** (`chunks.py`, `render.py`). Each change of speaker starts a chunk, and context
  crosses speakers. Cues don't split chunks. The request shape is unchanged, so the lab's
  cached turns were reused exactly: the proof render cost 0 credits.
- **Master** (`master.py`). The master walks the script's segments over the rendered chunks.
  A one-shot cue cuts its chunk at the paragraph break, with no re-render, and the gap becomes
  `sfx_gap` (0.5 s), the effect, then `sfx_gap`. A change of speaker gets `speaker_gap`
  (0.35 s). Beds fade in 1.5 s before the next speech and out over 3 s from the last speech
  before `stop`. They are ducked by a sidechain compressor keyed on the voice, with its
  threshold set from `duck_db` (ratio 4, the lab's attack and release). `level_db` and
  `duck_db` default to −9. Hobart's river uses `duck_db = -13`, which at this voice level is
  the lab reference's compressor setting exactly. Pauses and one-shots after the last speech
  now play; the old master dropped them, and no Hobart stop has one. `timeline.json` records
  each bed's measured level under speech and in the gaps.
- **Retired.** `[tracks.<id>.voices]`, `[[tracks.<id>.beds]]` and `check_voices` are removed.
  `tour check` reports the two tables if present, and render and master refuse them.
- **Trial drafts.** `--draft <file>.md` on `estimate`, `check`, `render` and `master` reads
  another file in `source/` and builds into `build/<file>/`, sharing the cache and
  `build/sfx/`. `tour save-voice` saves a design preview into a voice slot (free).
- **Hobart is unchanged.** Every stop's dry run is fully cached. Re-mastered from the cache
  into a scratch build, all eight decode to the same audio as `site/hobart/audio/`. The only
  byte difference is the genre tag, which has been "Audio tour" in the code since f44baa7,
  while the published files still say "Audiobook".
- **Proof.** `build/stop-6-platypus/stop-6.mp3` (69 s, 0.35 s hand-offs, bed −23.0 dB under
  speech and −16.3 dB in the gaps). `stop-6-speaker-gap-1.0.mp3` (75 s) uses the reference's
  roughly 1 s hand-offs for comparison. The lab reference measured about 1.0 s of silence between
  turns: its 0.6 s gap plus the trim padding.
