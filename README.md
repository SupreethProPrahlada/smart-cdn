# Smart Content Delivery System (TCP, SDN)

Clients request content from a virtual IP. A Ryu controller (OpenFlow 1.3) picks a content server
for each new flow from server heartbeats and link measurements, rewrites the packets, and reroutes
traffic when a server fails. Everything runs in Mininet with Open vSwitch.

See docs/architecture.md for the design, the selection rule and the failure behaviour.

## Layout

    topology/    Mininet script (4 clients, 3 servers, 4 switches, links with different delay and bandwidth)
    controller/  Ryu app (cdn_controller.py) and server selector (selector.py)
    app/         TCP content server (server.py) and client (client.py), raw sockets
    config/      fixed addresses and ports (settings.md)
    tests/       Mininet command scripts, experiment runner, graph script, helper scripts
    results/     raw data, summary table and graphs
    docs/        architecture document

## Install (Ubuntu in a VM, tested with Python 3.14 as system Python)

    sudo apt update
    sudo apt install -y mininet openvswitch-switch iperf tcpdump git python3-pip python3-venv curl python3-matplotlib
    sudo systemctl start openvswitch-switch

Ryu does not run on new Python versions, so it gets its own Python 3.9 environment:

    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
    uv python install 3.9
    uv venv --python 3.9 ~/ryu-env
    source ~/ryu-env/bin/activate
    uv pip install "setuptools<58" wheel pbr "eventlet==0.30.2"
    uv pip install --no-build-isolation "git+https://github.com/faucetsdn/ryu.git"
    ryu-manager --version

The last command should print 4.34.

## Run

    git clone <repo-url> smart-cdn
    cd smart-cdn
    tests/make_content.sh

Use three terminals, all in the repo folder. Order matters: run the cleanup first, because it
kills any running controller.

Terminal 3, once, before anything else:

    sudo mn -c

Terminal 1, controller (dynamic mode, or `static` for the baseline):

    tests/run_controller.sh dynamic

Terminal 2, topology:

    tests/run_topology.sh

Wait until terminal 1 prints "switch 1 connected" to "switch 4 connected".

At the mininet> prompt, start the three servers and wait about 15 seconds:

    srv1 python3 app/server.py --id srv1 &
    srv2 python3 app/server.py --id srv2 &
    srv3 python3 app/server.py --id srv3 &
    pingall

Terminal 1 prints "server srv1 is UP" and the same for srv2 and srv3.
Do not run `sudo mn -c` again while the controller is running.

Note: Mininet replaces a host name inside a command with its IP, so servers report their IP as id.
The selector translates 10.0.0.11 to 10.0.0.13 back to srv1 to srv3.

## Demos and tests (at the mininet> prompt, with the controller in dynamic mode)

    source tests/failover_check.cmd

Starts the servers, downloads 100 MB through the virtual IP, kills srv1's server after 5 seconds
and prints the client result. Expect "checksum=OK" and retries of at least 1. Terminal 1 shows the
download steered to srv1, then "server srv1 is DOWN", "deleted flow rules for srv1" and the
reconnect steered to srv2. Compare tests/expected/ for the reference output.

    source tests/checksum.cmd        data integrity, including after a failover
    source tests/congestion_check2.cmd   congestion with four iperf streams on srv1's path

Flow rules can be inspected during a download:

    sh ovs-ofctl -O OpenFlow13 dump-flows s1 | grep priority=100

## Experiments

Leave the mininet> prompt (type exit), keep the controller running in the matching mode, then:

    sudo python3 tests/run_experiments.py --mode dynamic --file video1.bin
    sudo python3 tests/run_experiments.py --mode static  --file video1.bin
    python3 tests/make_graphs.py

The controller mode and the --mode label must match. Each run takes 10 to 20 minutes per mode.
Add --only normal, --only congested or --only failed to run one condition. Results are appended
to results/experiments.csv. Graphs and results/summary.md are written by make_graphs.py.

## Results (3 repetitions per cell)

- Failed server: dynamic completed 30 of 30 downloads, static 18 of 30.
- Congested path, 1 client: 8.5 s (dynamic) against 28.0 s (static).
- Congested path with 3 and 6 clients, and normal conditions: inconclusive, differences are within noise.

Limitations are listed in docs/architecture.md.
