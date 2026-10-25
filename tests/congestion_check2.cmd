srv1 python3 app/server.py --id srv1 > /dev/null 2>&1 &
sh sleep 2
c4 iperf -s > /dev/null 2>&1 &
sh sleep 1
srv1 iperf -c 10.0.0.4 -t 25 -P 4 -i 5 > /tmp/ip.out 2>&1 &
sh sleep 5
c1 python3 app/client.py --name video1.bin --host 10.0.0.11 --client c1 --log /dev/null
sh sleep 22
sh cat /tmp/ip.out
sh pkill iperf
