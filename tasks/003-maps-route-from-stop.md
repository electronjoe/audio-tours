# 003: Google Maps route from each stop onward

Status: doing (deployed; needs a check on an Android phone) · Priority: medium · Raised: 2026-11-02 (Hobart road test)

## Why

> For each step in the audio tour, can we offer a Google Maps link that opens that step and
> onward as a multi-stop route?

Yes. Google Maps URLs support multi-stop directions, and on Android the link opens the Maps
app.

> **Since task 009 (2026-11-03)** there are no stop cards: Navigate from here is on each story
> in **All stories** (with "Open the trigger point in Google Maps" below it) and on each pin's
> card on the map page. `navLink` is unchanged.

## Now

Each stop card has "Open trigger point in Google Maps", a single-point search link
(`mapsLink` in `site/player/app.js`).

## Change

Add **Navigate from here** to each stop card:

```
https://www.google.com/maps/dir/?api=1
  &destination=<lat,lon of the final point>
  &waypoints=<lat,lon>%7C<lat,lon>%7C...      (pipe-separated, URL-encoded)
  &travelmode=driving                          (walking for walk tours, see 007)
```

- Leave out `origin` so Maps starts from the phone's current location.
- **Points:** this stop and every later stop, in sequence. Use a stop's `nav` coordinates if
  `tour.toml` gives them, otherwise its trigger point. Then add the tour's `end` point (new
  `[route] end = [lat, lon]`, e.g. Hobart) as the destination. Drop a point that repeats the one
  before it. Non-adjacent repeats are fine and wanted: stop 3 and stop 7 share a point, and
  that is what makes Maps drive out and back.
- **Limit:** Google's docs allow up to 9 waypoints plus the destination outside mobile
  browsers, and about 3 in a mobile browser. On Android the app should take 9. If there are
  more points than that, keep the first 9 and make the 10th the destination, and label the
  link "Navigate (next 10 stops)".
- **`nav` per stop** (optional, in `tour.toml`): the place you would actually drive to, such as
  a visitor centre car park rather than a trigger point on the road shoulder. Set `nav = false`
  for a drive-by stop that shouldn't be a waypoint. Trigger points sit on the route anyway, so
  Maps passes them without being told.
- Publish puts `nav` and `route.end` in `tour.json`. The player builds the links.

## Acceptance

- [ ] Each story has Navigate from here (All stories, and its pin's card). On an Android phone it opens the Google Maps app
      with the remaining stops in order, starting at the current location. (Every card has the
      link, checked by `tests/player_drive.py`; the phone check is still to do.)
- [x] From stop 6 on the Hobart tour, the route goes back through New Norfolk to Hobart, not
      somewhere else. (Waypoints stop 6, stop 7 at Bushy Park, stop 8 leaving New Norfolk, then
      Hobart: `tests/player_drive.py` and `tests/test_navigate.py`. Confirm on the phone that
      Maps draws it along the Lyell Highway.)
- [x] A tour with more than 10 remaining points produces a valid, truncated link.
      (`tests/test_navigate.py::test_more_than_ten_points_are_cut_to_ten`.)

## As built (2026-11-02)

- `tour.toml`: optional per-stop `nav = [lat, lon]` or `nav = false`, and `[route] end`.
  Publish checks each is a `[lat, lon]` pair in range (or `false`) and copies them into
  `tour.json` as stop `nav` and `route.end` (`nav_field`, `route_end` in `publish.py`;
  `docs/tour-json.md`). Hobart's `end` is the last point of the return leg in `route.json`,
  the city centre. No Hobart stop has `nav` yet: stop 5's trigger is already the visitor
  centre car park, and the arrival prompts need a road test before any stop is set to `false`.
- Player: `navLink(tour, i)` in `site/player/app.js`, in a self-contained block between marker
  comments. The link sits on the stop card before "Open trigger point in Google Maps". Points
  and the `%7C`-joined waypoints are URL-encoded; `travelmode` is `walking` for a walk tour.
  With no `route.end` the last point is the destination; with no points at all (every
  remaining stop `nav = false` and no end) the card has no link.
- Tests: `tests/test_navigate.py` runs the player's `navLink` block under Node (skipped if
  `node` is missing) for the order, `nav`, adjacent-repeat, cut-to-10 and Hobart stop 6 cases,
  and checks publish's `nav`/`end` handling. `tests/player_drive.py` checks the rendered links.
- Not done: a whole-route link at the top of the page (stop 1's card is that link).
- iPhone: Google says a mobile browser takes about 3 waypoints. Hobart's stop 1 link has 8, so
  on an iPhone without the Google Maps app, Maps in Safari may drop some. Untested.

## Open questions

- **Road-test the arrival prompts.** Does Maps stop and ask at every waypoint? If that gets
  annoying, mark drive-by stops `nav = false` and keep only real destinations.
- Should the tour page also have a whole-route link at the top (the same link built from
  stop 1)? It costs little.
