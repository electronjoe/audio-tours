# tour.json format

`site/<slug>/tour.json` is the contract between the pipeline and the web player. `uv run tour
publish <slug>` writes it from `tours/<slug>/tour.toml`, the draft's `## Script:` tracks,
`route.json` and the mastered audio in `build/`. The player (`site/player/app.js`) reads it.
Never edit it by hand: change the inputs and publish again.

## Schema version

`"schema": 1` is the first field. The publisher's `publish.SCHEMA` and the player's `SCHEMA`
constant must match, and `tests/test_publish.py` checks that they do.

- **Adding a field doesn't bump the schema.** The player ignores fields it doesn't know and
  falls back to a default when a field is missing. So a newer `tour.json` still works in an
  older player, and an older one works in a newer player.
- **Bump the schema only for a change an older player would misread**, such as renaming,
  removing or changing the meaning of a field. Then update the player in the same commit.
- A player that gets a schema it doesn't know stops with "Couldn't load the tour: it needs a
  newer player ... Reload while online." It never guesses.
- A missing `schema` is read as 1. Files published before the field existed (for example one
  cached on a phone for offline use) still open.

## Top level

| Field | Type | From | Meaning |
| --- | --- | --- | --- |
| `schema` | integer | `publish.SCHEMA` | Format version, currently `1`. |
| `slug` | string | folder name | The tour's id. The player stores progress in localStorage under `tour:<slug>`. |
| `title` | string | `[tour].title` (default: the slug) | Shown in the page header, the tour list and the lock-screen media controls. |
| `mode` | `"drive"` or `"walk"` | `[player].mode` (default `"drive"`) | Shown in the tour list. The player doesn't use it yet; walking-tour behaviour is task 007. |
| `lookahead` | integer | `[player].lookahead` (default 2) | How many unplayed stops, counting from the next one in sequence, GPS may trigger. |
| `stops` | array | `[stops.*]`, in file order | See below. |
| `route` | object | `tours/<slug>/route.json` (or `{}`) | `outbound` and `return`: arrays of `[lat, lon]` points. Used for the route sketch and the simulated drive. |

## Stops

| Field | Type | From | Meaning |
| --- | --- | --- | --- |
| `id` | string | the `[stops.<id>]` key | Must match a draft track id, e.g. `stop-1` for `## Script: Stop 1 — ...`. |
| `n` | integer | position, from 1 | The stop number shown in the player. |
| `title` | string | the track title in the draft | |
| `lat`, `lon` | number | `[stops.<id>]` | Trigger point (WGS84 degrees). |
| `radius` | number | `radius` (default 400) | Trigger radius in metres. |
| `place` | string | `place` (default `""`) | Where the stop triggers, in words. |
| `strict` | boolean | `strict` (default false) | The stop can't trigger until the stop before it has played or been skipped. |
| `audio` | string, optional | `build/<id>.mp3` | Path relative to the tour folder, e.g. `audio/stop-1-105ddfb9.mp3`. The 8 hex digits are a content hash, so a re-master gets a new URL. Missing if the stop isn't mastered yet. |
| `bytes` | integer, optional | | Size of the audio file. |
| `duration` | number, optional | | Length in seconds, to 0.1 s. |
| `song` | object, optional | `[stops.<id>.song]` | A song to play on Spotify after the stop (task 006), see below. |

### Song

| Field | Type | From | Meaning |
| --- | --- | --- | --- |
| `title` | string | `title` | The song's title, as on Spotify (`tour check` verifies it). |
| `artist` | string | `artist` | |
| `spotify` | string | `spotify` | `https://open.spotify.com/track/<id>`, without `intl-xx/` or a `?si=` tag. On Android it opens the Spotify app at the track. |
| `length` | integer | `length` (`"m:ss"` in tour.toml) | The song's length in **seconds**. The player shows ▶ Play on Spotify only if the next trigger is more than `length + 60` s away. |
| `why` | string | `why` | One line for the screen: why this song is here. |

The player escapes the song fields, so they may contain `&` or `<`. Publish refuses a song table
with a missing field, a link that isn't a track, or a length it can't read.

The player inserts `title` and `place` into the page as HTML. Keep them plain text, without `<`
or `&`.

If a stop's `build/<id>.mp3` is missing (for example in a fresh clone), publish keeps the stop's
existing `audio`, `bytes` and `duration`, as long as that file is still in `site/<slug>/audio/`.
It never deletes committed audio just because there is no local build.

## Planned fields

These are planned by open tasks. Each one is optional, so none of them bumps the schema.

| Field | Task | Meaning |
| --- | --- | --- |
| stop `nav`, `route.end` | [003](../tasks/003-maps-route-from-stop.md) | Where to navigate to for each stop, and the trip's end point, for Google Maps links. |
| `order`, `max_accuracy`, `sim_speed` | [007](../tasks/007-walking-tours.md) | Walking tours: any-order stops, the GPS accuracy threshold and the simulation speed, copied from `[player]`. |

## Pages written next to it

`tour publish <slug>` also writes these from templates in `site/player/`:

- `site/<slug>/index.html`, from `tour.html`, which fills in `${title}` and `${theme_color}`.
- `site/<slug>/manifest.webmanifest`, from `tour.webmanifest`, which fills in `${name}`,
  `${short_name}` and `${theme_color}`.
- `site/index.html` (the tour list), from `home.html`, with one card for each
  `site/*/tour.json`, sorted by title.

They take `title`, `short_name` (the home-screen label, default: the title) and `theme_color`
(default `#14532d`) from `[tour]` in `tour.toml`. `uv run tour pages` rewrites all of them for
every published tour without touching audio. Run it after editing a template.
`tests/test_publish.py` fails if the committed Hobart pages don't match the templates.

The `[book]` table from the audiobook pipeline is still read in place of `[tour]`, with a note
asking you to rename it.
