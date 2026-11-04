# Plan: Barossa Valley

The working plan for `barossa`, started 2026-11-04 (docs/process/). It is committed and public:
say "the family" or "the passengers", never names, ages or travel dates. Those go in
`source/research.md`, which is gitignored.

## Route (1-route.md)

A commercial coach day tour from Adelaide's north into the Barossa Valley. The route is an
estimate (1-route.md, "When someone else drives"; task 013); the evidence and sources are in
`source/research.route-estimate.md`.

Likely venues, in the published order, with how likely each is to be on the day:

| Venue | Area | Included |
| --- | --- | --- |
| Château Yaldara | Lyndoch | high |
| Seppeltsfield (palm avenue, Vasse Virgin, JamFactory) | Seppeltsfield | high |
| Browns Barossa Donuts | Tanunda | moderately high |
| Hemera Estate | Lyndoch / Rowland Flat | high |
| Kies Family Wines (lunch, about 90 min) | Lyndoch | high |
| Jacob's Creek (drive-by) | Rowland Flat | moderate |
| Barossa Valley Chocolate Company | Tanunda | high |
| Ubertas Wines | Light Pass / Angaston road | moderately high |
| Lambert Estate (advertised substitute) | Angaston | low |

Roads: Port Wakefield Road, Northern Expressway, Gawler, Barossa Valley Way toward Lyndoch
(moderately high); within the valley, back and forth between Lyndoch, Seppeltsfield and
Tanunda (moderate); the return to Adelaide (low to moderate). The last two stops' order
varies between traveller accounts.

`tour route barossa` (OSRM through the venues in order; waits at venues between the ends
aren't modelled):

| Leg | km | Minutes | Wait at end | Quiet stretches | Listening minutes |
| --- | --- | --- | --- | --- | --- |
| outbound: terminal, Bolivar, the eight venues to Ubertas | 141 | 142 driving, plus about 5 h at venues | 40 | the venues (the guide talks there) | the drives between venues |
| return: Ubertas, Bolivar, terminal | 85 | 70 | 0 | none known | all of it |

## Stops (2-stops.md)

Pins and radii from the stops report (`source/research.stops.md`), geocoded with
OpenStreetMap on 2026-11-04. `[route] estimated = true`, so plan-check allows kilometre radii
and triggers off the route (2-stops.md, "Uncertain routes"). Stop 2 may fire in the transfer
car before the bus boards: accepted. Budgets are the report's suggested lengths.

| Stop | Place | Direction | Radius km | Budget s | Road minutes to next trigger |
| --- | --- | --- | --- | --- | --- |
| 1 | Outer Harbor terminal (starts inside its zone) | outbound | 2 | 180 | 19 |
| 2 | OTR Bolivar | outbound | 5 | 180 + song 238 | 46 |
| 3 | Château Yaldara, Lyndoch | outbound | 2 | 210 | 11 |
| 4 | Seppeltsfield | outbound | 2 | 240 + song 149 | 9 (plus the visit) |
| 5 | Tanunda | outbound | 2.5 | 210 | 15 |
| 6 | Hemera Estate, Lyndoch | outbound | 1.5 | 210 | 101 (lunch and three venues) |
| 7 | Gawler (route passes 1.4 km away) | return | 8 | 180 + song 147 | 17 |
| 8 | Bolivar wetlands | return | 10 | 180 | 34 to the end |

`uv run tour plan-check barossa`, 2026-11-04: 8 stops, 0 errors; warnings only for no audio yet.

## Topics (4-topics.md)

Audience: `curious-adults` (audiences.md). Working titles from the stops report; the script
author may sharpen them to the "The <noun> That..." pattern.

| Stop | Title | Anchor story | Side facts | Wildlife | National or state | Song | Guest | SFX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | The Dolphins That Started a Fad | Billie, released 1988, and the tail-walking fad (Bossley et al. 2018) | Adelaide Dolphin Sanctuary: a working port with mangroves | dolphins, mangroves | | | | |
| 2 | Two Maps of the Same Country | Kaurna Country; the 1836 Letters Patent promise and what colonisation did | Ngadjuri, Peramangk and Kaurna; a free settlement, not convicts | | founding of South Australia | Ngana Nyunyi, Tilly Tjala Thomas | | |
| 3 | The Inventor and the Popping Bottles | Hermann Thumm: interned 1941–46, sparkling wine in beer bottles, Yaldara 1947 | fermentation; the château came in the 1960s | | WWII civilian internment | | Thumm, in his memoir's words? | |
| 4 | A Promise Longer Than a Lifetime | 1878: a barrel not to be bottled for a hundred years | palms planted for Depression work from 1929; the 1888 gravity winery | | the Depression | Time In A Bottle, Jim Croce | | |
| 5 | When a Language Became Suspect | German-speaking settlers before 1871; the 1841 arrivals and Bethany; 1917: 52 schools closed, 69 places renamed | Old Lutherans and coerced worship; not every migrant a refugee | | WWI at home | | | |
| 6 | The Tiny Insect and the Old Vines | Hemera's 1912 Grenache; phylloxera kept out of South Australia | Old Vine Charter ages; microbats in vineyards | microbats, beneficial insects | biosecurity | | an expert: a vine-health scientist? | |
| 7 | The Town That Entered a Song Contest | Gawler's 1859 competition; the 1977 national song poll | Carleton's words, Linger's music | | the national song | Song Of Australia, Peter Dawson | | |
| 8 | The Airport Without Runways | shorebirds from Siberia and Alaska on the flyway | Bolivar's polishing lagoons (SA Water, 2019) | shorebirds | conservation | | a sharp-tailed sandpiper? | |

Songs: three, on stops 2, 4 and 7: no two back to back, and each has 9–46 minutes of road
after it. Chosen for the strongest ties: a South Australian discovery (2), a song everyone
knows on a perfect metaphor (4), and the very song the story is about (7). Not used: The
Promise (The Dolphin Song) and Here Comes the Sun (weak ties), Die Gedanken Sind Frei (strong
for stop 5, but it would sit next to stop 4's song), I'm Still Standing (a stretch), and
Arrival of the Birds (a lovely closer, but next to stop 7's song). All three links verified
with Spotify on 2026-11-04.

Balance:

- [x] No two anchor stories in a row from the same category. (3–5 are all history, but
      different kinds: one man's internment, an estate's cellar, a community's migration.)
- [x] At least 2 stops with wildlife likely on that stretch, and one with something to spot or
      count. (Dolphins at 1, microbats at 6, shorebirds at 8; the palms to spot at 4.)
- [x] At least 2 stops connect to the national or state picture, with the main sides given
      fairly. (2 the founding, 5 the First World War, 6 biosecurity, 7 the national song.)
- [x] 2–4 songs, not on back-to-back stops or before a short gap. (2, 4, 7.)
- [x] 1–3 guest moments, ideally an expert, a historical figure and an animal. (Thumm at 3,
      a vine-health scientist at 6; no animal.)
- [x] 2–4 SFX per stop where they add something. (3–4 cues, 2 effects per stop.)
- [x] First Nations history is present and handled with care. (2; also 5 and 8.)
- [x] The day has a shape: gripping first, the big story at the parked stop, a lighter close.

## Scripts (5-scripts.md)

Agreed with the user on 2026-11-04. Written into `source/working-draft.md` in batches, with
the user reviewing each batch before the next.

Approach, per stop (about 3–4 minutes, about 400–520 words at about 130 a minute):

- Shape: a hook (a scene or a question), a story with a turn, a second layer for the listener
  who already knew the first (the science, the source that complicates it), and a close that
  starts an argument over the next glass. No quiz pauses (`curious-adults`).
- Facts only from the fact banks in `source/research.stops.md`, within their wording limits,
  plus the sourced additions in `source/research.md` ("Music" and "Thumm's own words"). A new
  fact goes into `research.md` with its source before a script uses it.
- Wide triggers: "around this estate", "this district", "nearby". The one look-out line is the
  Seppeltsfield palms on the approach. No tasting talk: the live guide covers the venues.
- Song segments on stops 2, 4 and 7, about 100 words: song and artist, why it's here, one
  gripping sourced fact, then an invitation to tap the button. No lyrics.
- Guests: Hermann Thumm at stop 3, speaking only his memoir's words (`research.md`, "Thumm's
  own words", from *The Road to Yaldara* via Loveday Lives); a vine-health scientist (a role,
  not a real person) at stop 6. Both on premade library voices (`uv run tour voices`); the
  free custom slot is in reserve. Alternative to the scientist: a clever sharp-tailed
  sandpiper at stop 8.
- SFX: 2–3 gentle cues per stop (harbour water, popping corks, a quiet cellar, shorebirds),
  each in `## Audio notes` with an `[sfx.<name>]` in `tour.toml`, not generated yet.

Titles (the house pattern, no spoilers):

| Stop | Title |
| --- | --- |
| 1 | The Dolphin That Started a Fashion |
| 2 | The Map That Leaves Things Out |
| 3 | The Bottles That Popped Under the Huts |
| 4 | The Wine That Must Not Be Bottled |
| 5 | The Towns That Changed Their Names |
| 6 | The Insect That Must Stay Out |
| 7 | The Town That Held a Song Contest |
| 8 | The Airport That Has No Runways |

Batches:

- [x] 1. Stops 1 and 2, plus the whole document's skeleton (`## Cast`, `## Audio notes`,
      `## Pronunciation`) so `uv run tour check barossa` runs from the start. User review.
      Written 2026-11-04: stop 1 399 words (3.1 min), stop 2 465 words with the song segment
      (3.6 min); `[voices.thumm]` (premade Bill) and `[voices.scientist]` (premade Charlie);
      four SFX prompts, not generated. `tour check`: 0 errors, 0 warnings. Awaiting review.
- [x] Optional ear check: a paid render of stop 1 in the new narrator voice (about 500
      credits), only with the user's go-ahead. Done on stop 2 instead (its First Nations
      names), 610 credits; voice only, at `build/ear-check/stop-2-voice-only.mp3`.
- [x] 2. Stops 3–5 (Thumm; the Time In A Bottle segment). User review.
      Written 2026-11-04: stop 3 451 words (3.5 min), stop 4 584 with the song segment
      (4.5 min), stop 5 461 (3.5 min); six SFX prompts, not generated. `tour check`: 0 errors,
      0 warnings. Awaiting review.
- [x] 3. Stops 6–8. Then a `teaser` per stop in `tour.toml`; `tour check`, `tour estimate`,
      `tour plan-check` clean; titles and Topics balance boxes here; the render cost estimate
      and `tour account` for the user's go-ahead before any paid render.
      Written 2026-11-04: stop 6 442 words (3.4 min), stop 7 432 with the song segment
      (3.3 min), stop 8 369 (2.8 min). Teasers added. `check` 0/0, `plan-check` 0/0 (song
      naming now ignores a version note such as "(version 2)"). Render estimate in Spend.
      Awaiting the user's go-ahead.

## Status (2026-11-04, evening: rendered and published)

Done: route estimate and stops research (`source/research.route-estimate.md`,
`source/research.stops.md`, both private), stops pinned in `tour.toml`, `route.json` built,
`site/barossa/map.json` drawn. New series narrator, Tour-Australia-Narrator; Hobart's two
custom voices deleted, leaving one free slot.

Scripts: all eight stops written in `source/working-draft.md`, all three batches reviewed and
approved by the user. Every new fact is in `source/research.md` with its source (sections
"Stops 1 and 2", "Stops 3–5", "Stops 6–8", "Music", "Thumm's own words"). Guest voices are
premade (`[voices.thumm]` Bill, `[voices.scientist]` Charlie). 16 SFX cues plus the chime
have `[sfx.*]` prompts in `tour.toml` (generated: see Sound). Teasers on all stops.
`tour check`: 0 errors, 0 warnings; `tour plan-check`: 0 errors, 0 warnings; `pytest`: 115
passed. Pipeline fix: song naming checks ignore a trailing version note (`songs.base_title`,
used by `songs.check` and `route.py`), with a test.

Ear check: stop 2 narration rendered (610 credits) and approved by ear; it sits in
`build/stop-2/` and is reused by the full render (0 chars to send). A voice-only listen copy
is at `build/ear-check/stop-2-voice-only.mp3`.

Sound (2026-11-04): 18 SFX clips generated; the chime is take 2, picked by ear. Narration
rendered for stops 1 and 3–8 (stop 2 from the ear-check cache). All eight stops mastered
(−16.4 LUFS) and published to `site/barossa/` (26.2 MB), with the tour list updated.

- Beds: four takes (cellar, vineyard, village, harbour) came back mostly sub-bass rumble,
  which LUFS barely counts, so the first master boosted them to −6 to −15 dB under speech
  (cellar +1 dB in the gaps). Pipeline fix: an optional `highpass` (Hz) per effect, applied
  before the level is measured and set (`master.highpass`, with a test). All nine beds use
  `highpass = 120`; they now sit 20–27.5 dB under speech (camp-night, dusk and village on the
  quiet side: listen on a phone).
- `tour check` 0/0; `tour plan-check` 0/0 with the real audio lengths (tightest gap: stop 4,
  456 s needed with the song, 539 s of road, before the visit); `pytest` 116 passed
  (`test_hobart_pages_match_committed` now copies every published tour, for the tour list).
- `tests/player_drive.py barossa`: the drive plays all eight in order, each by GPS, no
  interruptions; songs, map page, pins, labels, teasers and offline all pass. It reports
  failures that come from the test's Hobart assumptions, not the player: the route starts
  and ends inside stop 1's zone (so Start, Start from the beginning and the coarse-fix check
  find stop 1 playing, and the slow-link check times out), and it treats stops 6–8 as the
  return leg (Barossa's stop 6 is outbound). With a start 3 km outside stop 1 (a scratch copy),
  only those and the ring remain.
- One real quirk: after stop 6 the next story is Gawler (stop 7, return leg), whose zone the
  outbound route already passed; that looks to be why the progress ring falls back to a straight-line distance
  during the afternoon venues. Display only; stop 7 still triggers by GPS on the way home.

Next: the trip. Afterwards, write what worked into "After the trip"; candidate tasks: make
`player_drive.py` take the start and return-leg stops from the tour, and the ring for a
return-leg stop whose zone the outbound route has already passed.

## Spend (6-sound.md)

| Step | Estimate (credits) | Actual (ledger) | Account before | Account after |
| --- | --- | --- | --- | --- |
| Narrator Voice Design, 2 rounds plus 2 stopped attempts (2026-11-04) | about 1,000 | about 2,000 (the stopped attempts were charged) | 41,577 left | 39,577 left |
| Ear check: stop 2 narration (2026-11-04) | about 610 | 610 | 39,577 left | 38,967 left |
| SFX: 18 clips, 155.5 s (chime ×2, 16 cues ×1) (2026-11-04) | about 855 | 850 | 38,967 left | 38,215 left (752) |
| Full narration, stops 1 and 3–8 (stop 2 cached) (2026-11-04) | about 4,094 (dry run) | 4,084 | 38,215 left | 34,025 left |

The account reports usage late: right after the narration it read 34,278, later 34,025. Over
both steps the account fell 4,942 against 4,934 in the ledger.

## After the trip

What worked and what didn't. Turn anything general into a task in `tasks/` or an edit to
`docs/process/`.
