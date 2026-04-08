#!/bin/sh

current_date=$(date +%s)
capture_count=0
logpath="$HOME/rssfree.log"

rm -rf $logpath

initial_interval=1
initial_duration=120
subsequent_interval=60

# Calculate the number of captures during the initial interval
initial_captures=$((initial_duration / initial_interval))

capture_interval=$initial_interval

while true; do
    now=$(date +%s)
    delta=$((now - current_date))
    echo "TIME $delta" >> $logpath
    ps.procps --sort=-rss -eo user,pid,ppid,%cpu,%mem,vsz,rss,tty,stat,start_time,etime,time,args >> $logpath
    free >> $logpath

    capture_count=$((capture_count + 1))
    if [ $capture_count -eq $initial_captures ]; then
        capture_interval=$subsequent_interval
    fi
    sleep $capture_interval
done
