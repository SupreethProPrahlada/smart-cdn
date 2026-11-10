#!/usr/bin/env python3
"""Keep the last active route-map snapshot visible after Mininet stops."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
page = ROOT / "tools" / "route_map.html"
text = page.read_text(encoding="utf-8")
original = text


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one section for {label}; found {count}. No files changed.")
    text = text.replace(old, new, 1)


replace_once(
    '    <span id="fresh">Connecting to controller…</span>\n',
    '    <span id="fresh">Connecting to controller…</span>\n'
    '    <button id="clearSnapshot" type="button" onclick="clearSnapshot()">'
    'Clear saved snapshot</button>\n',
    "snapshot control",
)
replace_once(
    "async function refresh() {\n",
    "function clearSnapshot() {\n"
    "  localStorage.removeItem('smartCdnLastActiveSnapshot');\n"
    "  location.reload();\n"
    "}\n"
    "\n"
    "async function refresh() {\n",
    "clear snapshot handler",
)
old = '''    const data = await response.json();
    document.getElementById('mode').textContent = data.mode;
    const age = Math.max(0, (Date.now()/1000)-data.updated_at);
    document.getElementById('updated').textContent = new Date(data.updated_at*1000).toLocaleTimeString();
    document.getElementById('fresh').textContent = age < 3 ? 'LIVE' : `stale (${age.toFixed(0)}s old)`;
    document.getElementById('fresh').style.color = age < 3 ? colors.green : colors.amber;
    const routes = data.routes || [];
'''
new = '''    const liveData = await response.json();
    const savedKey = 'smartCdnLastActiveSnapshot';
    let displayData = liveData;
    let showingSaved = false;
    const hasActiveRoute = (liveData.routes || []).some(route => route.up && route.server_up);
    if (hasActiveRoute) {
      localStorage.setItem(savedKey, JSON.stringify(liveData));
    } else {
      const saved = localStorage.getItem(savedKey);
      if (saved) {
        displayData = JSON.parse(saved);
        showingSaved = true;
      }
    }
    document.getElementById('mode').textContent = displayData.mode;
    const age = Math.max(0, (Date.now()/1000)-displayData.updated_at);
    document.getElementById('updated').textContent = new Date(displayData.updated_at*1000).toLocaleTimeString();
    const fresh = document.getElementById('fresh');
    fresh.textContent = showingSaved
      ? `RUN ENDED — showing last active snapshot (${age.toFixed(0)}s old)`
      : age < 3 ? 'LIVE' : `stale (${age.toFixed(0)}s old)`;
    fresh.style.color = showingSaved ? colors.blue : age < 3 ? colors.green : colors.amber;
    const routes = displayData.routes || [];
'''
replace_once(old, new, "live snapshot preservation")
replace_once("    const choice = data.last_route;\n", "    const choice = displayData.last_route;\n",
             "last route preservation")

if text == original:
    raise SystemExit("No map changes produced; refusing to write an empty update.")
page.write_text(text, encoding="utf-8")
print("Route map now preserves its last active colors and measurements after a run ends.")
print("Open the map and complete one run while it is open to save a snapshot.")
