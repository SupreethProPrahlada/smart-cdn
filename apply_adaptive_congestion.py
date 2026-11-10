#!/usr/bin/env python3
"""Add a repeatable no-link-cut test for load-aware srv1 path selection."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
changes = {}


def replace_once(relative, old, new):
    content = changes.get(relative)
    if content is None:
        content = (ROOT / relative).read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching block in {relative}; found {count}. "
            "No files have been changed. Use the teammate's clean main clone."
        )
    changes[relative] = content.replace(old, new, 1)


replace_once(
    "controller/cdn_controller.py",
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n",
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n"
    "PIN_SERVER = os.environ.get('CDN_PIN_SERVER')  # optional test-only server pin\n",
)
replace_once(
    "controller/cdn_controller.py",
    "    def choose_route(self, client_ip):\n"
    "        if MODE == 'static':\n"
    "            # fixed assignment on each server's first route:\n"
    "            # c1->srv1, c2->srv2, c3->srv3, c4->srv1\n"
    "            name = ['srv1', 'srv2', 'srv3'][(int(client_ip.split('.')[-1]) - 1) % 3]\n"
    "            return next(route for route in ROUTES if route.server == name)\n"
    "        return self.sel.pick()\n",
    "    def choose_route(self, client_ip):\n"
    "        if PIN_SERVER:\n"
    "            if not self.sel.healthy(PIN_SERVER):\n"
    "                return None\n"
    "            usable = [route for route in ROUTES\n"
    "                      if route.server == PIN_SERVER and route.up]\n"
    "            return min(usable, key=self.sel.cost) if usable else None\n"
    "        if MODE == 'static':\n"
    "            # fixed assignment on each server's first route:\n"
    "            # c1->srv1, c2->srv2, c3->srv3, c4->srv1\n"
    "            name = ['srv1', 'srv2', 'srv3'][(int(client_ip.split('.')[-1]) - 1) % 3]\n"
    "            return next(route for route in ROUTES if route.server == name)\n"
    "        return self.sel.pick()\n",
)

replace_once(
    "topology/topo.py",
    "    net.addLink(s5, s2, port1=2, port2=3, delay='5ms', bw=100)\n\n"
    "    return net\n",
    "    net.addLink(s5, s2, port1=2, port2=3, delay='5ms', bw=100)\n\n"
    "    # Cross-traffic source attached to s2. Traffic to c7 crosses only the\n"
    "    # direct s1-s2 trunk; it does not consume srv1's shared access link.\n"
    "    loadsrc = net.addHost('loadsrc', ip='10.0.0.8/24',\n"
    "                          mac='00:00:00:00:00:08')\n"
    "    net.addLink(loadsrc, s2, bw=100)\n\n"
    "    return net\n",
)

replace_once(
    "tests/run_scenarios.py",
    "        self.load_sink = self.net.get(\"c7\")\n"
    "        self.procs = {}\n",
    "        self.load_sink = self.net.get(\"c7\")\n"
    "        self.load_source = self.net.get(\"loadsrc\")\n"
    "        self.procs = {}\n",
)
replace_once(
    "tests/run_scenarios.py",
    "    parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\", \"path\",\n"
    "                                              \"congestion\", \"all\", \"experiments\", \"report\"))\n",
    "    parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\", \"path\",\n"
    "                                              \"adaptive-congestion\", \"congestion\", \"all\",\n"
    "                                              \"experiments\", \"report\"))\n",
)
replace_once(
    "tests/run_scenarios.py",
    "    def congestion(self):\n",
    "    def adaptive_congestion(self):\n"
    "        \"\"\"Verify direct, loaded-backup, then direct selection with both routes up.\"\"\"\n"
    "        client = self.clients[0]\n"
    "        print(\"No background load: a fresh c1 flow should use the direct route.\")\n"
    "        started = time.monotonic()\n"
    "        self.download(client, \"small.bin\")\n"
    "        port, _, rule = self.route_rule(client, started)\n"
    "        print(f\"s1 rule: {rule}\")\n"
    "        if port != DIRECT_PORT:\n"
    "            raise RuntimeError(f\"unloaded srv1 flow used s1 port {port}, expected {DIRECT_PORT}\")\n"
    "\n"
    "        self.procs[\"adaptive_iperf_server\"] = self.load_sink.popen(\n"
    "            [\"iperf\", \"-s\"], stdout=DEVNULL, stderr=DEVNULL)\n"
    "        time.sleep(1)\n"
    "        self.procs[\"adaptive_iperf_client\"] = self.load_source.popen(\n"
    "            [\"iperf\", \"-c\", \"10.0.0.7\", \"-t\", \"60\", \"-P\", \"4\"],\n"
    "            stdout=DEVNULL, stderr=DEVNULL)\n"
    "        try:\n"
    "            time.sleep(8)  # wait for route port counters to record direct-trunk load\n"
    "            print(\"Direct s1-s2 trunk is loaded; a new c1 flow should use the backup.\")\n"
    "            started = time.monotonic()\n"
    "            self.download(client, \"video1.bin\")\n"
    "            port, _, rule = self.route_rule(client, started)\n"
    "            print(f\"s1 rule: {rule}\")\n"
    "            if port != BACKUP_PORT:\n"
    "                raise RuntimeError(\n"
    "                    f\"loaded srv1 flow used s1 port {port}, expected backup port {BACKUP_PORT}\")\n"
    "            print(\"Verified: new flow used srv1's backup path while both routes stayed up.\")\n"
    "        finally:\n"
    "            self.stop_process(\"adaptive_iperf_client\")\n"
    "            self.stop_process(\"adaptive_iperf_server\")\n"
    "\n"
    "        time.sleep(6)  # let fresh port counters show that the load has cleared\n"
    "        print(\"Load stopped: a fresh c1 flow should return to the direct route.\")\n"
    "        started = time.monotonic()\n"
    "        self.download(client, \"small.bin\")\n"
    "        port, _, rule = self.route_rule(client, started)\n"
    "        print(f\"s1 rule: {rule}\")\n"
    "        if port != DIRECT_PORT:\n"
    "            raise RuntimeError(f\"unloaded srv1 flow used s1 port {port}, expected {DIRECT_PORT}\")\n"
    "        print(\"Verified: new flow returned to the direct route after load cleared.\")\n"
    "\n"
    "    def congestion(self):\n",
)
replace_once(
    "tests/run_scenarios.py",
    "        elif args.scenario == \"congestion\":\n"
    "            runner.congestion()\n",
    "        elif args.scenario == \"adaptive-congestion\":\n"
    "            runner.adaptive_congestion()\n"
    "        elif args.scenario == \"congestion\":\n"
    "            runner.congestion()\n",
)

# Validate every expected source block before writing any file.
for relative, content in changes.items():
    target = ROOT / relative
    backup = target.with_suffix(target.suffix + ".before-adaptive-congestion")
    if not backup.exists():
        shutil.copy2(target, backup)
    target.write_text(content, encoding="utf-8")

print("Added adaptive-congestion: idle -> direct-link load -> idle, without link changes.")
print("For the targeted test, start Ryu with CDN_MODE=dynamic CDN_PIN_SERVER=srv1.")
print("Original source backups use the suffix .before-adaptive-congestion.")
