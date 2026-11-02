# 007: Walking tours (trails and city walks)

Status: todo (breadcrumbs only; background GPS measured) · Priority: low · Raised: 2026-11-02 (Hobart road test)

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
| Phone | mounted, screen on | **in hand or on a lanyard, screen on**: a pocketed phone gets no GPS (see below) |
| Route source | OSRM driving | OSRM foot profile, OpenStreetMap paths, the park authority's track notes or GPX |

**The hard problem: a pocketed phone.** Measured on 3 Nov 2026 with `site/lab/gps-probe/`
(Android Chrome 156; details in task 006): **while the page is hidden, it gets no fixes.** That
holds with the screen locked and with another app in front, and also while audio is playing.
With the screen locked and a quiet audio loop playing, the page stayed alive, unfrozen and with
timers running, yet received zero fixes for 1m19s. So neither a silent loop nor the tour's own
audio keeps a pocketed walk working. When the page comes back, fixes resume 4–7 s later, but
the first ones are ±26–54 m, larger than a walking trigger radius, and take 5–10 s to settle
under ±15 m.

Options, re-ranked after the test:

1. **Screen on with a wake lock (the only browser-only option).** The player already holds one.
   The phone stays in hand, on a lanyard or in a clear arm or chest pouch. Use a dark,
   low-brightness walk view to save battery (most of these phones have OLED screens). If the
   screen goes off anyway, triggers resume after unlocking. With the 40 m accuracy gate, the
   first 5–10 s of rough fixes are ignored, and 006's catch-up offers a stop passed while away.
   The battery cost is **unmeasured** (the test phone was charging); see the follow-up test
   below.
2. **A glance mode** ("Next stop in 120 m", plus a chime on arrival). This is option 1 with a
   simpler screen, not a separate route around the problem.
3. **A native wrapper with a foreground location service** (Capacitor or a small native app
   with a background-geolocation plugin). This is the only way to trigger from a pocket. A
   Trusted Web Activity doesn't help, because it runs in Chrome and has the same limits. This
   is real app work, so only do it if walking tours prove worth it.

Ruled out by measurement: an audio loop (or tour audio) to keep GPS alive with the screen off.

**Optional follow-up test (battery, about 40 minutes).** Open `site/lab/gps-probe/` on the phone,
**unplugged** and above 80 %:

1. Tick *Keep screen on*, set the screen brightness low and tap *Free test*. Walk or ride for 30
   minutes with the screen on.
2. Tap *Done*, then *Share log*.

The probe logs the battery level every time it changes, so the log gives the drain per 10
minutes with GPS at 1 fix/s and the screen on. Fix gaps should stay at about 1 s throughout. If
the drain is 10 % an hour or less, a 2-hour walk is fine on a charged phone. At 20 % an hour or
more, the walk view needs to be darker, or walks need a power-bank note.

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
- [x] Whether GPS works with the screen off is measured: it doesn't, even with audio
      playing (3 Nov 2026, above).
- [ ] The battery drain over an hour is recorded here. (The optional follow-up test above gives a first figure.)
