#!/usr/bin/env python3
"""Add seedable randomized congestion runs and a CSV record to smart-cdn-main."""

from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parent
target = ROOT / "tests" / "run_scenarios.py"
text = target.read_text(encoding="utf-8")
original = text


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one match for {label}; found {count}. No files were changed. "
            "Confirm random-congestion is already installed."
        )
    text = text.replace(old, new, 1)


replace_once(
    '    parser.add_argument("--only", choices=CONDITIONS, help="run one experiment condition")\n',
    '    parser.add_argument("--only", choices=CONDITIONS, help="run one experiment condition")\n'
    '    parser.add_argument("--seed", type=int, help="replay a random-congestion run")\n',
    "--seed argument",
)
replace_once(
    '    def __init__(self, filename):\n'
    '        self.filename = filename\n'
    '        self.net = build()\n',
    '    def __init__(self, filename, seed=None):\n'
    '        self.filename = filename\n'
    '        self.seed = seed\n'
    '        self.net = build()\n',
    "runner seed storage",
)

pattern = re.compile(r"    def random_congestion\(self\):\n.*?(?=    def congestion\(self\):\n)", re.S)
matches = list(pattern.finditer(text))
if len(matches) != 1:
    raise SystemExit(
        f"Expected one random_congestion method; found {len(matches)}. No files were changed."
    )
method = '''    def random_congestion(self):
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

'''
text = text[:matches[0].start()] + method + text[matches[0].end():]

replace_once(
    '    runner = ScenarioRunner(args.file)\n',
    '    if args.scenario == "random-congestion":\n'
    '        args.seed = args.seed if args.seed is not None else random.randrange(1 << 32)\n'
    '        random.seed(args.seed)\n'
    '    runner = ScenarioRunner(args.file, seed=args.seed)\n',
    "seed selection and runner setup",
)

if text == original:
    raise SystemExit("No changes produced; refusing to write an empty update.")

backup = target.with_suffix(target.suffix + ".before-reproducible-random-congestion")
if not backup.exists():
    shutil.copy2(target, backup)
target.write_text(text, encoding="utf-8")
print("Random congestion runs now print a seed and append results/data/random_congestion.csv.")
print("Replay a run with: uv run python tests/run_scenarios.py random-congestion --seed SEED")
print("Original runner backup: tests/run_scenarios.py.before-reproducible-random-congestion")
