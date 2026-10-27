#!/usr/bin/env python3
import os
from pathlib import Path
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

# Mininet host shells inherit this environment. Put the uv-managed interpreter
# first so the documented `python3` commands in the Mininet CLI use this env.
os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')

# srv1's direct s1-s2 link; tests/run_scenarios.py degrades and restores it.
DIRECT_LINK = dict(delay='5ms', bw=100)
DEGRADED_LINK = dict(delay='100ms', bw=100)

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
    net.addLink(s1, s2, **DIRECT_LINK)
    net.addLink(s1, s3, delay='20ms', bw=50)
    net.addLink(s1, s4, delay='50ms', bw=10)

    # Give the controller host a Mininet-facing address for server heartbeats.
    heartbeat_host = net.addHost('hb', ip='10.0.0.254/24',
                                 mac='00:00:00:00:00:fe', inNamespace=False)
    net.addLink(heartbeat_host, s1)

    # Keep these links after the server-path links so s1 server ports stay unchanged.
    # Six separate experiment clients; c7 is reserved for congestion traffic.
    for i in range(5, 8):
        client = net.addHost(f'c{i}', ip=f'10.0.0.{i}/24',
                             mac=f'00:00:00:00:00:0{i}')
        net.addLink(client, s1, bw=100)

    # Backup route to srv1: s1 port 12 - s5 - s2 port 3 (15 ms instead of 5 ms).
    # Port numbers match controller/paths.py.
    s5 = net.addSwitch('s5', protocols='OpenFlow13')
    net.addLink(s1, s5, port1=12, port2=1, delay='10ms', bw=100)
    net.addLink(s5, s2, port1=2, port2=3, delay='5ms', bw=100)

    return net

if __name__ == '__main__':
    setLogLevel('info')
    net = build()
    net.start()
    CLI(net)
    net.stop()
