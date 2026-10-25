import socket, time, sys, csv, argparse, os

p = argparse.ArgumentParser()
p.add_argument('--name', required=True)
p.add_argument('--host', default='10.0.0.100')
p.add_argument('--port', type=int, default=8000)
p.add_argument('--client', default='c?')
p.add_argument('--log', default='results/raw.csv')
p.add_argument('--tag', default='')
a = p.parse_args()

def recv_line(s):
    buf = b''
    while not buf.endswith(b'\n'):
        ch = s.recv(1)
        if not ch:
            raise ConnectionError
        buf += ch
    return buf.decode().strip()

offset, total, retries, ttfb = 0, None, 0, None
t0 = time.time()
while retries <= 5:
    try:
        s = socket.create_connection((a.host, a.port), timeout=3)
        s.settimeout(2)
        s.sendall(f'GET {a.name} {offset}\n'.encode())
        hdr = recv_line(s)
        if hdr.startswith('ERR'):
            print(hdr)
            sys.exit(1)
        _, total, remaining = hdr.split()
        total, remaining = int(total), int(remaining)
        got = 0
        while got < remaining:
            chunk = s.recv(65536)
            if not chunk:
                raise ConnectionError
            if ttfb is None:
                ttfb = time.time() - t0
            got += len(chunk)
            offset += len(chunk)
        s.close()
        break
    except OSError:
        retries += 1
        time.sleep(min(2 ** (retries - 1), 4))
else:
    print('FAILED')
    sys.exit(2)

dt = time.time() - t0
os.makedirs(os.path.dirname(a.log) or '.', exist_ok=True)
with open(a.log, 'a', newline='') as f:
    csv.writer(f).writerow([a.tag, a.client, a.name, total, round(ttfb or 0, 3),
                            round(dt, 3), round(total * 8 / dt / 1e6, 2), retries])
print(f'{a.client} got {total} bytes in {dt:.2f}s, retries={retries}')
