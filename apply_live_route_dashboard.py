#!/usr/bin/env python3
"""Add a read-only terminal dashboard for live route measurements."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
controller = ROOT / "controller" / "cdn_controller.py"
tools_dir = ROOT / "tools"
dashboard = tools_dir / "route_dashboard.py"
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
    "import os\nimport struct\n",
    "import json\nimport os\nimport struct\n",
    "controller imports",
)
replace_once(
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n",
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n"
    "STATUS_FILE = os.environ.get(\n"
    "    'CDN_STATUS_FILE',\n"
    "    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),\n"
    "                 'results', 'live_routes.json'))\n",
    "status file setting",
)
replace_once(
    "    def monitor(self):\n",
    "    def publish_status(self):\n"
    "        \"\"\"Publish a small atomic snapshot for the read-only terminal dashboard.\"\"\"\n"
    "        routes = []\n"
    "        for route in ROUTES:\n"
    "            routes.append({\n"
    "                'name': route.name,\n"
    "                'server': route.server,\n"
    "                'server_up': self.sel.healthy(route.server),\n"
    "                'up': route.up,\n"
    "                'rtt_ms': None if route.rtt is None else round(route.rtt * 1000, 1),\n"
    "                'utilization': round(route.util, 3),\n"
    "                'active_flows': sum(1 for flow in self.flows.values()\n"
    "                                    if flow.route.name == route.name),\n"
    "            })\n"
    "        snapshot = {'updated_at': time.time(), 'mode': MODE, 'routes': routes}\n"
    "        folder = os.path.dirname(STATUS_FILE)\n"
    "        os.makedirs(folder, exist_ok=True)\n"
    "        temporary = STATUS_FILE + '.tmp'\n"
    "        with open(temporary, 'w', encoding='utf-8') as stream:\n"
    "            json.dump(snapshot, stream)\n"
    "        os.replace(temporary, STATUS_FILE)\n"
    "\n"
    "    def monitor(self):\n",
    "status publisher",
)
replace_once(
    "            self.evaluate()\n"
    "            rounds += 1\n",
    "            self.evaluate()\n"
    "            try:\n"
    "                self.publish_status()\n"
    "            except OSError as error:\n"
    "                self.logger.warning('could not publish route status: %s', error)\n"
    "            rounds += 1\n",
    "monitor update",
)

if text == original:
    raise SystemExit("No controller changes produced; refusing to write an empty update.")
if dashboard.exists():
    raise SystemExit("tools/route_dashboard.py already exists; no files changed.")

dashboard_source = '''#!/usr/bin/env python3
"""Display live route health and utilization from the Ryu controller."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="results/live_routes.json",
                        help="controller status snapshot file")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="refresh interval in seconds")
    args = parser.parse_args()
    status_file = Path(args.file)

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("SMART CDN — LIVE ROUTE STATUS")
        print("Ctrl+C stops this display; it does not stop the controller.\\n")
        try:
            snapshot = json.loads(status_file.read_text(encoding="utf-8"))
            stamp = datetime.fromtimestamp(snapshot["updated_at"]).strftime("%H:%M:%S")
            print(f"Mode: {snapshot['mode']}    Updated: {stamp}\\n")
            print(f"{'ROUTE':<15} {'SERVER':<8} {'SERVER':<9} {'PATH':<8} "
                  f"{'RTT':>8} {'UTIL':>8} {'FLOWS':>7}")
            print("-" * 72)
            for route in snapshot["routes"]:
                rtt = "--" if route["rtt_ms"] is None else f"{route['rtt_ms']:.1f} ms"
                utilization = route["utilization"]
                bar = "#" * int(utilization * 20)
                print(f"{route['name']:<15} {route['server']:<8} "
                      f"{'UP' if route['server_up'] else 'DOWN':<9} "
                      f"{'UP' if route['up'] else 'DOWN':<8} {rtt:>8} "
                      f"{utilization * 100:>6.1f}% {route['active_flows']:>7}")
                print(f"  utilization [{bar:<20}]")
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(f"Waiting for controller status at {status_file}: {error}")
        time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\\nDashboard stopped.")
'''

backup = controller.with_suffix(controller.suffix + ".before-live-route-dashboard")
if not backup.exists():
    shutil.copy2(controller, backup)
controller.write_text(text, encoding="utf-8")
tools_dir.mkdir(exist_ok=True)
dashboard.write_text(dashboard_source, encoding="utf-8")
print("Added read-only live route dashboard.")
print("Controller snapshot: results/live_routes.json")
print("Start the display with: uv run python tools/route_dashboard.py")
print("Original controller backup: controller/cdn_controller.py.before-live-route-dashboard")
