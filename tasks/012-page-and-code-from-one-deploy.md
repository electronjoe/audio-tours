# 012: A page and its player code always come from one deploy

Status: done (deployed 2026-11-03) · Priority: high · Raised: 2026-11-03 (first phone load after task 009)

## Why

Right after task 009 deployed, Chrome on Android showed **Couldn't load the tour: Cannot set
properties of null (setting 'textContent')**. Clearing cookies and site data didn't help.

## Now (before)

The pages loaded `../player/app.js` and friends by a fixed URL. GitHub Pages sends
`Cache-Control: max-age=600`, so for ten minutes after a deploy Chrome's HTTP cache (which
"cookies and site data" doesn't clear) could hand the new page yesterday's `app.js`. The old
monolithic `app.js` writes to `#title` and other ids the redesigned page doesn't have:
reproduced exactly with the new page and the 2026-11-02 `app.js`. The reverse also happened:
`sw.js` serves the cached page when the network takes over 4 s, and the old page with new code
fails the same way.

## Change

- `tour pages` stamps the player files in each page with `?v=<hash>` of
  `publish.PLAYER_FILES` (`publish.player_version`). A new page asks for new URLs, so no cache
  can answer with old code.
- `site/sw.js` serves `?v=` requests cache-first and, once a new version is cached, deletes
  that file's other versions. A page kept offline runs the code it was published with.
- `test_hobart_pages_match_committed` already fails if the committed pages weren't
  regenerated after a player change, so the stamp can't go stale.

## Acceptance

- [x] The published pages load `app.js`, `map.js`, `view.js` and `style.css` with `?v=`.
- [x] A second load serves them from the service worker's cache; a page with a new `?v=`
      fetches the new files and the old copies are removed (checked by hand in headless
      Chrome).
- [x] `tests/player_drive.py` and `pytest` pass.
