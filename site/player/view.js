// The player's page: status chips, Start, the Now and Next cards, the stop list, More and the
// toast. Loaded last, after app.js (the engine) and map.js; main() at the bottom starts it all.

// --- rendering --------------------------------------------------------------------

// --- rendering --------------------------------------------------------------------

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 4000);
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

/** The engine logged an event: refresh the log if it's open. */
function onLog() {
  if ($("#log-box")?.open) renderLog();
}

// --- wiring -------------------------------------------------------------------------

async function main() {
  await loadTour();
  document.title = S.tour.title;
  $("#title").textContent = S.tour.title;
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
  audio.addEventListener("timeupdate", renderNow);
  audio.addEventListener("play", renderNow);
  audio.addEventListener("pause", renderNow);
  setInterval(renderNow, 1000);
  window.__tour = { S, onFix, trigger, startHere, skip, audio, save }; // for tests
}

main().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p class="error">Couldn't load the tour: ${err.message}</p>`);
});
