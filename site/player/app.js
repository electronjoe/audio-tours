// GPS audio tour player. No framework, no build step.
//
// Stops play in sequence. A cursor marks the next stop in the sequence; only the
// first `lookahead` unplayed stops from the cursor can trigger, so a story placed on
// the return leg can't fire on the way out. A triggered stop is queued, never
// interrupts the one playing, and stops it jumps over are marked skipped (still
// playable by hand). "Start here" is the manual override: it moves the cursor and
// plays that stop now.

const CACHE = "audio-tours";
const MAX_ACCURACY = 150; // metres; worse fixes are shown but never trigger (walking tours need ~40: tasks/007)
const $ = (sel) => document.querySelector(sel);

const S = {
  tour: null,
  cursor: 0,
  status: {}, // stop id -> "played" | "skipped"
  queue: [], // stops waiting to play
  current: null,
  started: false,
  fix: null, // {lat, lon, accuracy, speed, time}
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
function save() {
  try {
    // `pending` (the stop playing, then the queue) lets a reload resume where it was.
    const pending = [S.current, ...S.queue].filter(Boolean).map((s) => s.id);
    localStorage.setItem(key(), JSON.stringify({ cursor: S.cursor, status: S.status, pending }));
  } catch {}
}
function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(key()) || "{}");
    S.cursor = saved.cursor || 0;
    S.status = saved.status || {};
    S.queue = (saved.pending || []).map((id) => stops().find((s) => s.id === id)).filter(Boolean);
  } catch {}
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

function trigger(i) { // GPS, or the "Play now" button on the Next stop card
  advanceTo(i);
  enqueue(stops()[i]);
  save();
}

function enqueue(s) {
  if (busy(s)) return;
  delete S.status[s.id];
  S.queue.push(s);
  if (!S.current) playNext();
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
  save();
  play(s);
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
  S.current = s;
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

function onFix(lat, lon, accuracy, speed) {
  const prev = S.fix;
  const now = Date.now();
  if (speed == null && prev) {
    const dt = (now - prev.time) / 1000;
    if (dt > 0) speed = metres(prev, { lat, lon }) / dt;
  }
  S.fix = { lat, lon, accuracy, speed, time: now };
  if (S.started && accuracy <= MAX_ACCURACY) {
    for (const i of armed()) {
      const s = stops()[i];
      if (metres(S.fix, s) <= s.radius) trigger(i);
    }
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
          (p) => !S.sim && !S.fix && onFix(p.coords.latitude, p.coords.longitude, p.coords.accuracy, p.coords.speed),
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
  if (document.visibilityState === "visible" && S.started && !S.wakeLock) keepAwake();
});

function start() {
  S.started = true;
  // A play() inside the tap unlocks audio for later automatic playback.
  audio.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
  audio.play().catch(() => {});
  keepAwake();
  startGPS();
  if (S.queue.length && !S.current) playNext(); // resume after a reload
  render();
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
  if (S.status[s.id]) return S.status[s.id];
  if (armed().includes(i)) return "armed";
  return "upcoming";
}
const LABEL = { playing: "Playing", queued: "Queued", played: "Played", skipped: "Skipped", armed: "Listening for", upcoming: "Later" };

function renderNow() {
  const s = S.current;
  const box = $("#now");
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
    $("#now-sub").textContent = S.started ? "Waiting for the next stop" : "Tap Start tour when you set off";
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
    let dist = "", eta = "", fill = 0;
    if (S.fix) {
      const d = Math.max(0, metres(S.fix, s) - s.radius);
      dist = d === 0 ? "in the zone" : `${km(d)} to trigger`;
      if (d > 0 && S.fix.speed > 2) eta = ` · ~${Math.max(1, Math.round(d / S.fix.speed / 60))} min`;
      fill = Math.max(0, Math.min(1, 1 - d / 8000));
    }
    lines.push(`<div class="label">Next stop</div>
      <div class="title">${s.n}. ${s.title}</div>
      <div class="sub">${s.place}${dist ? ` · <b>${dist}</b>${eta}` : " · waiting for GPS"}</div>
      <div class="bar"><div style="width:${fill * 100}%"></div></div>
      <button class="next-now ${S.current ? "" : "primary"} wide" data-i="${a[0]}">${S.current ? "Queue it to play next" : "▶ Play now"}</button>`);
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
        <p class="actions">
          <button class="here primary" data-i="${i}">${state === "playing" ? "Restart" : "▶ Start here"}</button>
          <button class="queue" data-i="${i}">Queue next</button>
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
  const weak = f && f.accuracy > MAX_ACCURACY;
  const chips = [
    [S.gpsProblem === "denied" ? "GPS blocked (see Permissions)"
      : S.gpsProblem === "nofix" && (!f || weak) ? "GPS: no satellite fix yet (go outside); retrying"
      : f ? (weak ? `GPS weak (±${Math.round(f.accuracy)} m)` : "GPS ✓") : S.started ? "GPS: waiting…" : "",
     S.gpsProblem || weak || (S.started && !f)],
    [S.started && !S.wakeLock ? "Screen may sleep" : "", true],
    [all ? "Offline ✓" : `Downloaded ${S.cached.size}/${withAudio}`, !all],
    [S.sim ? `Simulating ×${S.sim.factor}` : "", false],
  ];
  $("#status").innerHTML = chips.filter(([c]) => c).map(([c, warn]) => `<span class="${warn ? "warn" : ""}">${c}</span>`).join("");
  $("#start").hidden = S.started;
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
  S.tour.lookahead ||= 2;
  document.title = S.tour.title;
  $("#title").textContent = S.tour.title;
  load();
  render();
  checkCached();

  $("#start").onclick = start;
  $("#download").onclick = downloadAll;
  $("#pause").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("#skip").onclick = skip;
  $("#tap-play").onclick = playNext;
  $("#next").addEventListener("click", (e) => {
    const b = e.target.closest("button.next-now");
    if (!b) return;
    if (!S.started) start();
    trigger(Number(b.dataset.i));
  });
  $("#map-box").addEventListener("toggle", renderMap);
  $("#reset").onclick = () => {
    if (!confirm("Reset the tour? Every stop becomes unplayed and the sequence restarts at stop 1.")) return;
    S.status = {};
    S.cursor = 0;
    S.queue = [];
    audio.pause();
    S.current = null;
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
    else if (b.classList.contains("queue")) enqueue(stops()[i]);
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
  setInterval(renderNow, 1000);
  window.__tour = { S, onFix, trigger, startHere, skip, audio }; // for tests
}

main().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p class="error">Couldn't load the tour: ${err.message}</p>`);
});
