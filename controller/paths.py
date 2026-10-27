"""Routes from s1 to each content server and their measured condition.

Port numbers must match topology/topo.py. srv1 has two routes: the direct
s1-s2 link and a slower backup through s5. srv2 and srv3 have one route each.
"""

from collections import namedtuple


# One switch on a route: the port leading toward the server, the port leading
# back toward s1 (None on s1, where it is the client's own port) and the
# bandwidth in bit/s of the link behind to_server.
Hop = namedtuple("Hop", "dpid to_server to_client bw")

PROBE_TIMEOUT = 3.0      # no probe reply for this long: route is down
RTT_SMOOTHING = 0.5      # weight of the newest probe sample


class Route:
    def __init__(self, name, server, hops):
        self.name = name
        self.server = server
        self.hops = hops
        self.rtt = None          # smoothed probe round-trip time in seconds
        self.util = 0.0          # busiest link on the route, 0..1
        self.last_reply = 0.0    # time of the latest probe reply
        self.ports_down = set()  # (dpid, port) on this route reported down
        self.up = False
        self.sent = {}           # probe sequence number -> send time

    def ports(self):
        """Every switch port the route uses, as (dpid, port)."""
        ports = {(hop.dpid, hop.to_server) for hop in self.hops}
        ports.update((hop.dpid, hop.to_client) for hop in self.hops[1:])
        return ports

    def trunk_ports(self):
        """Switch-to-switch ports, which can form loops for flooded traffic."""
        return self.ports() - {(self.hops[-1].dpid, self.hops[-1].to_server)}

    def probe_sent(self, seq, now):
        self.sent[seq] = now
        for old in [s for s, t in self.sent.items() if now - t > 2 * PROBE_TIMEOUT]:
            del self.sent[old]

    def probe_returned(self, seq, now):
        sent = self.sent.pop(seq, None)
        if sent is None:
            return
        sample = now - sent
        self.rtt = sample if self.rtt is None else (
            RTT_SMOOTHING * sample + (1 - RTT_SMOOTHING) * self.rtt)
        self.last_reply = now

    def check(self, now):
        """Update up/down state; return a reason string if it changed."""
        if self.ports_down:
            dpid, port = sorted(self.ports_down)[0]
            up, reason = False, "port s%d:%d down" % (dpid, port)
        elif now - self.last_reply >= PROBE_TIMEOUT:
            up, reason = False, "no probe reply for %.0fs" % PROBE_TIMEOUT
        else:
            up, reason = True, "probe rtt %.1f ms" % (self.rtt * 1000)
        if up == self.up:
            return None
        self.up = up
        return reason


ROUTES = [
    Route("srv1-direct", "srv1", [Hop(1, 5, None, 100e6), Hop(2, 1, 2, 100e6)]),
    Route("srv1-backup", "srv1", [Hop(1, 12, None, 100e6), Hop(5, 2, 1, 100e6),
                                  Hop(2, 1, 3, 100e6)]),
    Route("srv2", "srv2", [Hop(1, 6, None, 50e6), Hop(3, 1, 2, 100e6)]),
    Route("srv3", "srv3", [Hop(1, 7, None, 10e6), Hop(4, 1, 2, 100e6)]),
]
