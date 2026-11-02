# 004: Process and rule documents

Status: doing · Priority: high · Raised: 2026-11-02 (Hobart road test)

## Why

The Hobart tour's route, stops, research and scripts were produced ad hoc. The research was
done outside this repo (`tours/hobart/source/research.txt`, which is gitignored because it names
the family). The next tour should follow a written process that carries the road-test feedback
forward:

- Research **much more broadly**, then downselect into the stops: wildlife you are likely to
  see, national and state context (primary industries, major news and controversies), music,
  and more.
- **Music** in the tour, with Spotify links: a passenger loves music, and a song tied to the
  drive would be a highlight. Each song stop also gets spoken time explaining the song and why
  it belongs here (see 006).
- **More sound effects.** The ElevenLabs SFX API is already wired in.
- **More voices.** Keep a primary narrator, and add interviews now and then with experts, people
  from history, even animals.
- **Keep what worked:** both adult and child audiences, an educational aim, captivating
  historical stories, and chapter titles like "The Road That Tried to Sink".

## Change

First drafts written 2026-11-02 under `docs/process/`:

- [x] `README.md`: stage overview, the Hobart feedback, house rules
- [x] `1-route.md`: route discovery
- [x] `2-stops.md`: stop discovery and trigger placement
- [x] `3-research.md`: the broad research sweep
- [x] `4-topics.md`: downselecting research into stops
- [x] `5-scripts.md`: writing scripts (style and rules)
- [x] `6-sound.md`: voices, sound effects, songs
- [x] `CLAUDE.md` at the repo root points agents at these documents

Still to do:

- [ ] Use the documents on the next tour and revise wherever they were wrong or vague.
- [ ] Once 005 lands, fold `docs/script-format.md` (the parser contract) into the scripts
      process.
- [ ] Add a research-notes template, `tours/<slug>/source/research.md` (gitignored like
      `research.txt`), so the sweep has a fixed shape.

## Acceptance

- [ ] A new tour can go from "drive from A to B" to a published tour by following
      `docs/process/` alone, without consulting this conversation.
