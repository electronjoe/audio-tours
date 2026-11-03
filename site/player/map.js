// The route sketch (More → Route sketch): the route and the stops from tour.json, drawn as SVG.
// Loaded after app.js, whose state (S) and helpers it uses.

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
