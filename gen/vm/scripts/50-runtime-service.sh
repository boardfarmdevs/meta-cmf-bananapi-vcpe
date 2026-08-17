#!/usr/bin/env bash
set -euo pipefail

test -f /home/vagrant/.local/state/easymesh-vagrant/deploy.status

install -m 0755 /home/vagrant/easymesh-assets/easymesh-lab-runtime \
    /usr/local/sbin/easymesh-lab-runtime
install -m 0644 /home/vagrant/easymesh-assets/easymesh-lab.service \
    /etc/systemd/system/easymesh-lab.service
install -m 0755 /home/vagrant/easymesh-assets/easymesh-hwsim-pool \
    /usr/local/sbin/easymesh-hwsim-pool
install -m 0644 /home/vagrant/easymesh-assets/easymesh-hwsim-pool.service \
    /etc/systemd/system/easymesh-hwsim-pool.service
install -d /etc/systemd/system/snap.lxd.daemon.service.d
install -m 0644 /home/vagrant/easymesh-assets/lxd-easymesh-ordering.conf \
    /etc/systemd/system/snap.lxd.daemon.service.d/easymesh-ordering.conf

# Boardfarm reconstructs its Docker lab and br-wan105 first. The EasyMesh
# runtime then starts LXD nodes in dependency order.
for container in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003 \
    wlan-client wlan-client-001 wlan-client-002 wlan-client-003 wlan-client-004 \
    wlan-client-005 wlan-client-006 wlan-client-007 wlan-client-008 wlan-client-009; do
    lxc info "$container" >/dev/null 2>&1 || continue
    lxc config set "$container" boot.autostart false
done
systemctl daemon-reload
systemctl enable boardfarm-lab.service
systemctl enable easymesh-hwsim-pool.service
systemctl enable easymesh-lab.service
systemctl start easymesh-hwsim-pool.service
# Restarting this required dependency propagates a stop into an already healthy
# EasyMesh runtime. A newly installed helper is picked up on the next appliance
# boot; idempotent reprovision must leave the active lab undisturbed.
systemctl start easymesh-lxd-docker-forward.service
