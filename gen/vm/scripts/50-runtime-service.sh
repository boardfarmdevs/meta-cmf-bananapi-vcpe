#!/usr/bin/env bash
set -euo pipefail

test -f /home/easymesh/.local/state/easymesh-lab/deploy.status

profile=${EASYMESH_SCALE_PROFILE:-small}
expected_clients=${HEALTH_EXPECT_CLIENTS:-20}
cat > /etc/default/easymesh-lab <<EOF
EASYMESH_SCALE_PROFILE=$profile
HEALTH_EXPECT_CLIENTS=$expected_clients
EOF

install -m 0755 /home/easymesh/easymesh-assets/easymesh-lab-runtime \
    /usr/local/sbin/easymesh-lab-runtime
install -m 0644 /home/easymesh/easymesh-assets/easymesh-lab.service \
    /etc/systemd/system/easymesh-lab.service
install -m 0755 /home/easymesh/easymesh-assets/easymesh-hwsim-pool \
    /usr/local/sbin/easymesh-hwsim-pool
install -m 0644 /home/easymesh/easymesh-assets/easymesh-hwsim-pool.service \
    /etc/systemd/system/easymesh-hwsim-pool.service
install -d /etc/systemd/system/snap.lxd.daemon.service.d
install -m 0644 /home/easymesh/easymesh-assets/lxd-easymesh-ordering.conf \
    /etc/systemd/system/snap.lxd.daemon.service.d/easymesh-ordering.conf
install -m 0755 /home/easymesh/easymesh-assets/easymesh-labctl \
    /usr/local/sbin/easymesh-labctl
install -m 0755 /home/easymesh/easymesh-assets/easymesh-health-audit \
    /usr/local/sbin/easymesh-health-audit
install -m 0755 /home/easymesh/easymesh-assets/easymesh-package-cleanup \
    /usr/local/sbin/easymesh-package-cleanup
install -m 0755 /home/easymesh/easymesh-assets/easymesh-prepare-thin-package \
    /usr/local/sbin/easymesh-prepare-thin-package
install -m 0755 /home/easymesh/easymesh-assets/easymesh-complete-thin-firstboot \
    /usr/local/sbin/easymesh-complete-thin-firstboot
install -m 0755 /home/easymesh/easymesh-assets/easymesh-thin-firstboot \
    /usr/local/sbin/easymesh-thin-firstboot
install -m 0755 /home/easymesh/easymesh-assets/easymesh-select-thin-profile \
    /usr/local/sbin/easymesh-select-thin-profile
install -m 0644 /home/easymesh/easymesh-assets/easymesh-thin-firstboot.service \
    /etc/systemd/system/easymesh-thin-firstboot.service

# Boardfarm reconstructs its two-container WAN lab and br-wan101 first. The EasyMesh
# runtime then starts LXD nodes in dependency order.
for container in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003 \
    $(lxc list -c n --format csv | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V); do
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
