"""Track server health and choose the lowest-cost healthy server."""

import socket
import time

from ryu.lib import hub


PATH_DELAY_MS = {"srv1": 5, "srv2": 20, "srv3": 50}
SERVER_IPS = {
    "10.0.0.11": "srv1",
    "10.0.0.12": "srv2",
    "10.0.0.13": "srv3",
}
MAX_DELAY_MS = 50.0
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
        self.util = {name: 0.0 for name in PATH_DELAY_MS}
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

            parts = data.decode(errors="ignore").split()
            if len(parts) > 1:
                parts[1] = SERVER_IPS.get(parts[1], parts[1])
            if len(parts) >= 3 and parts[0] == "STATUS" and parts[1] in PATH_DELAY_MS:
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
            for name in PATH_DELAY_MS:
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

    def cost(self, name):
        delay = PATH_DELAY_MS[name] / MAX_DELAY_MS
        utilization = self.util[name]
        load = min(self.active.get(name, 0) / MAX_CONNECTIONS, 1.0)
        return (DELAY_WEIGHT * delay + UTILIZATION_WEIGHT * utilization
                + LOAD_WEIGHT * load)

    def pick(self):
        healthy = [name for name in PATH_DELAY_MS if self.healthy(name)]
        return min(healthy, key=self.cost) if healthy else None
