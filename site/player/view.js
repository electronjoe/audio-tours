// The player's screens (task 009, design A.3 in experiments/ui_ux_redesign/):
//
// - Setup: a checklist (save, location, home screen) and Start. Only on a first visit or with
//   stale progress; fresh progress opens the car screen, not started, one tap from carrying on.
// - The car screen (page one, always dark): a status row, a ring (distance to the next story, or
//   the story playing), one offer at a time, and a dock of two big buttons.
// - The map page (page two, map.js), one swipe or Map › away: the route, pins, the car, and a card
//   (a tapped pin, the song offer, what's playing or the next story). A story starting, a Resume
//   or missed offer, or arriving brings page one back; a song offer doesn't.
// - All stories: a full-screen list over either, with the log, Start over and the help.
//
// Loaded last, after app.js (the engine) and map.js; main() at the bottom starts it all.
// Buttons carry data-act (ACT below) and, where tests reach them, an id; tests/player_drive.py
// keeps every selector it uses in one table.

const V = {
  sheet: false, // All stories is open
  open: null, // the row whose actions are showing
  log: false, // Why did that play? is open
  page: 0, // the car screen's page: 0 the story, 1 the map
  key: null, // what was playing and offered at the last render: a change to something new returns to page one
  geo: null, // the geolocation permission: "granted", "prompt", "denied" or null (unknown)
  install: null, // Chrome's beforeinstallprompt event, while it offers one
  installed: false,
};
const RING = 2 * Math.PI * 46; // the ring's circumference in its 100-unit viewBox
const ICON = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z"/></svg>',
};
const LABEL = { playing: "Playing now", queued: "Next, after this one", resume: "Cut off: ready to resume", played: "Heard",
  skipped: "Skipped", missed: "Passed while away", next: "Next", upcoming: "Later" };

/** A stop's state as shown: of the armed stops (GPS may start any of the next `lookahead`),
 *  only the first is "next", and only while nothing is queued (the queued one is next then);
 *  the rest show as "upcoming", like any later stop. */
function shownState(s, i) {
  const st = stateOf(s, i);
  if (st !== "armed") return st;
  return !S.queue.length && armed()[0] === i ? "next" : "upcoming";
}
const HELP = `Keep this page open on screen while you drive; navigation can run in the background.
  Stories start by themselves as you reach each place, in order, and never interrupt each other: if two
  start close together, the second waits. The ring counts down to the next one. <b>Play it now</b>, or
  <b>Play now</b> on a story here or a pin on the map, plays a story straight away and carries on from it.
  If you switch to another app or the screen locks, the phone stops sending GPS to this page; a story you
  pass meanwhile is offered when you come back. Swipe left, or tap <b>Map ›</b>, for the map.
  <b>Why did that play?</b> shows what started each story.`;

/** Replace an element's HTML only when it changed, so buttons stay put between renders. */
function set(el, html) {
  if (el && el._html !== html) el.innerHTML = el._html = html;
}

const fmtMins = (m) => (m < 1 ? "under a minute" : m < 60 ? `${Math.round(m)} min` : `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`);
/** A distance for the ring: [number, unit]. */
function ringDist(m) {
  if (m <= 0) return ["0", "in the zone"];
  if (m < 1000) return [String(Math.max(50, Math.round(m / 50) * 50)), "metres"];
  return [(m / 1000).toFixed(m < 10000 ? 1 : 0), "km"];
}

// --- what the screens show --------------------------------------------------------

/** Fresh progress (saved within 8 hours) opens the car screen; a first visit or stale progress, setup. */
const carScreen = () => S.started || (!S.stale && S.savedAt > 0 && Date.now() - S.savedAt <= STALE_AFTER);
const withAudio = () => stops().filter((s) => s.audio);
const allSaved = () => withAudio().length > 0 && withAudio().every((s) => S.cached.has(s.id));
const finished = () => !S.current && !S.queue.length && !armed().length;
const heardCount = () => stops().filter((s) => S.status[s.id] === "played").length;

/** The next story GPS may start, and how far to the edge of its zone: by road on the route,
 *  else in a straight line (toStop, in app.js). */
function nextStory() {
  const i = armed()[0];
  if (i == null) return null;
  const { d, frac, secs, road } = toStop(i);
  return { i, s: stops()[i], d, frac, mins: secs == null ? null : secs / 60, road };
}

/** Length of the drive (outbound and return) in metres, and its time in seconds (OSRM's
 *  `route.seconds` when the route has it, else 80 km/h, as tour plan-check assumes). */
function trip() {
  const r = S.tour.route || {};
  let m = 0;
  for (const leg of [r.outbound || [], r.return || []])
    for (let k = 1; k < leg.length; k++) m += metres({ lat: leg[k - 1][0], lon: leg[k - 1][1] }, { lat: leg[k][0], lon: leg[k][1] });
  const timed = r.seconds && Object.values(r.seconds).every((v) => v.length);
  const secs = timed ? Object.values(r.seconds).reduce((a, v) => a + v[v.length - 1], 0) : m / (80 / 3.6);
  return { m, secs };
}
function about(secs) {
  const min = Math.max(5, Math.round(secs / 300) * 5);
  return `about ${min >= 60 ? `${Math.floor(min / 60)} h${min % 60 ? ` ${min % 60} min` : ""}` : `${min} min`}`;
}

// --- setup --------------------------------------------------------------------------

function check(id, done, n, title, why, button = "", extra = "") {
  return `<li class="check${done ? " done" : ""}" id="${id}"><span class="tick">${done ? "✓" : n}</span>
    <div class="check-t"><b>${title}</b><span>${why}</span>${extra}</div>${button}</li>`;
}

function setupHTML() {
  const all = stops().length, t = trip(), audioStops = withAudio();
  const bytes = audioStops.reduce((a, s) => a + (s.bytes || 0), 0);
  const have = audioStops.filter((s) => S.cached.has(s.id)).reduce((a, s) => a + (s.bytes || 0), 0);
  const pct = bytes ? Math.round((100 * have) / bytes) : 0;
  const saved = allSaved();
  const bar = `<div class="prog"><div id="save-bar" style="width:${pct}%"></div></div>`;
  const save = !audioStops.length ? check("check-save", false, 1, "Save the stories to this phone", "No audio is published yet.")
    : saved ? check("check-save", true, 1, "Save the stories to this phone", "Saved. The tour works with no signal.")
    : S.saving ? check("check-save", false, 1, "Save the stories to this phone", `Saving… ${pct} %`, "", bar)
    : S.saveError ? check("check-save", false, 1, "Save the stories to this phone",
      `<span class="no-signal">No signal: ${pct} % saved. Finish where you have coverage.</span>`,
      `<button class="act" id="download" data-act="download">Resume</button>`, bar)
    : check("check-save", false, 1, "Save the stories to this phone", `${Math.max(1, Math.round(bytes / 1e6))} MB, best on Wi-Fi. Then the tour works with no signal.`,
      `<button class="act" id="download" data-act="download">${have ? "Resume" : "Save"}</button>`, have ? bar : "");
  const geo = S.gpsProblem === "denied" ? "denied" : V.geo;
  const locate = check("check-gps", geo === "granted", 2, "Let stories start by themselves",
    geo === "denied" ? `<span class="no-signal">Location is blocked for this site: tap the icon left of the address bar → Permissions → Location → Allow, then reload.</span>`
      : "Uses your location only while this page is open.",
    geo === "granted" || geo === "denied" ? "" : `<button class="act" id="allow-gps" data-act="allowLocation">Allow</button>`);
  const standalone = matchMedia("(display-mode: standalone)").matches;
  const home = standalone || !(V.install || V.installed) ? ""
    : check("check-home", V.installed, 3, "Add to home screen", "Optional. Opens full screen, like an app.",
      V.installed ? "" : `<button class="act quiet" id="install" data-act="install">Add</button>`);
  let foot;
  if (S.stale) {
    const next = stops()[armed()[0] ?? S.cursor];
    foot = `<p class="fine top">This phone has progress on this tour from more than 8 hours ago.</p>
      <button class="go" id="restart" data-act="restart">Start from the beginning</button>
      <button class="go quiet" id="continue" data-act="continue">${next ? `Continue (next: stop ${next.n})` : "Continue"}</button>`;
  } else {
    foot = `${saved ? "" : `<p class="warn-line">Not saved yet: stories will need phone signal.</p>`}
      <button class="go" id="start" data-act="start">Start the tour</button>
      <p class="fine">Tap Start before you drive off. The screen stays on; nobody needs to touch it after that.</p>`;
  }
  return `<div class="setup-scroll">
      <p class="kicker">${S.tour.mode === "walk" ? "Walking" : "Driving"} audio tour</p>
      <h1>${esc(S.tour.title)}</h1>
      <p class="meta">${all} stor${all === 1 ? "y" : "ies"}${t.m ? ` · ${Math.round(t.m / 1000)} km · ${about(t.secs)}` : ""}</p>
      <h2>Get ready before you leave</h2>
      <ol class="checks">${save}${locate}${home}</ol>
      <button class="link" data-act="openSheet">See all ${all} stories →</button>
    </div>
    <div class="setup-foot">${foot}</div>`;
}

// --- the car screen -------------------------------------------------------------------

function statusHTML() {
  const f = S.fix, issues = [];
  const weak = f && (f.coarse || f.accuracy > MAX_ACCURACY);
  if (S.gpsProblem === "denied") issues.push("GPS blocked");
  else if (S.gpsProblem === "nofix" && (!f || weak)) issues.push("No GPS fix");
  else if (S.started && weak) issues.push(`GPS weak ±${Math.round(f.accuracy)} m`);
  else if (S.started && f && S.away) issues.push(`GPS settling ±${Math.round(f.accuracy)} m`);
  else if (S.started && !f) issues.push("Waiting for GPS");
  if (S.started && !S.wakeLock) issues.push("Screen may sleep");
  if (!allSaved()) issues.push("Not saved");
  if (S.sim) issues.push(`Simulating ×${S.sim.factor}`);
  return issues.length ? issues.map((t) => `<span class="pill warn">${t}</span>`).join("")
    : `<span class="pill"><span class="dot"></span>All set</span>`;
}

/** The ring's centre, the caption under it and the dock's left button, for the current state. */
function glanceParts() {
  const all = stops().length, cur = S.current;
  const ringBtn = (id, act, icon, label, text = "") =>
    `<button class="ring-btn" id="${id}" data-act="${act}" aria-label="${label}">${ICON[icon]}${text ? `<span>${text}</span>` : ""}</button>`;
  const playNow = (n) => `<button class="dock-btn" id="play-now" data-act="playNow" data-i="${n.i}">Play it now</button>`;
  if (!S.started && S.resume.length) {
    const r = S.resume[0];
    return {
      center: ringBtn("resume", "resume", "play", `Resume ${r.n}: ${r.title}`, "Resume"),
      cap: `<p class="label">Cut off · ${r.n} of ${all}</p><h1 class="big">${r.title}</h1>
        <button class="text-btn" id="carry-on" data-act="carryOn">Carry on without it</button>`,
      left: "",
    };
  }
  if (cur) {
    const q = S.queue[0];
    return {
      center: ringBtn("pause", "pause", audio.paused ? "play" : "pause", audio.paused ? "Play" : "Pause"),
      cap: `<p class="label">${audio.paused ? "Paused" : "Now playing"} · ${cur.n} of ${all}</p><h1 class="big">${cur.title}</h1>
        <p class="sub"><span id="left"></span> left</p>${q ? `<p class="then">Then ${q.n} · ${q.title}</p>` : ""}`,
      left: `<button class="dock-btn" id="skip" data-act="skip">Skip story</button>`,
    };
  }
  if (S.blocked && S.queue.length) {
    const b = S.queue[0];
    return {
      center: ringBtn("tap-play", "tapPlay", "play", `Play ${b.n}: ${b.title}`),
      cap: `<p class="label">Ready: tap to play · ${b.n} of ${all}</p><h1 class="big">${b.title}</h1>
        <p class="sub">The phone didn't start it by itself.</p>`,
      left: "",
    };
  }
  if (finished()) {
    return {
      center: `<div class="ring-txt"><span class="huge">✓</span></div>`,
      cap: `<p class="label">No more stories</p><h1 class="big">${heardCount()} of ${all} stories heard</h1>`,
      left: `<button class="dock-btn" id="start-over" data-act="reset">Start over</button>`,
    };
  }
  const n = nextStory();
  return {
    center: S.started ? `<div class="ring-txt"><span class="huge" id="dist"></span><span class="unit" id="mins"></span></div>`
      : ringBtn("carry-on", "carryOn", "play", "Carry on", "Carry on"),
    cap: n ? `<p class="label">Next story · ${n.s.n} of ${all}</p><h1 class="big">${n.s.title}</h1><p class="sub">${n.s.place}</p>` : "",
    left: n ? playNow(n) : "",
  };
}

/** One offer at a time: Resume (after Continue), then a stop passed while away, then a song. */
function offerHTML() {
  if (S.started && S.resume.length) {
    const r = S.resume[0];
    return `<div class="offer" id="offer"><p class="label">Pick up where you left off</p>
      <p class="o-title">${r.n} · ${r.title}</p><p class="o-why">It was playing when the page closed.</p>
      <div class="o-row"><button class="o-yes" data-act="resume">Play it</button>
      <button class="o-no" data-act="declineResume">Skip</button></div></div>`;
  }
  if (S.missed.length) {
    const s = S.missed[0], i = stops().indexOf(s);
    return `<div class="offer" id="offer"><p class="label">Passed while you were away</p>
      <p class="o-title">${s.n} · ${s.title}</p><p class="o-why">${s.place}</p>
      <div class="o-row"><button class="o-yes" data-act="playMissed" data-i="${i}">${S.current ? "Queue it" : "Play it"}</button>
      <button class="o-no" data-act="dismissMissed" data-i="${i}">Skip</button></div></div>`;
  }
  return songOffer();
}

/** The song after a stop (tasks/006): ▶ Play on Spotify when there's room before the next
 *  trigger, else Save for later. On the car screen and the map page. */
function songOffer(id = "offer") {
  const s = S.song, g = s?.song;
  if (!g) return "";
  const room = songRoom(g);
  return `<div class="offer song" id="${id}"><p class="label">♪ A song for this stretch</p>
    <p class="o-title">${esc(g.title)} · ${esc(g.artist)}</p><p class="o-why">${esc(g.why)} ${mmss(g.length)}.</p>
    ${room ? "" : `<p class="o-why song-save"><b>Save for later</b>: the next story comes before it would end. It stays in All stories, under story ${s.n}.</p>`}
    <div class="o-row">${room ? `<a class="o-yes song-play" href="${esc(g.spotify)}" target="_blank" rel="noopener" data-id="${s.id}">▶ Play on Spotify</a>` : ""}
    <button class="o-no" data-act="dismissSong">No thanks</button></div>
    ${room ? `<p class="o-hint">Come back to the tour when the song ends, so the next story can play.</p>` : ""}</div>`;
}

function glanceHTML() {
  const g = glanceParts();
  return `<div class="top">${statusHTML()}<span class="spacer"></span><button class="pg-btn" id="to-map" data-act="toMap">Map ›</button></div>
    <div class="hero"><div class="ring"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="track" cx="50" cy="50" r="46"/>
      <circle class="val" id="ring" cx="50" cy="50" r="46" stroke-dasharray="${RING}" stroke-dashoffset="${RING}"/></svg>${g.center}</div>
      <div class="caption">${g.cap}</div></div>
    ${offerHTML()}
    <div class="dock">${g.left}<button class="dock-btn" id="open-stories" data-act="openSheet">All stories</button></div>`;
}

// --- the map page's card ---------------------------------------------------------------

/** By priority: the tapped pin, the song offer, what's playing, the end, the next story. */
function mapCardHTML() {
  const all = stops().length, i = MAP.sel;
  const songLine = (s) => (s.song ? `<p class="o-why song-line">♪ Then a song: ${esc(s.song.title)} · ${esc(s.song.artist)}</p>` : "");
  if (i != null) {
    const s = stops()[i], st = shownState(s, i), nav = navLink(S.tour, i);
    return `<div class="offer pin-card" id="pin-card" data-id="${s.id}"><p class="label">Story ${s.n} · ${LABEL[st]}</p>
      <p class="o-title">${s.title}</p><p class="o-why">${[s.teaser ? esc(s.teaser) : s.place, s.duration ? mmss(s.duration) : "no audio yet"].filter(Boolean).join(" · ")}</p>
      ${songLine(s)}<div class="o-row"><button class="o-yes" id="pin-play" data-act="mapPlay" data-i="${i}">${st === "playing" ? "Restart" : "Play now"}</button>
      ${nav ? `<a class="o-no nav" href="${nav.url}" target="_blank" rel="noopener">${nav.label}</a>` : ""}</div></div>`;
  }
  if (S.song?.song) return songOffer("map-offer");
  const cur = S.current;
  if (cur) return `<p class="label">Now playing · ${cur.n} of ${all}</p><p class="o-title">${cur.title}</p>
    <p class="o-why">${cur.place ? `${cur.place} · ` : ""}<span id="p2-left"></span> left</p>${songLine(cur)}`;
  if (finished()) return `<p class="label">No more stories</p><p class="o-title">${heardCount()} of ${all} stories heard</p>`;
  const n = nextStory();
  // No "N of M" here (the car screen has it): with the distance and minutes, the line wrapped.
  return n ? `<p class="label">Next story<span id="p2-d"></span></p><p class="o-title">${n.s.title}</p><p class="o-why">${n.s.place}</p>` : "";
}

/** Something new for the car (a story starting, a Resume or missed offer, the end) brings page
 *  one back; a song offer doesn't, it's on the map page too. */
function backToStory() {
  const key = [S.current?.id, S.started && S.resume[0]?.id, S.missed.map((s) => s.id).join(), finished()].join("|");
  const fresh = S.current || (S.started && S.resume.length) || S.missed.length || finished();
  if (V.key != null && key !== V.key && fresh && V.page === 1) {
    MAP.sel = null;
    goto(0);
  }
  V.key = key;
}

// --- All stories ------------------------------------------------------------------------

function storiesHTML() {
  return stops().map((s, i) => {
    const state = shownState(s, i), nav = navLink(S.tour, i), g = s.song;
    const facts = [s.place, s.duration ? mmss(s.duration) : "no audio yet", LABEL[state]].filter(Boolean).join(" · ");
    return `<li class="row st-${state}" data-id="${s.id}">
      <button class="row-main" data-act="toggle" data-i="${i}" aria-expanded="${V.open === i}"><span class="num">${state === "played" ? "✓" : s.n}</span>
        <span class="row-t"><b>${s.title}${g ? ` <span class="note" aria-label="followed by a song">♪</span>` : ""}</b>
          <small>${facts}<span class="dist" data-i="${i}"></span>${s.audio && !S.cached.has(s.id) ? ` · <span class="unsaved">Not saved</span>` : ""}</small>
          ${g ? `<small class="song-line">♪ Then a song: ${esc(g.title)} · ${esc(g.artist)}</small>` : ""}</span></button>
      <div class="row-acts"${V.open === i ? "" : " hidden"}>
        <div class="o-row"><button class="o-yes" data-act="playHere" data-i="${i}">${state === "playing" ? "Restart" : "Play now"}</button>
          <button class="o-no" data-act="queue" data-i="${i}">Queue next</button></div>
        ${nav ? `<a class="o-no nav" href="${nav.url}" target="_blank" rel="noopener">${nav.label}</a>` : ""}
        <p class="row-links"><a class="maps" href="${mapsLink(s)}" target="_blank" rel="noopener">Open the trigger point in Google Maps</a>
          ${g ? `<a class="song-link" href="${esc(g.spotify)}" target="_blank" rel="noopener" data-id="${s.id}">▶ Play “${esc(g.title)}” on Spotify</a>` : ""}
          ${S.status[s.id] ? `<button class="text-btn" data-act="unplay" data-i="${i}">Mark unplayed</button>` : ""}</p>
      </div></li>`;
  }).join("");
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
    case "song-dismiss": return `${stop}song: No thanks`;
    case "dismiss": return `${stop}passed while away: Skip (stays skipped)`;
    case "resume-declined": return `${stop}not resumed after a reload (skipped: ${(e.skipped || []).join(", ")})`;
    default: return `${stop}${e.ev}`;
  }
}
function renderLog() {
  const time = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  $("#log").innerHTML = S.log.length
    ? [...S.log].reverse().map((e) => `<li data-ev="${e.ev}" data-cause="${e.cause || ""}"><b>${time(e.t)}</b> ${describe(e)}</li>`).join("")
    : "<li>Nothing yet.</li>";
}

/** The engine logged an event: refresh the log if it's open. */
function onLog() {
  if (V.log) renderLog();
}

function renderFiles() {
  set($("#files"), withAudio().map((s) => `<li><a href="${s.audio}" target="_blank">${s.n}. ${s.title}</a></li>`).join(""));
}

/** Clicks on a song's Spotify link are logged (tasks/006). */
function wireSongs() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a.song-play, a.song-link");
    if (a) logEvent("song-play", byId(a.dataset.id));
  });
}

// --- pager, toast ---------------------------------------------------------------------

const pager = () => $("#pager");
const smooth = () => !matchMedia("(prefers-reduced-motion: reduce)").matches;
function goto(k, animate = true) {
  pager().scrollTo({ left: k * pager().clientWidth, behavior: animate && smooth() ? "smooth" : "auto" });
}
function onPage() {
  const k = Math.round(pager().scrollLeft / Math.max(1, pager().clientWidth));
  if (k === V.page) return;
  V.page = k;
  document.querySelectorAll(".dots span").forEach((d, j) => d.classList.toggle("on", j === k));
  if (k === 1) {
    MAP.cam = null; // arrive framed, then glide
    drawMap();
  } else leaveMap();
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 4000);
}

// --- render -------------------------------------------------------------------------------

function render() {
  if (!S.tour) return;
  const car = carScreen();
  document.body.classList.toggle("car", car);
  $("#setup").hidden = car;
  $("#drive").hidden = !car;
  set($("#setup"), car ? "" : setupHTML());
  set($("#p1"), car ? glanceHTML() : "");
  if (car) {
    backToStory();
    set($("#p2card"), mapCardHTML());
    $("#map-mode").textContent = MAP.mode === "route" ? "Follow car" : "Whole route";
    if (V.page === 1) drawMap();
  }
  $("#sheet").hidden = !V.sheet;
  set($("#stories"), storiesHTML());
  $("#log-toggle").textContent = V.log ? "Hide the log" : "Why did that play?";
  $("#log").hidden = !V.log;
  renderFiles();
  tick();
}

/** The numbers that change between renders: the ring, distance, time left, row distances. */
function tick() {
  if (!S.tour) return;
  let frac = 0;
  const cur = S.current;
  if (cur) {
    const dur = audio.duration || cur.duration || 0, t = audio.currentTime || 0;
    frac = dur ? t / dur : 0;
    for (const el of [$("#left"), $("#p2-left")]) if (el) el.textContent = mmss(Math.max(0, dur - t));
  } else if (finished()) frac = 1;
  else {
    const n = nextStory();
    if (n && n.d != null) {
      frac = n.frac;
      const [num, unit] = ringDist(n.d);
      if ($("#dist")) $("#dist").textContent = num;
      if ($("#mins")) $("#mins").textContent = n.mins != null && n.d > 0 ? `${unit} · ${fmtMins(n.mins)}` : unit;
      if ($("#p2-d")) $("#p2-d").textContent = ` · ${n.d > 0 ? `${num} ${unit === "metres" ? "m" : unit}` : "in the zone"}${n.mins != null && n.d > 0 ? ` · ${fmtMins(n.mins)}` : ""}`;
    } else if ($("#dist")) {
      $("#dist").textContent = "–";
      $("#mins").textContent = "waiting for GPS";
    }
  }
  const ring = $("#ring");
  if (ring) ring.style.strokeDashoffset = RING * (1 - frac);
  if (V.page === 1 && carScreen()) drawMap(false);
  document.querySelectorAll(".dist[data-i]").forEach((el) => {
    const s = stops()[Number(el.dataset.i)];
    el.textContent = S.fix ? ` · ${km(metres(S.fix, s))} away` : "";
  });
}

// --- actions --------------------------------------------------------------------------------

const begin = () => S.started || start();
const ACT = {
  start,
  restart,
  continue: start,
  download: downloadAll,
  allowLocation() {
    navigator.geolocation?.getCurrentPosition(
      () => ((V.geo = "granted"), render()),
      (e) => ((V.geo = e.code === e.PERMISSION_DENIED ? "denied" : V.geo), render()),
      { enableHighAccuracy: true, timeout: 20000 },
    );
  },
  install() {
    const prompt = V.install;
    if (!prompt) return;
    prompt.prompt();
    prompt.userChoice.then((c) => ((V.installed = c.outcome === "accepted"), (V.install = null), render())).catch(() => {});
  },
  openSheet() { V.sheet = true; V.open = null; },
  closeSheet() { V.sheet = false; },
  toggle(i) { V.open = V.open === i ? null : i; },
  toggleLog() { V.log = !V.log; if (V.log) renderLog(); },
  pause() { audio.paused ? audio.play() : audio.pause(); },
  skip,
  tapPlay: playNext,
  playNow(i) { begin(); trigger(i, { cause: "manual" }); },
  resume,
  carryOn,
  declineResume,
  playMissed(i) { begin(); enqueue(stops()[i], { cause: "catch-up" }); save(); },
  dismissMissed: (i) => dismissMissed(stops()[i]),
  dismissSong,
  playHere(i) { begin(); startHere(i); V.sheet = false; },
  queue(i) { begin(); enqueue(stops()[i], { cause: "manual" }); },
  unplay,
  reset() {
    if (!confirm("Start over? Every story becomes unplayed and the tour restarts at story 1.")) return;
    resetTour();
    V.sheet = false;
  },
  toMap() { goto(1); },
  toStory() { goto(0); },
  mapMode() { MAP.mode = MAP.mode === "route" ? "follow" : "route"; MAP.sel = null; },
  pin(i) { MAP.sel = MAP.sel === i ? null : i; },
  mapPlay(i) { begin(); startHere(i); MAP.sel = null; },
  sim() { begin(); simulate(Number(new URLSearchParams(location.search).get("sim")) || 20); },
};

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-act]");
  if (!b || b.disabled || !S.tour) return;
  const fn = ACT[b.dataset.act];
  if (!fn) return console.warn("no action", b.dataset.act);
  fn(b.dataset.i == null ? undefined : Number(b.dataset.i));
  render();
});

// Chrome offers installing only now and then; keep its prompt for setup's third check.
addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  V.install = e;
  render();
});
addEventListener("appinstalled", () => ((V.installed = true), (V.install = null), render()));

// --- wiring -------------------------------------------------------------------------

async function main() {
  await loadTour();
  document.title = S.tour.title;
  $("#help").innerHTML = HELP;
  $("#sim").hidden = !new URLSearchParams(location.search).has("sim");
  pager().addEventListener("scroll", onPage, { passive: true });
  navigator.permissions?.query({ name: "geolocation" }).then((p) => {
    V.geo = p.state;
    p.onchange = () => ((V.geo = p.state), render());
    render();
  }).catch(() => {});
  render();
  checkCached();
  loadBase();
  wireSongs();
  audio.addEventListener("timeupdate", tick);
  audio.addEventListener("play", render);
  audio.addEventListener("pause", render);
  setInterval(tick, 1000);
  window.__tour = { S, onFix, trigger, startHere, skip, audio, save, render, nextStory }; // for tests
}

main().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p class="error">Couldn't load the tour: ${err.message}</p>`);
});
