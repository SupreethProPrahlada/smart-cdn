#!/usr/bin/env python3
import sys, os, re, csv, time, argparse
from subprocess import DEVNULL

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'topology'))
from mininet.log import setLogLevel
from topo import build

p = argparse.ArgumentParser()
p.add_argument('--mode', required=True, choices=['static', 'dynamic'])
p.add_argument('--quick', action='store_true')
p.add_argument('--file', default='exp.bin')
p.add_argument('--out', default='results/experiments.csv')
a = p.parse_args()

COUNTS = [1, 3] if a.quick else [1, 3, 6]
REPS = 1 if a.quick else 3
RESULT = re.compile(r'got (\d+) bytes in ([0-9.]+)s, retries=(\d+)')

setLogLevel('warning')
net = build()
net.start()
srv = {n: net.get(n) for n in ('srv1', 'srv2', 'srv3')}
cl = [net.get(n) for n in ('c1', 'c2', 'c3')]
c4 = net.get('c4')
procs = {}


def start_server(n):
    procs[n] = srv[n].popen(['python3', 'app/server.py', '--id', n],
                            stdout=DEVNULL, stderr=DEVNULL)


def stop_server(n):
    procs[n].kill()
    procs[n].wait()


def run_clients(n, tag):
    jobs = []
    for i in range(n):
        h = cl[i % len(cl)]
        t0 = time.time()
        pr = h.popen(['python3', 'app/client.py', '--name', a.file, '--client', h.name,
                      '--log', '/dev/null', '--tag', tag])
        jobs.append((h.name, pr, t0))
    out = []
    for name, pr, t0 in jobs:
        txt = pr.communicate()[0].decode()
        el = time.time() - t0
        m = RESULT.search(txt)
        if m and pr.returncode == 0:
            size, dt, r = int(m.group(1)), float(m.group(2)), int(m.group(3))
            out.append((name, round(dt, 2), round(size * 8 / dt / 1e6, 2), r, 'ok'))
        else:
            out.append((name, round(el, 2), 0.0, 5, 'FAILED'))
    return out


def condition(cond):
    if cond == 'congested':
        procs['iperf_s'] = c4.popen(['iperf', '-s'], stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(1)
        procs['iperf_c'] = srv['srv1'].popen(['iperf', '-c', '10.0.0.4', '-t', '3600'],
                                    stdout=DEVNULL, stderr=DEVNULL)
        time.sleep(8)
    elif cond == 'failed':
        stop_server('srv1')
        time.sleep(10)


def cleanup(cond):
    if cond == 'congested':
        for k in ('iperf_c', 'iperf_s'):
            procs[k].kill()
            procs[k].wait()
        time.sleep(6)
    elif cond == 'failed':
        start_server('srv1')
        time.sleep(10)


os.makedirs(os.path.dirname(a.out), exist_ok=True)
new = not os.path.exists(a.out)
f = open(a.out, 'a', newline='')
w = csv.writer(f)
if new:
    w.writerow(['mode', 'condition', 'nclients', 'rep', 'client', 'time_s', 'mbps', 'retries', 'status'])

try:
    for n in srv:
        start_server(n)
    time.sleep(10)
    net.pingAll()
    net.pingAll()
    for _ in range(2):
        run_clients(3, 'warmup')   # not recorded: primes caches and TCP state
    for cond in ('normal', 'congested', 'failed'):
        condition(cond)
        for n in COUNTS:
            for rep in range(1, REPS + 1):
                res = run_clients(n, cond)
                for r in res:
                    w.writerow([a.mode, cond, n, rep, *r])
                f.flush()
                ok = [r for r in res if r[4] == 'ok']
                avg = sum(r[1] for r in ok) / len(ok) if ok else float('nan')
                print(f'{a.mode} {cond} n={n} rep={rep}: ok={len(ok)}/{len(res)} avg_time={avg:.1f}s',
                      flush=True)
                time.sleep(2)
        cleanup(cond)
finally:
    f.close()
    for pr in list(procs.values()):
        try:
            pr.kill()
        except Exception:
            pass
    net.stop()
