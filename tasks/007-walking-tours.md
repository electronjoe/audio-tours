# 007: Walking tours (trails and city walks)

Status: todo (breadcrumbs only) · Priority: low · Raised: 2026-11-02 (Hobart road test)

## Why

> Open the door to walking guides: national park hiking trails (stops along the trail) or
> city walking tours.

## What carries over

Most of it: a sequence of GPS-triggered stops, offline audio (essential on trails with no
signal), queue-not-interrupt, Start here, Reset, and the whole content pipeline.

## What differs

| | Drive | Walk |
| --- | --- | --- |
| Trigger radius | 300–1000 m | 25–80 m |
| GPS accuracy gate (`MAX_ACCURACY`) | 150 m | about 40 m, and no larger than the radius. Under tree canopy or between tall buildings fixes get worse, so allow a slightly larger radius there. |
| Speed (simulation, ETA) | 22 m/s | 1.4 m/s |
| Stop length | about 3 minutes | 1–2 minutes. Budget by walking time between stops. |
| Order | sequence (`lookahead` 2) | Trails: sequence. City walks are often any order, so add `order = "any"`: every unplayed stop is armed and plays once. |
| Instructions | never "look left now" | "Look up at the third window" is fine, because the listener is standing still |
| Maps link (003) | `travelmode=driving` | `travelmode=walking` |
| Phone | mounted, screen on | **in a pocket, screen off (see below)** |
| Route source | OSRM driving | OSRM foot profile, OpenStreetMap paths, the park authority's track notes or GPX |

**The hard problem: a pocketed phone.** On Android, Chrome stops geolocation when the screen is
off or the tab is in the background, so a pure web page can't trigger stops from a pocket.
Options, in order of effort:

1. Keep the screen on (wake lock, already used) with the phone in hand or on a lanyard. This
   costs battery, and the screen should be dimmed.
2. A "Next stop in 120 m" mode: the walker glances at the screen, and a chime plays when they
   arrive. Still needs the screen on.
3. A thin Android wrapper (a Trusted Web Activity or Capacitor) with a foreground location
   service. This is real app work. Only do it if walking tours prove worth it.

Test option 1 on an Android phone for a 1-hour walk (battery drain, how many triggers are
missed) before choosing.

## Breadcrumbs (for when this starts)

- `tour.toml` `[player]`: `mode = "drive" | "walk"`, `order = "sequence" | "any"`,
  `max_accuracy`, `sim_speed`. `tour publish` already reads `[player].lookahead`. Add the
  others there and copy them into `tour.json`.
- `site/player/app.js`: `MAX_ACCURACY` and the simulation speed are constants. Make them
  `S.tour.max_accuracy ?? 150` and `S.tour.sim_speed ?? 22`. `armed()` needs a branch for
  `order = "any"`.
- `docs/process/1-route.md` and `2-stops.md` have walking notes.
- Safety rules for walking scripts: never stop the walker on a cliff edge, a road crossing or
  a narrow track. Put stops at lookouts, benches and wide places.

## Acceptance (when picked up)

- [ ] A short local test walk (5 stops) published with `mode = "walk"` triggers every stop on
      a real walk with the screen on.
- [ ] The battery drain over an hour is recorded here.
