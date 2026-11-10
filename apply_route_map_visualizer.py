#!/usr/bin/env python3
"""Add a browser-based live topology map to smart-cdn-main."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
controller = ROOT / "controller" / "cdn_controller.py"
map_file = ROOT / "tools" / "route_map.html"
text = controller.read_text(encoding="utf-8")
original = text


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching section for {label}; found {count}. No files changed."
        )
    text = text.replace(old, new, 1)


replace_once(
    "        self.flows = {}       # (client ip, client TCP port) -> Flow\n",
    "        self.flows = {}       # (client ip, client TCP port) -> Flow\n"
    "        self.last_route_event = None\n",
    "last route event state",
)
replace_once(
    "            flow = self.flows[key] = Flow(ip.src, t.src_port, in_port, route)\n",
    "            flow = self.flows[key] = Flow(ip.src, t.src_port, in_port, route)\n"
    "            self.last_route_event = {\n"
    "                'time': time.time(), 'client': ip.src,\n"
    "                'server': route.server, 'route': route.name}\n",
    "last route decision recording",
)
replace_once(
    "        snapshot = {'updated_at': time.time(), 'mode': MODE, 'routes': routes}\n",
    "        snapshot = {'updated_at': time.time(), 'mode': MODE, 'routes': routes,\n"
    "                    'last_route': self.last_route_event}\n",
    "snapshot route decision",
)

if text == original:
    raise SystemExit("No controller changes produced; refusing to write an empty update.")
if map_file.exists():
    raise SystemExit("tools/route_map.html already exists; no files changed.")

page = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Smart CDN Live Route Map</title>
  <style>
    :root { color-scheme: dark; --bg:#0b1220; --panel:#121d2d; --muted:#9fb0c6;
      --green:#35d07f; --amber:#ffbf47; --red:#ff5d68; --gray:#536174; --blue:#67b7ff; }
    * { box-sizing:border-box }
    body { margin:0; padding:24px; background:var(--bg); color:#edf4ff;
      font:15px/1.45 system-ui,Segoe UI,sans-serif }
    main { max-width:1250px; margin:auto }
    h1 { margin:0 0 5px; font-size:26px }
    .sub,.muted { color:var(--muted) }
    .status { display:flex; gap:20px; flex-wrap:wrap; margin:18px 0; padding:14px 16px;
      background:var(--panel); border:1px solid #27364a; border-radius:12px }
    #fresh { margin-left:auto }
    .mapbox { padding:10px; background:var(--panel); border:1px solid #27364a;
      border-radius:14px; overflow:auto }
    svg { display:block; width:100%; min-width:760px; height:auto }
    .base { stroke:#536174; stroke-width:5; opacity:.55; fill:none }
    .route { fill:none; stroke-width:8; stroke-linecap:round; stroke-linejoin:round;
      opacity:.78; transition:stroke .3s,opacity .3s,stroke-width .3s }
    .route.selected { stroke-width:13; opacity:1; filter:drop-shadow(0 0 7px currentColor) }
    .node rect { fill:#17263a; stroke:#8295ad; stroke-width:2; rx:12 }
    .node text { fill:#edf4ff; text-anchor:middle; font-size:16px; font-weight:700 }
    .node .small { fill:#aebdd0; font-size:12px; font-weight:400 }
    .edge-label { fill:#bdcbe0; font-size:12px; paint-order:stroke; stroke:#121d2d;
      stroke-width:4px; stroke-linejoin:round }
    .legend { display:flex; gap:18px; flex-wrap:wrap; color:var(--muted); margin:12px 4px 2px }
    .dot { display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin-top:16px }
    .card { background:var(--panel); border:1px solid #27364a; border-left:5px solid var(--gray);
      border-radius:10px; padding:12px 14px }
    .card h3 { margin:0 0 7px; font-size:16px }
    .metric { display:flex; justify-content:space-between; color:var(--muted); margin:3px 0 }
    #decision { min-height:25px; color:#dceaff }
    @media(max-width:700px) { body { padding:14px } .status { gap:8px } #fresh { margin-left:0 } }
  </style>
</head>
<body>
<main>
  <h1>Smart CDN — live route map</h1>
  <div class="sub">A live view of measured paths. Green = available, amber/red = loaded, gray = down.</div>
  <div class="status">
    <span>Controller mode: <b id="mode">waiting</b></span>
    <span>Snapshot: <b id="updated">waiting</b></span>
    <span id="fresh">Connecting to controller…</span>
  </div>
  <section class="mapbox">
    <svg viewBox="0 0 1120 620" role="img" aria-label="Client, switch, and CDN server routes">
      <g id="base-links">
        <path class="base" d="M125 310 L270 310"/>
        <path class="base" d="M330 310 L590 310"/>
        <path class="base" d="M330 310 L455 490 L590 310"/>
        <path class="base" d="M650 310 L900 310"/>
        <path class="base" d="M330 310 L590 135 L900 135"/>
        <path class="base" d="M330 310 L590 495 L900 495"/>
      </g>
      <g id="route-lines">
        <path id="line-srv1-direct" class="route" d="M330 310 L590 310"/>
        <path id="line-srv1-backup" class="route" d="M330 310 L455 490 L590 310"/>
        <path id="line-srv2" class="route" d="M330 310 L590 135 L900 135"/>
        <path id="line-srv3" class="route" d="M330 310 L590 495 L900 495"/>
      </g>
      <g class="node" transform="translate(55 280)"><rect width="90" height="60"/><text x="45" y="26">Clients</text><text class="small" x="45" y="46">c1–c6</text></g>
      <g class="node" transform="translate(270 280)"><rect width="60" height="60"/><text x="30" y="36">s1</text></g>
      <g class="node" transform="translate(590 280)"><rect width="60" height="60"/><text x="30" y="36">s2</text></g>
      <g class="node" transform="translate(425 460)"><rect width="60" height="60"/><text x="30" y="36">s5</text></g>
      <g class="node" transform="translate(590 105)"><rect width="60" height="60"/><text x="30" y="36">s3</text></g>
      <g class="node" transform="translate(590 465)"><rect width="60" height="60"/><text x="30" y="36">s4</text></g>
      <g class="node" transform="translate(900 280)"><rect width="120" height="60"/><text x="60" y="26">srv1</text><text class="small" x="60" y="46">content server</text></g>
      <g class="node" transform="translate(900 105)"><rect width="120" height="60"/><text x="60" y="26">srv2</text><text class="small" x="60" y="46">content server</text></g>
      <g class="node" transform="translate(900 465)"><rect width="120" height="60"/><text x="60" y="26">srv3</text><text class="small" x="60" y="46">content server</text></g>
      <text class="edge-label" x="430" y="295">srv1 direct</text>
      <text class="edge-label" x="385" y="425">srv1 backup</text>
      <text class="edge-label" x="410" y="190">srv2 route</text>
      <text class="edge-label" x="410" y="445">srv3 route</text>
      <text class="edge-label" x="720" y="295">shared srv1 access</text>
    </svg>
    <div class="legend">
      <span><i class="dot" style="background:var(--green)"></i>healthy / low use</span>
      <span><i class="dot" style="background:var(--amber)"></i>utilization ≥ 50%</span>
      <span><i class="dot" style="background:var(--red)"></i>utilization ≥ 80%</span>
      <span><i class="dot" style="background:var(--gray)"></i>route down</span>
      <span>Thick glowing line = most recently selected route</span>
    </div>
  </section>
  <h2>Latest controller decision</h2>
  <div id="decision" class="muted">Waiting for the first new client flow…</div>
  <section id="cards" class="cards"></section>
</main>
<script>
const colors = {green:'#35d07f', amber:'#ffbf47', red:'#ff5d68', gray:'#536174'};
const routeIds = {'srv1-direct':'line-srv1-direct','srv1-backup':'line-srv1-backup',
                  'srv2':'line-srv2','srv3':'line-srv3'};
function colorFor(route) {
  if (!route.up || !route.server_up) return colors.gray;
  if (route.utilization >= 0.8) return colors.red;
  if (route.utilization >= 0.5) return colors.amber;
  return colors.green;
}
async function refresh() {
  try {
    const response = await fetch('../results/live_routes.json?t='+Date.now(), {cache:'no-store'});
    if (!response.ok) throw new Error('HTTP '+response.status);
    const data = await response.json();
    document.getElementById('mode').textContent = data.mode;
    const age = Math.max(0, (Date.now()/1000)-data.updated_at);
    document.getElementById('updated').textContent = new Date(data.updated_at*1000).toLocaleTimeString();
    document.getElementById('fresh').textContent = age < 3 ? 'LIVE' : `stale (${age.toFixed(0)}s old)`;
    document.getElementById('fresh').style.color = age < 3 ? colors.green : colors.amber;
    const routes = data.routes || [];
    for (const route of routes) {
      const line = document.getElementById(routeIds[route.name]);
      if (line) { line.style.stroke = colorFor(route); line.classList.remove('selected'); }
    }
    const cards = document.getElementById('cards'); cards.replaceChildren();
    for (const route of routes) {
      const card = document.createElement('article'); card.className='card'; card.style.borderLeftColor=colorFor(route);
      const rtt = route.rtt_ms == null ? '—' : route.rtt_ms.toFixed(1)+' ms';
      card.innerHTML = `<h3>${route.name}</h3><div class="metric"><span>Server</span><b>${route.server_up?'UP':'DOWN'}</b></div>`+
        `<div class="metric"><span>Route</span><b>${route.up?'UP':'DOWN'}</b></div>`+
        `<div class="metric"><span>RTT</span><b>${rtt}</b></div>`+
        `<div class="metric"><span>Utilization</span><b>${(route.utilization*100).toFixed(1)}%</b></div>`+
        `<div class="metric"><span>Active flows</span><b>${route.active_flows}</b></div>`;
      cards.appendChild(card);
    }
    const choice = data.last_route;
    if (choice && routeIds[choice.route]) {
      document.getElementById(routeIds[choice.route]).classList.add('selected');
      const when = new Date(choice.time*1000).toLocaleTimeString();
      document.getElementById('decision').textContent =
        `Latest flow from ${choice.client} was sent to ${choice.server} via ${choice.route} at ${when}.`;
    }
  } catch (error) {
    document.getElementById('fresh').textContent = 'Waiting for controller status';
    document.getElementById('fresh').style.color = colors.amber;
  }
}
refresh(); setInterval(refresh, 1000);
</script>
</body>
</html>
'''

backup = controller.with_suffix(controller.suffix + ".before-route-map-visualizer")
if not backup.exists():
    shutil.copy2(controller, backup)
controller.write_text(text, encoding="utf-8")
map_file.parent.mkdir(exist_ok=True)
map_file.write_text(page, encoding="utf-8")
print("Added browser route map and latest-flow highlighting.")
print("Open tools/route_map.html through a local HTTP server at port 8765.")
print("Controller backup: controller/cdn_controller.py.before-route-map-visualizer")
