# 1. Route discovery

Goal: the exact path the listener will travel, split into legs, with times, so the stops can be
placed on it and the audio can be budgeted.

## Inputs to get from the traveller

- Start, destination(s), and end (often the start again).
- Fixed stops they will make anyway (a lunch spot, a waterfall walk, a ferry) and roughly how
  long each lasts.
- The date and time of day. These affect wildlife (dusk is when animals are on the road),
  opening hours and the light.
- Who is listening (adults only, or children and their ages), kept in gitignored notes only.
- Anything to avoid: a road they dislike, a detour that isn't wanted.

## Steps

1. **Get the drivable path.** List each leg's points in `tour.toml` (start, fixed stops as via
   points, end), with `wait` for the minutes parked at the leg's end:
   ```toml
   [route.outbound]
   points = [[-42.88199, 147.33654], [-42.68181, 146.71655]]
   wait = 30
   [route.return]
   points = [[-42.68181, 146.71655], [-42.75321, 146.97], [-42.88199, 147.33654]]
   ```
   Then `uv run tour route <slug>` asks OSRM (`router.project-osrm.org`, `driving` profile) for
   each leg, caches the answers in `cache/osrm/`, keeps one point every 300 m along the road,
   writes `route.json` (`{"outbound": [[lat, lon], ...], "return": [...], "seconds": {...}}`,
   where `seconds` is OSRM's driving time at each point) and prints the leg table. `--out FILE`
   writes elsewhere and compares with the current `route.json`. The player draws and simulates
   only `outbound` and `return`.
2. **Check it against how people really drive it.** Compare with Google Maps. If they differ,
   follow the route the traveller will actually take: they will navigate with Google.
3. **Time the legs.** Driving minutes per leg, plus dwell time at each fixed stop. The total
   listening time available is the sum of the leg times minus the quiet stretches (step 4).
4. **Mark the quiet stretches.** These are where audio shouldn't play: complex junctions, town
   centres with turns, roadworks, the last few minutes before arriving (people are looking for
   parking), and long stretches with no phone signal (fine once the audio is downloaded, but
   note them).
5. **Note the out-and-back overlap.** Where the return leg uses the same road, stories have to
   be split between directions (see 2-stops.md, `strict`).

## Output

- `route.json`.
- `[route] end = [lat, lon]` in `tour.toml`: where the trip finishes, usually the last point
  of the return leg. The stop cards' Navigate from here links end there (task 003). Use a
  public place, such as the town centre, never a home address.
- A leg table in `tours/<slug>/plan.md`: leg, distance, minutes, quiet stretches, and the
  listening minutes available.

## Walking tours (task 007)

Use the OSRM `foot` profile, OpenStreetMap paths (Overpass), or the park authority's GPX or
track notes. Record the surface, any steep sections, and where the track is narrow (no stops
there). Time at about 4 km/h on the flat, slower on climbs, plus time spent standing at each
stop.
