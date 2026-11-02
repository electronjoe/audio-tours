# 003: Google Maps route from each stop onward

Status: todo · Priority: medium · Raised: 2026-11-02 (Hobart road test)

## Why

> For each step in the audio tour, can we offer a Google Maps link that opens that step and
> onward as a multi-stop route?

Yes. Google Maps URLs support multi-stop directions, and on Android the link opens the Maps
app.

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

- [ ] Each stop card has Navigate from here. On an Android phone it opens the Google Maps app
      with the remaining stops in order, starting at the current location.
- [ ] From stop 6 on the Hobart tour, the route goes back through New Norfolk to Hobart, not
      somewhere else.
- [ ] A tour with more than 10 remaining points produces a valid, truncated link.

## Open questions

- **Road-test the arrival prompts.** Does Maps stop and ask at every waypoint? If that gets
  annoying, mark drive-by stops `nav = false` and keep only real destinations.
- Should the tour page also have a whole-route link at the top (the same link built from
  stop 1)? It costs little.
