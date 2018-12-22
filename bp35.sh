#!/bin/bash
SCRIPT=bp35a1_v02_loop.py 
/var/power/$SCRIPT 2>&1 >> /var/power/power.log &
ps -ef |grep $SCRIPT | grep -v grep|awk '{print $2}' > /var/run/bp35a1.pid
exit 0
