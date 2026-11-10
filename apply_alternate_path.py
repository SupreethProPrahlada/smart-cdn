#!/usr/bin/env python3
"""Add loop-safe, fast-failover paths for srv1 to the current smart-cdn checkout."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
changes = {}


def replace_once(path, old, new):
    text = changes.get(path)
    if text is None:
        text = (ROOT / path).read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching section in {path}, found {count}. "
            "No files have been changed; use the six-distinct-clients branch."
        )
    changes[path] = text.replace(old, new, 1)


replace_once(
    "topology/topo.py",
    "    s4 = net.addSwitch('s4', protocols='OpenFlow13')\n",
    "    s4 = net.addSwitch('s4', protocols='OpenFlow13')\n"
    "    s5 = net.addSwitch('s5', protocols='OpenFlow13')\n",
)

replace_once(
    "topology/topo.py",
    "        net.addLink(client, s1, bw=100)\n\n    return net\n",
    "        net.addLink(client, s1, bw=100)\n\n"
    "    # Backup for srv1: keep it disabled while s1-s2 is up, avoiding an L2 loop.\n"
    "    net.addLink(s1, s5, delay='10ms', bw=100)\n"
    "    net.addLink(s5, s2, delay='10ms', bw=100)\n\n"
    "    return net\n",
)

replace_once(
    "topology/topo.py",
    "if __name__ == '__main__':\n    setLogLevel('info')\n    net = build()\n    net.start()\n    CLI(net)\n",
    "def disable_alternate_srv1_path(net):\n"
    "    net.configLinkStatus('s1', 's5', 'down')\n"
    "    net.configLinkStatus('s5', 's2', 'down')\n\n\n"
    "if __name__ == '__main__':\n    setLogLevel('info')\n    net = build()\n    net.start()\n"
    "    disable_alternate_srv1_path(net)\n    CLI(net)\n",
)

replace_once(
    "controller/cdn_controller.py",
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n",
    "# Fast-failover groups for srv1's direct and alternate routes.\n"
    "SRV1_FORWARD_GROUP = 101\n"
    "SRV1_RETURN_GROUP = 102\n"
    "SRV1_S1_PRIMARY_PORT = 5\n"
    "SRV1_S1_BACKUP_PORT = 12\n"
    "SRV1_S2_PRIMARY_PORT = 2\n"
    "SRV1_S2_BACKUP_PORT = 3\n\n"
    "MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static\n",
)

replace_once(
    "controller/cdn_controller.py",
    "        self.dps[dp.id] = dp\n        self.logger.info('switch %s connected', dp.id)\n",
    "        self.dps[dp.id] = dp\n"
    "        if dp.id == 1:\n"
    "            self.add_fast_failover_group(dp, SRV1_FORWARD_GROUP,\n"
    "                                         (SRV1_S1_PRIMARY_PORT, SRV1_S1_BACKUP_PORT))\n"
    "        elif dp.id == 2:\n"
    "            self.add_fast_failover_group(dp, SRV1_RETURN_GROUP,\n"
    "                                         (SRV1_S2_PRIMARY_PORT, SRV1_S2_BACKUP_PORT))\n"
    "            s_ip = SERVERS['srv1'][0]\n"
    "            to_server = ps.OFPMatch(eth_type=0x0800, ipv4_dst=s_ip)\n"
    "            to_client = ps.OFPMatch(eth_type=0x0800, ipv4_src=s_ip)\n"
    "            self.add_flow(dp, 200, to_server, [ps.OFPActionOutput(1)])\n"
    "            self.add_flow(dp, 200, to_client, [ps.OFPActionGroup(SRV1_RETURN_GROUP)])\n"
    "        elif dp.id == 5:\n"
    "            s_ip = SERVERS['srv1'][0]\n"
    "            to_server = ps.OFPMatch(eth_type=0x0800, ipv4_dst=s_ip)\n"
    "            to_client = ps.OFPMatch(eth_type=0x0800, ipv4_src=s_ip)\n"
    "            self.add_flow(dp, 200, to_server, [ps.OFPActionOutput(2)])\n"
    "            self.add_flow(dp, 200, to_client, [ps.OFPActionOutput(1)])\n"
    "        self.logger.info('switch %s connected', dp.id)\n",
)

replace_once(
    "controller/cdn_controller.py",
    "    def add_flow(self, dp, prio, match, actions, idle=0):\n",
    "    def add_fast_failover_group(self, dp, group_id, ports):\n"
    "        ofp, ps = dp.ofproto, dp.ofproto_parser\n"
    "        buckets = [\n"
    "            ps.OFPBucket(weight=0, watch_port=port, watch_group=ofp.OFPG_ANY,\n"
    "                         actions=[ps.OFPActionOutput(port)])\n"
    "            for port in ports\n"
    "        ]\n"
    "        dp.send_msg(ps.OFPGroupMod(dp, ofp.OFPGC_ADD, ofp.OFPGT_FF,\n"
    "                                   group_id, buckets))\n\n"
    "    def add_flow(self, dp, prio, match, actions, idle=0):\n",
)

replace_once(
    "controller/cdn_controller.py",
    "        fwd_act = [ps.OFPActionSetField(eth_dst=s_mac),\n"
    "                   ps.OFPActionSetField(ipv4_dst=s_ip),\n"
    "                   ps.OFPActionOutput(out_s)]\n",
    "        fwd_act = [ps.OFPActionSetField(eth_dst=s_mac),\n"
    "                   ps.OFPActionSetField(ipv4_dst=s_ip)]\n"
    "        if name == 'srv1':\n"
    "            fwd_act.append(ps.OFPActionGroup(SRV1_FORWARD_GROUP))\n"
    "        else:\n"
    "            fwd_act.append(ps.OFPActionOutput(out_s))\n",
)

replace_once(
    "tests/run_scenarios.py",
    "from topo import build\n",
    "from topo import build, disable_alternate_srv1_path\n",
)

replace_once(
    "tests/run_scenarios.py",
    "parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\",\n"
    "                                              \"congestion\", \"all\", \"experiments\", \"report\"))\n",
    "parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\",\n"
    "                                              \"path-failover\", \"congestion\", \"all\",\n"
    "                                              \"experiments\", \"report\"))\n",
)

replace_once(
    "tests/run_scenarios.py",
    "        self.net.start()\n        for name, host in self.servers.items():\n",
    "        self.net.start()\n"
    "        disable_alternate_srv1_path(self.net)\n"
    "        for name, host in self.servers.items():\n",
)

replace_once(
    "tests/run_scenarios.py",
    "    def congestion(self):\n",
    "    def path_failover(self):\n"
    "        print(\"Downloading video2.bin from c1; srv1 should use its direct path first.\")\n"
    "        process = self.client(self.clients[0], \"video2.bin\")\n"
    "        time.sleep(5)\n"
    "        print(\"Taking down direct s1-s2 link, then enabling backup s1-s5-s2.\", flush=True)\n"
    "        self.net.configLinkStatus(\"s1\", \"s2\", \"down\")\n"
    "        time.sleep(1)\n"
    "        self.net.configLinkStatus(\"s1\", \"s5\", \"up\")\n"
    "        self.net.configLinkStatus(\"s5\", \"s2\", \"up\")\n"
    "        try:\n"
    "            output = process.communicate(timeout=180)[0].decode(errors=\"replace\")\n"
    "        except Exception:\n"
    "            if process.poll() is None:\n"
    "                process.kill()\n"
    "                process.wait()\n"
    "            raise\n"
    "        finally:\n"
    "            self.net.configLinkStatus(\"s1\", \"s5\", \"down\")\n"
    "            self.net.configLinkStatus(\"s5\", \"s2\", \"down\")\n"
    "            self.net.configLinkStatus(\"s1\", \"s2\", \"up\")\n"
    "        print(output.strip())\n"
    "        result = parse_client_output(output)\n"
    "        if process.returncode or not result or result[3] != \"OK\":\n"
    "            raise RuntimeError(\"download did not recover over the alternate srv1 path\")\n"
    "        print(\"Primary path restored; checking a fresh download.\")\n"
    "        self.download(self.clients[0], \"small.bin\")\n"
    "        for switch in (\"s1\", \"s2\"):\n"
    "            groups = self.net.get(switch).cmd(\n"
    "                f\"ovs-ofctl -O OpenFlow13 dump-groups {switch}\")\n"
    "            print(f\"Failover groups on {switch}:\\n{groups.strip()}\")\n\n"
    "    def congestion(self):\n",
)

replace_once(
    "tests/run_scenarios.py",
    "        elif args.scenario == \"failover\":\n"
    "            runner.failover()\n"
    "        elif args.scenario == \"congestion\":\n",
    "        elif args.scenario == \"failover\":\n"
    "            runner.failover()\n"
    "        elif args.scenario == \"path-failover\":\n"
    "            runner.path_failover()\n"
    "        elif args.scenario == \"congestion\":\n",
)

replace_once(
    "README.md",
    "replace `all` with `smoke`, `six-client-smoke`, `failover`, or `congestion`. The six-client\n",
    "replace `all` with `smoke`, `six-client-smoke`, `failover`, `path-failover`, or `congestion`. The six-client\n",
)

replace_once(
    "README.md",
    "The six-client\nsmoke starts one download on each of c1-c6 at the same time. The smoke scenario\n",
    "The six-client\nsmoke starts one download on each of c1-c6 at the same time. `path-failover` interrupts\n"
    "the direct srv1 link, enables a loop-safe backup route, verifies the download, then restores\n"
    "the direct link. The smoke scenario\n",
)

replace_once(
    "docs/architecture.md",
    "Ryu controls the four OpenFlow 1.3 switches.",
    "Ryu controls five OpenFlow 1.3 switches.",
)

replace_once(
    "docs/architecture.md",
    "Each server has one path, so the controller selects a server rather than an alternate path. Delay is configured rather than measured dynamically, and link failures are not detected independently of server heartbeats.\n",
    "srv1 has a direct s1-s2 path and an alternate s1-s5-s2 path. OpenFlow fast-failover groups watch the direct-link ports and use the backup buckets when the direct link is down. The backup links stay disabled during normal operation to prevent a layer-2 loop in the learning-switch topology. The path-failover scenario interrupts the direct link during a download, enables the backup links, verifies the checksum, then restores the primary path.\n",
)

replace_once(
    "docs/architecture.md",
    "provides smoke, failover, congestion, and experiment scenarios.",
    "provides smoke, server-failover, path-failover, congestion, and experiment scenarios.",
)

for relative, content in changes.items():
    file_path = ROOT / relative
    backup = file_path.with_suffix(file_path.suffix + ".before-alternate-path")
    if not backup.exists():
        shutil.copy2(file_path, backup)
    file_path.write_text(content, encoding="utf-8")

print("Added a loop-safe backup route for srv1 and a path-failover scenario.")
print("The backup links are disabled except during the failure demo.")
print("Source backups are saved beside modified files with suffix .before-alternate-path.")
