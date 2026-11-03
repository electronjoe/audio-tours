# 009: Player redesign: the glance screen and a map page (A.3)

Status: doing (on branch `player-redesign`, steps 1–5 of 9 done) · Priority: high · Raised: 2026-11-03 (player redesign demos)

## Why

The player is one long scrolling page of cards (`site/player/tour.html`): status chips, Start,
Now playing, Next stop, the stop list, and a "More" drawer holding the route sketch, plain files,
the event log, Simulate and Reset. It works, but in a car it asks to be read, and nothing shows
at a glance where the next story is.

`experiments/ui_ux_redesign/` tried three directions and three ways to add a map to the calmest
one. The README there picks **A.3** (`a3-map-page.html`), with two changes: songs visible before
they're offered, and a base map pre-drawn from OpenStreetMap at publish time (task 010).

## Now

| Piece | Where |
| --- | --- |
| Page markup (template for `site/<slug>/index.html`) | `site/player/tour.html` |
| Styles, shared with the tour list `site/index.html` | `site/player/style.css` |
| Engine and rendering in one file | `site/player/app.js` (904 lines) |
| Rendering | `renderStatus` app.js:728, `renderNow` :635, `renderOffers` :620, `songCard` :571, `renderNext` :667, `renderStops` :694, `renderMap` :755, `renderLog` :799, `render` :812 |
| Wiring | `main` app.js:824 (element ids, click delegation) |
| Navigate links | the marked block app.js:112–138, run under Node by `tests/test_navigate.py` |
| Tests | `tests/player_drive.py` drives it by selector (`#start`, `#resume`, `#now`, `#next`, `details.stop`, `button.here`, `#more`, `#log-box`, `#status`, `#download`, `#dl-card`, `#continue`, `#restart`, `a.nav`, `a.song-play`, `a.song-link`) and by `window.__tour` |

## Change

**Rebuild the view; keep the engine.** Everything below the line "what plays when" (the cursor,
lookahead and `strict`, queue-never-interrupts, Start never plays, coarse and settling fixes,
catch-up after a gap, the song room check, Resume, stale progress, the event log, offline
cache, Media Session, wake lock) stays as it is and keeps its tests. The redesign replaces how
it's shown and touched. Where the view needs a new action (dismissing an offer), the engine
gets a small, logged function, not new rules.

### Screens

As in the demo, with the real player's states:

1. **Setup** (before Start; follows the system light/dark theme). Title, "N stories · K km ·
   about H h M min", then a checklist:
   1. *Save the stories to this phone*: `downloadAll` with a progress bar, "No signal: X %
      saved" on failure, ticked when every stop's audio is cached.
   2. *Let stories start by themselves*: asks for location (`getCurrentPosition`), ticked from
      `navigator.permissions.query({name: "geolocation"})`. Denied shows how to unblock it
      (today's toast text).
   3. *Add to home screen* (optional): Chrome's `beforeinstallprompt`; hidden when already
      running standalone or when Chrome doesn't offer it.

   "See all N stories →" opens the story list. The footer holds **Start the tour** (with "Not
   saved yet: stories will need phone signal" above it when step 1 isn't done). With stale
   progress (over 8 hours old) it holds **Start from the beginning** and **Continue (next:
   stop N)** instead.

   **Setup only shows on a first visit or with stale progress.** After a reload with fresh
   progress (Chrome discarding the tab behind Maps or Spotify, mid-drive), the page opens on
   the car screen, not started, and one tap carries on: the ring's centre is **▶ Resume 3 ·
   title** when a story was cut off, with a smaller **Carry on without it** below (arms GPS,
   plays nothing, the cut-off story becomes skipped); or **Carry on** when nothing was playing
   (arms GPS, plays nothing, like Start). This keeps task 001's rule (no button plays anything
   its label doesn't name) at today's one tap: `resume()` already calls `start()`.
2. **Car screen**, page one (always dark). Status row: "All set", or warning pills (GPS
   blocked / no fix / weak / settling, Screen may sleep, Not saved, Simulating ×N) and a
   **Map ›** button. The hero is a ring:
   - *Between stories*: distance to the next trigger and minutes in the ring; "Next story",
     title, place below; the ring fills from the last story's zone to the next one's, by road.
     Dock: **Play it now** (or **Queue it next** while one plays), the same plain button at
     any distance.
   - *Playing*: the ring is progress, its centre a big pause/play button; "Now playing · N of
     M", title, "m:ss left"; "Then N · title" when one is queued. Dock: **Skip story**.
   - *Blocked autoplay*: the centre is a play button, "Ready: tap to play" (today's Tap to play).
   - *Arrived / no more stories*: ✓, "N of M stories heard"; dock: **Start over**.

   One offer card at a time sits between the hero and the dock, in this order: **Pick up where
   you left off** (Resume, after a reload: Play it / Skip), **Passed while you were away**
   (Play it / Skip), **A song for this stretch** (▶ Play on Spotify / No thanks, or the Save
   for later line when there's no room). The dock's right button is always **All stories**.

   **Landscape** (a phone in a sideways mount, about 390 px tall): two columns, the ring and
   caption on the left, the offer card and dock on the right. CSS only, one
   `@media (orientation: landscape) and (max-height: 500px)` block. Stacked, the dock would
   fall off the bottom. The manifest doesn't lock orientation.
3. **Map**, page two (swipe left or Map ›). Full-screen dark map: route, the part already
   driven, numbered pins with zones, ♪ on song stops, the car. **‹ Story** and **Whole route /
   Follow car** at the top. The bottom card shows, by priority: a tapped pin's details (state,
   place, length, its song; Play now / Navigate from here), the song offer, Now playing, or
   Next story with distance. "© OpenStreetMap contributors" when the base map is drawn.
   A story starting, a Resume or missed offer, or arriving returns to page one; a song offer
   doesn't.
4. **All stories** (full-screen sheet over either). One row per stop: number (✓ heard,
   dashed skipped or missed), title with ♪, place · length · state · distance away, "Not
   saved" when its audio isn't cached, and "♪ Then a song: title · artist". Tapping a row
   opens **Play now** (`startHere`; Restart when it's playing), **Queue next**, **Navigate
   from here**, then smaller: open the trigger point in Google Maps, the song's ▶ Play on
   Spotify, **Mark unplayed**. Below the list: **Why did that play?** (the event log, as
   today's `describe`), **Start over** (today's Reset, with its confirm), **Plain audio files**,
   the help text from today's "More", and **Simulate drive** when the URL has `?sim`.

### Where every current feature goes

| Today | After |
| --- | --- |
| Start tour | Setup footer: Start the tour (never plays, task 001) |
| Stale progress: Start from the beginning / Continue | Setup footer, in place of Start |
| Resume button in the Now card | The ring's centre after a reload: ▶ Resume N · title, or Carry on without it |
| Download for offline card | Setup check 1; "Not saved" pill on the car screen |
| Status chips | Car screen status row (setup shows them as check states) |
| Now playing card, bar, Pause, Skip | Ring, centre button, dock Skip |
| Tap to play | Ring centre play button |
| Next stop card, ▶ Play now / Queue it to play next | Ring and caption; dock button (no longer emphasised within 2 km: `NEAR` goes) |
| Passed while you were away | Offer card, now with a Skip (new `dismissMissed`) |
| Song card | Offer card on page one *and* the map page, now with No thanks (new `dismissSong`) |
| Stop list and its expanded actions | All stories rows |
| Song line in a stop's card | All stories row and the map pin card |
| More → Route sketch | The map page |
| More → Event log | All stories → Why did that play? |
| More → Plain audio files, help, Simulate, Reset | All stories, below the list |
| Toast | Unchanged, raised above the dock |

### Engine changes (small, each logged)

- `dismissMissed(s)`: the offer goes and the stop stays `skipped` (event `dismiss`).
- `dismissSong()`: `S.song = null` (event `song-dismiss`).
- `carryOn()`: after a reload, start without the cut-off story; the pending stops become
  `skipped` (event `resume-declined`).
- Delete `NEAR` (task 001's 2 km emphasis on Play now). It existed so Play now was less
  tempting than the green Start on the same page; Start and Play it now are never on one
  screen now. An early tap is recoverable (Mark unplayed, or Play now on arrival) and often
  deliberate. Add a note to task 001.
- **Progress along the route**, for display only (triggering stays straight-line):
  `S.along`, the index of the route point the car is at, over outbound then return. It only
  moves forward and searches a window ahead (about 6 km), so the out-and-back overlap near New
  Norfolk can't snap the car to the return leg; after a gap it searches the whole remaining
  route. It gives the ring's distance and fill (along the road to the next stop's zone, not a
  straight line), the minutes (from `route.seconds` when the route has it, else speed), the
  map's driven line and the car's heading. Without a route, or more than 300 m off it, it
  falls back to today's straight line and the 8 km fill.
- Expose what the view needs on `window.__tour` (already `S`, `onFix`, `trigger`, `startHere`,
  `skip`, `audio`, `save`).

### Code layout

No framework and no build step, as now. Split `app.js` into classic scripts loaded in order:

- `app.js`: the engine (state, persistence, log, geometry, navigate block, queue, audio,
  cache, GPS, simulation, songs' room check). Keeps the navigate block's marker comments.
- `view.js`: setup, car screen, offers, All stories, pager, toast; one `render()`.
  Buttons use `data-act` (as in the demo) plus stable ids/classes for tests.
- `map.js`: projection (equirectangular around the tour's centre, metres, as `renderMap`
  does), drawing, camera (follow: car and next stop; whole route), pin taps. It draws the
  route and stops from `tour.json`; when task 010's `map.json` exists it draws that underneath.
  It does nothing while page one is showing (no animation frames off-screen).
- `style.css`: the demo's tokens (setup follows the theme; `.car` is always dark). The tour
  list (`home.html`, `tour_card()` in `publish.py`) is restyled to match the setup screen, one
  row per tour: "Drive · 8 stories · 51 km · about 1 h 10 min". Restyle only; no
  thumbnails or descriptions until there are tours to browse. The old CSS goes.

### Content fields (optional, no schema bump)

The demo's pins and cards use short labels and teasers that `tour.json` doesn't have.

- `label` (stop): a short pin label ("Granton"). Missing: the pin shows only its number.
- `teaser` (stop): one line for the pin card. Missing: the card shows `place`.

Both go in `tour.toml`, are copied by publish and documented in `docs/tour-json.md`. Adding
labels to Hobart costs nothing, so it's allowed there. Teasers are proven on the next tour.

### Safety and both audiences

The driver needs to touch nothing after Start, and nothing big changes on screen except at a
story's start or end. The map is a passenger feature and stays off page one; nothing ever
switches to it by itself. Tap targets at least 48 px (dock 64 px); text sizes from the demo;
`prefers-reduced-motion` turns off the pulse and smooth paging.

## Steps

Each step ends with `player_drive.py` passing and a screenshot set, so it can merge on its own.

1. **Tests first.** Move `player_drive.py`'s selectors behind a small helper table (one place
   to change them), and add a screenshot pass: setup (light, dark), reloaded (Resume, Carry
   on), between stories, playing, queued, blocked, each offer, All stories, log, map (follow,
   whole route, pin card), arrived; the car screen in portrait and landscape.
2. **Split the code** (`app.js` → `app.js` + `view.js` + `map.js`) with the current UI, no
   visible change. `test_navigate.py` and `player_drive.py` pass untouched.
3. **Setup and car screen** (page one, offers, All stories, landscape, the tour list). Add
   `dismissMissed`, `dismissSong`, `carryOn`; delete `NEAR`. Update `player_drive.py`'s
   selector table and add: Start shows the car screen; a reload mid-story opens the car
   screen, and Resume plays that story in one tap; Carry on without it plays nothing and
   marks it skipped; a missed or song offer can be dismissed; ♪ marks in All stories.
4. **Route progress** (`S.along`) for the ring and minutes. Test: along the Hobart drive the
   ring's distance never increases between consecutive outbound points by more than GPS noise,
   and the return leg never shows outbound progress.
5. **Map page** with the route, pins, zones, car and driven line from `tour.json`, the pager
   and the return-to-page-one rules. Tests: pins = stops, the map page returns to page one when
   a stop starts and stays for a song offer, the pin card's Play now starts that stop.
6. **Base map** from task 010 drawn under the route, with the attribution, cached for offline.
7. **`label` and `teaser`**: publish, docs, Hobart labels.
8. **Docs**: `docs/tech-stack.md` (player rows), `docs/tour-json.md` (new fields), the help
   text, tasks 001/003/006 pointers that name old UI pieces (Now card, More → Event log).
9. **Road test** on an Android phone in a car: portrait and landscape mounts, glare at
   midday, a swipe while parked, the Navigate and Spotify round trips.

Publish templates after each template change (`uv run tour pages`): `tests/test_publish.py`
fails if the committed Hobart page doesn't match `tour.html`.

## Acceptance

- [ ] Every feature in the table above is reachable in the new UI.
- [ ] `tests/player_drive.py hobart` passes with every check it has today, plus the new ones
      from steps 3–5.
- [x] `uv run pytest` passes (`test_publish`, `test_navigate`).
- [ ] The screenshot set for step 1 is reviewed in light and dark.
- [ ] Works offline after Save, including the map page.
- [ ] Road-tested on an Android phone; findings added here.

## Decisions (2026-11-03)

Settled before any code; each is written into the sections above.

- **Reload mid-drive: the car screen, one tap.** Fresh progress opens the car screen with
  ▶ Resume N · title (or Carry on) in the ring; setup shows only on a first visit or with
  progress over 8 hours old. Rejected: setup then a Resume offer card (two taps and a
  checklist mid-drive, worse than today), and a Resume button on setup (one tap, but the
  checklist screen mid-drive).
- **Landscape: two columns, CSS only.** Rejected: locking portrait (works only when installed,
  and shows sideways in a landscape mount), and waiting for a road test (the dock is
  unreachable meanwhile).
- **Ring: along the road (step 4).** Road distance, OSRM minutes, filling from the last zone
  to the next; the map's driven line and heading need it too. Display only: triggering stays
  straight-line. Rejected: today's straight line and 8 km fill (short on winding roads,
  minutes that vanish at a light).
- **Tour list: restyled to match**, in step 3, so the old CSS can go. Rejected: keeping the
  old look in a legacy block or its own stylesheet.
- **Play it now: one plain button at any distance; `NEAR` goes.** Rejected: keeping the 2 km
  emphasis (its reason, sitting beside Start, is gone), and hiding it when far (the dock would
  change shape while driving).

## As built

**Step 1 (2026-11-03).** `tests/player_drive.py` reaches the UI only through `SEL`, one table:
a tuple is a sequence of taps, `"sheet"` opens All stories unless it's open, `None` marks
something the UI lacks (its screenshot is skipped). `text_of()` reads an element after the taps
that lead to it. The screenshot pass (`SCENES`) shoots 18 states into
`tours/<tour>/build/shots/`: setup light and dark, the driving states dark in portrait (412×860)
and landscape (860×390). `--no-shots` and `--shots-only` pick a part. `fresh()` stops the old
page writing to localStorage before it clears it: a story ending between the clear and the
reload used to leave fresh progress, which now opens the car screen instead of setup.

**Step 2.** `app.js` (engine, with `loadTour()`), `map.js` (the old route sketch) and `view.js`
(everything drawn, `main()`), loaded in that order. The screenshots matched step 1's pixel for
pixel but for clocks and distances.

**Step 3.** Setup, the car screen, the offers, All stories, landscape and the tour list.
- Engine: `declineResume`, `carryOn`, `dismissMissed`, `dismissSong`, `unplay`, `resetTour`
  (logged as `resume-declined`, `dismiss`, `song-dismiss`, `reset`); `downloadAll` reports
  through `S.saving` and `S.saveError` instead of a button; `S.savedAt` decides setup or car
  screen; `NEAR` is gone (note added to task 001).
- The view keeps changing numbers (distance, ring, time left, row distances) out of the HTML and
  updates them in place every second, so a GPS fix never rebuilds a button under a finger.
- Choices the plan left open: while a story plays the dock is **Skip story** (the plan's
  "Queue it next while one plays" is in All stories → Queue next); with nothing for the left
  button (a Resume after a reload, a blocked start) the dock is All stories alone. The trip time
  under the title uses `route.seconds`, else 80 km/h like `plan-check` (Hobart's route has no
  `seconds`: "144 km · about 1 h 50 min"). The tour list uses the same figures (`publish.trip`).
- The map page exists from step 3 with the old route sketch, so the route stays reachable;
  step 5 replaces it.
- Test change beyond selectors: the old reload check tapped Start and then Resume. The settled
  decision removes Start from that screen, so the check is now "the reload opens the car
  screen; nothing plays or starts until a tap names it; Resume plays the story in one tap".
  "Start plays nothing" is still checked after the first Start, and after Continue and Start
  from the beginning.

**Step 4.** Route progress, in `app.js` ("route progress"), display only.
- `buildPath()` joins outbound and return into one path at load (`S.path`: points, metres,
  OSRM seconds or null) and places each stop's zone on it in sequence, as `plan-check` does:
  `{entry, at, exit}` in metres, or null if the route doesn't pass within 300 m.
- `locate()` moves `S.along` (`{k: segment, m: metres}`) on every used fix: forward only, 6 km
  ahead, or the whole rest of the route after a gap (and when nothing in the window is within
  300 m). Where the route passes the same road twice, the earlier pass wins: the first place
  within 50 m of the nearest, then the nearest within 1 km after it; a place more than 50 m
  behind the car doesn't count. The first version took the earliest near place alone, and held
  the car 10 m short of Hobart's turnaround and then on the outbound road for a point of the
  return leg; the test caught it.
- `S.along` is saved with progress, so a reload on the return leg stays on it (where the legs
  share the road from Hobart to Bushy Park, a fresh search would put the car on the outbound
  leg). Start over and Start from the beginning clear it. `S.offRoute` starts true each
  session: until a used fix lands within 300 m of the route, the ring is the straight line.
- `toStop(i)` gives the ring: by road to the zone's entry, filling from the previous stop's zone
  exit; minutes from `route.seconds`, else `recentSpeed()` (the higher of the latest fix's and
  the 2-minute median, which the song room check now shares, so the lights don't blank the
  minutes). Off the route, or past the zone without it triggering: the straight line and the
  8 km fill, as before.
- Tests (player_drive.py, "Route progress", 9 checks): every route point measures by road; on
  the outbound leg the distance never grows between consecutive points and the fill never
  shrinks; no return point shows outbound progress; the road is longer than the straight line
  somewhere; minutes from speed on Hobart, and from a `route.seconds` fixture when it has one;
  a reload 5 km before stop 8 stays on the return leg; a gap that lands at New Norfolk on the
  way out jumps there on the outbound leg. 73 checks, 0 failures.

**Step 5.** The map page (`map.js`, rewritten; `mapCardHTML` and `backToStory` in `view.js`).
- SVG in metres around the route and stops' centre (the projection map.json uses), built the
  first time the page shows. Layers: a slot for the base map (step 6), the stops' zones at
  their real radius (lit when armed, playing, queued or offered), the route, the driven line
  (the route up to `S.along`), pins and the car. Line widths are `vector-effect:
  non-scaling-stroke`; pins and the car are scaled by metres per pixel, so they keep their
  size. Pins that would sit within 30 px of an earlier one move right (Hobart's stops 3 and 7
  share a point; 2 and 8 are 900 m apart).
- The car sits on the route at `S.along` and points along it; off the route, at the fix,
  pointing the way the last two fixes went.
- Camera: **Whole route** fits every pin and zone; **Follow car** frames the car and the story
  it's heading for (or the one playing), at least 4 km across; a tapped pin is framed while
  following. The frame is the part of the screen the buttons and card leave free (above the
  card in portrait, left of it in landscape, where the card is a right-hand column). It glides
  by animation frames only while the map page is showing, and snaps when the page arrives or
  with reduced motion.
- The card, by priority: a tapped pin (state, place, length, song; **Play now**, which is
  `startHere`, and **Navigate from here**), the song offer (its own id, `map-offer`), Now
  playing with time left, No more stories, Next story with distance and minutes.
- Back to page one: when what's playing, the Resume offer after Continue, the missed offers or
  "finished" change to something new. A story ending or a song offer doesn't.
- Tests (player_drive.py, "Map page", 15 checks): pins = stops with ♪ on the song's; car and
  driven line drawn; following frames the car and the next pin; Whole route shows every pin;
  a pin's card and its Play now; a story starting (by pin, by GPS), a missed offer and
  arriving bring page one back; a story ending and a song offer don't; No thanks on the map.
  `SEL` has `map_whole` and `map_pin` (from following: Whole route, then the pin), so the
  map-whole and map-pin scenes are shot. 88 checks, 0 failures.

## Progress (2026-11-03)

Work is on the branch `player-redesign`, not yet merged; the branch's copy of this file has the
full "As built" notes. Done there: step 1 (selector table and screenshot pass in
`tests/player_drive.py`), step 2 (`app.js` split into `app.js`, `map.js`, `view.js`), step 3
(setup, car screen, offers, All stories, landscape, the tour list), step 4 (route progress for
the ring), task 010's `tour map` (Hobart's `map.json`), step 5 (the map page). `uv run pytest`
110 passed; `player_drive.py hobart` 88 checks, 0 failures. Next: steps 6–8. Step 9 (road test)
is Scott's.

