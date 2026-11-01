"""End-to-end test of the web player in headless Chrome: a simulated drive.

    uv run --with playwright python tests/player_drive.py [tour]

Serves site/ locally, grants geolocation, taps Start, then drives the tour's route
(outbound then return) one route point at a time. Each route point is about 300 m,
i.e. about 14 s at 80 km/h, so a track "finishes" after its real duration in route
points. Checks:

- every stop plays exactly once, in sequence order
- a trigger never interrupts the track playing (it queues)
- return-leg stops never trigger on the outbound leg
- a reload mid-story resumes that story after Start
- "Start here" interrupts and continues the sequence from that stop
- after Download, the tour opens and plays with the network off
"""

from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TOUR = sys.argv[1] if len(sys.argv) > 1 else "hobart"
SECONDS_PER_POINT = 300 / 22


def serve() -> str:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/{TOUR}/"


def state(page) -> dict:
    return page.evaluate("""() => { const S = window.__tour.S; return {
        current: S.current && S.current.id, queue: S.queue.map(s => s.id), status: {...S.status},
        cursor: S.cursor, blocked: S.blocked, t: window.__tour.audio.currentTime,
        paused: window.__tour.audio.paused } }""")


def finish_current(page) -> None:
    page.evaluate("() => { const a = window.__tour.audio; a.currentTime = Math.max(0, a.duration - 0.05); }")
    page.wait_for_function("() => window.__tour.audio.ended || !window.__tour.S.current || window.__tour.audio.currentTime < 1", timeout=5000)


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
                    # Once, mid-story: reload and check the story resumes after Start.
                    if not reloaded and cur == stops[2]:
                        reloaded = True
                        page.reload()
                        page.wait_for_function("() => window.__tour")
                        resumed = state(page)
                        check(resumed["queue"][:1] == [cur], f"after a reload mid-{cur}, it is first in line ({resumed['queue']})")
                        page.click("#start")
                        page.wait_for_timeout(500)
                        check(state(page)["current"] == cur, f"Start resumes {cur}")
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

        print("Offline")
        page.click("summary >> text=More") if False else None
        page.evaluate("() => localStorage.clear()")
        page.reload()
        page.wait_for_function("() => window.__tour")
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
        page.screenshot(path=str(ROOT / "tours" / TOUR / "build" / "player-test.png"), full_page=True)
        browser.close()

    print(f"\n{len(failures)} failure(s)" + ("".join(f"\n  - {f}" for f in failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
