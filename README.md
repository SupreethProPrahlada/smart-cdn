# Smart Content Delivery System

A raw TCP content service that uses a Ryu SDN controller to select among three servers in Mininet. The controller considers server health, reported load, configured path delay, and measured link utilization. The experiment runner uses six distinct client hosts (c1-c6); c7 is reserved for congestion traffic.

## Requirements and setup

Install the system networking tools on Ubuntu:

```sh
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf curl
sudo systemctl start openvswitch-switch
```

Install `uv` using its official installer, then install the pinned Python environment and generate the sample payloads:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python tests/make_content.py
```

The `pyproject.toml` and `uv.lock` files pin the Python 3.9 environment and compatible Ryu/Mininet revisions.

`content/` stores generated binary payloads. Servers read these files and clients use them as checksum references. The scenario runner generates them automatically if they are missing; the binaries are ignored by Git.

## Run a scenario

Clean up stale Mininet state before starting a new run:

```sh
sudo mn -c
```

In Terminal 1, start the controller in dynamic mode (use
`CDN_MODE=static` for the fixed-assignment baseline). Leave it running:

```sh
uv run ryu-manager controller/cdn_controller.py
```

In Terminal 2, run all three demo scenarios:

```sh
uv run python tests/run_scenarios.py all
```

The runner re-launches itself with `sudo` when needed. For one scenario,
replace `all` with `smoke`, `six-client-smoke`, `failover`, or `congestion`. The six-client
smoke starts one download on each of c1-c6 at the same time. The smoke scenario
verifies downloads and prints the installed CDN flow rules. Run failover in
dynamic mode: after a server stops sending heartbeats, the controller waits
up to 10 seconds to mark it down and sends new connections to a healthy server.
The client retries during that detection window and resumes from its last
received byte; it allows 12 retries. The runner restarts the server afterward.
The `sch_htb: quantum ... is big` messages during topology startup are Linux
traffic-control warnings from Mininet's shaped links and do not indicate that
cleanup or scenario startup failed.
The runner checks that Ryu's OpenFlow port `6653` and heartbeat port `9000`
are both reachable on localhost before starting Mininet. If either port is
unavailable, the runner exits with the controller start command instead of
starting a scenario without a working controller.

## Performance comparison

Run experiments once per controller mode. Restart the controller in the matching mode between runs:

```sh
uv run python tests/run_scenarios.py experiments --mode dynamic
uv run python tests/run_scenarios.py experiments --mode static
uv run python tests/run_scenarios.py report
```

Restart the controller in the matching mode between experiment runs. Add `--quick` for fewer repetitions and client counts, or `--only normal`, `--only congested`, or `--only failed` to select one condition. Measurements append to `results/data/experiments.csv`; reports and figures are written under `results/reports/` and `results/figures/`.

## Project layout

- `app/`: TCP client and concurrent content server
- `controller/`: Ryu application and server selection logic
- `topology/`: Mininet network definition
- `config/`: fixed network addresses and ports
- `tests/`: content generator, scenario runner, and report generator
- `results/`: experiment data, reports, figures, and a separated archive of older runs

See [docs/architecture.md](docs/architecture.md) for protocol, selection, and failure details.
