# Fixed values (do not change)

VIP:            10.0.0.100
VIP MAC:        00:00:00:00:01:00
Service port:   8000

Clients c1-c4:  10.0.0.1 - 10.0.0.4   (MAC 00:00:00:00:00:01 - :04)
Servers srv1-3: 10.0.0.11 - 10.0.0.13 (MAC 00:00:00:00:00:11 - :13)

Heartbeat target: 10.0.0.254, TCP port 9000 (controller host's Mininet-facing interface)

Server routes (switch ports; controller/paths.py must match topology/topo.py):
  srv1-direct:  s1 port 5  -> s2 port 2;  s2 port 1 -> srv1
  srv1-backup:  s1 port 12 -> s5 port 1;  s5 port 2 -> s2 port 3;  s2 port 1 -> srv1
  srv2:         s1 port 6  -> s3 port 2;  s3 port 1 -> srv2
  srv3:         s1 port 7  -> s4 port 2;  s4 port 1 -> srv3

Path probes: EtherType 0x88b5, sent by the controller from s1 once per second per route
