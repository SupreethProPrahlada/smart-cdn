# Architecture: Smart Content Delivery System (TCP)

## Topology

    c1 c2 c3 c4          (10.0.0.1 - .4)
        \  |  |  /
          [ s1 ]  ---- NAT node (10.0.0.254, heartbeat target)
         /   |   \
  5 ms /     | 20 ms \ 50 ms
 100 Mbps  50 Mbps   10 Mbps
     [ s2 ]  [ s3 ]  [ s4 ]
       |       |       |
     srv1    srv2    srv3
   10.0.0.11 .12      .13

    Ryu controller (OpenFlow 1.3, 127.0.0.1:6653) controls s1 to s4.
    Servers send heartbeats to the controller on TCP port 9000.

Clients send requests to a virtual IP (10.0.0.100, MAC 00:00:00:00:01:00, TCP 8000).
No host owns it. The controller answers ARP for it and rewrites packets.

## Application protocol (raw TCP sockets)

- Client to server: `GET <name> <offset>\n`
- Server to client: `OK <total> <remaining>\n` then raw bytes, or `ERR NOTFOUND\n`
- Server to controller, every second: `STATUS <id> <active_connections> <timestamp>\n`
- The client uses a 2 s receive timeout, retries up to 5 times with waits of 1, 2, 4, 4, 4 s,
  and resumes from the byte offset it has reached. It verifies a SHA-256 of the received data.

## Flow rewriting (Ryu, OpenFlow 1.3)

1. A client ARPs for the VIP. The controller replies with the virtual MAC.
2. The first SYN has no matching rule and reaches the controller (packet-in).
3. The controller picks a server and installs two rules (priority 100, idle timeout 30 s):
   - forward: match src=client, dst=VIP, tcp dst 8000. Set eth_dst and ipv4_dst to the server, output toward it.
   - reverse: match src=server, tcp src 8000. Set eth_src to the virtual MAC and ipv4_src to the VIP, output toward the client.
4. The first packet is sent on with a packet-out so it is not lost.

A live TCP connection cannot move between servers because its state lives in the server kernel.
Recovery therefore happens in the client: it reconnects to the VIP and resumes by offset.

## Selection rule (as implemented)

For each new flow, among servers that are UP, choose the lowest cost:

    cost(S) = 0.4 * delay(S)/50 ms + 0.4 * utilisation(S) + 0.2 * min(active_connections(S)/10, 1)

- delay(S): configured link delay of the path to S (5, 20, 50 ms). It is not measured live.
- utilisation(S): port statistics of s1 every 2 s, rate divided by link capacity, taken as the larger of rx and tx.
- active_connections(S): reported by the server heartbeat.
- Not implemented: hysteresis (switching only for a clearly better server) and link-failure detection.

Static baseline: the controller started with CDN_MODE=static assigns client i to server (i-1) mod 3.

## Failure behaviour

- A server is UP while heartbeats arrive. After 10 s without one it is marked DOWN.
- On DOWN the controller deletes every flow rule on s1 that sends traffic to that server or carries its replies,
  so packets of running transfers return to the controller and are steered to a healthy server.
- Clients on a broken connection reconnect and resume. The new flow is steered to the cheapest UP server.
- A server that resumes heartbeats is marked UP and can be chosen again. Existing flows are not moved back.
- If no server is UP, the SYN is dropped and the client keeps retrying until it gives up.

## Results (3 repetitions per cell, 1, 3 and 6 clients, 20 MB file)

See results/summary.md and the graphs in results/.

- Failed server: dynamic completed 30 of 30 downloads, static completed 18 of 30.
- Congested path, 1 client: 8.5 s (dynamic) against 28.0 s (static).
- Congested path with 3 and 6 clients, and normal conditions: differences are within the run-to-run noise.

## Known limitations

- The flow-deletion on server failure was added after the experiment runs, so those runs used the earlier controller.
- The warm-up step in the experiment script was added after the normal and failed runs.
- The 10 s timeout was set after the runs, which used 6 s.
- Each server has a single path from s1, so the controller chooses servers but not between alternative paths.
- With a busy path, heartbeats can be delayed and a healthy server can briefly be marked DOWN.
