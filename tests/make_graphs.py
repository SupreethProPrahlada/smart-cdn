import csv, os, statistics as st
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
rows = list(csv.DictReader(open(os.path.join(ROOT, 'results', 'experiments.csv'))))
CONDS = ['normal', 'congested', 'failed']
COUNTS = [1, 3, 6]
MODES = ['dynamic', 'static']

g = defaultdict(list)
for r in rows:
    g[(r['mode'], r['condition'], int(r['nclients']))].append(r)


def stats(mode, cond, n):
    rs = g.get((mode, cond, n), [])
    ok = [r for r in rs if r['status'] == 'ok']
    times = [float(r['time_s']) for r in ok]
    mbps = [float(r['mbps']) for r in ok]
    return {
        'total': len(rs), 'ok': len(ok),
        'rate': 100.0 * len(ok) / len(rs) if rs else 0.0,
        'mean': st.mean(times) if times else None,
        'min': min(times) if times else None,
        'max': max(times) if times else None,
        'mbps': st.mean(mbps) if mbps else None,
    }


w = 0.35


def plot(metric, ylabel, fname):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, cond in zip(axes, CONDS):
        for i, mode in enumerate(MODES):
            xs, ys, lo, hi = [], [], [], []
            for j, n in enumerate(COUNTS):
                s = stats(mode, cond, n)
                v = s[metric]
                xs.append(j + (i - 0.5) * w)
                ys.append(v if v is not None else 0)
                if metric == 'mean' and v is not None:
                    lo.append(v - s['min'])
                    hi.append(s['max'] - v)
                else:
                    lo.append(0)
                    hi.append(0)
            err = [lo, hi] if metric == 'mean' else None
            ax.bar(xs, ys, w, label=mode, yerr=err, capsize=3)
        ax.set_xticks(range(len(COUNTS)))
        ax.set_xticklabels([str(n) for n in COUNTS])
        ax.set_xlabel('number of clients')
        ax.set_ylabel(ylabel)
        ax.set_title(cond)
        ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, 'results', fname), dpi=150)
    plt.close(fig)


plot('mean', 'mean download time (s), bars show min to max', 'time.png')
plot('mbps', 'mean throughput per download (Mbit/s)', 'throughput.png')
plot('rate', 'successful downloads (%)', 'success.png')

lines = ['| mode | condition | clients | ok/total | mean s | min s | max s | mean Mbit/s |',
         '|---|---|---|---|---|---|---|---|']
for cond in CONDS:
    for n in COUNTS:
        for mode in MODES:
            s = stats(mode, cond, n)
            f = lambda x: '-' if x is None else '%.1f' % x
            lines.append('| %s | %s | %d | %d/%d | %s | %s | %s | %s |' % (
                mode, cond, n, s['ok'], s['total'], f(s['mean']), f(s['min']), f(s['max']), f(s['mbps'])))
open(os.path.join(ROOT, 'results', 'summary.md'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
