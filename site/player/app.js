// GPS audio tour player. No framework, no build step.
//
// Stops play in sequence. A cursor marks the next stop in the sequence; only the
// first `lookahead` unplayed stops from the cursor can trigger, so a story placed on
// the return leg can't fire on the way out. A triggered stop is queued, never
// interrupts the one playing, and stops it jumps over are marked skipped (still
// playable by hand). "Start here" is the manual override: it moves the cursor and
// plays that stop now.
//
// Start never plays audio (tasks/001): it arms GPS, and saved progress is offered as
// Resume. Coarse (network) fixes never trigger. While the page is hidden Chrome sends no
// GPS (tasks/006), so after a gap the player waits for a fix of ±50 m or better, then
// offers any stop whose zone the jump crossed as "Passed while you were away" (status
// `missed`), never auto-playing it. Every trigger, play and ignored fix goes to an event
// log in localStorage (More → Event log).

const CACHE = "audio-tours";
const SCHEMA = 1; // the tour.json format this player reads (docs/tour-json.md)
const MAX_ACCURACY = 150; // metres; worse fixes are shown but never trigger (walking tours need ~40: tasks/007)
const SETTLE_ACCURACY = 50; // metres; after Start or a gap, the first fix used must be this good (tasks/006)
const SETTLE_PATIENCE = 30000; // ms; if no fix that good comes for this long, fall back to MAX_ACCURACY
const AWAY_AFTER = 20000; // ms without a fix that counts as being away, like a hidden page
const SPEED_HOLD = 10000; // ms after a gap in which no speed is derived from positions
const STALE_AFTER = 8 * 3600 * 1000; // ms; older saved progress asks "from the beginning or continue?"
const LOG_SIZE = 30; // event-log entries kept
const NEAR = 2000; // metres; "Play now" is the green button only this close to the zone
const SONG_MARGIN = 60; // s; offer a song only if the next trigger is this much further off than its length (tasks/006)
const SONG_MIN_SPEED = 8; // m/s; the room check never assumes slower, so a stop at the lights opens no window
const $ = (sel) => document.querySelector(sel);

const S = {
  tour: null,
  cursor: 0,
  status: {}, // stop id -> "played" | "skipped" | "missed" (passed while away)
  queue: [], // stops waiting to play
  current: null,
  started: false,
  stale: false, // saved progress older than STALE_AFTER: offer "from the beginning" or "continue"
  resume: [], // stops that were playing or queued when the page was last closed: offered, not played
  missed: [], // stops passed while away, offered in the Now card until the next stop starts
  song: null, // the stop whose song the Now card shows, from its end until the next stop starts (tasks/006)
  why: {}, // stop id -> {cause, d, acc}: why it was queued, for the event log
  fix: null, // the latest fix, shown: {lat, lon, accuracy, speed, time, coarse}
  last: null, // the latest fix used for triggering (the start of a catch-up segment)
  away: null, // {since, from, back}: set while hidden or after AWAY_AFTER without a fix
  holdSpeedUntil: 0, // no position-derived speed before this time (just after a gap)
  track: [], // the last 2 minutes of used fixes {lat, lon, speed, time}, speed null if unknown
  log: [], // event log, newest last (also in localStorage)
  cached: new Set(), // stop ids whose audio is in the cache
  wakeLock: null,
  sim: null,
  blocked: false, // the browser refused to start audio; show a "Tap to play" button
};
const audio = new Audio();
audio.preload = "auto";
let objectURL = null;

// --- persistence --------------------------------------------------------------

const key = () => `tour:${S.tour.slug}`;
const byId = (id) => stops().find((s) => s.id === id);
function save() {
  try {
    // `pending` (an unresumed offer, the stop playing, then the queue) is offered as Resume after a reload.
    const pending = [...S.resume, S.current, ...S.queue].filter(Boolean).map((s) => s.id);
    const missed = S.missed.map((s) => s.id);
    localStorage.setItem(key(), JSON.stringify({ cursor: S.cursor, status: S.status, pending, missed, savedAt: Date.now() }));
  } catch {}
}
function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(key()) || "{}");
    S.cursor = saved.cursor || 0;
    S.status = saved.status || {};
    S.resume = (saved.pending || []).map(byId).filter(Boolean);
    S.missed = (saved.missed || []).map(byId).filter(Boolean);
    const progress = S.cursor || Object.keys(S.status).length || S.resume.length;
    // Progress saved before savedAt existed counts as stale.
    S.stale = Boolean(progress) && Date.now() - (saved.savedAt || 0) > STALE_AFTER;
  } catch {}
  try {
    S.log = JSON.parse(localStorage.getItem(`${key()}:log`) || "[]");
  } catch {}
}

// --- event log ----------------------------------------------------------------
// Why each stop started, and the fixes that were ignored, so the next oddity on the road
// can be diagnosed (tasks/001). Kept in localStorage only.

function logEvent(ev, s, info = {}) {
  S.log.push({ t: Date.now(), ev, ...(s ? { n: s.n } : {}), ...info });
  S.log = S.log.slice(-LOG_SIZE);
  try {
    localStorage.setItem(`${key()}:log`, JSON.stringify(S.log));
  } catch {}
  if ($("#log-box")?.open) renderLog();
}

// --- geometry -----------------------------------------------------------------

function metres(a, b) {
  const R = 6371000, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
const km = (m) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1)} km`);
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const mapsLink = (s) => `https://www.google.com/maps/search/?api=1&query=${s.lat},${s.lon}`;

// --- navigate from here (tasks/003) -------------------------------------------------
// Self-contained: tests/test_navigate.py runs this block under Node.

const NAV_MAX = 10; // points: 9 waypoints plus the destination, what the Android Maps app takes

/** The Google Maps directions link from stop `i` onward: that stop and every later one (its
 *  `nav` point, else its trigger point; `nav: false` leaves it out), then `route.end`. A point
 *  equal to the one before it is dropped; repeats further apart stay (they make an out-and-back).
 *  No origin, so Maps starts from where the phone is. Returns {url, label, points} or null. */
function navLink(tour, i) {
  const pts = [];
  const add = (p) => {
    if (p && (!pts.length || String(pts[pts.length - 1]) !== String(p))) pts.push(p);
  };
  for (const s of tour.stops.slice(i)) add(s.nav === false ? null : s.nav || [s.lat, s.lon]);
  add(tour.route && tour.route.end);
  if (!pts.length) return null;
  const cut = pts.length > NAV_MAX;
  const points = pts.slice(0, NAV_MAX);
  const enc = (p) => encodeURIComponent(p.join(","));
  let url = `https://www.google.com/maps/dir/?api=1&destination=${enc(points[points.length - 1])}`;
  if (points.length > 1) url += `&waypoints=${points.slice(0, -1).map(enc).join("%7C")}`;
  url += `&travelmode=${tour.mode === "walk" ? "walking" : "driving"}`;
  return { url, label: cut ? `Navigate (next ${NAV_MAX} stops)` : "Navigate from here", points };
}

// --- end navigate from here ---------------------------------------------------------

// --- sequence and queue -------------------------------------------------------

const stops = () => S.tour.stops;
const busy = (s) => S.current === s || S.queue.includes(s);

/** Indexes of the stops GPS may trigger now: the next `lookahead` unplayed ones, cut short
 *  at a `strict` stop (one whose zone sits on the road to the stop before it). */
function armed() {
  const out = [];
  for (let i = S.cursor; i < stops().length && out.length < S.tour.lookahead; i++) {
    const s = stops()[i];
    if (S.status[s.id] || busy(s)) continue;
    if (s.strict && out.length) break; // a strict stop waits until the one before it is handled
    out.push(i);
  }
  return out;
}

/** Move the cursor past stop i, marking unhandled stops it jumps over as skipped. */
function advanceTo(i) {
  for (let j = S.cursor; j < i; j++) {
    const s = stops()[j];
    if (!S.status[s.id] && !busy(s)) S.status[s.id] = "skipped";
  }
  S.cursor = Math.max(S.cursor, i + 1);
}

/** Queue stop i by GPS or by hand (the "Play now" button on the Next stop card). */
function trigger(i, why = { cause: "manual" }) {
  advanceTo(i);
  enqueue(stops()[i], why);
  save();
}

/** Queue s; it plays now if nothing else is playing. `why` goes to the event log. */
function enqueue(s, why = { cause: "manual" }) {
  if (busy(s)) return;
  delete S.status[s.id];
  S.why[s.id] = why;
  S.queue.push(s);
  if (S.current) logEvent("queued", s, why);
  else playNext();
  render();
}

/** Manual override: play stop i now, interrupting anything playing, and resume the sequence after it. */
function startHere(i) {
  const s = stops()[i];
  S.queue = [];
  if (S.current && S.current !== s) S.status[S.current.id] ||= "skipped";
  advanceTo(i);
  S.cursor = i + 1;
  delete S.status[s.id];
  S.why[s.id] = { cause: "manual" };
  save();
  play(s);
}

/** The Resume offer: play what was playing (and queued) when the page was last closed. */
function resume() {
  if (!S.started) start();
  const list = S.resume;
  S.resume = [];
  for (const s of list) enqueue(s, { cause: "resume" });
  save();
}

/** A stop starting ends the offers, except that playing one offer leaves the others. */
function settleOffers(s) {
  if (S.resume.includes(s) || S.missed.includes(s)) {
    S.resume = S.resume.filter((x) => x !== s);
    S.missed = S.missed.filter((x) => x !== s);
    return;
  }
  for (const r of S.resume) if (!S.status[r.id] && !busy(r)) S.status[r.id] = "skipped";
  S.resume = [];
  S.missed = [];
}

function playNext() {
  S.blocked = false;
  const next = S.queue.shift();
  if (next) play(next);
  else {
    S.current = null;
    render();
  }
}

async function play(s) {
  settleOffers(s);
  S.song = null;
  S.current = s;
  logEvent("play", s, S.why[s.id] || { cause: "manual" });
  render();
  try {
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = URL.createObjectURL(await audioBlob(s));
    audio.src = objectURL;
    await audio.play();
  } catch (err) {
    // Usually autoplay being refused, or audio that isn't downloaded while offline.
    toast(`Couldn't play stop ${s.n}: ${err.message}`);
    S.current = null;
    S.queue.unshift(s);
    S.blocked = true;
    render();
    return;
  }
  save();
  if ("mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: s.title,
      artist: `Stop ${s.n} of ${stops().length}`,
      album: S.tour.title,
    });
  }
}

audio.addEventListener("ended", () => {
  if (S.current) S.status[S.current.id] = "played";
  offerSong(S.current);
  save();
  playNext();
});
audio.addEventListener("timeupdate", renderNow);
audio.addEventListener("play", renderNow);
audio.addEventListener("pause", renderNow);

function skip() {
  if (!S.current) return;
  S.status[S.current.id] = "skipped";
  audio.pause();
  save();
  playNext();
}

if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("nexttrack", skip);
  navigator.mediaSession.setActionHandler("previoustrack", () => (audio.currentTime = 0));
}

// --- audio cache (offline) ----------------------------------------------------

const audioKey = (s) => new URL(s.audio, location.href).href;

async function audioBlob(s) {
  if (!s.audio) throw new Error("no audio published yet");
  const cache = await caches.open(CACHE);
  let r = await cache.match(audioKey(s));
  if (!r) {
    r = await fetch(s.audio);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await cache.put(audioKey(s), r.clone());
    S.cached.add(s.id);
  }
  return r.blob();
}

async function checkCached() {
  const cache = await caches.open(CACHE);
  for (const s of stops()) if (s.audio && (await cache.match(audioKey(s)))) S.cached.add(s.id);
  render();
}

async function downloadAll() {
  const btn = $("#download");
  btn.disabled = true;
  try {
    if (navigator.storage?.persist) await navigator.storage.persist();
    const cache = await caches.open(CACHE);
    const todo = stops().filter((s) => s.audio && !S.cached.has(s.id));
    let done = 0;
    for (const s of todo) {
      btn.textContent = `Downloading ${done + 1} of ${todo.length}…`;
      const r = await fetch(s.audio);
      if (!r.ok) throw new Error(`stop ${s.n}: HTTP ${r.status}`);
      await cache.put(audioKey(s), r);
      S.cached.add(s.id);
      done++;
      render();
    }
    // Also cache the page itself (the service worker caches it too; this is belt and braces).
    await cache.addAll([location.href, "tour.json"]).catch(() => {});
    toast("Tour downloaded: it now works offline");
  } catch (err) {
    toast(`Download stopped: ${err.message}`);
  } finally {
    btn.disabled = false;
    render();
  }
}

// --- GPS, screen ------------------------------------------------------------------

/** Where p projects onto the segment a→b: t (0 at a, 1 at b) and its distance in metres
 *  from the segment. Flat-earth maths, fine over a few kilometres. */
function along(a, b, p) {
  const M = 111320, k = Math.cos((a.lat * Math.PI) / 180);
  const bx = (b.lon - a.lon) * k * M, by = (b.lat - a.lat) * M;
  const px = (p.lon - a.lon) * k * M, py = (p.lat - a.lat) * M;
  const L = bx * bx + by * by;
  const t = L ? (px * bx + py * by) / L : 0;
  const c = Math.max(0, Math.min(1, t));
  return { t, d: Math.hypot(px - c * bx, py - c * by) };
}

/** After a gap: mark armed stops whose zone the straight jump from `from` to `to` crossed
 *  as missed and offer them (tasks/006). A stop counts if its centre lies within
 *  `radius + 10 % of the jump` of the segment (curves) and between its ends (not one still
 *  ahead). A stop whose zone holds `to` isn't missed: it triggers as usual. */
function catchUp(from, to, gap) {
  const jump = metres(from, to);
  for (let found = true; found; ) {
    found = false;
    for (const i of armed()) {
      const s = stops()[i];
      if (metres(to, s) <= s.radius) continue;
      const { t, d } = along(from, to, s);
      if (t <= 0 || t >= 1 || d > s.radius + 0.1 * jump) continue;
      S.status[s.id] = "missed";
      advanceTo(i);
      S.missed.push(s);
      logEvent("missed", s, { cause: "catch-up", gap, jump: Math.round(jump), d: Math.round(d) });
      found = true;
    }
  }
}

/** Log a fix that landed in an armed zone but couldn't trigger it, at most once a minute per stop. */
function logIgnored(cause, fix) {
  for (const i of armed()) {
    const s = stops()[i];
    const d = metres(fix, s);
    if (d > s.radius || fix.time - (logIgnored.at[s.id] || 0) < 60000) continue;
    logIgnored.at[s.id] = fix.time;
    logEvent("ignored", s, { cause, d: Math.round(d), acc: Math.round(fix.accuracy) });
  }
}
logIgnored.at = {};

/** Every fix. `coarse` marks the low-accuracy network fallback: shown, never used. */
function onFix(lat, lon, accuracy, speed, { coarse = false } = {}) {
  const prev = S.fix;
  const now = Date.now();
  const fix = { lat, lon, accuracy, speed: speed ?? null, time: now, coarse };
  S.fix = fix;
  if (!S.started) return render();
  // No fix for a while counts as being away, like a hidden page.
  if (!S.away && prev && now - prev.time > AWAY_AFTER) S.away = { since: prev.time, from: S.last };
  if (coarse) {
    logIgnored("coarse-ignored", fix);
    return render();
  }
  if (S.away) S.away.back ||= now;
  // Right after Start or a gap the first fixes are rough and jumpy: wait for a good one.
  const limit = S.away && now - S.away.back < SETTLE_PATIENCE ? SETTLE_ACCURACY : MAX_ACCURACY;
  if (accuracy > limit) {
    logIgnored(S.away ? "settling" : "inaccurate", fix);
    return render();
  }
  if (S.away) {
    const { since, from, back } = S.away;
    S.away = null;
    S.holdSpeedUntil = back + SPEED_HOLD;
    if (from) {
      const gap = Math.round((now - since) / 1000);
      logEvent("back", null, { gap, jump: Math.round(metres(from, fix)), acc: Math.round(accuracy) });
      catchUp(from, fix, gap);
    }
  } else if (fix.speed == null && S.last && now >= S.holdSpeedUntil && now - S.last.time <= AWAY_AFTER) {
    // Speed from positions only between consecutive used fixes, never across or just after a gap.
    const dt = (now - S.last.time) / 1000;
    if (dt > 0) fix.speed = metres(S.last, fix) / dt;
  }
  S.last = fix;
  S.track = [...S.track.filter((f) => now - f.time <= 120000), { lat, lon, speed: fix.speed, time: now }];
  for (const i of armed()) {
    const s = stops()[i];
    const d = metres(fix, s);
    if (d <= s.radius) trigger(i, { cause: "gps", d: Math.round(d), acc: Math.round(accuracy) });
  }
  render();
}

// GPS problem shown in the status chip: "denied", "nofix" or null.
S.gpsProblem = null;
let watchId = null;

function startGPS() {
  if (!("geolocation" in navigator)) return toast("No GPS in this browser");
  if (watchId != null) navigator.geolocation.clearWatch(watchId);
  watchId = navigator.geolocation.watchPosition(
    (p) => {
      S.gpsProblem = null;
      if (!S.sim) onFix(p.coords.latitude, p.coords.longitude, p.coords.accuracy, p.coords.speed);
    },
    (e) => {
      if (e.code === e.PERMISSION_DENIED) {
        S.gpsProblem = "denied";
        toast("Location is blocked for this site: tap the icon left of the address bar → Permissions → Location → Allow, then reload.");
      } else {
        // No satellite fix yet (indoors, under a roof, a ship's hull). Keep trying, and
        // meanwhile ask for a rough network location so the distances show something.
        S.gpsProblem = "nofix";
        navigator.geolocation.getCurrentPosition(
          (p) => !S.sim && !S.fix && onFix(p.coords.latitude, p.coords.longitude, p.coords.accuracy, p.coords.speed, { coarse: true }),
          () => {},
          { enableHighAccuracy: false, maximumAge: 60000, timeout: 20000 },
        );
        setTimeout(startGPS, 5000);
      }
      render();
    },
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 30000 },
  );
}

async function keepAwake() {
  try {
    S.wakeLock = await navigator.wakeLock?.request("screen");
    S.wakeLock?.addEventListener("release", () => ((S.wakeLock = null), render()));
  } catch {}
  render();
}
document.addEventListener("visibilitychange", () => {
  if (!S.started) return;
  // Hidden means no GPS (tasks/006): what happened meanwhile is worked out on return.
  if (document.visibilityState === "hidden") S.away ||= { since: Date.now(), from: S.last };
  else if (!S.wakeLock) keepAwake();
});

/** Arm GPS, keep the screen on and unlock audio. Never plays a stop (tasks/001). */
function start() {
  if (S.started) return;
  S.started = true;
  S.stale = false;
  S.away = { since: Date.now(), from: null }; // wait for a good first fix; nothing to catch up
  // A play() inside the tap unlocks audio for later automatic playback. It must not
  // replace a stop that is already playing (Resume or Play now can call start()).
  if (!S.current) {
    audio.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
    audio.play().catch(() => {});
  }
  keepAwake();
  startGPS();
  logEvent("start");
  save();
  render();
}

/** "Start from the beginning" (stale progress): forget every stop's status, then start. */
function restart() {
  S.status = {};
  S.cursor = 0;
  S.queue = [];
  S.resume = [];
  S.missed = [];
  logEvent("reset");
  start();
}

// --- simulation (?sim) ---------------------------------------------------------------

function simulate(factor) {
  if (S.sim) {
    clearInterval(S.sim.timer);
    S.sim = null;
    return render();
  }
  const path = [...(S.tour.route.outbound || []), ...(S.tour.route.return || [])];
  let i = 0;
  const speed = 22; // m/s, about 80 km/h (walking tours: ~1.4, tasks/007)
  S.sim = { factor };
  S.sim.timer = setInterval(() => {
    let budget = speed * factor * 0.5;
    while (budget > 0 && i < path.length - 1) {
      budget -= metres({ lat: path[i][0], lon: path[i][1] }, { lat: path[i + 1][0], lon: path[i + 1][1] });
      i++;
    }
    onFix(path[i][0], path[i][1], 10, speed * factor);
    if (i >= path.length - 1) simulate();
  }, 500);
  render();
}

// --- songs (tasks/006) ---------------------------------------------------------------
// When a stop with a song ends, the Now card shows the song until the next stop starts. While
// Spotify is in front the page gets no GPS, so ▶ Play on Spotify is offered only if the next
// trigger is more than the song's length plus SONG_MARGIN away; otherwise "Save for later".
// The song stays in the stop's expanded card either way.

const esc = (t) => String(t).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** The speed the room check assumes: the higher of the latest fix's and the median of the last
 *  2 minutes, but at least SONG_MIN_SPEED. */
function songSpeed() {
  const now = Date.now();
  const v = S.track.filter((f) => now - f.time <= 120000 && f.speed != null).map((f) => f.speed).sort((a, b) => a - b);
  const median = v.length ? (v[(v.length - 1) >> 1] + v[v.length >> 1]) / 2 : 0;
  return Math.max(S.fix?.speed ?? 0, median, SONG_MIN_SPEED);
}

/** Seconds until GPS could trigger the next stop: straight-line distance to the edge of the
 *  nearest armed zone over songSpeed(). Never longer than by road, so it errs toward "no room".
 *  0 without a usable fix; Infinity when no stop is armed (the end of the tour). */
function secondsToTrigger() {
  const a = armed();
  if (!a.length) return Infinity;
  if (!S.fix || S.fix.coarse || S.away) return 0;
  const d = Math.min(...a.map((i) => Math.max(0, metres(S.fix, stops()[i]) - stops()[i].radius)));
  return d / songSpeed();
}

const songRoom = (song) => secondsToTrigger() > song.length + SONG_MARGIN;

/** Stop s has just ended: show its song, if it has one. */
function offerSong(s) {
  if (!s?.song) return;
  S.song = s;
  const secs = secondsToTrigger();
  logEvent("song", s, { room: songRoom(s.song), secs: Number.isFinite(secs) ? Math.round(secs) : null });
}

function songCard() {
  const s = S.song, g = s?.song;
  if (!g) return "";
  const action = songRoom(g)
    ? `<a class="song-play button primary wide" href="${esc(g.spotify)}" target="_blank" rel="noopener" data-id="${s.id}">▶ Play on Spotify</a>
      <div class="help">Come back to the tour when the song ends, so the next stop can play.</div>`
    : `<div class="song-save"><b>Save for later</b>: the next stop comes before the song would end. It stays in stop ${s.n}'s card below.</div>`;
  return `<div class="offer song"><div class="label">Song for this stretch</div>
    <div class="title">${esc(g.title)}</div>
    <div class="sub">${esc(g.artist)} · ${mmss(g.length)}</div>
    <p class="why">${esc(g.why)}</p>${action}</div>`;
}

/** The song in a stop's expanded card, always playable from there. */
function songLine(s) {
  const g = s.song;
  if (!g) return "";
  return `<p class="song-line">♪ <b>${esc(g.title)}</b>, ${esc(g.artist)} (${mmss(g.length)}). ${esc(g.why)}
          <a class="song-link" href="${esc(g.spotify)}" target="_blank" rel="noopener" data-id="${s.id}">▶ Play on Spotify</a></p>`;
}

function wireSongs() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a.song-play, a.song-link");
    if (a) logEvent("song-play", byId(a.dataset.id));
  });
}

// --- rendering --------------------------------------------------------------------

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 4000);
}

function stateOf(s, i) {
  if (S.current === s) return "playing";
  if (S.queue.includes(s)) return "queued";
  if (S.resume.includes(s)) return "resume";
  if (S.status[s.id]) return S.status[s.id];
  if (armed().includes(i)) return "armed";
  return "upcoming";
}
const LABEL = { playing: "Playing", queued: "Queued", played: "Played", skipped: "Skipped", missed: "Passed while away", resume: "Ready to resume", armed: "Listening for", upcoming: "Later" };

/** Resume and "Passed while you were away" offers in the Now card. */
function renderOffers() {
  let html = "";
  if (S.resume.length) {
    const r = S.resume[0];
    html += `<button id="resume" class="primary wide">▶ Resume: ${r.n}. ${r.title}</button>`;
  }
  for (const s of S.missed) {
    html += `<div class="offer"><div class="label">Passed while you were away</div>
      <button class="offer-play wide" data-id="${s.id}">${S.current ? "Queue next" : "▶ Play"}: stop ${s.n}. ${s.title}</button></div>`;
  }
  html += songCard();
  // renderNow runs every second: rewrite only on a change, so the buttons stay tappable.
  if (renderOffers.html !== html) $("#now-offers").innerHTML = renderOffers.html = html;
}

function renderNow() {
  const s = S.current;
  const box = $("#now");
  renderOffers();
  $("#tap-play").hidden = !(S.blocked && S.queue.length);
  if (S.blocked && S.queue.length) {
    box.className = "card blocked";
    $("#now-title").textContent = `${S.queue[0].n}. ${S.queue[0].title}`;
    $("#now-sub").textContent = "Ready, but the phone didn't start it";
    $("#now-bar").style.width = "0%";
    $("#now-controls").hidden = true;
    return;
  }
  if (!s) {
    box.className = "card idle";
    $("#now-title").textContent = S.started ? "Nothing playing" : "Tour not started";
    $("#now-sub").textContent = !S.started ? "Tap Start tour when you set off"
      : S.away ? "Waiting for a good GPS fix" : "Waiting for the next stop";
    $("#now-bar").style.width = "0%";
    $("#now-controls").hidden = true;
    return;
  }
  box.className = "card playing";
  $("#now-title").textContent = `${s.n}. ${s.title}`;
  const dur = audio.duration || s.duration || 0;
  const t = audio.currentTime || 0;
  $("#now-sub").textContent = `${audio.paused ? "Paused" : "Playing"} · ${mmss(t)} / ${mmss(dur)} · ${mmss(Math.max(0, dur - t))} left`;
  $("#now-bar").style.width = dur ? `${(100 * t) / dur}%` : "0%";
  $("#now-controls").hidden = false;
  $("#pause").textContent = audio.paused ? "Resume" : "Pause";
}

function renderNext() {
  const box = $("#next");
  const queued = S.queue.map((s) => `${s.n}. ${s.title}`);
  const a = armed();
  const lines = [];
  if (queued.length) lines.push(`<div class="queued"><b>Queued to play next:</b> ${queued.join(" → ")}</div>`);
  if (a.length) {
    const s = stops()[a[0]];
    let dist = "", eta = "", fill = 0, near = false;
    if (S.fix) {
      const d = Math.max(0, metres(S.fix, s) - s.radius);
      near = d <= NEAR;
      dist = d === 0 ? "in the zone" : `${km(d)} to trigger`;
      if (d > 0 && S.fix.speed > 2) eta = ` · ~${Math.max(1, Math.round(d / S.fix.speed / 60))} min`;
      fill = Math.max(0, Math.min(1, 1 - d / 8000));
    }
    lines.push(`<div class="label">Next stop</div>
      <div class="title">${s.n}. ${s.title}</div>
      <div class="sub">${s.place}${dist ? ` · <b>${dist}</b>${eta}` : " · waiting for GPS"}</div>
      <div class="bar"><div style="width:${fill * 100}%"></div></div>
      <button class="next-now ${S.current || !near ? "" : "primary"} wide" data-i="${a[0]}">${S.current ? "Queue it to play next" : "▶ Play now"}</button>`);
  } else if (!queued.length) {
    lines.push(`<div class="label">Next stop</div><div class="title">${S.cursor >= stops().length ? "End of the tour" : "—"}</div>`);
  }
  box.innerHTML = lines.join("");
}

function renderStops() {
  const list = $("#stops");
  const open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.dataset.id));
  list.innerHTML = "";
  stops().forEach((s, i) => {
    const state = stateOf(s, i);
    const d = S.fix ? km(metres(S.fix, s)) : "";
    const nav = navLink(S.tour, i);
    const el = document.createElement("details");
    el.className = `stop ${state}`;
    el.dataset.id = s.id;
    el.open = open.has(s.id);
    el.innerHTML = `
      <summary>
        <span class="num">${state === "played" ? "✓" : s.n}</span>
        <span class="info"><span class="t">${s.title}</span>
          <span class="s">${LABEL[state]}${d ? ` · ${d} away` : ""}${S.cached.has(s.id) ? "" : " · not downloaded"}</span></span>
        <span class="chev">›</span>
      </summary>
      <div class="more">
        <p>${s.place}. Triggers within ${km(s.radius)}. ${s.duration ? mmss(s.duration) + " long." : "No audio yet."}</p>
        ${songLine(s)}
        <p class="actions">
          <button class="here primary" data-i="${i}">${state === "playing" ? "Restart" : "▶ Start here"}</button>
          <button class="queue" data-i="${i}">Queue next</button>
          ${nav ? `<a class="nav" href="${nav.url}" target="_blank" rel="noopener">${nav.label}</a>` : ""}
          <a href="${mapsLink(s)}" target="_blank" rel="noopener">Open trigger point in Google Maps</a>
          ${S.status[s.id] ? `<button class="unplay" data-i="${i}">Mark unplayed</button>` : ""}
        </p>
      </div>`;
    list.appendChild(el);
  });
}

function renderStatus() {
  const f = S.fix;
  const withAudio = stops().filter((s) => s.audio).length;
  const all = withAudio > 0 && S.cached.size >= withAudio;
  const weak = f && (f.coarse || f.accuracy > MAX_ACCURACY);
  const settling = S.started && f && !weak && S.away;
  const chips = [
    [S.gpsProblem === "denied" ? "GPS blocked (see Permissions)"
      : S.gpsProblem === "nofix" && (!f || weak) ? "GPS: no satellite fix yet (go outside); retrying"
      : f ? (weak ? `GPS weak (±${Math.round(f.accuracy)} m)` : settling ? `GPS settling (±${Math.round(f.accuracy)} m)` : "GPS ✓")
      : S.started ? "GPS: waiting…" : "",
     S.gpsProblem || weak || settling || (S.started && !f)],
    [S.started && !S.wakeLock ? "Screen may sleep" : "", true],
    [all ? "Offline ✓" : `Downloaded ${S.cached.size}/${withAudio}`, !all],
    [S.sim ? `Simulating ×${S.sim.factor}` : "", false],
  ];
  $("#status").innerHTML = chips.filter(([c]) => c).map(([c, warn]) => `<span class="${warn ? "warn" : ""}">${c}</span>`).join("");
  $("#start").hidden = S.started || S.stale;
  $("#stale").hidden = S.started || !S.stale;
  if (S.stale) {
    const next = stops()[armed()[0] ?? S.cursor];
    $("#continue").textContent = next ? `Continue (next: stop ${next.n})` : "Continue";
  }
  $("#dl-card").hidden = all;
  if (!$("#download").disabled) $("#download").textContent = "Download tour for offline";
}

function renderMap() {
  const svg = $("#map");
  const r = S.tour.route;
  const pts = [...(r.outbound || []), ...(r.return || []), ...stops().map((s) => [s.lat, s.lon])];
  if (!pts.length) return;
  const lat0 = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const xs = pts.map((p) => p[1] * k), ys = pts.map((p) => -p[0]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const w = Math.max(...xs) - minX, h = Math.max(...ys) - minY;
  const sc = 1000 / Math.max(w, h);
  const P = (lat, lon) => [((lon * k - minX) * sc + 40).toFixed(1), ((-lat - minY) * sc + 40).toFixed(1)];
  svg.setAttribute("viewBox", `0 0 ${w * sc + 80} ${h * sc + 80}`);
  const line = (path, cls) => `<polyline class="${cls}" points="${path.map((p) => P(p[0], p[1]).join(",")).join(" ")}"/>`;
  let out = line(r.outbound || [], "route") + line(r.return || [], "route ret");
  stops().forEach((s, i) => {
    const [x, y] = P(s.lat, s.lon);
    out += `<g class="pin ${stateOf(s, i)}"><circle cx="${x}" cy="${y}" r="${(s.radius * sc) / 111000 / 1}"/><text x="${x}" y="${y}">${s.n}</text></g>`;
  });
  if (S.fix) {
    const [x, y] = P(S.fix.lat, S.fix.lon);
    out += `<circle class="me" cx="${x}" cy="${y}" r="14"/>`;
  }
  svg.innerHTML = out;
}

const CAUSE = { gps: "GPS", manual: "tapped", resume: "Resume", "catch-up": "catch-up", "coarse-ignored": "coarse network fix", settling: "first fixes after a gap", inaccurate: "inaccurate fix" };
function describe(e) {
  const stop = e.n ? `Stop ${e.n} ` : "";
  const fix = [e.d != null ? `${km(e.d)} from centre` : "", e.acc != null ? `±${e.acc} m` : ""].filter(Boolean).join(", ");
  const why = [CAUSE[e.cause] || e.cause, fix].filter(Boolean).join(", ");
  switch (e.ev) {
    case "play": return `${stop}started (${why})`;
    case "queued": return `${stop}queued (${why})`;
    case "missed": return `${stop}passed while away, offered (catch-up: ${km(e.jump)} jump, ${km(e.d)} from the line)`;
    case "ignored": return `${stop}not triggered: ${why}`;
    case "back": return `Back after ${mmss(e.gap)} without GPS: jumped ${km(e.jump)}, ±${e.acc} m`;
    case "start": return "Tour started (GPS armed, nothing played)";
    case "reset": return "Progress reset";
    case "song": return `${stop}ended: song offered with ${e.room ? "▶ Play on Spotify" : "Save for later"} (${e.secs == null ? "no stop ahead" : `~${mmss(e.secs)} to the next trigger`})`;
    case "song-play": return `${stop}song opened in Spotify`;
    default: return `${stop}${e.ev}`;
  }
}
function renderLog() {
  const time = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  $("#log").innerHTML = S.log.length
    ? [...S.log].reverse().map((e) => `<li data-ev="${e.ev}" data-cause="${e.cause || ""}"><b>${time(e.t)}</b> ${describe(e)}</li>`).join("")
    : "<li>Nothing yet.</li>";
}

function renderFiles() {
  const html = stops().filter((s) => s.audio)
    .map((s) => `<li><a href="${s.audio}" target="_blank">${s.n}. ${s.title}</a></li>`).join("");
  if ($("#files").innerHTML !== html) $("#files").innerHTML = html;
}

function render() {
  if (!S.tour) return;
  renderStatus();
  renderNow();
  renderNext();
  renderStops();
  if ($("#more").open && $("#map-box").open) renderMap();
  renderFiles();
}

// --- wiring -------------------------------------------------------------------------

async function main() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("../sw.js", { scope: "../" }).catch(() => {});
  S.tour = await (await fetch("tour.json", { cache: "no-cache" })).json();
  // docs/tour-json.md. A missing schema is a tour.json from before it was added: read it as 1.
  const schema = S.tour.schema ?? SCHEMA;
  if (schema !== SCHEMA) throw new Error(`it needs a newer player (tour.json schema ${schema}, this player reads ${SCHEMA}). Reload while online.`);
  S.tour.lookahead ||= 2;
  document.title = S.tour.title;
  $("#title").textContent = S.tour.title;
  load();
  render();
  checkCached();

  $("#start").onclick = start;
  $("#restart").onclick = restart;
  $("#continue").onclick = start;
  $("#log-box").addEventListener("toggle", renderLog);
  $("#now").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b?.id === "resume") resume();
    else if (b?.classList.contains("offer-play")) {
      if (!S.started) start();
      enqueue(byId(b.dataset.id), { cause: "catch-up" });
      save();
    }
  });
  $("#download").onclick = downloadAll;
  $("#pause").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("#skip").onclick = skip;
  $("#tap-play").onclick = playNext;
  $("#next").addEventListener("click", (e) => {
    const b = e.target.closest("button.next-now");
    if (!b) return;
    if (!S.started) start();
    trigger(Number(b.dataset.i), { cause: "manual" });
  });
  $("#map-box").addEventListener("toggle", renderMap);
  $("#reset").onclick = () => {
    if (!confirm("Reset the tour? Every stop becomes unplayed and the sequence restarts at stop 1.")) return;
    S.status = {};
    S.cursor = 0;
    S.queue = [];
    S.resume = [];
    S.missed = [];
    S.song = null;
    audio.pause();
    S.current = null;
    logEvent("reset");
    save();
    render();
  };
  $("#stops").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    e.preventDefault();
    const i = Number(b.dataset.i);
    if (!S.started) start();
    if (b.classList.contains("here")) startHere(i);
    else if (b.classList.contains("queue")) enqueue(stops()[i], { cause: "manual" });
    else if (b.classList.contains("unplay")) {
      delete S.status[stops()[i].id];
      S.cursor = Math.min(S.cursor, i);
      save();
      render();
    }
  });
  if (new URLSearchParams(location.search).has("sim")) {
    $("#sim").hidden = false;
    $("#sim").onclick = () => {
      if (!S.started) start();
      simulate(Number(new URLSearchParams(location.search).get("sim")) || 20);
    };
  }
  wireSongs();
  setInterval(renderNow, 1000);
  window.__tour = { S, onFix, trigger, startHere, skip, audio, save }; // for tests
}

main().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p class="error">Couldn't load the tour: ${err.message}</p>`);
});
