# 008: Route and stop tools: `tour route`, `tour plan-check`

Status: done · Priority: medium · Raised: 2026-11-02 (process docs, 004)

## Why

Hobart's `route.json` was fetched from OSRM by hand, and its triggers, radii, `strict` flag and
time budgets were checked by eye and in the simulated drive. `docs/process/1-route.md` and
`2-stops.md` describe the rules. The next tour should have commands that do the fetching and
the checking.

## Now

- `tours/hobart/route.json` (committed in 5c3e28a): `{"outbound": [...], "return": [...]}`, 212
  and 217 points, with no record of how it was made.
- The player draws and simulates `route.outbound` and `route.return` (`site/player/app.js`)
  and arms the next `lookahead` stops, cut short at a `strict` one (`armed()`).

## Change

- **`uv run tour route <slug>`** (`src/audiotour/route.py`, `cli.py`): for each `[route.<leg>]`
  in `tour.toml` (`points` = start, fixed stops as via points, end; optional `wait` minutes
  parked at the end), it asks OSRM's public `driving` server once per leg and caches the answer
  in `tours/<slug>/cache/osrm/` (gitignored), so `--refresh` is needed to ask again. It keeps one
  OSRM vertex every 300 m along the road (`--spacing`) plus the last, and writes `route.json`
  with an extra `seconds` key: OSRM's cumulative driving time at each kept point, per leg. Then
  it prints the leg table (km, minutes, points) and notes any input point more than 50 m from a
  road. `--out FILE` writes elsewhere and compares with the current `route.json`.
- **`uv run tour plan-check <slug>`** (offline, `--route FILE` for another route.json): samples
  the trip every 20 m and places each trigger in sequence. Each trigger goes on the first
  stretch of road inside its zone, after the stop before it, that passes within 100 m of the
  trigger point. It then checks:
  - **On the route:** within 100 m, otherwise an error.
  - **Road time:** from entering this zone to entering the next, using OSRM's `seconds`, plus
    the `wait` of any leg end crossed, or 80 km/h when `route.json` has no `seconds`. It must
    cover the audio, and for a song stop the audio, the song's `length` and 60 s. Otherwise
    it's an error. A plain stop with under 60 s of quiet after it gets a warning.
  - **Audio length:** taken from `build/<id>.mp3` if it exists, else the published
    `site/<slug>/tour.json` `duration`, else estimated from the draft (130 wpm plus pauses,
    head, sting, title and tail). It warns when a published length and the draft estimate
    differ by more than 15%.
  - **Song stops:** `[stops.<id>.song] length` (task 006) is read as `"m:ss"`, `"h:mm:ss"` or
    seconds. A song with an unreadable length is an error. If the draft doesn't name the song
    yet, 60 s more is budgeted for its segment, with a warning.
  - **Radii:** 300-1000 m for drive tours, 25-80 m for walks (`[player] mode`).
  - **`strict`:** wherever the road crosses a stop's zone before its own trigger, it replays
    the player's `armed()` with every earlier-triggered stop handled. A stop that would be armed
    there and isn't the next stop needs `strict = true`, and is an error if that's missing. If
    it is the next stop, it gets a warning that it will play there. Each strict stop gets a
    note saying whether it was needed.
- Decisions taken as defaults (no question needed):
  - The route inputs live in `[route.<leg>]` tables. They sit alongside task 003's
    `[route] end` without touching it.
  - Times are kept in route.json. The `seconds` key flows into tour.json's `route`, and the
    player ignores it, so the schema isn't bumped.
  - The 100 m on-route tolerance is generous, because 300 m chords cut curves.

## Acceptance

- [x] `tour route hobart --out <scratch>` rebuilds the route close to the committed one; the
      committed `tours/hobart/route.json` is unchanged.
- [x] `tour plan-check hobart` passes, against the committed route (80 km/h) and the rebuild
      (OSRM times): 0 errors, 0 warnings, and a note that stop 6's `strict` is needed.
- [x] Unit tests use recorded OSRM responses (`tests/fixtures/osrm/`), never the live service:
      `tests/test_route.py`, 28 tests.

## As built (2026-11-02)

- **How the old route was made:** the committed route thins OSRM's vertices to one every 300 m
  along the road. Its return leg went **via the Salmon Ponds** at Plenty: a 4-point spur, up to
  499 m off the highway, that only a via point at (-42.75321, 146.97) reproduces. Both legs are
  now in `tours/hobart/tour.toml`. The outbound `wait = 30` (the Russell Falls walk) is a
  planning figure, not a measurement.
- **How close (measured 2026-11-02 against today's OSRM):** outbound 200 of 212 points
  identical, return 216 of 217. No point of either route is more than 141 m from the other's
  line (symmetric Hausdorff distance on 20 m samples). Lengths are 71.6 against 71.6 km and
  72.6 against 72.7 km. All the differences are in New Norfolk, where OSRM now takes a parallel
  street. `test_hobart_legs_rebuild_the_committed_route` holds this, from the recorded responses.
- **OSRM annotations leave out turn penalties** (4278 s against the route's 4348 s), so each
  leg's per-segment times are scaled up to its `duration`.
- **plan-check on Hobart found no real problems.** The tightest gap is stop 4 to stop 5:
  159 s spare at 80 km/h, 351 s with OSRM times. Stop 6's trigger is 71 m from the
  simplified route but 1 m from OSRM's full road. That is why there's no "off the route"
  warning under 100 m. Draft estimates are within 6% of the mastered lengths.
- **Not done:** the committed `route.json` has no `seconds`. Running `uv run tour route
  hobart` (without `--out`) adds them, and moves 12 outbound points in New Norfolk by up to
  141 m. Stop 1-8 triggers stay on the route either way.

## Open questions

- Replace Hobart's committed `route.json` with the rebuild (adds `seconds`)? It is harmless to
  the player but changes `site/hobart/tour.json` on the next publish.
- Is `wait = 30` at Mount Field about right? It matters for stop 5 to stop 6. With no
  wait, the 1.3 km of road from the car park out to stop 6 gives 178 s for stop 5's 182 s,
  which is an error. Any real stop at the falls covers it.
