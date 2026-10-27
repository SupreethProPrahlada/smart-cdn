# Architecture

## Network

    c1-c6 ---- s1 ---- 5 ms / 100 Mbps ----------------- s2 ---- srv1
                  \--- 10 ms / 100 Mbps --- s5 --- 5 ms ---/      (backup route to srv1)
                   --- 20 ms / 50 Mbps ----------------- s3 ---- srv2
                   --- 50 ms / 10 Mbps ----------------- s4 ---- srv3

Ryu controls the five OpenFlow 1.3 switches. srv1 can be reached over two routes, so the controller chooses a path as well as a server:

| route | s1 port | switches | one-way delay | bottleneck |
|---|---|---|---|---|
| `srv1-direct` | 5 | s1-s2 | 5 ms | 100 Mbps |
| `srv1-backup` | 12 | s1-s5-s2 | 15 ms | 100 Mbps |
| `srv2` | 6 | s1-s3 | 20 ms | 50 Mbps |
| `srv3` | 7 | s1-s4 | 50 ms | 10 Mbps |

The route table, with every switch port, is in `controller/paths.py` and must match `topology/topo.py`.

Clients request the virtual address `10.0.0.100:8000`; no host owns that address. The controller answers its ARP requests and rewrites each new TCP flow to a selected server. A root namespace interface connects the controller host to `s1` at `10.0.0.254`; servers send status heartbeats to that address on TCP port 9000. Experiments run up to six separate client hosts (`c1`-`c6`) concurrently; `c7` is reserved as the iperf congestion sink.

Addresses and ports are listed in `config/settings.md`.

## TCP protocol

- Client request: `GET <filename> <byte-offset>\n`
- Server response: `OK <total-bytes> <remaining-bytes>\n`, followed by the remaining bytes; errors begin with `ERR`.
- Server heartbeat: `STATUS <server-id> <active-connections> <timestamp>\n`

The client retries interrupted connections up to five times and resumes from its received byte offset. It verifies the completed download with SHA-256 against the generated file in `content/`. The server handles each request in its own thread.

## Controller behavior

### Flow rules

For each new client flow the controller installs a forward and a reverse rule on every switch of the chosen route. On `s1` the forward rule rewrites the VIP destination to the chosen server and sends the packet out of the route's port; the reverse rule restores the VIP source and sends the reply to the client's port. On the other switches of the route the rules match the rewritten connection and forward it one hop toward the server or back toward `s1`. Because the route is held in these rules, the controller can move a live connection to another route to the same server by rewriting them: the TCP endpoints stay the same, so the connection carries on.

| priority | switches | match | action | cookie |
|---|---|---|---|---|
| 200 | s1 | probe EtherType `0x88b5` | to controller | 4 |
| 200 | s2-s5 | probe EtherType, in port | next hop, or back out of the in port at the route's last switch | 4 |
| 100 | s1 | client -> VIP connection | set server MAC and IP, out of the route's port | 2 |
| 100 | s1 | server -> client connection | set VIP MAC and IP, out of the client's port | 2 |
| 100 | s2-s5 on the route | client -> server, server -> client | next hop | 2 |
| 50 | spare-route switch ports | in port | drop | 3 |
| 1 | all | in port, learned destination MAC | learned port | 1 |
| 0 | all | anything else | to controller | 0 |

CDN rules time out after 30 idle seconds. The `s1` forward rule asks the switch to report its removal, which tells the controller the connection has ended.

### Network measurements

- **Round-trip time.** Every second the controller sends one probe frame out of `s1` on each route. Probe rules carry it to the route's last switch, which sends it back the way it came; `s1` returns it to the controller. The time from packet-out to packet-in is smoothed (`rtt = 0.5 * sample + 0.5 * rtt`). It includes queueing, so a congested link shows a higher round trip, and it includes the controller's own processing time, which is the same for every route.
- **Utilization.** Port statistics from every switch every second. A route's utilization is that of its busiest link (bytes per second / link capacity), including the server's own access link.
- **Link state.** OpenFlow port-status messages report a link going down or up immediately.

A route is **down** when one of its ports reports link down or no probe has returned for 3 seconds, and **up** again once its ports are up and probes return.

### Selection

In dynamic mode a new flow gets the lowest-cost route that is up and leads to a healthy server:

    cost = 0.4 * min(rtt / 100 ms, 1) + 0.4 * route_utilization
           + 0.2 * min(active_connections / 10, 1)

Active connections and availability come from server heartbeats; a server is marked down after 10 seconds without one. In static mode, clients are assigned to servers by client number, always on that server's first route, and flows are never moved, for the baseline comparison.

### Failure, degradation and recovery

Every second, and immediately after a port-status message, the controller re-checks every live flow (dynamic mode):

- **Path failure.** If the flow's route is down, the flow moves at once to the fastest working route to the same server. A link failure reported by port status is handled within milliseconds, so TCP only retransmits what was in flight and the client keeps its connection.
- **Path degradation.** If another route to the same server has a round trip at least 50 ms shorter, the flow moves to it. Utilization does not move existing flows, because a flow's own traffic would make it bounce between routes; it only steers new flows.
- **No route left.** If the server has no working route, the flow's rules are deleted. The client's next packet is steered as a new flow to another server, which resets the connection; the client reconnects and resumes from its byte offset.
- **Server failure.** When heartbeats stop, the server's flows are deleted the same way.
- **Recovery.** A route that comes back up is used for new flows again as soon as its cost is lowest. Existing flows move back only if that saves at least 50 ms of round trip, to avoid reordering a connection for little gain.

### Loop-free forwarding for other traffic

ARP, heartbeats and `pingAll` use ordinary MAC learning and flooding, and the backup route forms a loop. For each server, the first route that is up carries this traffic; the switch ports of the other route get a priority-50 drop rule, which CDN and probe rules override. When the direct route to srv1 fails, the controller blocks its ports, opens the backup's, and clears learned MAC addresses so hosts are found again over the new tree. srv1's heartbeats therefore keep reaching the controller during a direct-link failure, and srv1 stays available.

### Limitations

Only srv1 has an alternative route. A reduced link bandwidth is not measured directly; the controller sees it only through queueing delay in the round trip or through utilization. Probe round trips include controller processing time, which can rise when the controller is busy. The controller learns that a connection has ended only when its `s1` rule has been idle for 30 seconds, so a finished connection can still appear in the log as moved during that time; this has no effect on traffic.

## Scenarios and measurements

`tests/run_scenarios.py` manages the Mininet topology and provides smoke, failover, path, congestion, and experiment scenarios. The path scenario takes srv1's direct link down, and later raises its delay from 5 ms to 100 ms, while a client downloads; it checks that the controller moved the flow to the backup route, that the download completed on the same connection, and that new connections use the direct route again once it is restored. The experiment runner records response time, throughput, retries, and success for normal, congested, and failed-server conditions at multiple client counts. Run it in both controller modes; `tests/make_graphs.py` creates the summary and plots.

Current generated results live under `results/data/`, `results/reports/`, and `results/figures/`. Earlier run artifacts with unclear or outdated provenance are kept separately under `results/archive/unverified/` and are not used in generated reports.
