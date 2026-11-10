#!/usr/bin/env python3
"""Add a randomized, no-link-cut test for dynamic server selection.

Run this helper from a clean smart-cdn-main checkout after the adaptive-
congestion update has been applied. It changes only the test runner.
"""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
target = ROOT / "tests" / "run_scenarios.py"
text = target.read_text(encoding="utf-8")
original = text


def replace_once(old, new):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching section in tests/run_scenarios.py; found {count}. "
            "No files were changed. Confirm the adaptive-congestion update is applied."
        )
    text = text.replace(old, new, 1)


replace_once("import re\nimport socket\n", "import random\nimport re\nimport socket\n")
replace_once(
    '"adaptive-congestion", "congestion", "all",\n'
    '                                              "experiments", "report"))\n',
    '"adaptive-congestion", "random-congestion", "congestion", "all",\n'
    '                                              "experiments", "report"))\n',
)
replace_once(
    "    def congestion(self):\n",
    "    def random_congestion(self):\n"
    "        \"\"\"Randomly load one server route or leave the network unloaded.\"\"\"\n"
    "        congested = random.choice((None, 'srv1', 'srv2', 'srv3'))\n"
    "        print(f'Realized condition: {congested or \"no congestion\"}.')\n"
    "        if congested is not None:\n"
    "            self.procs[\"random_iperf_server\"] = self.load_sink.popen(\n"
    "                [\"iperf\", \"-s\"], stdout=DEVNULL, stderr=DEVNULL)\n"
    "            time.sleep(1)\n"
    "            self.procs[\"random_iperf_client\"] = self.servers[congested].popen(\n"
    "                [\"iperf\", \"-c\", \"10.0.0.7\", \"-t\", \"60\", \"-P\", \"4\"],\n"
    "                stdout=DEVNULL, stderr=DEVNULL)\n"
    "            time.sleep(8)  # let OpenFlow port counters report the load\n"
    "\n"
    "        try:\n"
    "            started = time.monotonic()\n"
    "            self.download(self.clients[0], \"small.bin\")\n"
    "            port, _, rule = self.route_rule(self.clients[0], started)\n"
    "            print(f\"Selected s1 rule: {rule}\")\n"
    "            port_server = {5: 'srv1', 12: 'srv1', 6: 'srv2', 7: 'srv3'}.get(port)\n"
    "            if port_server is None:\n"
    "                raise RuntimeError(f\"could not map selected output port {port} to a server\")\n"
    "            print(f\"Controller selected {port_server} (s1 output port {port}).\")\n"
    "            if congested is not None and port_server == congested:\n"
    "                raise RuntimeError(\n"
    "                    f\"controller selected congested {congested}; expected another healthy server\")\n"
    "            if congested is None:\n"
    "                print(\"No congestion was generated; selection reflects the measured baseline costs.\")\n"
    "            else:\n"
    "                print(f\"Verified: congestion on {congested} caused a new flow to use {port_server}.\")\n"
    "        finally:\n"
    "            self.stop_process(\"random_iperf_client\")\n"
    "            self.stop_process(\"random_iperf_server\")\n"
    "\n"
    "    def congestion(self):\n",
)
replace_once(
    '        elif args.scenario == "adaptive-congestion":\n'
    '            runner.adaptive_congestion()\n'
    '        elif args.scenario == "congestion":\n',
    '        elif args.scenario == "adaptive-congestion":\n'
    '            runner.adaptive_congestion()\n'
    '        elif args.scenario == "random-congestion":\n'
    '            runner.random_congestion()\n'
    '        elif args.scenario == "congestion":\n',
)

if text == original:
    raise SystemExit("No changes produced; refusing to write an empty update.")

backup = target.with_suffix(target.suffix + ".before-random-server-congestion")
if not backup.exists():
    shutil.copy2(target, backup)
target.write_text(text, encoding="utf-8")
print("Added random-congestion: each run randomly loads srv1, srv2, srv3, or no server route.")
print("Run it with CDN_MODE=dynamic and without CDN_PIN_SERVER to test global server selection.")
print("Original test runner backup: tests/run_scenarios.py.before-random-server-congestion")
