# Architecture

## Network

    c1-c6 ---- s1 ---- 5 ms / 100 Mbps ---- srv1
                    ---- 20 ms / 50 Mbps --- srv2
                    ---- 50 ms / 10 Mbps --- srv3

Ryu controls the four OpenFlow 1.3 switches. Clients request the virtual address `10.0.0.100:8000`; no host owns that address. The controller answers its ARP requests and rewrites each new TCP flow to a selected server. A root namespace interface connects the controller host to `s1` at `10.0.0.254`; servers send status heartbeats to that address on TCP port 9000. Experiments run up to six separate client hosts (`c1`-`c6`) concurrently; `c7` is reserved as the iperf congestion sink.

Addresses and ports are listed in `config/settings.md`.

## TCP protocol

- Client request: `GET <filename> <byte-offset>\n`
- Server response: `OK <total-bytes> <remaining-bytes>\n`, followed by the remaining bytes; errors begin with `ERR`.
- Server heartbeat: `STATUS <server-id> <active-connections> <timestamp>\n`

The client retries interrupted connections up to five times and resumes from its received byte offset. It verifies the completed download with SHA-256 against the generated file in `content/`. The server handles each request in its own thread.

## Controller behavior

The controller installs forward and reverse OpenFlow rules for each new client flow. Forward rules rewrite the VIP destination to the chosen server; reverse rules restore the VIP source. On server failure, it removes rules associated with that server. A reconnecting client is then selected again and resumes its transfer.

In dynamic mode, the selector chooses the lowest cost healthy server:

    cost = 0.4 * path_delay / 50 ms + 0.4 * path_utilization
           + 0.2 * min(active_connections / 10, 1)

Path delays come from the topology. Utilization comes from switch port statistics; active connections and availability come from server heartbeats. A server is marked down after 10 seconds without a heartbeat. In static mode, clients are assigned to servers by client number for the baseline comparison.

Each server has one path, so the controller selects a server rather than an alternate path. Delay is configured rather than measured dynamically, and link failures are not detected independently of server heartbeats.

## Scenarios and measurements

`tests/run_scenarios.py` manages the Mininet topology and provides smoke, failover, congestion, and experiment scenarios. The experiment runner records response time, throughput, retries, and success for normal, congested, and failed-server conditions at multiple client counts. Run it in both controller modes; `tests/make_graphs.py` creates the summary and plots.

Current generated results live under `results/data/`, `results/reports/`, and `results/figures/`. Earlier run artifacts with unclear or outdated provenance are kept separately under `results/archive/unverified/` and are not used in generated reports.
