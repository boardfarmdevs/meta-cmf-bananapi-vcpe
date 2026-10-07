#!/usr/bin/env bash
set -euo pipefail

repo=/home/easymesh/boardfarm-open-0406/boardfarm-lab-staging

test "$(sudo -u easymesh git -C "$repo" rev-parse HEAD)" = \
    ddb5a2b9e1707562595afc7e4000a3b8efa3cd81
# Boardfarm's lab keeps and uses its images (easymesh-resources lab-storage W5, W14): its setup
# brings the containers up without --build and builds an image only when it is missing, a
# base image only for a service image it must build, and its teardown keeps them, so the
# recovery path needs no build cache, no base image and no network. lab.py is put back to
# the pinned commit first: a VM from an older base image has an earlier version applied.
patch=/home/easymesh/easymesh-assets/boardfarm-lab-images.patch
sudo -u easymesh git -C "$repo" checkout -- lab/lab.py
sudo -u easymesh git -C "$repo" apply "$patch"

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
# A VM made from the base image already runs the service from its boot, racing Docker's
# preserved containers and the nested LXD: on rev150 (6 October) that run failed after 7 s,
# this start joined it and failed the build, and the service passed when run again. One
# more start after a bounded delay; a second failure still fails the step.
if ! systemctl start boardfarm-lab.service; then
    sleep 15
    systemctl restart boardfarm-lab.service
fi
systemctl start easymesh-lxd-docker-forward.service

test "$(docker network inspect wan-cpe1 -f '{{index .Options "com.docker.network.bridge.name"}}')" = \
    br-wan101
ip link show br-wan101 >/dev/null
test "$(docker ps --filter 'name=^/dhcp-cpe1$' --filter 'name=^/wan-cpe1$' --format '{{.Names}}' | sort | paste -sd, -)" = \
    dhcp-cpe1,wan-cpe1

# Only the images a container runs stay (W5, W14), before a base image is made from this VM:
# the build cache, the dangling layers, the build stages' bases and bf-ssh (the patched setup
# builds it only to build a missing service image) go.
docker builder prune -af >/dev/null
docker image prune -f >/dev/null
docker image rm debian:bookworm-slim python:3.13.5-slim-bookworm bf-ssh:bookworm >/dev/null 2>&1 || true

printf '%s\n' 'boardfarm-wan-ready' \
    > /var/lib/easymesh-lab/boardfarm.status
