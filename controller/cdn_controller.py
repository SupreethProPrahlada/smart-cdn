import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
# s1 port -> (server, link capacity in bit/s)
PATHS = {
    5: ('srv1', 100e6),
    6: ('srv2', 50e6),
    7: ('srv3', 10e6),
}
SERVERS = {
    'srv1': ('10.0.0.11', '00:00:00:00:00:11'),
    'srv2': ('10.0.0.12', '00:00:00:00:00:12'),
    'srv3': ('10.0.0.13', '00:00:00:00:00:13'),
}


MODE = os.environ.get('CDN_MODE', 'dynamic')   # dynamic or static


class CDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mac_to_port = {}
        self.sel = Selector(self.logger)
        self.dps = {}
        self.logger.info('mode: %s', MODE)
        self.prev = {}
        self.sel.on_down = self.flush_server
        hub.spawn(self.monitor)

    def choose_server(self, client_ip):
        if MODE == 'static':
            # fixed assignment: c1->srv1, c2->srv2, c3->srv3, c4->srv1
            return ['srv1', 'srv2', 'srv3'][(int(client_ip.split('.')[-1]) - 1) % 3]
        return self.sel.pick()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        ofp, ps = dp.ofproto, dp.ofproto_parser
        # wipe stale flows left by any previous controller
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE,
                                  out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                  match=ps.OFPMatch()))
        # table-miss: send unknown packets to the controller
        actions = [ps.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, ps.OFPMatch(), actions)
        self.dps[dp.id] = dp
        self.logger.info('switch %s connected', dp.id)

    def add_flow(self, dp, prio, match, actions, idle=0):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        inst = [ps.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(ps.OFPFlowMod(datapath=dp, priority=prio, match=match,
                                  instructions=inst, idle_timeout=idle))

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
        self.mac_to_port.setdefault(dp.id, {})[eth.src] = in_port

        a = pkt.get_protocol(arp.arp)
        if a and a.opcode == arp.ARP_REQUEST and a.dst_ip == VIP:
            return self.reply_arp(dp, in_port, eth, a)

        ip = pkt.get_protocol(ipv4.ipv4)
        t = pkt.get_protocol(tcp.tcp)
        if ip and t and ip.dst == VIP and t.dst_port == PORT:
            return self.steer(dp, in_port, eth, ip, t, msg.data)

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

    def steer(self, dp, in_port, eth, ip, t, data):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        name = self.choose_server(ip.src)
        if name is None:
            self.logger.warning('no healthy server, dropping SYN from %s', ip.src)
            return
        s_ip, s_mac = SERVERS[name]
        out_s = self.mac_to_port[dp.id].get(s_mac, ofp.OFPP_FLOOD)

        fwd_match = ps.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=ip.src,
                                ipv4_dst=VIP, tcp_src=t.src_port, tcp_dst=PORT)
        fwd_act = [ps.OFPActionSetField(eth_dst=s_mac),
                   ps.OFPActionSetField(ipv4_dst=s_ip),
                   ps.OFPActionOutput(out_s)]
        self.add_flow(dp, 100, fwd_match, fwd_act, idle=30)

        rev_match = ps.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=s_ip,
                                ipv4_dst=ip.src, tcp_src=PORT, tcp_dst=t.src_port)
        rev_act = [ps.OFPActionSetField(eth_src=VIP_MAC),
                   ps.OFPActionSetField(ipv4_src=VIP),
                   ps.OFPActionOutput(in_port)]
        self.add_flow(dp, 100, rev_match, rev_act, idle=30)

        self.packet_out(dp, in_port, fwd_act, data)   # do not lose the first SYN
        self.logger.info('flow %s:%d -> VIP steered to %s', ip.src, t.src_port, name)

    def l2_forward(self, dp, in_port, eth, data):
        ofp, ps = dp.ofproto, dp.ofproto_parser
        out = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [ps.OFPActionOutput(out)]
        if out != ofp.OFPP_FLOOD:
            self.add_flow(dp, 1, ps.OFPMatch(in_port=in_port, eth_dst=eth.dst),
                          actions, idle=60)
        self.packet_out(dp, in_port, actions, data)

    def monitor(self):
        while True:
            dp = self.dps.get(1)
            if dp is not None:
                ps = dp.ofproto_parser
                dp.send_msg(ps.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(2)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats(self, ev):
        dp = ev.msg.datapath
        if dp.id != 1:
            return
        now = time.time()
        for st in ev.msg.body:
            if st.port_no not in PATHS:
                continue
            name, cap = PATHS[st.port_no]
            old = self.prev.get(st.port_no)
            self.prev[st.port_no] = (now, st.rx_bytes, st.tx_bytes)
            if old is None or now <= old[0]:
                continue
            dt = now - old[0]
            rate = max(st.rx_bytes - old[1], st.tx_bytes - old[2]) * 8 / dt
            util = min(rate / cap, 1.0)
            self.sel.util[name] = util
            if util >= 0.1:
                self.logger.info('path %s utilisation %.2f', name, util)

    def flush_server(self, name):
        dp = self.dps.get(1)
        if dp is None:
            return
        ofp, ps = dp.ofproto, dp.ofproto_parser
        s_ip = SERVERS[name][0]
        port = [p for p, v in PATHS.items() if v[0] == name][0]
        # forward rules (and L2 rules) that send traffic toward this server
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE,
                                  out_port=port, out_group=ofp.OFPG_ANY,
                                  match=ps.OFPMatch()))
        # reverse rules that carry this server's replies
        dp.send_msg(ps.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE,
                                  out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                  match=ps.OFPMatch(eth_type=0x0800, ip_proto=6,
                                                    ipv4_src=s_ip, tcp_src=PORT)))
        self.logger.info('deleted flow rules for %s', name)
