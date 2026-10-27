import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import ROUTES
from selector import Selector

from ryu.lib import hub
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, ether_types

VIP = '10.0.0.100'
VIP_MAC = '00:00:00:00:01:00'
PORT = 8000
SERVERS = {
    'srv1': ('10.0.0.11', '00:00:00:00:00:11'),
    'srv2': ('10.0.0.12', '00:00:00:00:00:12'),
    'srv3': ('10.0.0.13', '00:00:00:00:00:13'),
}
# Probe frames carry a route index and sequence number under the IEEE local
# experimental EtherType; switches never forward them to hosts.
PROBE_TYPE = 0x88b5
PROBE_MAC = '02:00:00:00:00:fe'
PROBE_INTERVAL = 1.0
# Move an existing flow to another route to the same server when that route's
# round trip is at least this much shorter.
SHIFT_RTT = 0.05
# Cookies tag each kind of rule so one kind can be deleted on its own.
COOKIE_L2, COOKIE_FLOW, COOKIE_BLOCK, COOKIE_PROBE = 1, 2, 3, 4


MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static


class Flow:
    """One client TCP connection to the VIP and the route it currently uses."""

    def __init__(self, ip, port, in_port, route):
        self.ip = ip
        self.port = port
        self.in_port = in_port   # s1 port of the client
        self.route = route


class CDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mac_to_port = {}
        self.sel = Selector(self.logger)
        self.dps = {}
        self.logger.info('mode: %s', MODE)
        self.prev = {}
        self.rates = {}
        self.flows = {}       # (client ip, client TCP port) -> Flow
        self.blocked = self.tree_blocked()
        self.seq = 0
        self.sel.on_down = self.flush_server
        hub.spawn(self.monitor)

    def choose_route(self, client_ip):
        if MODE == 'static':
            # fixed assignment on each server's first route:
            # c1->srv1, c2->srv2, c3->srv3, c4->srv1
            name = ['srv1', 'srv2', 'srv3'][(int(client_ip.split('.')[-1]) - 1) % 3]
            return next(route for route in ROUTES if route.server == name)
        return self.sel.pick()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        ofp, ps = dp.ofproto, dp.ofproto_parser
        # wipe stale flows left by any previous controller
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE,
                                  out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                  match=ps.OFPMatch()))
        self.dps[dp.id] = dp
        for dpid, port in self.blocked:
            if dpid == dp.id:
                self.block(dp, port)
        self.add_probe_rules(dp)
        # table-miss: send unknown packets to the controller
        actions = [ps.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, ps.OFPMatch(), actions)
        self.logger.info('switch %s connected', dp.id)

    def add_flow(self, dp, prio, match, actions, idle=0, cookie=0, flags=0):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        inst = [ps.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(ps.OFPFlowMod(datapath=dp, cookie=cookie, priority=prio, match=match,
                                  instructions=inst, idle_timeout=idle, flags=flags))

    def delete_flow(self, dp, prio, match):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE_STRICT,
                                  priority=prio, out_port=ofp.OFPP_ANY,
                                  out_group=ofp.OFPG_ANY, match=match))

    def delete_cookie(self, dp, cookie):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE,
                                  cookie=cookie, cookie_mask=0xffffffffffffffff,
                                  out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                  match=ps.OFPMatch()))

    def packet_out(self, dp, in_port, actions, data):
        ps = dp.ofproto_parser
        dp.send_msg(ps.OFPPacketOut(datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER,
                                    in_port=in_port, actions=actions, data=data))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        if eth.ethertype == PROBE_TYPE:
            return self.probe_reply(dp, pkt)
        if (dp.id, in_port) in self.blocked:
            return
        self.mac_to_port.setdefault(dp.id, {})[eth.src] = in_port

        a = pkt.get_protocol(arp.arp)
        if a and a.opcode == arp.ARP_REQUEST and a.dst_ip == VIP:
            return self.reply_arp(dp, in_port, eth, a)

        ip = pkt.get_protocol(ipv4.ipv4)
        t = pkt.get_protocol(tcp.tcp)
        if ip and t and ip.dst == VIP and t.dst_port == PORT:
            return self.steer(dp, in_port, ip, t, msg.data)

        self.l2_forward(dp, in_port, eth, msg.data)

    def reply_arp(self, dp, in_port, eth, a):
        ps = dp.ofproto_parser
        r = packet.Packet()
        r.add_protocol(ethernet.ethernet(dst=eth.src, src=VIP_MAC,
                                         ethertype=ether_types.ETH_TYPE_ARP))
        r.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=VIP_MAC, src_ip=VIP,
                               dst_mac=a.src_mac, dst_ip=a.src_ip))
        r.serialize()
        self.packet_out(dp, dp.ofproto.OFPP_CONTROLLER,
                        [ps.OFPActionOutput(in_port)], r.data)

    def steer(self, dp, in_port, ip, t, data):
        key = (ip.src, t.src_port)
        flow = self.flows.get(key)
        if flow is None:
            route = self.choose_route(ip.src)
            if route is None:
                self.logger.warning('no healthy route, dropping SYN from %s', ip.src)
                return
            flow = self.flows[key] = Flow(ip.src, t.src_port, in_port, route)
            self.logger.info('flow %s:%d -> VIP steered to %s via %s',
                             ip.src, t.src_port, route.server, route.name)
        self.install(flow)
        self.packet_out(dp, in_port, self.forward_actions(dp, flow.route), data)   # do not lose the first SYN

    def forward_actions(self, dp, route):
        ps = dp.ofproto_parser
        s_ip, s_mac = SERVERS[route.server]
        return [ps.OFPActionSetField(eth_dst=s_mac),
                ps.OFPActionSetField(ipv4_dst=s_ip),
                ps.OFPActionOutput(route.hops[0].to_server)]

    def flow_matches(self, ps, flow, route, first):
        """Match both directions of a flow; on s1 the client still addresses the VIP."""
        s_ip = SERVERS[route.server][0]
        fwd = ps.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=flow.ip,
                          ipv4_dst=VIP if first else s_ip, tcp_src=flow.port, tcp_dst=PORT)
        rev = ps.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=s_ip,
                          ipv4_dst=flow.ip, tcp_src=PORT, tcp_dst=flow.port)
        return fwd, rev

    def install(self, flow):
        """Install the flow's rules on every switch of its route, server end first."""
        route = flow.route
        for i, hop in reversed(list(enumerate(route.hops))):
            dp = self.dps.get(hop.dpid)
            if dp is None:
                continue
            ofp, ps = dp.ofproto, dp.ofproto_parser
            fwd_match, rev_match = self.flow_matches(ps, flow, route, i == 0)
            if i == 0:
                # s1 rewrites VIP <-> server address; report when the flow ends
                fwd_act = self.forward_actions(dp, route)
                rev_act = [ps.OFPActionSetField(eth_src=VIP_MAC),
                           ps.OFPActionSetField(ipv4_src=VIP),
                           ps.OFPActionOutput(flow.in_port)]
                flags = ofp.OFPFF_SEND_FLOW_REM
            else:
                fwd_act = [ps.OFPActionOutput(hop.to_server)]
                rev_act = [ps.OFPActionOutput(hop.to_client)]
                flags = 0
            self.add_flow(dp, 100, fwd_match, fwd_act, idle=30, cookie=COOKIE_FLOW, flags=flags)
            self.add_flow(dp, 100, rev_match, rev_act, idle=30, cookie=COOKIE_FLOW)

    def remove_rules(self, flow, route, keep=()):
        for i, hop in enumerate(route.hops):
            dp = self.dps.get(hop.dpid)
            if dp is None or hop.dpid in keep:
                continue
            for match in self.flow_matches(dp.ofproto_parser, flow, route, i == 0):
                self.delete_flow(dp, 100, match)

    def move(self, flow, route, reason):
        """Shift a live connection to another route to the same server."""
        old = flow.route
        flow.route = route
        self.install(flow)
        self.remove_rules(flow, old, keep={hop.dpid for hop in route.hops})
        self.logger.info('flow %s:%d moved from %s to %s (%s)',
                         flow.ip, flow.port, old.name, route.name, reason)

    def remove_flow(self, flow):
        """Forget a flow; its next packet is steered again and the client reconnects."""
        self.remove_rules(flow, flow.route)
        self.flows.pop((flow.ip, flow.port), None)

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed(self, ev):
        msg = ev.msg
        if msg.cookie == COOKIE_FLOW and msg.reason == msg.datapath.ofproto.OFPRR_IDLE_TIMEOUT:
            self.flows.pop((msg.match['ipv4_src'], msg.match['tcp_src']), None)

    def l2_forward(self, dp, in_port, eth, data):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        out = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [ps.OFPActionOutput(out)]
        if out != ofp.OFPP_FLOOD:
            self.add_flow(dp, 1, ps.OFPMatch(in_port=in_port, eth_dst=eth.dst),
                          actions, idle=60, cookie=COOKIE_L2)
        self.packet_out(dp, in_port, actions, data)

    # --- loop-free tree for flooded and learned (non-CDN) traffic ---

    def tree_blocked(self):
        """Switch-to-switch ports of the routes not carrying ordinary L2 traffic.

        Each server's first working route (else its first route) forms the
        tree; drop rules on the other routes' ports stop flooding loops. CDN
        flow rules and probes have higher priority and still use those ports.
        """
        tree, spare = set(), set()
        for server in SERVERS:
            routes = [route for route in ROUTES if route.server == server]
            active = next((route for route in routes if route.up), routes[0])
            for route in routes:
                (tree if route is active else spare).update(route.trunk_ports())
        return spare - tree

    def block(self, dp, port):
        ps = dp.ofproto_parser
        self.add_flow(dp, 50, ps.OFPMatch(in_port=port), [], cookie=COOKIE_BLOCK)

    def update_tree(self):
        blocked = self.tree_blocked()
        if blocked == self.blocked:
            return
        # close newly spare ports before opening the others, so no loop forms
        for dpid, port in sorted(blocked - self.blocked):
            if dpid in self.dps:
                self.block(self.dps[dpid], port)
        for dpid, port in sorted(self.blocked - blocked):
            if dpid in self.dps:
                dp = self.dps[dpid]
                self.delete_flow(dp, 50, dp.ofproto_parser.OFPMatch(in_port=port))
        self.blocked = blocked
        # hosts may now be reached through different ports: learn them again
        self.mac_to_port.clear()
        for dp in self.dps.values():
            self.delete_cookie(dp, COOKIE_L2)
        self.logger.info('L2 tree changed; blocked ports: %s', ', '.join(
            's%d:%d' % key for key in sorted(blocked)) or 'none')

    # --- path measurement and failover ---

    def add_probe_rules(self, dp):
        """Probes leave s1 along a route, turn round at its last switch and come back."""
        ofp, ps = dp.ofproto, dp.ofproto_parser
        if dp.id == ROUTES[0].hops[0].dpid:
            self.add_flow(dp, 200, ps.OFPMatch(eth_type=PROBE_TYPE),
                          [ps.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)],
                          cookie=COOKIE_PROBE)
            return
        for route in ROUTES:
            for i, hop in enumerate(route.hops[1:], 1):
                if hop.dpid != dp.id:
                    continue
                last = i == len(route.hops) - 1
                out = ofp.OFPP_IN_PORT if last else hop.to_server
                self.add_flow(dp, 200, ps.OFPMatch(in_port=hop.to_client, eth_type=PROBE_TYPE),
                              [ps.OFPActionOutput(out)], cookie=COOKIE_PROBE)
                if not last:
                    self.add_flow(dp, 200, ps.OFPMatch(in_port=hop.to_server, eth_type=PROBE_TYPE),
                                  [ps.OFPActionOutput(hop.to_client)], cookie=COOKIE_PROBE)

    def send_probes(self):
        dp = self.dps.get(ROUTES[0].hops[0].dpid)
        if dp is None:
            return
        ps = dp.ofproto_parser
        self.seq += 1
        for index, route in enumerate(ROUTES):
            frame = packet.Packet()
            frame.add_protocol(ethernet.ethernet(dst=PROBE_MAC, src=PROBE_MAC,
                                                 ethertype=PROBE_TYPE))
            frame.add_protocol(struct.pack('!HI', index, self.seq))
            frame.serialize()
            route.probe_sent(self.seq, time.monotonic())
            self.packet_out(dp, dp.ofproto.OFPP_CONTROLLER,
                            [ps.OFPActionOutput(route.hops[0].to_server)], frame.data)

    def probe_reply(self, dp, pkt):
        payload = pkt.protocols[-1]
        if not isinstance(payload, (bytes, bytearray)) or len(payload) < 6:
            return
        index, seq = struct.unpack_from('!HI', payload)
        if index < len(ROUTES):
            ROUTES[index].probe_returned(seq, time.monotonic())

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, ev):
        msg = ev.msg
        dp, desc = msg.datapath, msg.desc
        ofp = dp.ofproto
        key = (dp.id, desc.port_no)
        down = (msg.reason == ofp.OFPPR_DELETE or desc.state & ofp.OFPPS_LINK_DOWN
                or desc.config & ofp.OFPPC_PORT_DOWN)
        for route in ROUTES:
            if key in route.ports():
                if down:
                    route.ports_down.add(key)
                else:
                    route.ports_down.discard(key)
        self.logger.info('port s%d:%d is %s', dp.id, desc.port_no, 'down' if down else 'up')
        self.evaluate()

    def evaluate(self):
        """Apply route state changes: L2 tree, then (dynamic mode) live flows."""
        now = time.monotonic()
        for route in ROUTES:
            reason = route.check(now)
            if reason:
                self.logger.info('route %s is %s (%s)', route.name,
                                 'UP' if route.up else 'DOWN', reason)
        self.update_tree()
        if MODE != 'dynamic':
            return
        for flow in list(self.flows.values()):
            route = flow.route
            best = self.sel.best_route(route.server)
            if best is None:
                if not route.up:
                    self.logger.info('flow %s:%d has no route to %s; client must reconnect',
                                     flow.ip, flow.port, route.server)
                    self.remove_flow(flow)
            elif not route.up:
                self.move(flow, best, '%s down' % route.name)
            elif best is not route and route.rtt - best.rtt >= SHIFT_RTT:
                self.move(flow, best, 'rtt %.0f ms vs %.0f ms' % (
                    route.rtt * 1000, best.rtt * 1000))

    def monitor(self):
        rounds = 0
        while True:
            self.send_probes()
            for dp in list(self.dps.values()):
                ps = dp.ofproto_parser
                dp.send_msg(ps.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(PROBE_INTERVAL)
            self.evaluate()
            rounds += 1
            if rounds % 5 == 0 and self.dps:
                self.logger.info('routes: %s', ' | '.join(
                    '%s %s rtt %s util %.2f' % (
                        route.name, 'up' if route.up else 'DOWN',
                        '-' if route.rtt is None else '%.1fms' % (route.rtt * 1000),
                        route.util)
                    for route in ROUTES))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats(self, ev):
        dpid = ev.msg.datapath.id
        now = time.time()
        for st in ev.msg.body:
            key = (dpid, st.port_no)
            old = self.prev.get(key)
            self.prev[key] = (now, st.rx_bytes, st.tx_bytes)
            if old is None or now <= old[0]:
                continue
            dt = now - old[0]
            self.rates[key] = max(st.rx_bytes - old[1], st.tx_bytes - old[2]) * 8 / dt
        for route in ROUTES:
            route.util = min(max(self.rates.get((hop.dpid, hop.to_server), 0.0) / hop.bw
                                 for hop in route.hops), 1.0)

    def flush_server(self, name):
        for flow in [f for f in self.flows.values() if f.route.server == name]:
            self.remove_flow(flow)
        self.logger.info('deleted flow rules for %s', name)
