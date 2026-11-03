"""End-to-end test of the web player in headless Chrome: a simulated drive.

    uv run --with playwright python tests/player_drive.py [tour] [--no-shots | --shots-only]

Serves site/ locally, grants geolocation, taps Start, then drives the tour's route
(outbound then return) one route point at a time. Each route point is about 300 m,
i.e. about 14 s at 80 km/h, so a track "finishes" after its real duration in route
points. Checks:

- every stop plays exactly once, in sequence order
- a trigger never interrupts the track playing (it queues)
- return-leg stops never trigger on the outbound leg
- a reload mid-story offers Resume: Start plays nothing, Resume plays that story
- "Start here" interrupts and continues the sequence from that stop
- progress older than 8 hours offers Start from the beginning / Continue instead of Start
- a coarse (network fallback) fix inside a zone is ignored; a precise one triggers
- a hidden gap whose jump crosses a whole stop zone offers that stop as "Passed while you
  were away" (not played, logged as catch-up), derives no speed across the gap, and the
  next stop still triggers
- the event log shows why each stop started
- every stop card has Navigate from here: a Maps route through that stop and every later
  one to the tour's end; stop 6's goes back through New Norfolk to Hobart
- a song on a stop (a fixture served in place of tour.json, never committed): the Now card
  shows it only after the stop ends, offers ▶ Play on Spotify or Save for later by the room
  before the next trigger, clears when the next stop starts, and stays in the stop's card
- route progress (the ring): along the drive the distance to the next story never grows
  between consecutive outbound points, the fill never shrinks, the return leg never shows
  outbound progress (not after a reload there either), and a gap that lands where the legs
  share a road stays on the outbound leg
- after Download, the tour opens and plays with the network off

The final screenshot goes to tours/<tour>/build/player-test.png, or to $PLAYER_TEST_SHOT.
Then a screenshot pass shoots every state the player shows (SCENES), light and dark, portrait
and landscape, into tours/<tour>/build/shots/ (or $PLAYER_SHOTS). Every selector is in SEL.
"""

from __future__ import annotations

import functools
import http.server
import json
import math
import os
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TOUR = next((a for a in sys.argv[1:] if not a.startswith("--")), "hobart")
SECONDS_PER_POINT = 300 / 22


# Every selector the test uses, in one place, so a UI change edits only this table (task 009).
# A tuple is a sequence of taps; "sheet" opens All stories unless it's open; "scroll:<selector>"
# scrolls it into view instead of tapping; None means this UI has no such thing (a screenshot
# that needs it is skipped). `{id}` is a stop id. "now" is the region holding what plays, its
# offers and the song card.
SEL: dict[str, str | tuple[str, ...] | None] = {
    "setup": "#setup",
    "car": "#p1",
    "start": "#start",
    "resume": "[data-act=resume]",  # the ring after a reload, or the offer after Continue
    "carry_on": "#carry-on",
    "continue": "#continue",
    "restart": "#restart",
    "now": "#p1",
    "song_play": "#p1 a.song-play",
    "dismiss_missed": "#offer [data-act=dismissMissed]",
    "dismiss_song": "#offer [data-act=dismissSong]",
    "next": ("sheet", "#stories .row.st-armed"),
    "next_now": ("sheet", "#stories .row.st-armed .row-main", "#stories .row.st-armed [data-act=queue]"),
    "status": "#p1 .top",
    "download": "#download",
    "saved": "#check-save.done",  # in the page once every stop's audio is cached
    "nav_links": "#stories a.nav",
    "open_stories": "[data-act=openSheet]:visible",
    "story_row": "#stories .row[data-id={id}]",
    "open_stop": ("sheet", "#stories .row[data-id={id}] .row-main"),
    "stop_here": "#stories .row[data-id={id}] [data-act=playHere]",
    "stop_song_link": "#stories .row[data-id={id}] a.song-link",
    "open_log": ("sheet", "#log-toggle"),
    "log": "#log",
    "open_map": "#to-map",
    "map_whole": None,
    "map_pin": None,
}


def sel(name: str, **kw) -> str:
    """The selector for `name` (the last one, for a sequence of taps)."""
    s = SEL[name]
    s = s[-1] if isinstance(s, tuple) else s
    assert s is not None, f"this UI has no {name}"
    return s.removeprefix("scroll:").format(**kw)


def _steps(page, steps, **kw) -> None:
    for one in steps:
        if one == "sheet":
            if page.is_hidden("#sheet"):
                tap(page, "open_stories")
        elif one.startswith("scroll:"):
            page.locator(one.removeprefix("scroll:").format(**kw)).scroll_into_view_if_needed()
        else:
            page.click(one.format(**kw))


def tap(page, name: str, **kw) -> None:
    s = SEL[name]
    assert s is not None, f"this UI has no {name}"
    _steps(page, s if isinstance(s, tuple) else (s,), **kw)


def text_of(page, name: str, **kw) -> str:
    """The text of `name`, after the taps that lead to it."""
    s = SEL[name]
    if isinstance(s, tuple):
        _steps(page, s[:-1], **kw)
    return page.inner_text(sel(name, **kw))


def has(*names: str) -> bool:
    return all(SEL[n] is not None for n in names)


OVERRIDE: dict[str, bytes] = {}  # URL path -> body served instead of the file (test fixtures)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        body = OVERRIDE.get(self.path.split("?")[0])
        if body is None:
            return super().do_GET()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve() -> str:
    handler = functools.partial(Quiet, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/{TOUR}/"


def state(page) -> dict:
    return page.evaluate("""() => { const S = window.__tour.S; return {
        current: S.current && S.current.id, queue: S.queue.map(s => s.id), status: {...S.status},
        cursor: S.cursor, blocked: S.blocked, t: window.__tour.audio.currentTime,
        paused: window.__tour.audio.paused, started: S.started, stale: S.stale,
        resume: S.resume.map(s => s.id), missed: S.missed.map(s => s.id), away: Boolean(S.away),
        speed: S.fix && S.fix.speed, log: S.log } }""")


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    rad = math.pi / 180
    dlat, dlon = (b[0] - a[0]) * rad, (b[1] - a[1]) * rad
    h = math.sin(dlat / 2) ** 2 + math.cos(a[0] * rad) * math.cos(b[0] * rad) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def fresh(page) -> None:
    """A first visit: no saved progress, no log. The old page may still save (a story ending)
    before the reload lands, and fresh progress would open the car screen: stop it writing first."""
    page.evaluate("() => { Storage.prototype.setItem = () => {}; localStorage.clear(); }")
    page.reload()
    page.wait_for_function("() => window.__tour")
    page.evaluate("() => window.scrollTo(0, 0)")  # Chrome restores the last scroll position on reload


def set_visible(page, visible: bool) -> None:
    """Headless Chrome is always visible: fake the page going behind Spotify and coming back."""
    page.evaluate("""(v) => {
        Object.defineProperty(document, 'visibilityState', {value: v ? 'visible' : 'hidden', configurable: true});
        Object.defineProperty(document, 'hidden', {value: !v, configurable: true});
        document.dispatchEvent(new Event('visibilitychange')); }""", visible)


def logged(st: dict, ev: str, n: int | None = None, cause: str | None = None) -> bool:
    return any(e["ev"] == ev and (n is None or e.get("n") == n) and (cause is None or e.get("cause") == cause) for e in st["log"])


def finish_current(page) -> None:
    page.evaluate("() => { const a = window.__tour.audio; a.currentTime = Math.max(0, a.duration - 0.05); }")
    page.wait_for_function("() => window.__tour.audio.ended || !window.__tour.S.current || window.__tour.audio.currentTime < 1", timeout=5000)


def check_nav_links(page, tour: dict, check) -> None:
    """Task 003: each stop card's Navigate from here link, as rendered."""
    print("Navigate from here")
    links = page.eval_on_selector_all(sel("nav_links"), "els => els.map(a => [a.textContent, a.href, a.target])")
    stops = tour["stops"]
    check(len(links) == len(stops) and all(text == "Navigate from here" and target == "_blank" for text, _, target in links),
          f"every stop card has Navigate from here ({len(links)} of {len(stops)})")
    end = tour["route"].get("end")
    point = lambda s: f"{s['lat']},{s['lon']}"
    simple = len(stops) <= 9 and end and not any("nav" in s for s in stops)  # no nav points, no cut
    for k in ((0, 5) if simple and len(links) == len(stops) else ()):
        q = {key: v[0] for key, v in parse_qs(urlsplit(links[k][1]).query).items()}
        want = [point(s) for s in stops[k:]]
        check(urlsplit(links[k][1]).path == "/maps/dir/" and "origin" not in q and q.get("travelmode") == "driving"
              and q.get("waypoints", "").split("|") == want and q.get("destination") == ",".join(map(str, end)),
              f"stop {k + 1}: Maps route from here through stops {k + 1}-{len(stops)} to the end, from the current location")
    if TOUR == "hobart":
        check("New Norfolk" in stops[7]["place"] and end == tour["route"]["return"][-1],
              "stop 6's route goes back through New Norfolk (stop 8) to Hobart (the end of the return leg)")


def song_check(page, ctx, tour: dict, check) -> None:
    """A song on the first stop, served from a fixture copy of tour.json (task 006)."""
    s1, s2 = tour["stops"][0], tour["stops"][1]
    song = TEST_SONG
    fixture = json.loads(json.dumps(tour))
    fixture["stops"][0]["song"] = song
    OVERRIDE[f"/{TOUR}/tour.json"] = json.dumps(fixture).encode()
    # Room = straight line to the edge of the next zone / speed (at least 8 m/s) > length + 60 s.
    edge = metres((s1["lat"], s1["lon"]), (s2["lat"], s2["lon"])) - s2["radius"]
    assert edge / 10 > song["length"] + 60 and edge / 50 < song["length"] + 60, "pick another fixture length"
    near = next(pt for pt in tour["route"]["outbound"]
                if 0 < metres(pt, (s2["lat"], s2["lon"])) - s2["radius"] < 10 * (song["length"] + 60) - 300)

    def fix(lat, lon, speed):
        # onFix renders synchronously, so the Now card is current when this returns.
        page.evaluate("([lat, lon, v]) => window.__tour.onFix(lat, lon, 8, v)", [lat, lon, speed])

    def card() -> str:
        return page.inner_text(sel("now"))

    try:
        # At s1 before the reload, so no fix from an earlier section reaches the new page. The
        # browser's own GPS may then trigger stop 1 the moment Start is tapped, while the unlock
        # clip Start plays is ending: that must not count as stop 1 ending.
        ctx.set_geolocation({"latitude": s1["lat"], "longitude": s1["lon"], "accuracy": 8})
        fresh(page)
        check(page.evaluate("() => Boolean(window.__tour.S.tour.stops[0].song)"), "the fixture tour.json (with a song) is served")
        tap(page, "start")
        fix(s1["lat"], s1["lon"], 10)
        page.wait_for_function("() => { const S = window.__tour.S, a = window.__tour.audio; "
                               "return S.current && !a.paused && a.currentTime > 0.2; }", timeout=10000)
        st = state(page)
        check(st["current"] == s1["id"] and not st["status"].get(s1["id"]) and song["title"] not in card(),
              f"while {s1['id']} plays, no song card (current={st['current']}, status={st['status']}, now={card()[:120]!r})")
        tap(page, "open_stop", id=s1["id"])
        link = page.locator(sel("stop_song_link", id=s1["id"]))
        check(link.count() == 1 and link.get_attribute("href") == song["spotify"], "the song is in the stop's expanded card")
        finish_current(page)
        page.wait_for_function("() => window.__tour.S.song && !window.__tour.S.current", timeout=5000)
        play = page.locator(sel("song_play"))
        check(state(page)["current"] is None and song["title"] in card() and song["why"] in card(),
              "after the stop ends, the Now card shows the song")
        check(play.count() == 1 and play.get_attribute("href") == song["spotify"] and play.get_attribute("target") == "_blank",
              f"{edge / 1000:.1f} km to the next zone at 10 m/s: ▶ Play on Spotify")
        check(any(e["ev"] == "song" and e.get("room") for e in state(page)["log"]), "event log: song offered with room")
        fix(s1["lat"], s1["lon"], 50)
        check(play.count() == 0 and "Save for later" in card(), "the same place at 50 m/s: Save for later")
        fix(*near, 10)
        check(play.count() == 0 and "Save for later" in card(), f"{(metres(near, (s2['lat'], s2['lon'])) - s2['radius']) / 1000:.1f} km from the next zone: Save for later")
        fix(s1["lat"], s1["lon"], 10)
        check(play.count() == 1 and "Save for later" not in card(), "back where there is room: ▶ Play on Spotify again")
        fix(s2["lat"], s2["lon"], 10)
        st = state(page)
        check(st["current"] == s2["id"] and song["title"] not in card(), f"the card clears when {s2['id']} starts")
        check(link.count() == 1, "and the song stays in the stop's card")
    finally:
        OVERRIDE.clear()


def progress_check(page, ctx, tour: dict, check) -> None:
    """Task 009 step 4: the ring measures along the road (S.along), outbound then return."""
    out, ret = tour["route"]["outbound"], tour["route"]["return"]
    path = out + ret
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + metres(a, b))
    out_end = cum[len(out) - 1]
    probe = """() => { const t = window.__tour, n = t.nextStory();
        return {along: t.S.along, off: t.S.offRoute, i: n && n.i, d: n && n.d, frac: n && n.frac, mins: n && n.mins, road: n && n.road}; }"""
    fresh(page)
    at(page, ctx, out[0])
    tap(page, "start")
    page.wait_for_timeout(300)
    rows = []
    for pt in path:
        at(page, ctx, pt)
        rows.append(page.evaluate(probe))
    on_road = [r for r in rows if r["i"] is not None]
    check(on_road and all(r["road"] and not r["off"] for r in on_road), "every route point is on the route: the ring measures by road")
    grew = [(k, rows[k]["d"], rows[k + 1]["d"]) for k in range(len(out) - 1)
            if rows[k]["i"] is not None and rows[k]["i"] == rows[k + 1]["i"] and rows[k + 1]["d"] > rows[k]["d"] + 30]
    check(not grew, f"outbound: the distance to the next story never grows between consecutive points {grew[:3]}")
    shrank = [k for k in range(len(path) - 1) if rows[k]["i"] is not None and rows[k]["i"] == rows[k + 1]["i"]
              and rows[k + 1]["frac"] < rows[k]["frac"] - 1e-6]
    check(not shrank, f"and the ring never empties on the way to it {shrank[:3]}")
    behind = [k for k in range(len(out), len(path)) if rows[k]["along"]["m"] < out_end - 1]
    check(not behind, f"the return leg never shows outbound progress {behind[:3]}")
    straight = [metres(path[k], stop_pt(tour, r["i"])) - tour["stops"][r["i"]]["radius"] for k, r in enumerate(rows) if r["i"] is not None]
    check(any(r["d"] > 1.1 * x + 200 for r, x in zip(on_road, straight)), "somewhere the road is clearly longer than the straight line")
    timed = all(tour["route"].get("seconds", {}).get(k) for k in ("outbound", "return"))
    if not timed:
        check(all(r["mins"] is not None and abs(r["mins"] * 60 * 22 - r["d"]) < 1 for r in on_road if r["d"] > 0),
              "route.json has no seconds: the minutes come from the speed (22 m/s)")
    # With OSRM's seconds (a fixture: 20 m/s everywhere) the minutes come from them, not the speed.
    fixture = json.loads(json.dumps(tour))
    secs = {}
    for leg in ("outbound", "return"):
        pts, t = fixture["route"][leg], [0.0]
        for a, b in zip(pts, pts[1:]):
            t.append(t[-1] + metres(a, b) / 20)
        secs[leg] = t
    fixture["route"]["seconds"] = secs
    OVERRIDE[f"/{TOUR}/tour.json"] = json.dumps(fixture).encode()
    try:
        fresh(page)
        at(page, ctx, out[0])
        tap(page, "start")
        page.wait_for_timeout(300)
        for pt in out[:20]:
            at(page, ctx, pt, speed=30)
        r = page.evaluate(probe)
        check(r["road"] and r["d"] > 1000 and abs(r["mins"] * 60 - r["d"] / 20) < 2,
              f"with route.seconds the minutes are OSRM's time to the zone, not the speed ({r['mins']:.1f} min for {r['d']:.0f} m)")
    finally:
        OVERRIDE.clear()
    # A reload where the return leg runs over the outbound road, 5 km before the last story: still the return leg.
    last = tour["stops"][-1]
    k = next(j for j in range(len(out), len(path)) if metres(path[j], stop_pt(tour, len(tour["stops"]) - 1)) - last["radius"] < 5000)
    fresh(page)
    at(page, ctx, out[0])
    tap(page, "start")
    page.wait_for_timeout(300)
    for pt in path[: k + 1]:
        at(page, ctx, pt)
    page.evaluate("() => window.__tour.save()")
    page.reload()
    page.wait_for_function("() => window.__tour")
    tap(page, "carry_on")
    page.wait_for_timeout(300)
    at(page, ctx, path[k])
    at(page, ctx, path[k + 1])
    r = page.evaluate(probe)
    check(r["along"] and r["along"]["m"] >= out_end and r["road"] and r["i"] == len(tour["stops"]) - 1, f"after a reload on the return leg before New Norfolk, the ring still counts the return leg ({r['along']})")
    # A gap that lands where both legs share the road: the earlier (outbound) place wins.
    j = min(range(len(out)), key=lambda j: metres(out[j], stop_pt(tour, 1)))
    fresh(page)
    at(page, ctx, out[0])
    tap(page, "start")
    page.wait_for_timeout(300)
    for pt in out[:3]:
        at(page, ctx, pt)
    set_visible(page, False)
    set_visible(page, True)
    at(page, ctx, out[j])
    at(page, ctx, out[j + 1])
    r = page.evaluate(probe)
    check(r["along"] and abs(r["along"]["m"] - cum[j + 1]) < 300, f"after a gap to New Norfolk on the way out, progress jumps there on the outbound leg ({r['along']}, want ~{cum[j + 1]:.0f})")


def drive_checks(browser, url: str, tour: dict, check, failures: list[str]) -> None:
    """Every behaviour check, in one browser context."""
    stops = [s["id"] for s in tour["stops"]]
    out, ret = tour["route"]["outbound"], tour["route"]["return"]
    ctx = browser.new_context(permissions=["geolocation"], geolocation={"latitude": out[0][0], "longitude": out[0][1]})
    page = ctx.new_page()
    page.on("pageerror", lambda e: failures.append(f"page error: {e}"))
    page.goto(url)
    page.wait_for_function("() => window.__tour")
    page.evaluate("() => localStorage.clear()")
    page.reload()
    page.wait_for_function("() => window.__tour")
    check_nav_links(page, tour, check)
    tap(page, "start")
    page.wait_for_timeout(500)
    st = state(page)
    check(st["started"] and st["current"] is None and not st["queue"], f"Start plays nothing (current={st['current']})")
    check(page.is_visible(sel("car")) and not page.is_visible(sel("setup")), "Start shows the car screen")

    print("Drive: real GPS path via the browser's geolocation")
    started_at: dict[str, int] = {}
    order: list[str] = []
    interrupted = []
    reloaded = False
    prev = None
    for k, (lat, lon) in enumerate(out + ret):
        leg = "out" if k < len(out) else "ret"
        ctx.set_geolocation({"latitude": lat, "longitude": lon, "accuracy": 10})
        page.wait_for_timeout(60)
        st = state(page)
        if st["current"] and st["current"] not in started_at:
            started_at[st["current"]] = k
            order.append(st["current"])
            if leg == "out" and stops.index(st["current"]) >= 5:
                failures.append(f"{st['current']} played on the outbound leg")
        if prev and prev["current"] and st["current"] != prev["current"] and prev["status"].get(prev["current"]) is None and st["status"].get(prev["current"]) != "played":
            interrupted.append((prev["current"], st["current"]))
        # The track ends after its real duration in route points.
        cur = st["current"]
        if cur:
            dur = next(s for s in tour["stops"] if s["id"] == cur).get("duration", 180)
            if k - started_at[cur] >= dur / SECONDS_PER_POINT:
                # Once, mid-story: reload. Start plays nothing; Resume plays the story.
                if not reloaded and cur == stops[2]:
                    reloaded = True
                    page.reload()
                    page.wait_for_function("() => window.__tour")
                    resumed = state(page)
                    check(resumed["resume"][:1] == [cur] and not resumed["queue"], f"after a reload mid-{cur}, it is offered, not queued ({resumed['resume']})")
                    check(page.is_visible(sel("car")) and not page.is_visible(sel("setup")), "the reload opens the car screen, not setup")
                    check(not resumed["started"] and resumed["current"] is None, "nothing plays (or starts) until a tap names it")
                    check(page.is_visible(sel("resume")) and "Resume" in page.inner_text(sel("resume")), "a Resume button is offered")
                    tap(page, "resume")
                    page.wait_for_timeout(500)
                    st = state(page)
                    check(st["current"] == cur and not st["paused"] and st["started"], f"Resume plays {cur} in one tap, and starts the tour")
                    check(logged(st, "play", stops.index(cur) + 1, "resume"), "event log: started by Resume")
                    started_at[cur] = k
                    continue
                finish_current(page)
        if st["blocked"]:
            failures.append(f"audio blocked at point {k}: {st}")
            break
        prev = state(page)
    # Let the queue drain.
    for _ in range(len(stops)):
        if state(page)["current"]:
            finish_current(page)
            page.wait_for_timeout(200)
            st = state(page)
            if st["current"] and st["current"] not in order:
                order.append(st["current"])
    final = state(page)
    check(order == stops, f"played in sequence: {order}")
    check(not interrupted, f"no trigger interrupted a playing track {interrupted or ''}")
    check(all(final["status"].get(s) == "played" for s in stops), f"every stop marked played: {final['status']}")
    check(not any("outbound" in f for f in failures), "no return-leg stop played on the way out")
    check(all(logged(final, "play", n, "gps") for n in (1, 2, 4, 5)), "event log: each stop started by GPS")
    tap(page, "open_log")
    page.wait_for_timeout(200)
    check("started (GPS" in page.inner_text(sel("log")), "the event log shows why stops started")

    print("Start here")
    page.evaluate("() => { localStorage.clear(); }")
    page.reload()
    page.wait_for_function("() => window.__tour")
    tap(page, "start")
    page.evaluate("() => window.__tour.trigger(0)")
    page.wait_for_timeout(300)
    tap(page, "open_stop", id=stops[4])
    tap(page, "stop_here", id=stops[4])
    page.wait_for_timeout(500)
    st = state(page)
    check(st["current"] == stops[4], f"Start here on {stops[4]} plays it now (current={st['current']})")
    check(st["status"].get(stops[0]) == "skipped" and st["cursor"] == 5, f"stops before it skipped, cursor after it ({st['cursor']})")
    next_title = text_of(page, "next")
    check(tour["stops"][5]["title"] in next_title, "the next story shown is the following stop")
    tap(page, "next_now")
    page.wait_for_timeout(200)
    check(state(page)["queue"] == [stops[5]], "the next story's button queues (does not interrupt) while playing")

    print("Stale progress")
    old = {"cursor": 3, "status": {stops[0]: "played", stops[1]: "played"}, "pending": [stops[2]]}
    for choice in ("continue", "restart"):
        page.evaluate("""(saved) => { const S = window.__tour.S; S.current = null; window.__tour.audio.pause();
            localStorage.setItem(`tour:${S.tour.slug}`, JSON.stringify({...saved, savedAt: Date.now() - 9 * 3600e3})); }""", old)
        page.reload()
        page.wait_for_function("() => window.__tour")
        if choice == "continue":
            check(not page.is_visible(sel("start")) and page.is_visible(sel("restart")) and page.is_visible(sel("continue")),
                  "progress from 9 h ago offers Start from the beginning / Continue instead of Start")
            check("stop 4" in page.inner_text(sel("continue")), f"Continue names the next stop ({page.inner_text(sel('continue'))!r})")
        tap(page, choice)
        page.wait_for_timeout(500)
        st = state(page)
        check(st["started"] and st["current"] is None, f"{choice} plays nothing")
        if choice == "continue":
            check(st["cursor"] == 3 and st["resume"] == [stops[2]], "Continue keeps progress and still offers Resume")
        else:
            check(st["cursor"] == 0 and not st["status"] and not st["resume"], "Start from the beginning clears progress")

    print("Coarse fix")
    fresh(page)
    ctx.set_geolocation({"latitude": out[0][0], "longitude": out[0][1], "accuracy": 10})
    tap(page, "start")
    page.wait_for_timeout(500)
    s1 = tour["stops"][0]
    page.evaluate("([lat, lon]) => window.__tour.onFix(lat, lon, 120, null, {coarse: true})", [s1["lat"], s1["lon"]])
    page.wait_for_timeout(300)
    st = state(page)
    check(st["current"] is None and not st["queue"], f"a coarse fix at the centre of {stops[0]} triggers nothing")
    check(logged(st, "ignored", 1, "coarse-ignored"), "event log: coarse-ignored")
    page.evaluate("([lat, lon]) => window.__tour.onFix(lat, lon, 10, null)", [s1["lat"], s1["lon"]])
    page.wait_for_timeout(300)
    check(state(page)["current"] == stops[0], "a precise fix there triggers it")

    print("Hidden gap")
    g = 1  # the stop whose zone the jump crosses
    zone, after = tour["stops"][g], tour["stops"][g + 1]
    d = [metres(pt, (zone["lat"], zone["lon"])) for pt in out]
    inside = [k for k in range(len(out)) if d[k] <= zone["radius"]]
    a = max(k for k in range(inside[0]) if d[k] > zone["radius"] + 300)
    b = min(k for k in range(inside[-1], len(out)) if d[k] > zone["radius"] + 300)
    fresh(page)
    ctx.set_geolocation({"latitude": out[a - 3][0], "longitude": out[a - 3][1], "accuracy": 10})
    tap(page, "start")
    page.wait_for_timeout(300)
    for k in range(a - 2, a + 1):
        ctx.set_geolocation({"latitude": out[k][0], "longitude": out[k][1], "accuracy": 8})
        page.wait_for_timeout(100)
    set_visible(page, False)
    check(state(page)["away"], "hiding the page marks the player away")
    set_visible(page, True)
    jump = metres(out[a], out[b])
    ctx.set_geolocation({"latitude": out[b][0], "longitude": out[b][1], "accuracy": 54})
    page.wait_for_timeout(300)
    st = state(page)
    check(st["away"] and not st["status"].get(stops[g]), f"the first fix back, ±54 m, is not used ({jump:.0f} m jump over {stops[g]})")
    ctx.set_geolocation({"latitude": out[b + 1][0], "longitude": out[b + 1][1], "accuracy": 12})
    page.wait_for_timeout(300)
    st = state(page)
    check(st["status"].get(stops[g]) == "missed" and st["missed"] == [stops[g]], f"{stops[g]}, crossed while hidden, is marked missed ({st['status']})")
    check(st["current"] is None and not st["queue"], "and is not auto-played")
    text = page.inner_text(sel("now")).lower()
    check("passed while you were away" in text and zone["title"].lower() in text, "it is offered as Passed while you were away")
    check(logged(st, "missed", g + 1, "catch-up"), "event log: catch-up")
    check(st["speed"] is None, f"no speed derived across the gap ({st['speed']})")
    ctx.set_geolocation({"latitude": out[b + 2][0], "longitude": out[b + 2][1], "accuracy": 8})
    page.wait_for_timeout(300)
    check(state(page)["speed"] is None, "nor in the first 10 s after it")
    for k in range(b + 3, len(out)):
        ctx.set_geolocation({"latitude": out[k][0], "longitude": out[k][1], "accuracy": 8})
        page.wait_for_timeout(60)
        if state(page)["current"]:
            break
    st = state(page)
    check(st["current"] == after["id"] and st["status"].get(stops[g]) == "missed", f"the next stop still triggers ({st['current']})")
    check(not st["missed"] and "passed while you were away" not in page.inner_text(sel("now")).lower(), "the offer clears when the next stop starts")
    # No fix for over 20 s counts as away too.
    page.evaluate("() => { const S = window.__tour.S; S.fix.time -= 25000; S.last.time -= 25000; }")
    ctx.set_geolocation({"latitude": out[k + 1][0], "longitude": out[k + 1][1], "accuracy": 60})
    page.wait_for_timeout(300)
    check(state(page)["away"] and "settling" in page.inner_text(sel("status")).lower(), "25 s without a fix: the next rough fix waits for a better one")

    print("Song")
    song_check(page, ctx, tour, check)

    print("Carry on without it")
    fresh(page)
    tap(page, "start")
    page.wait_for_timeout(300)
    at(page, ctx, stop_pt(tour, 0))
    page.wait_for_function("() => window.__tour.S.current", timeout=5000)
    page.reload()
    page.wait_for_function("() => window.__tour")
    check(page.is_visible(sel("car")) and page.is_visible(sel("carry_on")), "a reload mid-story offers Carry on without it")
    tap(page, "carry_on")
    page.wait_for_timeout(300)
    st = state(page)
    check(st["started"] and st["current"] is None and not st["queue"] and not st["resume"], "Carry on without it starts the tour and plays nothing")
    check(st["status"].get(stops[0]) == "skipped" and logged(st, "resume-declined", 1), f"the cut-off story is skipped, and logged ({st['status']})")

    print("Dismissing offers")
    sc_offer_missed(page, ctx, tour)
    tap(page, "dismiss_missed")
    st = state(page)
    check(not st["missed"] and st["status"].get(stops[1]) == "skipped" and logged(st, "dismiss", 2),
          f"Skip on Passed while you were away: the offer goes, the stop stays skipped ({st['status']})")
    check("passed while you were away" not in text_of(page, "now").lower(), "and the card is gone")
    try:
        sc_offer_song(page, ctx, tour)
        check(TEST_SONG["title"] in text_of(page, "now"), "the song is offered")
        tap(page, "dismiss_song")
        st = state(page)
        check(TEST_SONG["title"] not in text_of(page, "now") and logged(st, "song-dismiss", 1)
              and not page.evaluate("() => window.__tour.S.song"), "No thanks clears the song offer, logged")
    finally:
        OVERRIDE.clear()

    print("Songs in All stories")
    fresh(page)
    tap(page, "open_stories")
    rows = {s["id"]: page.inner_text(sel("story_row", id=s["id"])) for s in tour["stops"]}
    check(all(("♪" in rows[s["id"]]) == ("song" in s) for s in tour["stops"]), "♪ marks exactly the stories followed by a song")
    check(any("song" in s for s in tour["stops"])
          and all(f"Then a song: {s['song']['title']} · {s['song']['artist']}" in rows[s["id"]] for s in tour["stops"] if "song" in s),
          "and each names its song")

    print("Route progress")
    progress_check(page, ctx, tour, check)

    print("Offline")

    fresh(page)
    if page.is_visible(sel("download")):
        tap(page, "download")
    page.wait_for_selector(sel("saved"), state="attached", timeout=60000)
    check(True, "Download finished; shown as saved")
    ctx.set_offline(True)
    page.reload()
    page.wait_for_function("() => window.__tour", timeout=10000)
    tap(page, "start")
    page.evaluate("() => window.__tour.trigger(1)")
    page.wait_for_timeout(800)
    st = state(page)
    check(st["current"] == stops[1] and not st["paused"], f"offline: stop plays from the cache ({st['current']}, paused={st['paused']})")
    ctx.set_offline(False)
    shot = os.environ.get("PLAYER_TEST_SHOT") or ROOT / "tours" / TOUR / "build" / "player-test.png"
    page.screenshot(path=str(shot), full_page=True)
    ctx.close()

# --- screenshots (task 009) -----------------------------------------------------------
# One picture of each state the player shows, for review in light and dark, portrait and
# landscape. Each scene starts from a first visit and sets itself up through the engine
# (window.__tour) and the selector table, so the same scenes shoot the old and the new UI.
# A scene that needs something this UI doesn't have (SEL None) is skipped.

VIEWS = {"portrait": {"width": 412, "height": 860}, "landscape": {"width": 860, "height": 390}}
TEST_SONG = {"title": "Test Song", "artist": "Test Artist", "spotify": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
             "length": 214, "why": "A fixture song for the player test."}


def at(page, ctx, pt, speed: float = 22.0, acc: float = 8) -> None:
    """A fix at `pt`, from the browser's GPS and straight into onFix (which renders)."""
    ctx.set_geolocation({"latitude": pt[0], "longitude": pt[1], "accuracy": acc})
    page.evaluate("([lat, lon, a, v]) => window.__tour.onFix(lat, lon, a, v)", [pt[0], pt[1], acc, speed])


def begin(page, ctx, tour: dict, heard: int = 0) -> None:
    """A first visit, Start tapped, a good fix at the route's start, the first `heard` stops played."""
    fresh(page)
    at(page, ctx, tour["route"]["outbound"][0])
    tap(page, "start")
    page.wait_for_timeout(300)
    at(page, ctx, tour["route"]["outbound"][0])
    if heard:
        page.evaluate("""(n) => { const t = window.__tour, S = t.S;
            S.tour.stops.slice(0, n).forEach((s) => (S.status[s.id] = "played"));
            S.cursor = n; t.save(); }""", heard)


def stop_pt(tour: dict, k: int) -> tuple[float, float]:
    s = tour["stops"][k]
    return s["lat"], s["lon"]


def before(tour: dict, k: int, metres_before: float) -> tuple[float, float]:
    """The first outbound route point within `metres_before` of stop k's zone."""
    s = tour["stops"][k]
    return next(pt for pt in tour["route"]["outbound"] if metres(pt, (s["lat"], s["lon"])) - s["radius"] < metres_before)


def playing(page, ctx, tour: dict, k: int, frac: float = 0.4) -> None:
    at(page, ctx, stop_pt(tour, k))
    page.wait_for_function("() => window.__tour.S.current && window.__tour.audio.duration > 0", timeout=10000)
    page.evaluate("(f) => { const a = window.__tour.audio; a.currentTime = a.duration * f; }", frac)


def stale_progress(page, tour: dict) -> None:
    ids = [s["id"] for s in tour["stops"]]
    old = {"cursor": 3, "status": {ids[0]: "played", ids[1]: "played"}, "pending": [ids[2]], "savedAt": 0}
    fresh(page)
    page.evaluate("""(saved) => localStorage.setItem(`tour:${window.__tour.S.tour.slug}`,
        JSON.stringify({...saved, savedAt: Date.now() - 9 * 3600e3}))""", old)
    page.reload()
    page.wait_for_function("() => window.__tour")


def sc_setup(page, ctx, tour):
    fresh(page)


def sc_setup_stories(page, ctx, tour):
    fresh(page)
    tap(page, "open_stories")


def sc_reloaded_resume(page, ctx, tour):
    begin(page, ctx, tour, heard=2)
    playing(page, ctx, tour, 2, 0.3)
    page.evaluate("() => window.__tour.save()")
    page.reload()
    page.wait_for_function("() => window.__tour")


def sc_reloaded_carry_on(page, ctx, tour):
    begin(page, ctx, tour, heard=3)
    at(page, ctx, before(tour, 3, 6000))
    page.reload()
    page.wait_for_function("() => window.__tour")


def sc_stale(page, ctx, tour):
    stale_progress(page, tour)


def sc_between(page, ctx, tour):
    begin(page, ctx, tour, heard=1)
    at(page, ctx, before(tour, 1, 5000))


def sc_playing(page, ctx, tour):
    begin(page, ctx, tour, heard=1)
    playing(page, ctx, tour, 1)


def sc_queued(page, ctx, tour):
    sc_playing(page, ctx, tour)
    page.evaluate("() => window.__tour.trigger(2)")


def sc_blocked(page, ctx, tour):
    begin(page, ctx, tour, heard=1)
    page.evaluate("""() => { HTMLMediaElement.prototype.play = function () {
        return Promise.reject(new DOMException("play() can only be initiated by a user gesture.", "NotAllowedError")); }; }""")
    at(page, ctx, stop_pt(tour, 1))
    page.wait_for_function("() => window.__tour.S.blocked", timeout=5000)


def sc_offer_missed(page, ctx, tour):
    out, zone = tour["route"]["outbound"], tour["stops"][1]
    d = [metres(pt, (zone["lat"], zone["lon"])) for pt in out]
    inside = [k for k in range(len(out)) if d[k] <= zone["radius"]]
    a = max(k for k in range(inside[0]) if d[k] > zone["radius"] + 300)
    b = min(k for k in range(inside[-1], len(out)) if d[k] > zone["radius"] + 300)
    begin(page, ctx, tour, heard=1)
    at(page, ctx, out[a - 1])
    at(page, ctx, out[a])
    set_visible(page, False)
    set_visible(page, True)
    at(page, ctx, out[b + 1])
    page.wait_for_function("() => window.__tour.S.missed.length", timeout=5000)


def sc_offer_resume(page, ctx, tour):
    stale_progress(page, tour)
    tap(page, "continue")


def sc_offer_song(page, ctx, tour):
    fixture = json.loads(json.dumps(tour))
    fixture["stops"][0]["song"] = TEST_SONG
    OVERRIDE[f"/{TOUR}/tour.json"] = json.dumps(fixture).encode()
    begin(page, ctx, tour)
    playing(page, ctx, tour, 0, 0.5)
    finish_current(page)
    page.wait_for_function("() => window.__tour.S.song && !window.__tour.S.current", timeout=5000)
    at(page, ctx, stop_pt(tour, 0), speed=10)


def sc_stories(page, ctx, tour):
    begin(page, ctx, tour, heard=2)
    playing(page, ctx, tour, 2)
    tap(page, "open_stories")
    tap(page, "open_stop", id=tour["stops"][-1]["id"])


def sc_log(page, ctx, tour):
    begin(page, ctx, tour, heard=1)
    playing(page, ctx, tour, 1)
    tap(page, "open_log")


def sc_map_follow(page, ctx, tour):
    begin(page, ctx, tour, heard=2)
    at(page, ctx, before(tour, 2, 4000))
    tap(page, "open_map")


def sc_map_whole(page, ctx, tour):
    sc_map_follow(page, ctx, tour)
    tap(page, "map_whole")


def sc_map_pin(page, ctx, tour):
    sc_map_follow(page, ctx, tour)
    tap(page, "map_pin", id=tour["stops"][-1]["id"])


def sc_arrived(page, ctx, tour):
    begin(page, ctx, tour, heard=len(tour["stops"]))
    at(page, ctx, tour["route"]["return"][-1])


# name: (scene, what it needs from SEL, where it is shot)
SCENES = {
    "setup": (sc_setup, (), ("light-portrait", "dark-portrait", "dark-landscape")),
    "setup-stories": (sc_setup_stories, (), ("light-portrait", "dark-portrait")),
    "reloaded-resume": (sc_reloaded_resume, (), ("dark-portrait", "dark-landscape")),
    "reloaded-carry-on": (sc_reloaded_carry_on, (), ("dark-portrait", "dark-landscape")),
    "stale": (sc_stale, (), ("light-portrait", "dark-portrait")),
    "between": (sc_between, (), ("dark-portrait", "dark-landscape")),
    "playing": (sc_playing, (), ("dark-portrait", "dark-landscape")),
    "queued": (sc_queued, (), ("dark-portrait", "dark-landscape")),
    "blocked": (sc_blocked, (), ("dark-portrait", "dark-landscape")),
    "offer-missed": (sc_offer_missed, (), ("dark-portrait", "dark-landscape")),
    "offer-resume": (sc_offer_resume, (), ("dark-portrait", "dark-landscape")),
    "offer-song": (sc_offer_song, (), ("dark-portrait", "dark-landscape")),
    "stories": (sc_stories, (), ("dark-portrait",)),
    "log": (sc_log, (), ("dark-portrait",)),
    "map-follow": (sc_map_follow, (), ("dark-portrait", "dark-landscape")),
    "map-whole": (sc_map_whole, ("map_whole",), ("dark-portrait",)),
    "map-pin": (sc_map_pin, ("map_pin",), ("dark-portrait",)),
    "arrived": (sc_arrived, (), ("dark-portrait", "dark-landscape")),
}


def screenshots(browser, url: str, tour: dict, failures: list[str]) -> None:
    """Every scene in SCENES as a PNG in tours/<tour>/build/shots/ (or $PLAYER_SHOTS)."""
    outdir = Path(os.environ.get("PLAYER_SHOTS") or ROOT / "tours" / TOUR / "build" / "shots")
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        old.unlink()
    print(f"Screenshots -> {outdir}")
    start = tour["route"]["outbound"][0]
    for view in ("light-portrait", "dark-portrait", "dark-landscape"):
        theme, orient = view.split("-")
        ctx = browser.new_context(permissions=["geolocation"], geolocation={"latitude": start[0], "longitude": start[1]},
                                  viewport=VIEWS[orient], color_scheme=theme, device_scale_factor=2)
        page = ctx.new_page()
        page.on("pageerror", lambda e, v=view: failures.append(f"page error ({v}): {e}"))
        page.goto(url)
        page.wait_for_function("() => window.__tour")
        for name, (scene, needs, views) in SCENES.items():
            if view not in views or not has(*needs):
                continue
            try:
                scene(page, ctx, tour)
                page.wait_for_timeout(500)
                page.screenshot(path=str(outdir / f"{name}-{view}.png"), animations="disabled")
                print(f"  shot {name}-{view}")
            except Exception as e:  # a scene that can't be set up is a failure, not a crash
                failures.append(f"screenshot {name}-{view}: {e}")
                print(f"  FAIL screenshot {name}-{view}: {str(e).splitlines()[0]}")
            finally:
                OVERRIDE.clear()
        ctx.close()


def main() -> None:
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    tour = json.loads((SITE / TOUR / "tour.json").read_text())
    url = serve()
    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            failures.append(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        if "--shots-only" not in flags:
            drive_checks(browser, url, tour, check, failures)
        if "--no-shots" not in flags:
            screenshots(browser, url, tour, failures)
        browser.close()

    print(f"\n{len(failures)} failure(s)" + ("".join(f"\n  - {f}" for f in failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
