#!/usr/bin/env python3
"""Enable load-aware path selection for srv1 on the alternate-path branch."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
changes = {}


def replace_once(path, old, new):
    text = changes.get(path)
    if text is None:
        text = (ROOT / path).read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"Expected one matching section in {path}; no files changed. "
                         "Check that the earlier alternate-path update is applied.")
    changes[path] = text.replace(old, new, 1)


replace_once(
    "topology/topo.py",
    "def disable_alternate_srv1_path(net):\n"
    "    net.configLinkStatus('s1', 's5', 'down')\n"
    "    net.configLinkStatus('s5', 's2', 'down')\n",
    "def configure_alternate_srv1_path(net):\n"
    "    # Keep both routes up. Suppress flooding on the alternate links only,\n"
    "    # so direct-path ARP and heartbeat traffic still reach s1/s2. Explicit\n"
    "    # OpenFlow group outputs can still use the alternate ports.\n"
    "    net.get('s1').cmd('ovs-ofctl -O OpenFlow13 mod-port s1 s1-eth12 no-flood')\n"
    "    net.get('s2').cmd('ovs-ofctl -O OpenFlow13 mod-port s2 s2-eth3 no-flood')\n",
)
replace_once("topology/topo.py", "    disable_alternate_srv1_path(net)\n",
             "    configure_alternate_srv1_path(net)\n")

replace_once(
    "controller/cdn_controller.py",
    "# Fast-failover groups for srv1's direct and alternate routes.\n"
    "SRV1_FORWARD_GROUP = 101\n"
    "SRV1_RETURN_GROUP = 102\n"
    "SRV1_S1_PRIMARY_PORT = 5\n"
    "SRV1_S1_BACKUP_PORT = 12\n"
    "SRV1_S2_PRIMARY_PORT = 2\n"
    "SRV1_S2_BACKUP_PORT = 3\n",
    "# Direct-first and alternate-first fast-failover groups for srv1.\n"
    "SRV1_DIRECT_FORWARD_GROUP = 101\n"
    "SRV1_DIRECT_RETURN_GROUP = 102\n"
    "SRV1_ALT_FORWARD_GROUP = 103\n"
    "SRV1_ALT_RETURN_GROUP = 104\n"
    "SRV1_S1_DIRECT_PORT = 5\n"
    "SRV1_S1_ALT_PORT = 12\n"
    "SRV1_S2_DIRECT_PORT = 2\n"
    "SRV1_S2_ALT_PORT = 3\n"
    "SRV1_DIRECT_DELAY_MS = 5.0\n"
    "SRV1_ALT_DELAY_MS = 20.0\n"
    "SRV1_MAX_DELAY_MS = 50.0\n"
    "SRV1_LINK_CAPACITY = 100e6\n",
)
replace_once(
    "controller/cdn_controller.py",
    "        self.prev = {}\n        self.sel.on_down = self.flush_server\n",
    "        self.prev = {}\n"
    "        self.srv1_path_util = {'direct': 0.0, 'alternate': 0.0}\n"
    "        self.sel.on_down = self.flush_server\n",
)
replace_once(
    "controller/cdn_controller.py",
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
    "            self.add_flow(dp, 200, to_client, [ps.OFPActionGroup(SRV1_RETURN_GROUP)])\n",
    "        if dp.id == 1:\n"
    "            self.add_fast_failover_group(dp, SRV1_DIRECT_FORWARD_GROUP,\n"
    "                                         (SRV1_S1_DIRECT_PORT, SRV1_S1_ALT_PORT))\n"
    "            self.add_fast_failover_group(dp, SRV1_ALT_FORWARD_GROUP,\n"
    "                                         (SRV1_S1_ALT_PORT, SRV1_S1_DIRECT_PORT))\n"
    "        elif dp.id == 2:\n"
    "            self.add_fast_failover_group(dp, SRV1_DIRECT_RETURN_GROUP,\n"
    "                                         (SRV1_S2_DIRECT_PORT, SRV1_S2_ALT_PORT))\n"
    "            self.add_fast_failover_group(dp, SRV1_ALT_RETURN_GROUP,\n"
    "                                         (SRV1_S2_ALT_PORT, SRV1_S2_DIRECT_PORT))\n"
    "            s_ip = SERVERS['srv1'][0]\n"
    "            to_server = ps.OFPMatch(eth_type=0x0800, ipv4_dst=s_ip)\n"
    "            to_client = ps.OFPMatch(eth_type=0x0800, ipv4_src=s_ip)\n"
    "            self.add_flow(dp, 200, to_server, [ps.OFPActionOutput(1)])\n"
    "            self.add_flow(dp, 200, to_client, [ps.OFPActionGroup(SRV1_DIRECT_RETURN_GROUP)])\n",
)
replace_once(
    "controller/cdn_controller.py",
    "    def add_flow(self, dp, prio, match, actions, idle=0):\n",
    "    def choose_srv1_path(self):\n"
    "        direct_cost = (0.4 * SRV1_DIRECT_DELAY_MS / SRV1_MAX_DELAY_MS\n"
    "                       + 0.4 * self.srv1_path_util['direct'])\n"
    "        alt_cost = (0.4 * SRV1_ALT_DELAY_MS / SRV1_MAX_DELAY_MS\n"
    "                    + 0.4 * self.srv1_path_util['alternate'])\n"
    "        if alt_cost < direct_cost:\n"
    "            return ('alternate', SRV1_ALT_FORWARD_GROUP, SRV1_ALT_RETURN_GROUP)\n"
    "        return ('direct', SRV1_DIRECT_FORWARD_GROUP, SRV1_DIRECT_RETURN_GROUP)\n\n"
    "    def add_flow(self, dp, prio, match, actions, idle=0):\n",
)
replace_once(
    "controller/cdn_controller.py",
    "        fwd_act = [ps.OFPActionSetField(eth_dst=s_mac),\n"
    "                   ps.OFPActionSetField(ipv4_dst=s_ip)]\n"
    "        if name == 'srv1':\n"
    "            fwd_act.append(ps.OFPActionGroup(SRV1_FORWARD_GROUP))\n"
    "        else:\n"
    "            fwd_act.append(ps.OFPActionOutput(out_s))\n",
    "        path_name = None\n"
    "        return_group = None\n"
    "        fwd_act = [ps.OFPActionSetField(eth_dst=s_mac),\n"
    "                   ps.OFPActionSetField(ipv4_dst=s_ip)]\n"
    "        if name == 'srv1':\n"
    "            path_name, forward_group, return_group = self.choose_srv1_path()\n"
    "            fwd_act.append(ps.OFPActionGroup(forward_group))\n"
    "        else:\n"
    "            fwd_act.append(ps.OFPActionOutput(out_s))\n",
)
replace_once(
    "controller/cdn_controller.py",
    "        self.add_flow(dp, 100, rev_match, rev_act, idle=30)\n\n"
    "        self.packet_out(dp, in_port, fwd_act, data)   # do not lose the first SYN\n"
    "        self.logger.info('flow %s:%d -> VIP steered to %s', ip.src, t.src_port, name)\n",
    "        self.add_flow(dp, 100, rev_match, rev_act, idle=30)\n"
    "        if name == 'srv1':\n"
    "            dp2 = self.dps.get(2)\n"
    "            if dp2 is not None:\n"
    "                ps2 = dp2.ofproto_parser\n"
    "                return_match = ps2.OFPMatch(\n"
    "                    eth_type=0x0800, ip_proto=6, ipv4_src=s_ip, ipv4_dst=ip.src,\n"
    "                    tcp_src=PORT, tcp_dst=t.src_port)\n"
    "                self.add_flow(dp2, 300, return_match,\n"
    "                              [ps2.OFPActionGroup(return_group)], idle=30)\n\n"
    "        self.packet_out(dp, in_port, fwd_act, data)   # do not lose the first SYN\n"
    "        if path_name:\n"
    "            self.logger.info('flow %s:%d -> %s via %s path '\n"
    "                             '(direct util %.2f, alternate util %.2f)',\n"
    "                             ip.src, t.src_port, name, path_name,\n"
    "                             self.srv1_path_util['direct'],\n"
    "                             self.srv1_path_util['alternate'])\n"
    "        else:\n"
    "            self.logger.info('flow %s:%d -> VIP steered to %s', ip.src, t.src_port, name)\n",
)
replace_once(
    "controller/cdn_controller.py",
    "        for st in ev.msg.body:\n"
    "            if st.port_no not in PATHS:\n"
    "                continue\n"
    "            name, cap = PATHS[st.port_no]\n",
    "        for st in ev.msg.body:\n"
    "            if st.port_no == SRV1_S1_ALT_PORT:\n"
    "                name, cap, path_key = 'srv1', SRV1_LINK_CAPACITY, 'alternate'\n"
    "            elif st.port_no in PATHS:\n"
    "                name, cap = PATHS[st.port_no]\n"
    "                path_key = 'direct' if st.port_no == SRV1_S1_DIRECT_PORT else None\n"
    "            else:\n"
    "                continue\n",
)
replace_once(
    "controller/cdn_controller.py",
    "            self.sel.util[name] = util\n"
    "            if util >= 0.1:\n",
    "            if path_key is not None:\n"
    "                self.srv1_path_util[path_key] = util\n"
    "            if name == 'srv1':\n"
    "                self.sel.util[name] = min(self.srv1_path_util.values())\n"
    "            else:\n"
    "                self.sel.util[name] = util\n"
    "            if util >= 0.1:\n",
)

replace_once(
    "tests/run_scenarios.py",
    "from topo import build, disable_alternate_srv1_path\n",
    "from topo import build, configure_alternate_srv1_path\n",
)
replace_once(
    "tests/run_scenarios.py",
    "parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\",\n"
    "                                              \"path-failover\", \"congestion\", \"all\",\n"
    "                                              \"experiments\", \"report\"))\n",
    "parser.add_argument(\"scenario\", choices=(\"smoke\", \"six-client-smoke\", \"failover\",\n"
    "                                              \"path-failover\", \"path-congestion\",\n"
    "                                              \"congestion\", \"all\", \"experiments\",\n"
    "                                              \"report\"))\n",
)
replace_once("tests/run_scenarios.py", "        disable_alternate_srv1_path(self.net)\n",
             "        configure_alternate_srv1_path(self.net)\n")
replace_once(
    "tests/run_scenarios.py",
    "        print(\"Taking down direct s1-s2 link, then enabling backup s1-s5-s2.\", flush=True)\n"
    "        self.net.configLinkStatus(\"s1\", \"s2\", \"down\")\n"
    "        time.sleep(1)\n"
    "        self.net.configLinkStatus(\"s1\", \"s5\", \"up\")\n"
    "        self.net.configLinkStatus(\"s5\", \"s2\", \"up\")\n",
    "        print(\"Taking down direct s1-s2 link; the alternate route stays up.\", flush=True)\n"
    "        self.net.configLinkStatus(\"s1\", \"s2\", \"down\")\n",
)
replace_once(
    "tests/run_scenarios.py",
    "        finally:\n"
    "            self.net.configLinkStatus(\"s1\", \"s5\", \"down\")\n"
    "            self.net.configLinkStatus(\"s5\", \"s2\", \"down\")\n"
    "            self.net.configLinkStatus(\"s1\", \"s2\", \"up\")\n",
    "        finally:\n"
    "            self.net.configLinkStatus(\"s1\", \"s2\", \"up\")\n",
)
replace_once(
    "tests/run_scenarios.py",
    "    def congestion(self):\n",
    "    def path_congestion(self):\n"
    "        print(\"Starting iperf load on srv1's direct route to c7.\")\n"
    "        self.procs[\"path_iperf_server\"] = self.load_sink.popen(\n"
    "            [\"iperf\", \"-s\"], stdout=DEVNULL, stderr=DEVNULL)\n"
    "        time.sleep(1)\n"
    "        self.procs[\"path_iperf_client\"] = self.servers[\"srv1\"].popen(\n"
    "            [\"iperf\", \"-c\", \"10.0.0.7\", \"-t\", \"3600\", \"-P\", \"4\"],\n"
    "            stdout=DEVNULL, stderr=DEVNULL)\n"
    "        time.sleep(8)  # allow the controller to sample the direct-link load\n"
    "        try:\n"
    "            print(\"Downloading with c1 pinned to srv1; run the controller in static mode.\")\n"
    "            self.download(self.clients[0], \"video1.bin\")\n"
    "            flows = self.net.get(\"s1\").cmd(\"ovs-ofctl -O OpenFlow13 dump-flows s1\")\n"
    "            rules = [line.strip() for line in flows.splitlines()\n"
    "                     if \"ipv4_src=10.0.0.1\" in line and \"priority=100\" in line]\n"
    "            print(\"c1 flow rules on s1:\\n\" + \"\\n\".join(rules))\n"
    "            if not any(\"group:103\" in line for line in rules):\n"
    "                raise RuntimeError(\"the controller did not select the alternate path under load\")\n"
    "        finally:\n"
    "            self.stop_process(\"path_iperf_client\")\n"
    "            self.stop_process(\"path_iperf_server\")\n"
    "        time.sleep(4)  # allow port statistics to observe the cleared load\n"
    "        print(\"Direct-path load stopped; checking a fresh download.\")\n"
    "        self.download(self.clients[0], \"small.bin\")\n\n"
    "    def congestion(self):\n",
)
replace_once(
    "tests/run_scenarios.py",
    "        elif args.scenario == \"path-failover\":\n"
    "            runner.path_failover()\n"
    "        elif args.scenario == \"congestion\":\n",
    "        elif args.scenario == \"path-failover\":\n"
    "            runner.path_failover()\n"
    "        elif args.scenario == \"path-congestion\":\n"
    "            runner.path_congestion()\n"
    "        elif args.scenario == \"congestion\":\n",
)

replace_once(
    "README.md",
    "replace `all` with `smoke`, `six-client-smoke`, `failover`, `path-failover`, or `congestion`.",
    "replace `all` with `smoke`, `six-client-smoke`, `failover`, `path-failover`, `path-congestion`, or `congestion`.",
)
replace_once(
    "README.md",
    "`path-failover` interrupts\nthe direct srv1 link, enables a loop-safe backup route, verifies the download, then restores\nthe direct link.",
    "`path-failover` tests a direct-link failure. `path-congestion` leaves both routes up,\n"
    "adds iperf load to the direct srv1 path, then checks that a new c1 flow uses the alternate\n"
    "route. Run `path-congestion` with the controller in static mode so c1 stays assigned to srv1.",
)
replace_once(
    "docs/architecture.md",
    "OpenFlow fast-failover groups watch the direct-link ports and use the backup buckets when the direct link is down. The backup links stay disabled during normal operation to prevent a layer-2 loop in the learning-switch topology. The path-failover scenario interrupts the direct link during a download, enables the backup links, verifies the checksum, then restores the primary path.\n",
    "OpenFlow fast-failover groups watch the direct-link ports and use the alternate buckets when the direct link is down. For congestion-aware routing, the controller samples s1 port statistics on both routes and selects a direct-first or alternate-first group for each new TCP flow. Both routes stay up; flooding is suppressed on the direct parallel link to avoid a layer-2 loop. The path-congestion scenario creates iperf load on the direct srv1 route and verifies that a new c1 flow uses the alternate route. The separate path-failover scenario tests link-down recovery.\n",
)

for relative, content in changes.items():
    target = ROOT / relative
    backup = target.with_suffix(target.suffix + ".before-congestion-path")
    if not backup.exists():
        shutil.copy2(target, backup)
    target.write_text(content, encoding="utf-8")

print("Both srv1 routes now remain up; new flows select routes using measured utilization.")
print("The new path-congestion scenario tests route selection without cutting a link.")
print("Backups use the suffix .before-congestion-path.")
