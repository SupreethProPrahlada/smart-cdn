"""Track server health and choose the lowest-cost healthy route."""

import socket
import time

from ryu.lib import hub

from paths import ROUTES


SERVERS = ("srv1", "srv2", "srv3")
SERVER_IPS = {
    "10.0.0.11": "srv1",
    "10.0.0.12": "srv2",
    "10.0.0.13": "srv3",
}
MAX_RTT = 0.1            # seconds: round trip of the slowest healthy route (srv3)
MAX_CONNECTIONS = 10.0
DELAY_WEIGHT = 0.4
UTILIZATION_WEIGHT = 0.4
LOAD_WEIGHT = 0.2
HEARTBEAT_TIMEOUT = 10.0


class Selector:
    def __init__(self, logger, port=9000):
        self.log = logger
        self.last_seen = {}
        self.active = {}
        self.was_healthy = {}
        self.on_down = None
        hub.spawn(self._listen, port)
        hub.spawn(self._watch)

    def _listen(self, port):
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(64)
        self.log.info("heartbeat listener on port %d", port)
        while True:
            conn, _ = server.accept()
            hub.spawn(self._handle, conn)

    def _handle(self, conn):
        try:
            data = bytearray()
            while b"\n" not in data and len(data) < 256:
                chunk = conn.recv(256)
                if not chunk:
                    break
                data.extend(chunk)

            if not data:
                return
            parts = data.decode(errors="ignore").split()
            if len(parts) > 1:
                parts[1] = SERVER_IPS.get(parts[1], parts[1])
            if len(parts) >= 3 and parts[0] == "STATUS" and parts[1] in SERVERS:
                if parts[1] not in self.last_seen:
                    self.log.info("received first heartbeat from %s", parts[1])
                self.last_seen[parts[1]] = time.time()
                self.active[parts[1]] = int(parts[2])
            else:
                self.log.warning("bad heartbeat: %r", data)
        except (OSError, ValueError, UnicodeError) as error:
            self.log.warning("heartbeat error: %r", error)
        finally:
            conn.close()

    def _watch(self):
        while True:
            for name in SERVERS:
                healthy = self.healthy(name)
                if self.was_healthy.get(name) == healthy:
                    continue

                age = time.time() - self.last_seen.get(name, time.time())
                state = "UP" if healthy else "DOWN"
                self.log.info("server %s is %s (last heartbeat %.1fs ago)", name, state, age)
                self.was_healthy[name] = healthy
                if not healthy and self.on_down:
                    self.on_down(name)
            hub.sleep(1)

    def healthy(self, name):
        return time.time() - self.last_seen.get(name, 0) < HEARTBEAT_TIMEOUT

    def cost(self, route):
        delay = min(route.rtt / MAX_RTT, 1.0)
        load = min(self.active.get(route.server, 0) / MAX_CONNECTIONS, 1.0)
        return (DELAY_WEIGHT * delay + UTILIZATION_WEIGHT * route.util
                + LOAD_WEIGHT * load)

    def pick(self):
        """Lowest-cost route to any healthy server, for a new client flow."""
        usable = [route for route in ROUTES if route.up and self.healthy(route.server)]
        return min(usable, key=self.cost) if usable else None

    def best_route(self, server):
        """Lowest-delay working route to one server, for moving an existing flow."""
        usable = [route for route in ROUTES if route.server == server and route.up]
        return min(usable, key=lambda route: route.rtt) if usable else None
