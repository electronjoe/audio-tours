"""End-to-end test of the web player in headless Chrome: a simulated drive.

    uv run --with playwright python tests/player_drive.py [tour]

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
- a song on a stop (a fixture served in place of tour.json, never committed): the Now card
  shows it only after the stop ends, offers ▶ Play on Spotify or Save for later by the room
  before the next trigger, clears when the next stop starts, and stays in the stop's card
- after Download, the tour opens and plays with the network off

The screenshot goes to tours/<tour>/build/player-test.png, or to $PLAYER_TEST_SHOT.
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TOUR = sys.argv[1] if len(sys.argv) > 1 else "hobart"
SECONDS_PER_POINT = 300 / 22


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
    """A first visit: no saved progress, no log."""
    page.evaluate("() => localStorage.clear()")
    page.reload()
    page.wait_for_function("() => window.__tour")


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


def song_check(page, ctx, tour: dict, check) -> None:
    """A song on the first stop, served from a fixture copy of tour.json (task 006)."""
    s1, s2 = tour["stops"][0], tour["stops"][1]
    song = {"title": "Test Song", "artist": "Test Artist", "spotify": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
            "length": 214, "why": "A fixture song for the player test."}
    fixture = json.loads(json.dumps(tour))
    fixture["stops"][0]["song"] = song
    OVERRIDE[f"/{TOUR}/tour.json"] = json.dumps(fixture).encode()
    # Room = straight line to the edge of the next zone / speed (at least 8 m/s) > length + 60 s.
    edge = metres((s1["lat"], s1["lon"]), (s2["lat"], s2["lon"])) - s2["radius"]
    assert edge / 10 > song["length"] + 60 and edge / 50 < song["length"] + 60, "pick another fixture length"
    near = next(pt for pt in tour["route"]["outbound"]
                if 0 < metres(pt, (s2["lat"], s2["lon"])) - s2["radius"] < 10 * (song["length"] + 60) - 300)

    def fix(lat, lon, speed):
        page.evaluate("([lat, lon, v]) => window.__tour.onFix(lat, lon, 8, v)", [lat, lon, speed])
        page.wait_for_timeout(200)

    def card() -> str:
        return page.inner_text("#now")

    try:
        fresh(page)
        check(page.evaluate("() => Boolean(window.__tour.S.tour.stops[0].song)"), "the fixture tour.json (with a song) is served")
        ctx.set_geolocation({"latitude": s1["lat"], "longitude": s1["lon"], "accuracy": 8})
        page.click("#start")
        page.wait_for_timeout(300)
        fix(s1["lat"], s1["lon"], 10)
        page.wait_for_function("() => window.__tour.S.current", timeout=5000)
        st = state(page)
        check(st["current"] == s1["id"] and song["title"] not in card(),
              f"while {s1['id']} plays, no song card (current={st['current']}, queue={st['queue']}, now={card()[:120]!r})")
        page.click(f"details.stop[data-id={s1['id']}] summary")
        link = page.locator(f"details.stop[data-id={s1['id']}] a.song-link")
        check(link.count() == 1 and link.get_attribute("href") == song["spotify"], "the song is in the stop's expanded card")
        finish_current(page)
        page.wait_for_timeout(300)
        play = page.locator("#now a.song-play")
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


def main() -> None:
    tour = json.loads((SITE / TOUR / "tour.json").read_text())
    stops = [s["id"] for s in tour["stops"]]
    out, ret = tour["route"]["outbound"], tour["route"]["return"]
    url = serve()
    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            failures.append(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(permissions=["geolocation"], geolocation={"latitude": out[0][0], "longitude": out[0][1]})
        page = ctx.new_page()
        page.on("pageerror", lambda e: failures.append(f"page error: {e}"))
        page.goto(url)
        page.wait_for_function("() => window.__tour")
        page.evaluate("() => localStorage.clear()")
        page.reload()
        page.wait_for_function("() => window.__tour")
        page.click("#start")
        page.wait_for_timeout(500)

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
                        check(page.is_visible("#resume") and "Resume" in page.inner_text("#resume"), "Now card shows a Resume button")
                        page.click("#start")
                        page.wait_for_timeout(500)
                        st = state(page)
                        check(st["started"] and st["current"] is None and not st["queue"], f"Start plays nothing (current={st['current']})")
                        page.click("#resume")
                        page.wait_for_timeout(500)
                        st = state(page)
                        check(st["current"] == cur and not st["paused"], f"Resume plays {cur}")
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
        page.click("#more > summary")
        page.click("#log-box > summary")
        page.wait_for_timeout(200)
        check("started (GPS" in page.inner_text("#log"), "More → Event log shows why stops started")

        print("Start here")
        page.click("#reset") if False else page.evaluate("() => { localStorage.clear(); }")
        page.reload()
        page.wait_for_function("() => window.__tour")
        page.click("#start")
        page.evaluate("() => window.__tour.trigger(0)")
        page.wait_for_timeout(300)
        page.click(f"details.stop[data-id={stops[4]}] summary")
        page.click(f"details.stop[data-id={stops[4]}] button.here")
        page.wait_for_timeout(500)
        st = state(page)
        check(st["current"] == stops[4], f"Start here on {stops[4]} plays it now (current={st['current']})")
        check(st["status"].get(stops[0]) == "skipped" and st["cursor"] == 5, f"stops before it skipped, cursor after it ({st['cursor']})")
        next_title = page.inner_text("#next")
        check(tour["stops"][5]["title"] in next_title, "Next stop card shows the following stop")
        page.click("#next button.next-now")
        page.wait_for_timeout(200)
        check(state(page)["queue"] == [stops[5]], "Next card button queues (does not interrupt) while playing")

        print("Stale progress")
        old = {"cursor": 3, "status": {stops[0]: "played", stops[1]: "played"}, "pending": [stops[2]]}
        for choice in ("#continue", "#restart"):
            page.evaluate("""(saved) => { const S = window.__tour.S; S.current = null; window.__tour.audio.pause();
                localStorage.setItem(`tour:${S.tour.slug}`, JSON.stringify({...saved, savedAt: Date.now() - 9 * 3600e3})); }""", old)
            page.reload()
            page.wait_for_function("() => window.__tour")
            if choice == "#continue":
                check(not page.is_visible("#start") and page.is_visible("#restart") and page.is_visible("#continue"),
                      "progress from 9 h ago offers Start from the beginning / Continue instead of Start")
                check("stop 4" in page.inner_text("#continue"), f"Continue names the next stop ({page.inner_text('#continue')!r})")
            page.click(choice)
            page.wait_for_timeout(500)
            st = state(page)
            check(st["started"] and st["current"] is None, f"{choice} plays nothing")
            if choice == "#continue":
                check(st["cursor"] == 3 and st["resume"] == [stops[2]], "Continue keeps progress and still offers Resume")
            else:
                check(st["cursor"] == 0 and not st["status"] and not st["resume"], "Start from the beginning clears progress")

        print("Coarse fix")
        fresh(page)
        ctx.set_geolocation({"latitude": out[0][0], "longitude": out[0][1], "accuracy": 10})
        page.click("#start")
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
        page.click("#start")
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
        text = page.inner_text("#now").lower()
        check("passed while you were away" in text and zone["title"].lower() in text, "Now card offers it as Passed while you were away")
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
        check(not st["missed"] and "passed while you were away" not in page.inner_text("#now").lower(), "the offer clears when the next stop starts")
        # No fix for over 20 s counts as away too.
        page.evaluate("() => { const S = window.__tour.S; S.fix.time -= 25000; S.last.time -= 25000; }")
        ctx.set_geolocation({"latitude": out[k + 1][0], "longitude": out[k + 1][1], "accuracy": 60})
        page.wait_for_timeout(300)
        check(state(page)["away"] and "settling" in page.inner_text("#status"), "25 s without a fix: the next rough fix waits for a better one")

        print("Song")
        song_check(page, ctx, tour, check)

        print("Offline")
        fresh(page)
        if page.is_visible("#download"):
            page.click("#download")
        page.wait_for_function("() => document.querySelector('#dl-card').hidden", timeout=60000)
        check(True, "Download finished; download card hidden")
        ctx.set_offline(True)
        page.reload()
        page.wait_for_function("() => window.__tour", timeout=10000)
        page.click("#start")
        page.evaluate("() => window.__tour.trigger(1)")
        page.wait_for_timeout(800)
        st = state(page)
        check(st["current"] == stops[1] and not st["paused"], f"offline: stop plays from the cache ({st['current']}, paused={st['paused']})")
        ctx.set_offline(False)
        shot = os.environ.get("PLAYER_TEST_SHOT") or ROOT / "tours" / TOUR / "build" / "player-test.png"
        page.screenshot(path=str(shot), full_page=True)
        browser.close()

    print(f"\n{len(failures)} failure(s)" + ("".join(f"\n  - {f}" for f in failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
