# Player redesign: three directions

Three throwaway demos of the tour player, each a single self-contained HTML file with a made-up
tour ("Coast Road to Cape Wren") and a simulated drive. No audio plays. They're here to choose a
direction, not to ship.

| File | Direction | Built around |
| --- | --- | --- |
| `a-glance.html` | **Glance**: a setup checklist, then one dark car screen | Cooper's postures (setup is transient, driving is background), driver safety |
| `b-map.html` | **Map**: a full-screen route map with a Material 3 bottom sheet | Norman's mapping: show where you are and where the stories are |
| `c-journey.html` | **Journey**: a narrated feed for passengers | Norman's gulf of evaluation: every event explains itself; both audiences |

### A with a map: A.1–A.3

Three ways to add B's map to A without losing what A is good at: a calm, glanceable dark
screen with big type and big buttons. The setup checklist and "All stories" list are A's,
unchanged.

| File | Where the map goes | How it works |
| --- | --- | --- |
| `a1-porthole.html` | **Inside** the ring | A small live map fills A's ring, framing the car and the next story; the distance stays in the ring, over a dark fade. Pause is a big button on the ring's edge. Tap the map for the whole route. |
| `a2-backdrop.html` | **Behind** the words | The map fills the screen behind A's text, framed in whatever space the text leaves. **Map** (or a tap on the map) peeks at the whole route with tappable stories; it returns to the story view after 20 s, or as soon as a story starts or an offer appears. |
| `a3-map-page.html` | **Beside** A | A is unchanged as page one. Swipe left (or tap **Map ›**) for a full map page with follow/whole-route and tappable stories. Any new story or offer slides back to page one. |

They trade map presence for calm in that order: A.1's map is always on but small, A.2's is
always on and large but dimmed, and A.3's is out of sight until a passenger asks for it.

## Viewing

Open a file in Chrome. On a wide window it shows a phone frame with the demo controls beside
it. To feel it as a phone, open DevTools (⌥⌘I), turn on the device toolbar (⇧⌘M), and pick a
Pixel 7 (or similar). The demo controls then sit behind the **Demo** tab on the right edge.

Demo controls: jump to a moment (night before, no signal, story playing, two stories close
together, back from Maps, song offer, arrived), freeze time or change the speed, simulate
switching to Maps (no GPS reaches the page), lose signal, and force a light or dark theme.

The simulation follows the real player's rules: stops play in order, a stop that triggers
during another one waits, and stops passed while the page is in the background are offered,
never auto-played.

## Trade-offs

- **A · Glance**: the safest in a car and the least to build (it's the current player's
  features, reorganised). It shows least while driving: the story list, songs and log sit
  behind "All stories".
- **B · Map**: the clearest answer to "where's the next story?" and "why did that play here?".
  It needs real map drawing (the current SVG sketch, or offline tiles), and a map invites
  the driver's eye more than A.
- **C · Journey**: the richest for passengers and kids, and it replaces the event log with a
  readable history. It's the most new content: each stop would need a teaser and a car
  question (new optional `tour.json` fields), and it has the most text to read.

Elements mix well across directions: A's setup checklist works in front of B or C, and C's
car questions could appear as A's "between stories" card.

The demo engine (fake tour, simulation, controls) is the same in every file; only the part
after "Design X" differs. A.1–A.3 also share A's code and one dark route map.

## Chosen direction: A.3, with these changes

A.3 (`a3-map-page.html`) is the direction for the redesign, with two changes. The song
changes are in the demo; the map is still the demo's made-up drawing.

### Songs visible before they're offered

A song is offered after its story ends, and only if the next story is far enough away (the
song's length plus 60 s, as in the real player). Before this change it appeared only as a card
on the story page, and nothing showed in advance which stories had one.

- Mark stories with a song with ♪ in **All stories** and on their map pin.
- Name the song under the story in **All stories** and in a pin's detail card.
- Show the song card on the map page as well as the story page, with the same Play on Spotify
  and No thanks buttons. Songs are for passengers, so the map page is a natural place for them,
  and a song offer no longer sends the map page back to the story page (a new story, a missed
  stop and arriving still do).

### The map: pre-drawn in our own style, embedded in the site

No live map tiles. Each tour's map is drawn from OpenStreetMap data **once, at publish time**,
committed to `site/<slug>/`, and cached by the service worker with the audio:

- A publish step (for example `uv run tour map <slug>`) fetches the route corridor's
  coastline, water, main roads, parks and town names from OpenStreetMap once, simplifies them,
  and writes a small file next to `tour.json` (expect tens to hundreds of KB). The route
  itself is already in `tour.json`.
- The player draws it as SVG in A's dark style, like the demo map, with no map library. There's
  no street-level zoom, which a car doesn't need.
- It works offline, costs nothing, needs no API key, and sends nobody the phone's location.
- The map shows "© OpenStreetMap contributors" (required by OSM's ODbL licence).
- Not used: tiles from tile.openstreetmap.org, whose usage policy prohibits saving areas for
  offline use, and commercial tile services, whose free tiers usually restrict commercial use
  and offline caching.

If passengers later want to zoom into streets, the fallback is a Protomaps `.pmtiles`
extract of the region, served from GitHub Pages and drawn with MapLibre GL JS (a few MB to
tens of MB, and the service worker must handle range requests).
