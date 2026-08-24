#!/usr/bin/env bash
set -euo pipefail

repo=/home/vagrant/boardfarm-open-0406/boardfarm-lab-staging

test "$(git -C "$repo" rev-parse HEAD)" = \
    510c65fc4a880471e344a88d824fd0bc07a342d8

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

test "$(docker network inspect wan-cpe5 -f '{{index .Options "com.docker.network.bridge.name"}}')" = \
    br-wan105
ip link show br-wan105 >/dev/null

printf '%s\n' 'boardfarm-wan-ready' \
    > /var/lib/easymesh-vagrant/boardfarm.status
