# Tech stack

A summary of what the project is built with. There are two halves: a Python pipeline that turns a
tour's research and script into mastered audio and a publishable bundle, and a static web player
that runs the tour on a phone. Details live in `README.md`, `docs/` and the module docstrings.

```
tours/<slug>/                 src/audiotour/ (Python CLI)               site/ (static, GitHub Pages)
  tour.toml      ─┐            check ─ render ─ sfx ─ master ─ publish ─►  <slug>/tour.json
  source/*.md    ─┼──────────►   │        │                 │              <slug>/audio/*.mp3
  route.json     ─┘              │   ElevenLabs API     ffmpeg             player/ (app.js) + sw.js
                                 └─ spend.Guard (cache, cap, ledger)        ▲
                                                                           │ Android Chrome: GPS,
                                                                           │ offline cache, audio
```

## Pipeline (`src/audiotour/`)

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python ≥ 3.12 | Standard library first: `tomllib`, `argparse`, `dataclasses`, `subprocess`, `hashlib`. |
| Packaging and runs | [uv](https://docs.astral.sh/uv/), hatchling build backend | `uv run tour <command>`; the `tour` script is `audiotour.cli:main`. |
| HTTP | `httpx` | `eleven.py` wraps the ElevenLabs REST endpoints directly. The `elevenlabs` SDK is a declared dependency but isn't imported. |
| Secrets | `python-dotenv` | `ELEVENLABS_API_KEY` in a gitignored `.env`. |
| Audio | `ffmpeg` / `ffprobe` (system install) | Trimming, joining, sound-cue mixing and EBU R128 loudness (`loudnorm`) in `master.py`. Nothing local costs credits. |
| Tests | `pytest` | Unit tests in `tests/`. |

**Modules:**
- `cli.py`: the `tour` commands. Free: `check`, `estimate`, `account`, `models`, `voices`, `master`, `combine`, `publish`, `pages`, `ledger`, `route`, `plan-check`. Paid: `render`, `sfx`, `design`, `audition`, `save-voice`.
- `config.py`: reads `tour.toml`.
- `script.py`: parses the Markdown working draft into tracks, pauses, cast and sound cues (`docs/script-format.md`).
- `chunks.py`: splits each track into TTS requests.
- `render.py`: does the paid rendering.
- `spend.py`: every paid call passes through `spend.Guard`, which caches it by request hash, caps and confirms it, and logs it to `ledger.jsonl`.
- `master.py`: mixes the final MP3.
- `publish.py`: writes `site/<slug>/`.
- `route.py`: `tour route` fetches each leg from OSRM and writes `route.json`; `tour plan-check` checks stop spacing against it offline.
- `songs.py`: the per-stop song table; `tour check` verifies each Spotify link's title (oEmbed) and length (the track page's `music:duration` tag).

## Content (`tours/<slug>/`)

- **`tour.toml`:** title, voices, sound effects, mastering settings, route legs and end point, and stops (trigger point, radius, `strict`, optional `nav` point and Spotify song).
- **`source/working-draft.md`:** the narration, one `## Script:` section per stop.
- **`source/research.*`:** private research notes. These are gitignored because they name family members.
- **`route.json`:** outbound and return legs as `[lat, lon]` points about 300 m apart, from the public [OSRM](https://project-osrm.org/) driving router (`tour route`).
- **`build/`, `cache/`:** generated audio and cached ElevenLabs, OSRM and Spotify responses (gitignored). The published MP3s under `site/` are committed.

## Player (`site/`)

| Layer | Choice | Notes |
| --- | --- | --- |
| Code | Plain HTML, CSS and JavaScript | No framework, bundler or build step. `site/player/app.js` is shared by every tour. Each tour page is generated from `tour.html` and reads its own `tour.json` (`docs/tour-json.md`). |
| Location | Geolocation API (`watchPosition`) | A stop triggers when a fix lands in its zone. Catch-up handles stops passed while the page was hidden. Speed comes from fixes. |
| Offline | Service worker (`site/sw.js`) and the Cache API | Audio is cache-first (content-hashed file names). Pages and `tour.json` are network-first with a cache fallback. `navigator.storage.persist()` asks Chrome not to evict the cache. |
| Playback | `HTMLAudioElement` and the Media Session API | Lock-screen and headset controls. |
| Phone behaviour | Screen Wake Lock API, `visibilitychange` | Keeps the screen on while driving and notices when the page is hidden. |
| State | `localStorage` | Progress, queue and the event log, per device. |
| Install | Web app manifest (PWA) | Can be added to the home screen. |
| Navigation links | Google Maps URLs | Links only, no API key. Each stop's Navigate from here routes through the remaining stops. |
| Songs | `open.spotify.com/track/…` links | After a song stop, ▶ Play on Spotify opens the app, only when there is time before the next trigger. No music is embedded or played by the tour. |

The target is Android Chrome. `?sim=20` replays the route as a simulated drive. `site/lab/gps-probe/`
is a stand-alone page that measured background GPS behaviour (task 006).

## Hosting and deploy

- **GitHub Pages:** deployed by `.github/workflows/pages.yml` on every push to `main` that touches `site/**`. There is no server.
- **HTTPS:** Pages serves over HTTPS, which geolocation needs.

## Testing

- **`uv run pytest`:** unit tests for the parser, chunking, mastering, publish, songs and route tools, including a check that the committed pages match their templates. OSRM and Spotify tests use recorded responses in `tests/fixtures/`. `tests/test_navigate.py` runs the player's link builder under Node, and is skipped without `node`.
- **`tests/player_drive.py`:** drives the real player in headless Chrome with [Playwright](https://playwright.dev/python/). Run it with `uv run --with playwright …`; Playwright is not a project dependency. It feeds browser geolocation along `route.json`, and also covers stale progress, coarse fixes, hidden-page gaps and offline playback.

## External services

| Service | Used for | Cost |
| --- | --- | --- |
| ElevenLabs | Narration (text to speech with timestamps), sound effects, voice design | Paid, only through `spend.Guard`. |
| OSRM public server | Driving routes for `route.json` | Free; responses cached. |
| Spotify oEmbed and track pages | Checking song links and lengths | Free, no account; responses cached. |
| Google Maps | Links that open a place or a route | Free; no key. |
| GitHub Pages | Hosting | Free. |
