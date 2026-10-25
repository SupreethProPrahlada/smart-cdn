import socket, threading, os, time, argparse

p = argparse.ArgumentParser()
p.add_argument('--id', required=True)
p.add_argument('--port', type=int, default=8000)
p.add_argument('--dir', default='content')
p.add_argument('--ctrl', default='10.0.0.254')
p.add_argument('--ctrl-port', type=int, default=9000)
a = p.parse_args()

active = 0
lock = threading.Lock()

def recv_line(conn):
    buf = b''
    while not buf.endswith(b'\n'):
        ch = conn.recv(1)
        if not ch or len(buf) > 1024:
            raise ConnectionError
        buf += ch
    return buf.decode().strip()

def handle(conn):
    global active
    with lock:
        active += 1
    try:
        conn.settimeout(10)
        parts = recv_line(conn).split()
        if parts and parts[0] == 'PING':
            conn.sendall(f'PONG {a.id} {active}\n'.encode())
        elif len(parts) == 3 and parts[0] == 'GET':
            path = os.path.join(a.dir, os.path.basename(parts[1]))
            offset = int(parts[2])
            if not os.path.isfile(path):
                conn.sendall(b'ERR NOTFOUND\n')
                return
            size = os.path.getsize(path)
            conn.sendall(f'OK {size} {max(size - offset, 0)}\n'.encode())
            with open(path, 'rb') as f:
                f.seek(offset)
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    conn.sendall(data)
    except (OSError, ValueError):
        pass
    finally:
        with lock:
            active -= 1
        conn.close()

def heartbeat():
    while True:
        try:
            with socket.create_connection((a.ctrl, a.ctrl_port), timeout=1) as s:
                s.sendall(f'STATUS {a.id} {active} {time.time()}\n'.encode())
        except OSError:
            pass
        time.sleep(1)

threading.Thread(target=heartbeat, daemon=True).start()
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', a.port))
srv.listen(64)
print(f'server {a.id} listening on port {a.port}', flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
