c1 python3 app/client.py --name video2.bin --client c1 --tag failover > /tmp/c1.out 2>&1 &
sh sleep 5
sh pkill -f "id 10.0.0.1[1]"
sh sleep 45
sh cat /tmp/c1.out
srv1 python3 app/server.py --id srv1 &
