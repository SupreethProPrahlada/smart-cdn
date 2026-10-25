c1 python3 app/client.py --name video2.bin --client c1 --tag cong > /tmp/c1.out 2>&1 &
sh sleep 6
c2 python3 app/client.py --name video1.bin --client c2 --tag cong > /tmp/c2.out 2>&1 &
sh sleep 30
sh cat /tmp/c1.out /tmp/c2.out
