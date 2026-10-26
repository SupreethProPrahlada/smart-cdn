# Smart Content Delivery System

A raw TCP content service that uses a Ryu SDN controller to select among three servers in Mininet. The controller considers server health, reported load, configured path delay, and measured link utilization.

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

Stop stale Mininet/controller processes before cleanup:

```sh
sudo mn -c
```

In one terminal, start the controller in dynamic mode (use `CDN_MODE=static` for the fixed-assignment baseline):

```sh
uv run ryu-manager controller/cdn_controller.py
```

In another terminal, run all three demo scenarios:

```sh
uv run python tests/run_scenarios.py all
```

The runner creates and stops its own topology, servers, and clients, and re-launches itself with `sudo` when needed. For one scenario, replace `all` with `smoke`, `failover`, or `congestion`. The smoke scenario verifies downloads and prints the installed CDN flow rules. Run failover in dynamic mode to kill a server during a download and check checksum verified resume. The runner restarts the server afterward.

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
