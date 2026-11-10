from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: python3 apply_six_client_alt_path.py /path/to/smart-cdn")

root = Path(sys.argv[1]).expanduser().resolve()
topology_path = root / "topology" / "topo.py"
experiments_path = root / "tests" / "run_experiments.py"

topology = topology_path.read_text(encoding="utf-8")
experiments = experiments_path.read_text(encoding="utf-8")

if "# alternate route to srv1" not in topology or "x1 = net.addHost('x1'" not in topology:
    raise SystemExit("topo.py does not look like the alt-path version; no files were changed")


def replace_once(content, old, new, label):
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match for {label}, found {count}; no files were changed")
    return content.replace(old, new, 1)


topology = replace_once(
    topology,
    "    net.addLink(x1, s2, bw=100)\n    return net",
    "    net.addLink(x1, s2, bw=100)\n\n"
    "    # Six distinct experiment clients; added last to preserve the controller's port numbers.\n"
    "    for i in range(5, 8):\n"
    "        c = net.addHost(f'c{i}', ip=f'10.0.0.{i}/24', mac=f'00:00:00:00:00:0{i}')\n"
    "        net.addLink(c, s1, bw=100)\n"
    "    return net",
    "alt-path topology client insertion point",
)

experiments = replace_once(
    experiments,
    "RESULT = re.compile(r'got (\\d+) bytes in ([0-9.]+)s, retries=(\\d+)')\n",
    "RESULT = re.compile(r'got (\\d+) bytes in ([0-9.]+)s, retries=(\\d+)')\n"
    "CLIENT_HOSTS = ('c1', 'c2', 'c3', 'c4', 'c5', 'c6')\n",
    "experiment client list",
)
experiments = replace_once(
    experiments,
    "cl = [net.get(n) for n in ('c1', 'c2', 'c3')]\nc4 = net.get('c4')",
    "cl = [net.get(n) for n in CLIENT_HOSTS]\nload_sink = net.get('c7')",
    "experiment host setup",
)
experiments = replace_once(
    experiments,
    "def run_clients(n, tag):\n    jobs = []",
    "def run_clients(n, tag):\n"
    "    if n < 1 or n > len(cl):\n"
    "        raise ValueError(f'client count must be between 1 and {len(cl)}, got {n}')\n"
    "    jobs = []",
    "experiment client-count guard",
)
experiments = replace_once(
    experiments,
    "h = cl[i % len(cl)]",
    "h = cl[i]",
    "distinct experiment clients",
)
experiments = replace_once(
    experiments,
    "procs['iperf_s'] = c4.popen(['iperf', '-s'], stdout=DEVNULL, stderr=DEVNULL)",
    "procs['iperf_s'] = load_sink.popen(['iperf', '-s'], stdout=DEVNULL, stderr=DEVNULL)",
    "dedicated congestion sink",
)
experiments = replace_once(
    experiments,
    "procs['iperf_c'] = srv['srv1'].popen(['iperf', '-c', '10.0.0.4', '-t', '3600', '-P', '4'],",
    "procs['iperf_c'] = srv['srv1'].popen(['iperf', '-c', '10.0.0.7', '-t', '3600', '-P', '4'],",
    "congestion sink address",
)

topology_path.write_text(topology, encoding="utf-8")
experiments_path.write_text(experiments, encoding="utf-8")
print("Updated topology and experiment runner for six distinct clients; existing alt-path controller changes were left untouched.")
