srv1 python3 app/server.py --id srv1 > /dev/null 2>&1 &
sh sleep 2
c1 python3 app/client.py --name video1.bin --host 10.0.0.11 --client c1 --log /dev/null
c4 iperf -s > /dev/null 2>&1 &
srv1 iperf -c 10.0.0.4 -t 40 -P 4 > /dev/null 2>&1 &
sh sleep 4
c1 python3 app/client.py --name video1.bin --host 10.0.0.11 --client c1 --log /dev/null
sh pkill iperf
