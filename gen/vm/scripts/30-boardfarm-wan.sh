#!/usr/bin/env bash
set -euo pipefail

repo=/home/easymesh/boardfarm-open-0406/boardfarm-lab-staging

test "$(sudo -u easymesh git -C "$repo" rev-parse HEAD)" = \
    ddb5a2b9e1707562595afc7e4000a3b8efa3cd81

systemctl enable --now docker

install -m 0755 /home/easymesh/easymesh-assets/easymesh-lxd-docker-forward \
    /usr/local/sbin/easymesh-lxd-docker-forward
install -m 0644 /home/easymesh/easymesh-assets/easymesh-lxd-docker-forward.service \
    /etc/systemd/system/easymesh-lxd-docker-forward.service
install -m 0755 /home/easymesh/easymesh-assets/boardfarm-lab-rebuild \
    /usr/local/sbin/boardfarm-lab-rebuild
install -m 0644 /home/easymesh/easymesh-assets/boardfarm-lab.service \
    /etc/systemd/system/boardfarm-lab.service
systemctl daemon-reload
systemctl enable boardfarm-lab.service easymesh-lxd-docker-forward.service
systemctl start boardfarm-lab.service
systemctl start easymesh-lxd-docker-forward.service

test "$(docker network inspect wan-cpe1 -f '{{index .Options "com.docker.network.bridge.name"}}')" = \
    br-wan101
ip link show br-wan101 >/dev/null
test "$(docker ps --format '{{.Names}}' | sort | paste -sd, -)" = \
    dhcp-cpe1,wan-cpe1

printf '%s\n' 'boardfarm-wan-ready' \
    > /var/lib/easymesh-lab/boardfarm.status
