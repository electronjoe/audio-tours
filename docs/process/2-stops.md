# 2. Stop discovery and trigger placement

Goal: a list of stops. Each one is a place worth a story, a trigger point on the route that fires
early enough for the story to finish before the next, and a time budget.

## Finding candidate places

Walk the route (1-route.md) and list everything a story could hang on: towns, rivers, bridges,
historic buildings, farms and industries visible from the road, lookouts, national park
entrances, sites that were in the news, places named after something odd. At this stage, cast
wider than you need. Research (3-research.md) decides which ones carry a story.

## Placing triggers

- **Place the trigger before the landmark, not at it.** Put the trigger point on the route a few
  minutes (or a few kilometres) before the landmark, so the story is under way as it comes
  into view. Use a point from `route.json` so it is guaranteed to be on the road.
- **Radius.** Driving: 300–1000 m. Use a larger radius on fast roads, so at least two GPS fixes
  land inside, and a smaller one where roads run close together. Parked stops (car park,
  visitor centre): about 300 m.
- **Spacing.** Allow the story's length plus about a minute of quiet between stops. At 80 km/h,
  a 3-minute stop needs about 4–5 km of road. A stop with a song segment (006) needs another
  30–60 seconds of road, and the song itself plays outside the tour, so allow its length too if
  the next trigger shouldn't fire while Spotify has the screen.
- **Avoid quiet stretches** (1-route.md, step 4).
- **Out-and-back roads.** Stops play in sequence, and only the next two unplayed stops are
  armed (`lookahead`). A return-leg stop at the same place as an outbound one stays silent on
  the way out. If a return stop's zone lies on the road to the stop before it, set
  `strict = true` (Hobart stop 6), and run `tests/player_drive.py` to prove it.
- **Parked stops** suit a longer story, or one meant for looking around ("you're standing among
  the tallest flowering plants on Earth"). Hobart stop 5 played at the visitor centre car park.

## Record in `tour.toml`

```toml
[stops.stop-3]
lat = -42.73207
lon = 146.90506
radius = 1000
place = "Approaching Bushy Park and the hop fields"   # shown on screen
# strict = true          # waits for the stop before it
# nav = [lat, lon]       # where Maps should take you, if not the trigger (task 003)
# nav = false            # or: a drive-by stop that isn't a Maps waypoint
```

Each stop card's **Navigate from here** link routes through this stop and every later one to
`[route] end` (1-route.md). Give a stop `nav` when the place you would actually drive to,
such as a car park, isn't its trigger point. Trigger points sit on the route already, so
Maps passes a drive-by stop's point anyway; `nav = false` only spares the arrival prompt.

Then add a row per stop to `plan.md`: stop, place, direction (outbound, return or parked),
budget in seconds, and the minutes of road until the next trigger.

## Walking tours (task 007)

Radius 25–80 m. Put stops where it is safe to stand: lookouts, benches, wide places. Never on
a narrow track, a cliff edge or a road crossing. Budget 1–2 minutes per stop.
