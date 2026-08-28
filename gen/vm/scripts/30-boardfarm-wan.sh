#!/usr/bin/env bash
set -euo pipefail

repo=/home/vagrant/boardfarm-open-0406/boardfarm-lab-staging

test "$(sudo -u vagrant git -C "$repo" rev-parse HEAD)" = \
    eeb4803c00dc1cae2dda05eb6e1b52c06ad79aa8

systemctl enable --now docker

install -m 0755 /home/vagrant/easymesh-assets/easymesh-lxd-docker-forward \
    /usr/local/sbin/easymesh-lxd-docker-forward
install -m 0644 /home/vagrant/easymesh-assets/easymesh-lxd-docker-forward.service \
    /etc/systemd/system/easymesh-lxd-docker-forward.service
install -m 0755 /home/vagrant/easymesh-assets/boardfarm-lab-rebuild \
    /usr/local/sbin/boardfarm-lab-rebuild
install -m 0644 /home/vagrant/easymesh-assets/boardfarm-lab.service \
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
    > /var/lib/easymesh-vagrant/boardfarm.status
