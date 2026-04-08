#!/bin/sh

export HOME=/home/root

# mount rdklogs to tmpfs
mkdir -p /rdklogs
mount -t tmpfs -o size=128m tmpfs /rdklogs

# webpa: server ip
sed -i 's|SERVERURL=https://webpa.rdkcentral.com:8080|SERVERURL=http://10.10.10.210:8080|' /etc/device.properties

# usp-pa
for f in /etc/usp-pa/oktopus*.txt; do
    [ -f "$f" ] && sed -i 's/127\.0\.0\.1/10.10.10.220/g' "$f"
done
ln -sf /etc/usp-pa/oktopus-mqtt-obuspa.txt /etc/usp-pa/usp_factory_reset.conf
#ln -sf /etc/usp-pa/oktopus-websockets-obuspa.txt /etc/usp-pa/usp_factory_reset.conf
#ln -sf /etc/usp-pa/oktopus-stomp-obuspa.txt /etc/usp-pa/usp_factory_reset.conf
rm -rf /nvram/usp-pa.db

# prevent early log rotation
logmaxsize=2000000
[ ! -z "${logmaxsize}" ] && sed -i "s/\(maxsize=\"\)[0-9]*\"/\1${logmaxsize}\"/g" /etc/log4crc

# enable debug for tr069
sed -i '/^LOG\.RDK\.TR69/{ /DEBUG/! s/$/ DEBUG/ }' /etc/debug.ini

#
if [ ! -f "$HOME/.bashrc" ]; then
    cat > "$HOME/.bashrc" << EOL
alias c="clear && printf '\033[3J'; printf '\033[0m'"
PS1='\u@\h:\w\$ '
export SYSTEMD_PAGER=""
EOL
fi

# retrieve bash history
if [ -f /nvram/.bash_history ]; then
    cp /nvram/.bash_history /home/root/
    history -r
fi

# debug rbus
# touch /nvram/rtrouted_traffic_monitor

# track rss and free
rssfree &

# PartnerID is required for tr069
sed -i 's/PartnerID=.*/PartnerID=comcast/' /nvram/syscfg.db

exit 0
