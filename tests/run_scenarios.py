#!/usr/bin/env python3
"""Run repeatable CDN scenarios in a managed Mininet topology."""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path
from subprocess import DEVNULL

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "topology"))

from mininet.log import setLogLevel
from topo import build


RESULTS = ROOT / "results"
DATA = RESULTS / "data"
RESULT_LINE = re.compile(r"got (\d+) bytes in ([0-9.]+)s, retries=(\d+) checksum=(\w+)")
CONDITIONS = ("normal", "congested", "failed")
CLIENT_COUNTS = (1, 3, 6)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("smoke", "failover", "congestion", "all",
                                              "experiments", "report"))
    parser.add_argument("--mode", choices=("dynamic", "static"), default="dynamic",
                        help="must match the running controller")
    parser.add_argument("--file", default="exp.bin", help="content file to request")
    parser.add_argument("--quick", action="store_true", help="run one repetition with up to 3 clients")
    parser.add_argument("--only", choices=CONDITIONS, help="run one experiment condition")
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
    def __init__(self, filename):
        self.filename = filename
        self.net = build()
        self.servers = {name: self.net.get(name) for name in ("srv1", "srv2", "srv3")}
        self.clients = [self.net.get(name) for name in ("c1", "c2", "c3")]
        self.procs = {}

    def start(self):
        self.net.start()
        for name, host in self.servers.items():
            self.start_server(name, host)
        time.sleep(12)
        self.net.pingAll()

    def start_server(self, name, host=None):
        host = host or self.servers[name]
        self.procs[name] = host.popen(
            [sys.executable, str(ROOT / "app/server.py"), "--id", name],
            stdout=DEVNULL, stderr=DEVNULL,
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
            raise RuntimeError("failover did not complete with a verified resumed download")
        print("Restarting srv1 to demonstrate recovery")
        self.start_server("srv1")

    def congestion(self):
        c4 = self.net.get("c4")
        server = self.servers["srv1"]
        self.procs["iperf_server"] = c4.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(1)
        self.procs["iperf_client"] = server.popen(
            ["iperf", "-c", "10.0.0.4", "-t", "30", "-P", "4"],
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
        jobs = []
        for index in range(count):
            host = self.clients[index % len(self.clients)]
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
            c4 = self.net.get("c4")
            self.procs["iperf_server"] = c4.popen(["iperf", "-s"], stdout=DEVNULL, stderr=DEVNULL)
            time.sleep(1)
            self.procs["iperf_client"] = self.servers["srv1"].popen(
                ["iperf", "-c", "10.0.0.4", "-t", "3600", "-P", "4"],
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
    runner = ScenarioRunner(args.file)
    try:
        runner.start()
        if args.scenario == "smoke":
            runner.smoke()
        elif args.scenario == "failover":
            runner.failover()
        elif args.scenario == "congestion":
            runner.congestion()
        elif args.scenario == "all":
            runner.failover()
            time.sleep(2)
            runner.smoke()
            runner.congestion()
        else:
            runner.experiments(args.mode, args.quick, args.only)
    finally:
        runner.stop()


if __name__ == "__main__":
    main()
