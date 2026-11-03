# 010: A base map for each tour, drawn from OpenStreetMap at publish time

Status: doing (on branch `player-redesign`: built, and drawn by the player (task 009 step 6); needs a look on a phone) · Priority: medium · Raised: 2026-11-03 (player redesign demos)

## Why

The map page in task 009 needs land, water, roads and town names under the route, or it's a
line on black. The redesign README (`experiments/ui_ux_redesign/README.md`, "The map") settles
how: no live tiles; draw each tour's map from OpenStreetMap **once**, commit it to
`site/<slug>/`, and let the player draw it as SVG in its own dark style. It works offline,
costs nothing, needs no API key and sends nobody the phone's location.

## Now

The player draws only `route.outbound`, `route.return` and the stops (`renderMap`,
`site/player/app.js:755`). `tour route` (`src/audiotour/route.py`) already fetches from a
public service (OSRM) with a response cache in `tours/<slug>/cache/` and recorded fixtures in
`tests/fixtures/`; this follows the same pattern.

## Change

**`uv run tour map <slug>`** (free) writes `site/<slug>/map.json`:

1. **Area**: the route and stops' bounding box plus a margin (5 km, or 15 % of the larger
   side). Hobart's is about 50 × 25 km.
2. **Fetch** one Overpass API query for the area (`overpass-api.de`, a server-side
   `[timeout:180]`), cached for good by query hash in `tours/<slug>/cache/overpass/`; only
   `--refresh` fetches again. The `User-Agent` names the project and its repo, as Overpass's
   usage policy asks. No mirror servers or paid services. On a timeout or a busy server (HTTP
   429 or 504), wait and retry once, then stop with a message naming the area's size and the
   fix: try again later, or, for a large area, split the query (below). Features:
   - water: `natural=water`, `waterway=riverbank`, `natural=coastline`
   - green: `boundary=national_park`, `leisure=nature_reserve`, large `leisure=park`
   - roads: `highway=motorway|trunk|primary|secondary` (lines)
   - rivers: `waterway=river` (lines)
   - names: `place=city|town|village` nodes
3. **Assemble polygons**: join multipolygon member ways into rings (water, parks). The
   coastline is drawn **as a line** in the first version (see Decisions); filling the sea
   means joining coastline ways into chains, clipping them to the area and closing them along
   its edge (land is on the left of a coastline way), which is the fiddliest geometry here.
4. **Simplify**: project to metres around the tour's centre (the player's projection),
   Douglas–Peucker at about 25 m (the map never zooms closer than a few km wide), drop
   polygons under about 0.05 km² and roads shorter than 300 m, round to whole metres.
5. **Write** `map.json`: `{"version": 1, "origin": [lat, lon], "bbox": [...], "attribution":
   "© OpenStreetMap contributors", "license": "ODbL-1.0", "water": [...], "green": [...],
   "roads": [{"rank": 1-3, "pts": [...]}], "rivers": [...], "places": [{"name", "at", "rank"}]}`,
   coordinates as flat integer arrays. Print its size and warn over 300 KB. **Never write a
   partial file**: if any step fails, nothing is written (a temporary file renamed into place
   at the end), so an older `map.json` stays and a new tour has none. The player draws the
   route without a base map when there's none.

**Publish** adds `"map": "map.json"` to `tour.json` when the file exists (optional field, no
schema bump; documented in `docs/tour-json.md`). The player fetches it with `tour.json`;
**Save** in setup caches it with the audio; the service worker's network-first rule already
covers it.

**Player** (task 009, `map.js`): draws water, green, rivers, roads (width by rank), then the
route, pins and car, with place names at a fixed screen size, labels that would overlap a pin
or each other dropped. Shows the attribution, linking to
`https://www.openstreetmap.org/copyright`.

**Process docs**: a step in `docs/process/1-route.md` after `tour route`: run `tour map`,
look at the map page with `?sim`, commit `site/<slug>/map.json`.

### Licence

OSM data is under the ODbL. The map on screen is a Produced Work and needs the attribution.
`map.json` itself is a derived database published in a public repo, so it's offered under the
ODbL too: the `license` field says so, and a line in `README.md` notes that
`site/*/map.json` is ODbL, © OpenStreetMap contributors.

### Not used

- Tiles from `tile.openstreetmap.org`: its usage policy forbids saving areas for offline use.
- Commercial tile services: free tiers usually restrict offline caching and commercial use.
- Street-level zoom. If passengers ask for it later, the fallback is a Protomaps `.pmtiles`
  extract served from Pages and drawn with MapLibre GL JS (several MB, and the service worker
  must handle range requests, which it currently passes to the network).

## Acceptance

- [x] `uv run tour map hobart` writes `site/hobart/map.json` under 300 KB; a second run is
      served from the cache and writes the same file.
- [x] Unit tests on a recorded Overpass fixture in `tests/fixtures/`: ring assembly, a
      coastline closed along the area's edge, simplification keeps every ring closed, the
      output's shape.
- [x] A fetch that fails twice (a fake fetcher in the test) stops with the message, retries
      exactly once, and leaves an existing `map.json` untouched.
- [x] Publish adds `map` to `tour.json` only when the file exists; `docs/tour-json.md` updated.
- [ ] The Hobart map page shows the Derwent, Mount Field National Park, the Lyell Highway and
      New Norfolk, with the attribution, online and offline.

## Decisions (2026-11-03)

- **Coastline: a line first, then decide on Hobart's data.** The line version proves the
  fetch, cache, simplification, size, drawing, offline and attribution without waiting on the
  hardest geometry. Once the first `tour map hobart` is fetched (free, cached), check where
  OSM's coastline runs up the Derwent and look at the map page with `?sim`. If the unfilled
  water is a corner of the map, ship the line and say so here; if it runs beside the route
  (stops 1, 2 and 8 follow the river), add the sea fill, with a fixture test, before this
  task closes. Either way, add it before a coastal tour.
- **Overpass failures: retry once, then fail with a clear message, now; split the query later.**
  The command runs about once per tour and its answer is cached for good, so a failure costs a
  rerun, not a broken tour. Splitting into one query per feature type (water, green, roads,
  places) and merging the results is built when a tour's area actually times out: Hobart's
  50 × 25 km box shouldn't, so the split code would go untested until then.
- **Never write a partial `map.json`**, and **name the project in the `User-Agent`** (both
  above, under Change).

## As built (2026-11-03)

`src/audiotour/basemap.py`, `uv run tour map <slug> [--refresh]`; tests in
`tests/test_basemap.py` (15) on `tests/fixtures/overpass/hobart-waterfront.json.gz`, the Hobart
answer trimmed to the waterfront and the Derwent, and on small hand-built areas.

- **Hobart's run:** an area of 66 × 38 km (bigger than the 50 × 25 km guessed: the margin is 15 %
  of the 61 km route box), one query, 4540 elements, answered in about 50 s and cached
  (1.9 MB gzipped, `tours/hobart/cache/overpass/`). `site/hobart/map.json` is **96 KB**: 1 land
  polygon, 14 water, 179 green, 110 road chains, 13 rivers, 12 places. A cached rerun writes
  the same bytes.
- **Where the coastline runs:** OSM's `natural=coastline` comes up the Derwent from the south
  edge of the area, past Hobart and Glenorchy, to its head at Granton and the Bridgewater
  bridge, right where stop 1's zone is, and back down the eastern shore. Above Bridgewater the
  river is `natural=water` polygons, which fill anyway. So the unfilled water was beside the
  route for its first 20 km (Hobart to stop 1), not tucked in a corner: **the sea fill is
  built** (Decisions, first point). Stops 2 and 8 at New Norfolk sit by the river polygons.
- **Sea fill:** coastline ways joined without reversing (land is on the left), clipped to the
  area, and closed along its edge, walking anticlockwise from each chain's end to the next
  chain's start; closed rings (islands) are clipped as polygons. map.json then has `land`, and
  the rest of the area is sea. If a clipped chain ends inside the area (data missing), it falls
  back to `coast` lines with a note. Tested on a straight coast both ways round, an estuary in
  two ways with an island, a coast that stops short, and the recorded waterfront (the Derwent
  between Hobart and Bellerive is sea, both shores land).
- **Format:** as planned, plus `extent` (the area in metres), `land` or `coast`, and rings that
  close implicitly, outer rings clockwise on screen and holes anticlockwise, so the player
  draws each class as one nonzero-filled path (`docs/tour-json.md`, "map.json").
- `tour map` also adds `"map": "map.json"` to an already published `tour.json` (Hobart's was);
  publish adds it whenever the file exists.
- `README.md` notes the ODbL for `site/*/map.json`; `docs/process/1-route.md` has the step.
- **Drawn** by task 009 step 6 (see its "As built"): under the route, with the attribution,
  saved by Save, and checked offline by `player_drive.py`. The last acceptance box waits for a
  look on a phone, online and offline (task 009 step 9).

