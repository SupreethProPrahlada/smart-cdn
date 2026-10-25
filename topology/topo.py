#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

def build():
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')
    s3 = net.addSwitch('s3', protocols='OpenFlow13')
    s4 = net.addSwitch('s4', protocols='OpenFlow13')

    for i in range(1, 5):
        c = net.addHost(f'c{i}', ip=f'10.0.0.{i}/24', mac=f'00:00:00:00:00:0{i}')
        net.addLink(c, s1, bw=100)

    for i, sw in zip((1, 2, 3), (s2, s3, s4)):
        h = net.addHost(f'srv{i}', ip=f'10.0.0.1{i}/24', mac=f'00:00:00:00:00:1{i}')
        net.addLink(h, sw, bw=100)

    # path quality: this is what the controller chooses between
    net.addLink(s1, s2, delay='5ms',  bw=100)
    net.addLink(s1, s3, delay='20ms', bw=50)
    net.addLink(s1, s4, delay='50ms', bw=10)

    # NAT node in the root namespace so servers can reach the controller's socket
    net.addNAT(connect=s1, ip='10.0.0.254/24')
    return net

if __name__ == '__main__':
    setLogLevel('info')
    net = build()
    net.start()
    CLI(net)
    net.stop()
