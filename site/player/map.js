// The map page (page two, task 009 design A.3): the route, the part already driven, numbered pins
// with their trigger zones, ♪ on stops followed by a song, and the car, drawn as SVG in metres
// around the tour's centre (equirectangular, the projection map.json uses: docs/tour-json.md).
// Pins (with their `label`, when a stop has one), the car and line widths keep their size on
// screen at any zoom. The camera follows the car
// and the story it's heading for (or playing), or shows the whole route.
//
// Under the route goes the tour's base map, map.json from `tour map` (task 010), when it has one:
// land and sea, water, parks, rivers, main roads by rank, and town names at a fixed size, those
// that would cover a pin or each other left out. The attribution shows while it's drawn.
//
// Nothing runs while page one is showing: view.js calls drawMap() only while the map page is on
// screen, and the camera's glide stops when the page goes.
// Loaded after app.js, whose state (S) and helpers it uses.

const MAP = {
  built: false,
  mode: "follow", // or "route": the whole route
  sel: null, // the pin tapped, its card showing
  origin: null, // [lat, lon]: the projection's centre
  cam: null, // where the camera is: {cx, cy, s} (centre in metres, metres per pixel)
  goal: null, // where it's going
  frame: 0, // the glide's animation frame, while one is pending
  pins: [], // [x, y] of each stop, metres
};
const FOLLOW_MIN = 4000; // metres: the narrowest view across the free part of the screen when following
const PIN_GAP = 30; // px: pins nearer than this on screen are spread sideways
const LBL_X = 19; // px: a pin label's gap from its pin's centre
const EDGE_FADE = 3000; // metres: the base map fades out this far inside its edge
const M_PER_DEG = 111320;

/** [x, y] in metres from the origin, y south, as map.json. */
function mxy(lat, lon) {
  const [lat0, lon0] = MAP.origin;
  return [(lon - lon0) * M_PER_DEG * Math.cos((lat0 * Math.PI) / 180), -(lat - lat0) * M_PER_DEG];
}

/** The centre of the route and stops' bounding box (map.json's origin, give or take rounding). */
function routeOrigin() {
  const pts = [...(S.path?.pts || []), ...stops()];
  const lats = pts.map((p) => p.lat), lons = pts.map((p) => p.lon);
  return [(Math.min(...lats) + Math.max(...lats)) / 2, (Math.min(...lons) + Math.max(...lons)) / 2];
}

const pathD = (pts) => (pts.length ? "M" + pts.map(([x, y]) => `${x.toFixed(0)} ${y.toFixed(0)}`).join("L") : "");

/** SVG path data from map.json's flat arrays: rings closed, lines open. */
function flatD(list, closed) {
  let d = "";
  for (const a of list) {
    d += `M${a[0]} ${a[1]}`;
    for (let k = 2; k < a.length; k += 2) d += `L${a[k]} ${a[k + 1]}`;
    if (closed) d += "Z";
  }
  return d;
}

/** The base map's SVG: sea (when the coastline crosses the area) and land, parks, water,
 *  rivers, roads, the coastline as a line if it couldn't be closed, a fade at its edge, and the
 *  place names (placed in placeMap). */
function baseSVG(b) {
  const [x0, y0, x1, y1] = b.extent, w = x1 - x0, h = y1 - y0, f = EDGE_FADE;
  const fade = [["l", x0, y0, f, h], ["r", x1 - f, y0, f, h], ["t", x0, y0, w, f], ["b", x0, y1 - f, w, f]]
    .map(([k, x, y, fw, fh]) => `<rect fill="url(#m-fade-${k})" x="${x}" y="${y}" width="${fw}" height="${fh}"/>`).join("");
  const grad = (k, x1_, y1_, x2_, y2_) => `<linearGradient id="m-fade-${k}" x1="${x1_}" y1="${y1_}" x2="${x2_}" y2="${y2_}">
    <stop offset="0" stop-color="#0d1312"/><stop offset="1" stop-color="#0d1312" stop-opacity="0"/></linearGradient>`;
  const roads = [1, 2, 3].map((r) => `<path class="m-road r${r}" d="${flatD((b.roads || []).filter((x) => x.rank === r).map((x) => x.pts), false)}"/>`).join("");
  return `<defs>${grad("l", 0, 0, 1, 0)}${grad("r", 1, 0, 0, 0)}${grad("t", 0, 0, 0, 1)}${grad("b", 0, 1, 0, 0)}</defs>
    ${b.land ? `<rect class="m-sea" x="${x0}" y="${y0}" width="${w}" height="${h}"/><path class="m-land" d="${flatD(b.land, true)}"/>` : ""}
    <path class="m-park" d="${flatD(b.green || [], true)}"/><path class="m-sea" d="${flatD(b.water || [], true)}"/>
    <path class="m-river" d="${flatD(b.rivers || [], false)}"/>${roads}<path class="m-coast" d="${flatD(b.coast || [], false)}"/>
    ${fade}`;
}

function buildMap() {
  const b = S.base;
  MAP.origin = b ? b.origin : routeOrigin();
  MAP.pins = stops().map((s) => mxy(s.lat, s.lon));
  const route = (S.path?.pts || []).map((p) => mxy(p.lat, p.lon));
  const d = pathD(route);
  const zones = stops().map((s, i) => `<circle class="m-zone" data-i="${i}" cx="${MAP.pins[i][0].toFixed(0)}" cy="${MAP.pins[i][1].toFixed(0)}" r="${s.radius}"/>`).join("");
  const pins = stops().map((s, i) => `<g class="m-pin" data-act="pin" data-i="${i}" data-id="${s.id}" role="button" aria-label="Story ${s.n}: ${esc(s.title)}">
      <circle class="m-hit" r="24"/><circle class="m-pdot" r="13"/><text class="m-n" dy=".35em">${s.n}</text>${s.song ? `<g class="m-song" transform="translate(12 -12)"><circle r="8.5"/><text dy=".35em">♪</text></g>` : ""}${s.label ? `<text class="m-lbl" x="${LBL_X}" dy=".35em">${esc(s.label)}</text>` : ""}</g>`).join("");
  const places = (b?.places || []).map((p) => `<g class="m-place r${p.rank}"><circle r="2.5"/><text x="7" dy=".35em">${esc(p.name)}</text></g>`).join("");
  $("#p2map").innerHTML = `<svg class="m" id="map" role="img" aria-label="Map of the route and its stories" preserveAspectRatio="xMidYMid meet">
    <g class="m-base">${b ? baseSVG(b) : ""}</g><g class="m-zones">${zones}</g>
    <path class="m-edge" d="${d}"/><path class="m-route" d="${d}"/><path class="m-done" d=""/><g class="m-places">${places}</g>
    <g class="m-pins">${pins}</g>
    <g class="m-car" display="none"><circle class="m-halo" r="20"/><circle class="m-dot" r="10"/><path class="m-arrow" d="M0 -5 L4 4 L0 2 L-4 4 Z"/></g>
  </svg>`;
  MAP.whole = bounds([...route, ...MAP.pins.map(([x, y], i) => [x, y, stops()[i].radius])]);
  MAP.places = b?.places || [];
  MAP.labels = null; // place names' sizes in px, measured on the first frame
  MAP.pinLabels = null; // pin labels' widths in px, likewise
  MAP.built = true;
  $("#map-attr").hidden = !b;
}

/** map.json has come (app.js loadBase): draw it under the route. */
function onBase() {
  MAP.built = false;
  if (V.page === 1) drawMap();
}

/** [minx, miny, maxx, maxy] of points [x, y, r?], each grown by its r. */
function bounds(pts) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y, r = 0] of pts) {
    b[0] = Math.min(b[0], x - r); b[1] = Math.min(b[1], y - r);
    b[2] = Math.max(b[2], x + r); b[3] = Math.max(b[3], y + r);
  }
  return b;
}
const grow = (b, m) => [b[0] - m, b[1] - m, b[2] + m, b[3] + m];

/** The car: on the route at S.along when it's on it, else at the latest fix. {x, y, ang} or null. */
function carAt() {
  const P = S.path, a = S.along;
  if (P && a && !S.offRoute) {
    const p = P.pts[a.k], q = P.pts[a.k + 1], L = P.cum[a.k + 1] - P.cum[a.k];
    const f = L ? Math.max(0, Math.min(1, (a.m - P.cum[a.k]) / L)) : 0;
    const [x0, y0] = mxy(p.lat, p.lon), [x1, y1] = mxy(q.lat, q.lon);
    return { x: x0 + f * (x1 - x0), y: y0 + f * (y1 - y0), ang: L ? (Math.atan2(y1 - y0, x1 - x0) * 180) / Math.PI + 90 : null };
  }
  if (!S.fix) return null;
  const [x, y] = mxy(S.fix.lat, S.fix.lon), t = S.track;
  const prev = t.length > 1 ? t[t.length - 2] : null;
  const [px, py] = prev ? mxy(prev.lat, prev.lon) : [x, y];
  return { x, y, ang: Math.hypot(x - px, y - py) > 10 ? (Math.atan2(y - py, x - px) * 180) / Math.PI + 90 : null };
}

/** The part of the screen the camera frames, in px: above the bottom card (or left of it, in
 *  landscape) and below the top buttons. */
function freeRect(w, h) {
  const page = $("#p2").getBoundingClientRect(), top = $("#p2 .p2-top").getBoundingClientRect();
  const card = $("#p2-bottom").getBoundingClientRect();
  const t = top.bottom - page.top + 8;
  const F = card.width < 0.7 * w ? { l: 16, t, r: card.left - page.left - 8, b: h - 16 } : { l: 20, t, r: w - 20, b: card.top - page.top + 24 };
  if (F.r - F.l < 80 || F.b - F.t < 80) return { l: 0, t: 0, r: w, b: h };
  return F;
}

/** Where the camera should be: the whole route, a tapped pin, or the car and its next story. */
function camGoal(w, h) {
  const F = freeRect(w, h), fw = F.r - F.l, fh = F.b - F.t;
  const car = carAt(), wholeB = grow(MAP.whole, 600);
  const fit = (b) => Math.max((b[2] - b[0]) / fw, (b[3] - b[1]) / fh);
  const wholeS = fit(wholeB);
  let B = wholeB, s;
  if (MAP.mode === "follow" && MAP.sel != null) {
    const [x, y] = MAP.pins[MAP.sel];
    B = grow([x, y, x, y], Math.max(1500, stops()[MAP.sel].radius * 1.6));
  } else if (MAP.mode === "follow" && car) {
    const f = S.current ? stops().indexOf(S.current) : nextStory()?.i;
    B = f == null || f < 0 ? [car.x, car.y, car.x, car.y] : bounds([[car.x, car.y], [...MAP.pins[f], stops()[f].radius]]);
    B = grow(B, 400);
  }
  s = fit(B);
  if (B !== wholeB) s = Math.min(wholeS, Math.max(s, FOLLOW_MIN / fw));
  MAP.free = F;
  return { cx: (B[0] + B[2]) / 2, cy: (B[1] + B[3]) / 2, s, fx: (F.l + F.r) / 2, fy: (F.t + F.b) / 2 };
}

/** Draw the map page: pin states (when `full`), the driven line, the car, then move the camera. */
function drawMap(full = true) {
  if (!S.tour) return;
  if (!MAP.built) buildMap();
  const el = $("#p2map"), w = el.clientWidth, h = el.clientHeight;
  if (!w || !h) return;
  const svg = $("#map");
  if (full) {
    stops().forEach((s, i) => {
      const st = stateOf(s, i), cls = `${st}${MAP.sel === i ? " sel" : ""}`;
      svg.querySelector(`.m-pin[data-i="${i}"]`).setAttribute("class", `m-pin ${cls}`);
      svg.querySelector(`.m-zone[data-i="${i}"]`).setAttribute("class", `m-zone ${st}`);
    });
  }
  const P = S.path, a = S.along, car = carAt();
  let done = "";
  if (P && a && S.started) {
    const pts = P.pts.slice(0, a.k + 1).map((p) => mxy(p.lat, p.lon));
    if (car && !S.offRoute) pts.push([car.x, car.y]);
    done = pathD(pts);
  }
  const d = svg.querySelector(".m-done");
  if (d.getAttribute("d") !== done) d.setAttribute("d", done);
  MAP.car = car;
  MAP.goal = camGoal(w, h);
  if (!MAP.cam || !smooth()) MAP.cam = { ...MAP.goal };
  MAP.size = [w, h];
  glide();
}

/** One step of the camera towards its goal, then the next frame, while the map page is showing. */
function glide() {
  if (MAP.frame) return;
  const step = () => {
    MAP.frame = 0;
    const c = MAP.cam, g = MAP.goal;
    c.cx += (g.cx - c.cx) * 0.18;
    c.cy += (g.cy - c.cy) * 0.18;
    c.s *= (g.s / c.s) ** 0.18;
    c.fx = g.fx; c.fy = g.fy;
    const near = Math.abs(g.cx - c.cx) < c.s && Math.abs(g.cy - c.cy) < c.s && Math.abs(Math.log(g.s / c.s)) < 0.003;
    if (near) Object.assign(c, g);
    placeMap();
    if (!near && V.page === 1) MAP.frame = requestAnimationFrame(step);
  };
  step();
}

/** Set the view box and keep pins and the car their size on screen. */
function placeMap() {
  const svg = $("#map"), { cx, cy, s, fx, fy } = MAP.cam, [w, h] = MAP.size;
  const x0 = cx - fx * s, y0 = cy - fy * s;
  svg.setAttribute("viewBox", `${x0.toFixed(1)} ${y0.toFixed(1)} ${(w * s).toFixed(1)} ${(h * s).toFixed(1)}`);
  const placed = []; // where pins went on screen, px
  svg.querySelectorAll(".m-pin").forEach((g, i) => {
    const [x, y] = MAP.pins[i], sx = (x - x0) / s, sy = (y - y0) / s;
    let dx = 0; // px: a pin that would sit on an earlier one moves right (Hobart's stops 3 and 7 share a point)
    while (placed.some(([px, py]) => Math.hypot(sx + dx - px, sy - py) < PIN_GAP)) dx += PIN_GAP;
    placed.push([sx + dx, sy]);
    g.setAttribute("transform", `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(4)}) translate(${dx} 0)`);
  });
  const lbl = placePinLabels(svg, placed, w, h);
  placeLabels(svg, s, x0, y0, placed, lbl);
  const car = svg.querySelector(".m-car"), c = MAP.car;
  car.setAttribute("display", c ? "inline" : "none");
  if (c) car.setAttribute("transform", `translate(${c.x.toFixed(1)} ${c.y.toFixed(1)}) scale(${s.toFixed(4)})${c.ang == null ? "" : ` rotate(${c.ang.toFixed(0)})`}`);
  svg.querySelector(".m-arrow").setAttribute("display", c && c.ang != null ? "inline" : "none");
}

const pinBox = ([x, y]) => [x - 18, y - 18, x + 18, y + 18];
const overlaps = (a, k) => a[0] < k[2] && a[2] > k[0] && a[1] < k[3] && a[3] > k[1];

/** Pins' labels (`label` in tour.json), right of the pin, else left: the pin tapped first, then
 *  the story playing or next, then the rest in order. One that would cover a pin or an earlier
 *  label, or leave the screen, is left out, and so is one repeating a label shown on a pin
 *  within 60 px (Hobart's stops 3 and 7 share a point and a name). `pins` are the pins' screen
 *  positions. Returns the labels shown: {name, box}. */
function placePinLabels(svg, pins, w, h) {
  const texts = stops().map((s, i) => svg.querySelector(`.m-pin[data-i="${i}"] .m-lbl`));
  if (!MAP.pinLabels) MAP.pinLabels = texts.map((t) => (t ? t.getBBox().width : 0));
  const focus = S.current ? stops().indexOf(S.current) : armed()[0];
  const order = [...new Set([MAP.sel, focus, ...stops().keys()])].filter((i) => i != null && i >= 0 && texts[i]);
  const taken = pins.map(pinBox), shown = [];
  for (const i of order) {
    const t = texts[i], [x, y] = pins[i], lw = MAP.pinLabels[i], name = stops()[i].label;
    const spots = [[LBL_X, "start", [x + LBL_X - 2, y - 10, x + LBL_X + lw + 2, y + 10]],
      [-LBL_X, "end", [x - LBL_X - lw - 2, y - 10, x - LBL_X + 2, y + 10]]];
    const twin = shown.some((o) => o.name === name && Math.hypot(o.at[0] - x, o.at[1] - y) < 60);
    const spot = twin ? null : spots.find(([, , b]) => b[0] >= 0 && b[2] <= w && b[1] >= 0 && b[3] <= h
      && !taken.some((k, j) => j !== i && overlaps(b, k)));
    t.setAttribute("display", spot ? "inline" : "none");
    if (!spot) continue;
    t.setAttribute("x", spot[0]);
    t.setAttribute("text-anchor", spot[1]);
    taken.push(spot[2]);
    shown.push({ name, at: [x, y], box: spot[2] });
  }
  return shown;
}

/** Place names at a fixed size on screen, biggest places first, each to the right of its dot,
 *  else left, above or below; one that would cover a pin, a pin's label or another name, or not
 *  fit in the free part of the screen, is left out, and so is one a pin's label already names.
 *  `pins` are the pins' screen positions, `lbl` the pin labels shown (placePinLabels). */
function placeLabels(svg, s, x0, y0, pins, lbl = []) {
  const groups = svg.querySelectorAll(".m-place");
  if (!groups.length) return;
  if (!MAP.labels) MAP.labels = [...groups].map((g) => { const b = g.querySelector("text").getBBox(); return [b.width, b.height]; });
  const F = MAP.free, taken = [...pins.map(pinBox), ...lbl.map((o) => o.box)];
  const named = new Set(lbl.map((o) => o.name.toLowerCase()));
  const free = ([l, t, r, b]) => {
    [l, t, r, b] = [l - 2, t - 3, r + 2, b + 3]; // a little air between names
    return l >= F.l && r <= F.r && t >= F.t && b <= F.b && !taken.some((k) => overlaps([l, t, r, b], k));
  };
  groups.forEach((g, i) => {
    const p = MAP.places[i], [w, h] = MAP.labels[i], sx = (p.at[0] - x0) / s, sy = (p.at[1] - y0) / s;
    if (named.has(p.name.toLowerCase())) return g.setAttribute("display", "none");
    const spots = [ // [text x, y, anchor, the label's box relative to the dot]
      [7, 0, "start", [3, -h / 2, w + 11, h / 2]], [-7, 0, "end", [-w - 11, -h / 2, -3, h / 2]],
      [0, -h * 0.75, "middle", [-w / 2 - 4, -h * 1.3, w / 2 + 4, -3]], [0, h * 0.85, "middle", [-w / 2 - 4, 3, w / 2 + 4, h * 1.4]]];
    const spot = spots.find(([, , , b]) => free([sx + b[0], sy + b[1], sx + b[2], sy + b[3]]));
    g.setAttribute("display", spot ? "inline" : "none");
    if (!spot) return;
    const [tx, ty, anchor, b] = spot, t = g.querySelector("text");
    taken.push([sx + b[0], sy + b[1], sx + b[2], sy + b[3]]);
    t.setAttribute("x", tx);
    t.setAttribute("y", ty.toFixed(1));
    t.setAttribute("text-anchor", anchor);
    g.setAttribute("transform", `translate(${p.at[0]} ${p.at[1]}) scale(${s.toFixed(4)})`);
  });
}

/** The map page went away: stop the glide. */
function leaveMap() {
  if (MAP.frame) cancelAnimationFrame(MAP.frame);
  MAP.frame = 0;
}
