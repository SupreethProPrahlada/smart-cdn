srv1 python3 app/server.py --id srv1 > /dev/null 2>&1 &
srv2 python3 app/server.py --id srv2 > /dev/null 2>&1 &
srv3 python3 app/server.py --id srv3 > /dev/null 2>&1 &
sh sleep 8
pingall
c1 python3 app/client.py --name video1.bin --client c1 --log /dev/null
c1 python3 app/client.py --name video2.bin --client c1 --log /dev/null > /tmp/c1.out 2>&1 &
sh sleep 5
sh pkill -f "id 10.0.0.1[1]"
sh sleep 50
sh cat /tmp/c1.out
