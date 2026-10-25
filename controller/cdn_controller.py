import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selector import Selector
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, ether_types

VIP, VIP_MAC, PORT = '10.0.0.100', '00:00:00:00:01:00', 8000
SERVERS = {'srv1': ('10.0.0.11', '00:00:00:00:00:11'),
           'srv2': ('10.0.0.12', '00:00:00:00:00:12'),
           'srv3': ('10.0.0.13', '00:00:00:00:00:13')}


class CDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mac_to_port = {}
        self.sel = Selector(self.logger)

    def choose_server(self):
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
        name = self.choose_server()
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
