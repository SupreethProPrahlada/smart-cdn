# Smart Content Delivery System

A raw TCP content service that uses a Ryu SDN controller to select among three servers in Mininet, and among two paths to srv1. The controller considers server health and reported load, and measures path round-trip time, link utilization and link state itself. When a path fails or degrades it moves live connections to the other path. The experiment runner uses six distinct client hosts (c1-c6); c7 is reserved for congestion traffic.

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

In Terminal 2, run the failover, smoke, path, and congestion demo scenarios:

```sh
uv run python tests/run_scenarios.py all
```

The runner re-launches itself with `sudo` when needed. For one scenario,
replace `all` with `smoke`, `six-client-smoke`, `failover`, `path`, or `congestion`. The six-client
smoke starts one download on each of c1-c6 at the same time. The smoke scenario
verifies downloads and prints the installed CDN flow rules. Run failover in
dynamic mode: after a server stops sending heartbeats, the controller waits
up to 10 seconds to mark it down and sends new connections to a healthy server.
The client retries during that detection window and resumes from its last
received byte; it allows 12 retries. The runner restarts the server afterward.

Run the path scenario in dynamic mode too. While c1 downloads a 100 MB file
over srv1's direct link (s1-s2), the runner first takes that link down, and in
a second download raises its delay from 5 ms to 100 ms. Each time the
controller must move the live connection to the backup route through s5
(s1 port 12) without the client reconnecting. After the link is restored, a
new download must use the direct route (s1 port 5) again. Expected output
(times, ports and counters vary):

```text
c1 is downloading over srv1's direct path; applying path failure
c1 got 104857600 bytes in 9.66s, retries=0 checksum=OK
s1 rule: cookie=0x2, ... priority=100,tcp,nw_src=10.0.0.1,nw_dst=10.0.0.100,tp_src=39042,tp_dst=8000 actions=set_field:00:00:00:00:00:11->eth_dst,set_field:10.0.0.11->ip_dst,output:12
Path failure: flow moved to the backup path on the same TCP connection
c1 got 2097152 bytes in 0.21s, retries=0 checksum=OK
s1 rule: cookie=0x2, ... priority=100,tcp,nw_src=10.0.0.1,nw_dst=10.0.0.100,tp_src=56290,tp_dst=8000 actions=set_field:00:00:00:00:00:11->eth_dst,set_field:10.0.0.11->ip_dst,output:5
Path recovered: new connections use srv1's direct path again
c1 is downloading over srv1's direct path; applying path degradation
c1 got 104857600 bytes in 11.53s, retries=0 checksum=OK
s1 rule: cookie=0x2, ... output:12
Path degradation: flow moved to the backup path on the same TCP connection
c1 got 2097152 bytes in 0.19s, retries=0 checksum=OK
s1 rule: cookie=0x2, ... output:5
Path recovered: new connections use srv1's direct path again
```

The controller log shows the same events, for example (numbers vary):

```text
route srv1-direct is DOWN (port s1:5 down)
L2 tree changed; blocked ports: s1:5, s2:2
flow 10.0.0.1:39042 moved from srv1-direct to srv1-backup (srv1-direct down)
route srv1-direct is UP (probe rtt 13.9 ms)
flow 10.0.0.1:56296 moved from srv1-direct to srv1-backup (rtt 463 ms vs 34 ms)
```

Every 5 seconds it also logs each route's measured round trip, utilization
and state (`routes: srv1-direct up rtt 12.5ms util 0.00 | ...`).
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
