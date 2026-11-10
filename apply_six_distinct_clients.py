#!/usr/bin/env python3
"""Apply the six-distinct-client experiment update to the current smart-cdn repo."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent


changes = {}


def replace_once(path, old, new):
    text = changes.get(path)
    if text is None:
        text = (ROOT / path).read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching section in {path}, found {count}. "
            "No files have been changed; use a clean current-main checkout."
        )
    changes[path] = text.replace(old, new, 1)


replace_once(
    "topology/topo.py",
    "    net.addLink(heartbeat_host, s1)\n    return net\n",
    "    net.addLink(heartbeat_host, s1)\n\n"
    "    # Keep these links after the server-path links so s1 server ports stay unchanged.\n"
    "    # Six separate experiment clients; c7 is reserved for congestion traffic.\n"
    "    for i in range(5, 8):\n"
    "        client = net.addHost(f'c{i}', ip=f'10.0.0.{i}/24',\n"
    "                             mac=f'00:00:00:00:00:0{i}')\n"
    "        net.addLink(client, s1, bw=100)\n\n"
    "    return net\n",
)

replace_once(
    "tests/run_scenarios.py",
    '        self.clients = [self.net.get(name) for name in ("c1", "c2", "c3")]\n'
    '        self.procs = {}\n',
    '        self.clients = [self.net.get(f"c{i}") for i in range(1, 7)]\n'
    '        self.load_sink = self.net.get("c7")\n'
    '        self.procs = {}\n',
)

replace_once(
    "tests/run_scenarios.py",
    '    parser.add_argument("scenario", choices=("smoke", "failover", "congestion", "all",\n'
    '                                              "experiments", "report"))\n',
    '    parser.add_argument("scenario", choices=("smoke", "six-client-smoke", "failover",\n'
    '                                              "congestion", "all", "experiments", "report"))\n',
)

replace_once(
    "tests/run_scenarios.py",
    '    def smoke(self):\n',
    '    def six_client_smoke(self):\n'
    '        rows = self.run_clients(6)\n'
    '        for name, elapsed, mbps, retries, status in rows:\n'
    '            print(f"{name}: {status}, {elapsed:.2f}s, {mbps:.2f} Mbit/s, retries={retries}")\n'
    '        expected = [f"c{i}" for i in range(1, 7)]\n'
    '        if [row[0] for row in rows] != expected or any(row[4] != "ok" for row in rows):\n'
    '            raise RuntimeError("six-client smoke did not complete successfully on c1-c6")\n\n'
    '    def smoke(self):\n',
)

replace_once(
    "tests/run_scenarios.py",
    '        c4 = self.net.get("c4")\n'
    '        server = self.servers["srv1"]\n'
    '        self.procs["iperf_server"] = c4.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)\n'
    '        time.sleep(1)\n'
    '        self.procs["iperf_client"] = server.popen(\n'
    '            ["iperf", "-c", "10.0.0.4", "-t", "30", "-P", "4"],\n',
    '        server = self.servers["srv1"]\n'
    '        self.procs["iperf_server"] = self.load_sink.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)\n'
    '        time.sleep(1)\n'
    '        self.procs["iperf_client"] = server.popen(\n'
    '            ["iperf", "-c", "10.0.0.7", "-t", "30", "-P", "4"],\n',
)

replace_once(
    "tests/run_scenarios.py",
    '        jobs = []\n'
    '        for index in range(count):\n'
    '            host = self.clients[index % len(self.clients)]\n',
    '        if count < 1 or count > len(self.clients):\n'
    '            raise ValueError(f"client count must be between 1 and {len(self.clients)}, got {count}")\n'
    '        jobs = []\n'
    '        for index in range(count):\n'
    '            host = self.clients[index]\n',
)

replace_once(
    "tests/run_scenarios.py",
    '            c4 = self.net.get("c4")\n'
    '            self.procs["iperf_server"] = c4.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)\n'
    '            time.sleep(1)\n'
    '            self.procs["iperf_client"] = self.servers["srv1"].popen(\n'
    '                ["iperf", "-c", "10.0.0.4", "-t", "3600", "-P", "4"],\n',
    '            self.procs["iperf_server"] = self.load_sink.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)\n'
    '            time.sleep(1)\n'
    '            self.procs["iperf_client"] = self.servers["srv1"].popen(\n'
    '                ["iperf", "-c", "10.0.0.7", "-t", "3600", "-P", "4"],\n',
)

replace_once(
    "tests/run_scenarios.py",
    '        if args.scenario == "smoke":\n'
    '            runner.smoke()\n'
    '        elif args.scenario == "failover":\n',
    '        if args.scenario == "smoke":\n'
    '            runner.smoke()\n'
    '        elif args.scenario == "six-client-smoke":\n'
    '            runner.six_client_smoke()\n'
    '        elif args.scenario == "failover":\n',
)

replace_once(
    "README.md",
    "A raw TCP content service that uses a Ryu SDN controller to select among three servers in Mininet. The controller considers server health, reported load, configured path delay, and measured link utilization.\n",
    "A raw TCP content service that uses a Ryu SDN controller to select among three servers in Mininet. The controller considers server health, reported load, configured path delay, and measured link utilization. The experiment runner uses six distinct client hosts (c1-c6); c7 is reserved for congestion traffic.\n",
)

replace_once(
    "README.md",
    'replace `all` with `smoke`, `failover`, or `congestion`. The smoke scenario\n',
    'replace `all` with `smoke`, `six-client-smoke`, `failover`, or `congestion`. The six-client\n'
    'smoke starts one download on each of c1-c6 at the same time. The smoke scenario\n',
)

replace_once(
    "docs/architecture.md",
    "    c1-c4 ---- s1 ---- 5 ms / 100 Mbps ---- srv1\n",
    "    c1-c6 ---- s1 ---- 5 ms / 100 Mbps ---- srv1\n",
)

replace_once(
    "docs/architecture.md",
    "Ryu controls the four OpenFlow 1.3 switches. Clients request the virtual address `10.0.0.100:8000`; no host owns that address. The controller answers its ARP requests and rewrites each new TCP flow to a selected server. A root namespace interface connects the controller host to `s1` at `10.0.0.254`; servers send status heartbeats to that address on TCP port 9000.\n",
    "Ryu controls the four OpenFlow 1.3 switches. Clients request the virtual address `10.0.0.100:8000`; no host owns that address. The controller answers its ARP requests and rewrites each new TCP flow to a selected server. A root namespace interface connects the controller host to `s1` at `10.0.0.254`; servers send status heartbeats to that address on TCP port 9000. Experiments run up to six separate client hosts (`c1`-`c6`) concurrently; `c7` is reserved as the iperf congestion sink.\n",
)

csv_path = ROOT / "results" / "data" / "experiments.csv"
csv_backup = None
if csv_path.is_file() and csv_path.stat().st_size:
    csv_backup = csv_path.with_name("experiments_before_six_clients.csv")
    suffix = 2
    while csv_backup.exists():
        csv_backup = csv_path.with_name(f"experiments_before_six_clients_{suffix}.csv")
        suffix += 1

for relative, content in changes.items():
    file_path = ROOT / relative
    backup = file_path.with_suffix(file_path.suffix + ".before-six-clients")
    if not backup.exists():
        shutil.copy2(file_path, backup)
    file_path.write_text(content, encoding="utf-8")

if csv_backup:
    shutil.copy2(csv_path, csv_backup)
    csv_path.write_text(
        "mode,condition,nclients,rep,client,time_s,mbps,retries,status\n",
        encoding="utf-8",
    )
    print(f"Preserved old measurements at {csv_backup.relative_to(ROOT)}")

print("Applied six distinct experiment clients c1-c6; c7 is the congestion traffic sink.")
print("Source backups are saved beside modified files with suffix .before-six-clients.")
