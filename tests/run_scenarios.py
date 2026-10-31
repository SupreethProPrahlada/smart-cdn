#!/usr/bin/env python3
"""Run repeatable CDN scenarios in a managed Mininet topology."""

import argparse
import csv
import os
import random
import re
import socket
import sys
import time
from pathlib import Path
from subprocess import DEVNULL

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "topology"))

from mininet.log import setLogLevel
from topo import DEGRADED_LINK, DIRECT_LINK, build


RESULTS = ROOT / "results"
DATA = RESULTS / "data"
RESULT_LINE = re.compile(r"got (\d+) bytes in ([0-9.]+)s, retries=(\d+) checksum=(\w+)")
CONDITIONS = ("normal", "congested", "failed")
CLIENT_COUNTS = (1, 3, 6)
# s1 ports of srv1's two routes (see controller/paths.py)
DIRECT_PORT, BACKUP_PORT = 5, 12


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("smoke", "six-client-smoke", "failover", "path",
                                              "adaptive-congestion", "random-congestion", "congestion", "all",
                                              "experiments", "report"))
    parser.add_argument("--mode", choices=("dynamic", "static"), default="dynamic",
                        help="must match the running controller")
    parser.add_argument("--file", default="exp.bin", help="content file to request")
    parser.add_argument("--quick", action="store_true", help="run one repetition with up to 3 clients")
    parser.add_argument("--only", choices=CONDITIONS, help="run one experiment condition")
    parser.add_argument("--seed", type=int, help="replay a random-congestion run")
    return parser.parse_args()


def prepare_content():
    from make_content import FILES, main

    content = ROOT / "content"
    if not all((content / name).is_file() for name in FILES):
        main()


def parse_client_output(output):
    match = RESULT_LINE.search(output)
    if not match:
        return None
    size, elapsed, retries, checksum = match.groups()
    return int(size), float(elapsed), int(retries), checksum


class ScenarioRunner:
    def __init__(self, filename, seed=None):
        self.filename = filename
        self.seed = seed
        self.net = build()
        self.servers = {name: self.net.get(name) for name in ("srv1", "srv2", "srv3")}
        self.clients = [self.net.get(f"c{i}") for i in range(1, 7)]
        self.load_sink = self.net.get("c7")
        self.load_source = self.net.get("loadsrc")
        self.procs = {}

    def start(self):
        self.wait_for_controller()
        self.net.start()
        for name, host in self.servers.items():
            self.start_server(name, host)
        time.sleep(12)
        self.net.pingAll()

    @staticmethod
    def wait_for_controller(timeout=10):
        ports = (9000, 6653)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                for port in ports:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        pass
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError(
            "Ryu must be listening on 127.0.0.1:6653 (OpenFlow) and "
            "127.0.0.1:9000 (server heartbeats) in the runner's network namespace. "
            "Start it in another terminal with: "
            "uv run ryu-manager controller/cdn_controller.py"
        )

    def start_server(self, name, host=None):
        host = host or self.servers[name]
        self.procs[name] = host.popen(
            [sys.executable, str(ROOT / "app/server.py"), "--id", name],
            stdout=DEVNULL, stderr=None,
        )

    def stop_process(self, name):
        process = self.procs.pop(name, None)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
                process.wait()

    def client(self, host, filename=None, log="/dev/null"):
        return host.popen(
            [sys.executable, str(ROOT / "app/client.py"), "--name", filename or self.filename,
             "--client", host.name, "--log", log],
            stdout=-1, stderr=-2,
        )

    def download(self, host, filename=None):
        process = self.client(host, filename)
        output = process.communicate()[0].decode(errors="replace")
        result = parse_client_output(output)
        if process.returncode or not result or result[3] != "OK":
            raise RuntimeError(f"{host.name} download failed: {output.strip()}")
        print(output.strip())
        return result

    def six_client_smoke(self):
        rows = self.run_clients(6)
        for name, elapsed, mbps, retries, status in rows:
            print(f"{name}: {status}, {elapsed:.2f}s, {mbps:.2f} Mbit/s, retries={retries}")
        expected = [f"c{i}" for i in range(1, 7)]
        if [row[0] for row in rows] != expected or any(row[4] != "ok" for row in rows):
            raise RuntimeError("six-client smoke did not complete successfully on c1-c6")

    def smoke(self):
        self.download(self.clients[0], "small.bin")
        self.download(self.clients[1], "small.bin")
        flows = self.net.get("s1").cmd("ovs-ofctl -O OpenFlow13 dump-flows s1")
        rules = [line.strip() for line in flows.splitlines() if "priority=100" in line]
        if not rules:
            raise RuntimeError("no CDN forwarding rules found on s1")
        print("Installed CDN rules:")
        print("\n".join(rules))

    def failover(self):
        process = self.client(self.clients[0], "video2.bin")
        time.sleep(5)
        self.stop_process("srv1")
        output = process.communicate()[0].decode(errors="replace")
        print(output.strip())
        result = parse_client_output(output)
        if process.returncode or not result or result[3] != "OK" or result[2] < 1:
            raise RuntimeError(
                "failover did not complete with a verified resumed download; "
                f"client exit={process.returncode}, output={output.strip()!r}"
            )
        print("Restarting srv1 to demonstrate recovery")
        self.start_server("srv1")

    def path(self):
        """Fail, then degrade, srv1's direct path during a download, restoring it each time."""
        client = self.clients[0]
        self.path_change(client, "failure", lambda: self.net.configLinkStatus("s1", "s2", "down"))
        self.net.configLinkStatus("s1", "s2", "up")
        self.path_recovered(client)
        self.path_change(client, "degradation", lambda: self.set_direct_link(**DEGRADED_LINK))
        self.set_direct_link(**DIRECT_LINK)
        self.path_recovered(client)

    def path_change(self, host, label, change):
        started = time.monotonic()
        process = self.client(host, "video2.bin")
        port, tcp_port, _ = self.route_rule(host, started)
        if port != DIRECT_PORT:
            process.kill()
            raise RuntimeError(f"{host.name} was steered to s1 port {port}, not srv1's direct path")
        time.sleep(2)
        print(f"{host.name} is downloading over srv1's direct path; applying path {label}")
        change()
        output = process.communicate()[0].decode(errors="replace")
        print(output.strip())
        result = parse_client_output(output)
        if process.returncode or not result or result[3] != "OK":
            raise RuntimeError(f"download failed after path {label}: {output.strip()!r}")
        port, _, rule = self.route_rule(host, started, tcp_port)
        print(f"s1 rule: {rule}")
        if port != BACKUP_PORT:
            raise RuntimeError(f"controller did not move the flow to the backup path (port {port})")
        if result[2]:
            raise RuntimeError(f"client reconnected {result[2]} times instead of keeping its connection")
        print(f"Path {label}: flow moved to the backup path on the same TCP connection")

    def path_recovered(self, host):
        # Probes need a few rounds to show the direct path is up and fast again.
        time.sleep(8)
        started = time.monotonic()
        self.download(host, "small.bin")
        port, _, rule = self.route_rule(host, started)
        print(f"s1 rule: {rule}")
        if port != DIRECT_PORT:
            raise RuntimeError(f"new connections did not return to srv1's direct path (port {port})")
        print("Path recovered: new connections use srv1's direct path again")

    def set_direct_link(self, **params):
        """Reconfigure tc on both ends of srv1's direct s1-s2 link."""
        link = self.net.linksBetween(self.net.get("s1"), self.net.get("s2"))[0]
        for intf in (link.intf1, link.intf2):
            intf.config(**params)

    def route_rule(self, host, since, tcp_port=None, timeout=5):
        """Find the host's newest CDN flow rule on s1.

        Only rules installed (or last rewritten) after `since` count; `tcp_port`
        selects one connection. Returns (output port, client TCP port, rule text).
        """
        pattern = re.compile(rf"nw_src={re.escape(host.IP())},nw_dst=10\.0\.0\.100,tp_src=(\d+),")
        deadline = time.monotonic() + timeout
        while True:
            rules = self.net.get("s1").cmd("ovs-ofctl -O OpenFlow13 --no-names dump-flows s1")
            newest = None
            for line in rules.splitlines():
                match = pattern.search(line)
                if not match or tcp_port not in (None, int(match.group(1))):
                    continue
                age = float(re.search(r"duration=([0-9.]+)s", line).group(1))
                if age > time.monotonic() - since:
                    continue
                if newest is None or age < newest[0]:
                    newest = (age, int(match.group(1)), line.strip())
            if newest or time.monotonic() > deadline:
                break
            time.sleep(0.2)
        if newest is None:
            return None, None, None
        _, tcp_port, line = newest
        return int(re.search(r"output:(\d+)", line).group(1)), tcp_port, line

    def adaptive_congestion(self):
        """Verify direct, loaded-backup, then direct selection with both routes up."""
        client = self.clients[0]
        print("No background load: a fresh c1 flow should use the direct route.")
        started = time.monotonic()
        self.download(client, "small.bin")
        port, _, rule = self.route_rule(client, started)
        print(f"s1 rule: {rule}")
        if port != DIRECT_PORT:
            raise RuntimeError(f"unloaded srv1 flow used s1 port {port}, expected {DIRECT_PORT}")

        self.procs["adaptive_iperf_server"] = self.load_sink.popen(
            ["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(1)
        self.procs["adaptive_iperf_client"] = self.load_source.popen(
            ["iperf", "-c", "10.0.0.7", "-t", "60", "-P", "4"],
            stdout=DEVNULL, stderr=DEVNULL)
        try:
            time.sleep(8)  # wait for route port counters to record direct-trunk load
            print("Direct s1-s2 trunk is loaded; a new c1 flow should use the backup.")
            started = time.monotonic()
            self.download(client, "video1.bin")
            port, _, rule = self.route_rule(client, started)
            print(f"s1 rule: {rule}")
            if port != BACKUP_PORT:
                raise RuntimeError(
                    f"loaded srv1 flow used s1 port {port}, expected backup port {BACKUP_PORT}")
            print("Verified: new flow used srv1's backup path while both routes stayed up.")
        finally:
            self.stop_process("adaptive_iperf_client")
            self.stop_process("adaptive_iperf_server")

        time.sleep(6)  # let fresh port counters show that the load has cleared
        print("Load stopped: a fresh c1 flow should return to the direct route.")
        started = time.monotonic()
        self.download(client, "small.bin")
        port, _, rule = self.route_rule(client, started)
        print(f"s1 rule: {rule}")
        if port != DIRECT_PORT:
            raise RuntimeError(f"unloaded srv1 flow used s1 port {port}, expected {DIRECT_PORT}")
        print("Verified: new flow returned to the direct route after load cleared.")

    def random_congestion(self):
        """Load one random server path or none, then record the decision and result."""
        congested = random.choice((None, "srv1", "srv2", "srv3"))
        condition = congested or "none"
        print(f"Random seed: {self.seed}")
        print(f"Realized condition: {condition}.")
        if congested is not None:
            self.procs["random_iperf_server"] = self.load_sink.popen(
                ["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
            time.sleep(1)
            self.procs["random_iperf_client"] = self.servers[congested].popen(
                ["iperf", "-c", "10.0.0.7", "-t", "60", "-P", "4"],
                stdout=DEVNULL, stderr=DEVNULL)
            time.sleep(8)  # allow port counters to observe the generated load

        try:
            started = time.monotonic()
            result = self.download(self.clients[0], "small.bin")
            port, _, rule = self.route_rule(self.clients[0], started)
            routes = {5: ("srv1", "srv1-direct"), 12: ("srv1", "srv1-backup"),
                      6: ("srv2", "srv2"), 7: ("srv3", "srv3")}
            selected, route_name = routes.get(port, ("unknown", "unknown"))
            passed = congested is None or selected != congested
            print(f"Selected s1 rule: {rule}")
            print(f"Controller selected {selected} via {route_name} (s1 port {port}).")

            output = DATA / "random_congestion.csv"
            DATA.mkdir(parents=True, exist_ok=True)
            columns = ("seed", "condition", "congested_server", "selected_server",
                       "selected_route", "s1_port", "bytes", "time_s", "retries",
                       "checksum", "status")
            write_header = not output.exists() or output.stat().st_size == 0
            with output.open("a", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                if write_header:
                    writer.writeheader()
                writer.writerow({
                    "seed": self.seed,
                    "condition": condition,
                    "congested_server": congested or "none",
                    "selected_server": selected,
                    "selected_route": route_name,
                    "s1_port": "" if port is None else port,
                    "bytes": result[0],
                    "time_s": result[1],
                    "retries": result[2],
                    "checksum": result[3],
                    "status": "pass" if passed and result[3] == "OK" else "fail",
                })
            print(f"Recorded run in {output.relative_to(ROOT)}")

            if result[3] != "OK":
                raise RuntimeError("download checksum failed")
            if not passed:
                raise RuntimeError(
                    f"controller selected congested {congested}; expected another healthy server")
            if congested is None:
                print("Verified baseline selection with no generated congestion.")
            else:
                print(f"Verified: congestion on {congested} sent the new flow to {selected}.")
        finally:
            self.stop_process("random_iperf_client")
            self.stop_process("random_iperf_server")

    def congestion(self):
        server = self.servers["srv1"]
        self.procs["iperf_server"] = self.load_sink.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(1)
        self.procs["iperf_client"] = server.popen(
            ["iperf", "-c", "10.0.0.7", "-t", "30", "-P", "4"],
            stdout=DEVNULL, stderr=DEVNULL,
        )
        time.sleep(3)
        self.download(self.clients[0], "video1.bin")

    def experiments(self, mode, quick, only):
        RESULTS.mkdir(exist_ok=True)
        DATA.mkdir(exist_ok=True)
        path = DATA / "experiments.csv"
        counts = (1, 3) if quick else CLIENT_COUNTS
        repetitions = 1 if quick else 3
        conditions = (only,) if only else CONDITIONS
        is_new = not path.exists() or path.stat().st_size == 0

        with path.open("a", newline="") as output:
            writer = csv.writer(output)
            if is_new:
                writer.writerow(("mode", "condition", "nclients", "rep", "client", "time_s",
                                 "mbps", "retries", "status"))
            for _ in range(2):
                self.run_clients(3)
            for condition in conditions:
                self.set_condition(condition)
                for count in counts:
                    for repetition in range(1, repetitions + 1):
                        results = self.run_clients(count)
                        for client, elapsed, mbps, retries, status in results:
                            writer.writerow((mode, condition, count, repetition, client,
                                             elapsed, mbps, retries, status))
                        output.flush()
                        successful = [row[1] for row in results if row[4] == "ok"]
                        average = sum(successful) / len(successful) if successful else float("nan")
                        print(f"{mode} {condition} clients={count} rep={repetition}: "
                              f"ok={len(successful)}/{len(results)} mean={average:.1f}s", flush=True)
                        time.sleep(2)
                self.clear_condition(condition)

    def run_clients(self, count):
        if count < 1 or count > len(self.clients):
            raise ValueError(f"client count must be between 1 and {len(self.clients)}, got {count}")
        jobs = []
        for index in range(count):
            host = self.clients[index]
            jobs.append((host.name, self.client(host), time.monotonic()))
        rows = []
        for name, process, started in jobs:
            output = process.communicate()[0].decode(errors="replace")
            result = parse_client_output(output)
            if process.returncode == 0 and result and result[3] == "OK":
                size, elapsed, retries, _ = result
                rows.append((name, round(elapsed, 2), round(size * 8 / elapsed / 1e6, 2), retries, "ok"))
            else:
                rows.append((name, round(time.monotonic() - started, 2), 0, 5, "failed"))
        return rows

    def set_condition(self, condition):
        if condition == "congested":
            self.procs["iperf_server"] = self.load_sink.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
            time.sleep(1)
            self.procs["iperf_client"] = self.servers["srv1"].popen(
                ["iperf", "-c", "10.0.0.7", "-t", "3600", "-P", "4"],
                stdout=DEVNULL, stderr=DEVNULL,
            )
            time.sleep(8)
        elif condition == "failed":
            self.stop_process("srv1")
            time.sleep(11)

    def clear_condition(self, condition):
        if condition == "congested":
            self.stop_process("iperf_client")
            self.stop_process("iperf_server")
            time.sleep(6)
        elif condition == "failed":
            self.start_server("srv1")
            time.sleep(11)

    def stop(self):
        for name in list(self.procs):
            self.stop_process(name)
        self.net.stop()


def main():
    args = parse_args()
    os.chdir(ROOT)
    if args.scenario == "report":
        import make_graphs
        return
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])

    prepare_content()
    setLogLevel("warning")
    if args.scenario == "random-congestion":
        args.seed = args.seed if args.seed is not None else random.randrange(1 << 32)
        random.seed(args.seed)
    runner = ScenarioRunner(args.file, seed=args.seed)
    try:
        runner.start()
        if args.scenario == "smoke":
            runner.smoke()
        elif args.scenario == "six-client-smoke":
            runner.six_client_smoke()
        elif args.scenario == "failover":
            runner.failover()
        elif args.scenario == "path":
            runner.path()
        elif args.scenario == "adaptive-congestion":
            runner.adaptive_congestion()
        elif args.scenario == "random-congestion":
            runner.random_congestion()
        elif args.scenario == "congestion":
            runner.congestion()
        elif args.scenario == "all":
            runner.failover()
            time.sleep(2)
            runner.smoke()
            runner.path()
            runner.congestion()
        else:
            runner.experiments(args.mode, args.quick, args.only)
    finally:
        runner.stop()


if __name__ == "__main__":
    main()
