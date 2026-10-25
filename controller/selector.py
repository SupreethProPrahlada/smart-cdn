import socket, time
from ryu.lib import hub

LAT = {'srv1': 5, 'srv2': 20, 'srv3': 50}   # path delay in ms (from the topology)
L_MAX = 50.0
IPMAP = {'10.0.0.11': 'srv1', '10.0.0.12': 'srv2', '10.0.0.13': 'srv3'}
C_MAX = 10.0
W_LAT, W_UTIL, W_LOAD = 0.4, 0.4, 0.2
TIMEOUT = 3.0                               # seconds without heartbeat = DOWN


class Selector:
    def __init__(self, logger, port=9000):
        self.log = logger
        self.last_seen = {}
        self.active = {}
        self.util = {n: 0.0 for n in LAT}   # filled by port stats in a later step
        self.was_healthy = {}
        hub.spawn(self._listen, port)
        hub.spawn(self._watch)

    def _listen(self, port):
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', port))
        srv.listen(64)
        self.log.info('heartbeat listener on port %d', port)
        while True:
            c, _ = srv.accept()
            hub.spawn(self._handle, c)

    def _handle(self, c):
        try:
            data = b''
            while b'\n' not in data and len(data) < 256:
                chunk = c.recv(256)
                if not chunk:
                    break
                data += chunk
            parts = data.decode(errors='ignore').split()
            if len(parts) > 1:
                parts[1] = IPMAP.get(parts[1], parts[1])
            if len(parts) >= 3 and parts[0] == 'STATUS' and parts[1] in LAT:
                self.last_seen[parts[1]] = time.time()
                self.active[parts[1]] = int(parts[2])
            else:
                self.log.warning('bad heartbeat: %r', data)
        except Exception as e:
            self.log.warning('heartbeat error: %r', e)
        finally:
            c.close()

    def _watch(self):
        while True:
            for n in LAT:
                h = self.healthy(n)
                if self.was_healthy.get(n) != h:
                    self.log.info('server %s is %s', n, 'UP' if h else 'DOWN')
                    self.was_healthy[n] = h
            hub.sleep(1)

    def healthy(self, n):
        return time.time() - self.last_seen.get(n, 0) < TIMEOUT

    def cost(self, n):
        load = min(self.active.get(n, 0) / C_MAX, 1.0)
        return W_LAT * LAT[n] / L_MAX + W_UTIL * self.util[n] + W_LOAD * load

    def pick(self):
        ok = [n for n in LAT if self.healthy(n)]
        if not ok:
            return None
        return min(ok, key=self.cost)
