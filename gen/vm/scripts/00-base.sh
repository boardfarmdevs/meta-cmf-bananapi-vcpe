#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
assets=/home/vagrant/easymesh-assets

apt-get update
apt-get install -y --no-install-recommends \
    apparmor \
    bridge-utils \
    build-essential \
    ca-certificates \
    curl \
    docker-compose-v2 \
    docker.io \
    git \
    iw \
    jq \
    libconfig-dev \
    libnl-3-dev \
    libnl-genl-3-dev \
    net-tools \
    patch \
    pkg-config \
    rsync \
    sqlite3 \
    sshpass \
    tcpdump \
    uidmap \
    zstd

systemctl enable --now docker
usermod -aG docker vagrant

# The user's snap-based installation is valid. Pin the verified revision so a
# rebuild does not silently consume a different resolver or Python manager.
if ! snap list astral-uv 2>/dev/null | awk 'NR == 2 {exit !($3 == 1662)}'; then
    snap remove astral-uv --purge >/dev/null 2>&1 || true
    snap ack "$assets/astral-uv_1662.assert"
    snap install "$assets/astral-uv_1662.snap" --classic
fi
test "$(/snap/bin/uv --version | awk '{print $1, $2}')" = "uv 0.12.3"

cd "$assets"
sha256sum -c SHA256SUMS

# The accepted native lab uses LXD 6.7 revision 38768. Install that exact snap
# instead of following a channel which can advance between appliance builds.
if snap list lxd >/dev/null 2>&1; then
    installed_revision=$(snap list lxd | awk 'NR == 2 {print $3}')
    if [ "$installed_revision" != 38768 ]; then
        # A newer LXD may already have migrated its database. Reverting only
        # the snap then leaves revision 38768 unable to read that database.
        # This appliance is constructed from immutable inputs, so discard the
        # generated LXD state and let later provisioners recreate it.
        snap remove lxd --purge
    fi
fi
if ! snap list lxd 2>/dev/null | awk 'NR == 2 {exit !($3 == 38768)}'; then
    # Preserve the store assertion as well as the snap payload. Installing the
    # payload with --dangerous turns it into an unasserted sideload and prevents
    # LXD's privileged interfaces from auto-connecting during activation.
    snap ack "$assets/lxd_38768.assert"
    snap install "$assets/lxd_38768.snap"
fi
# A sideloaded asserted snap can still refresh when the store publishes a
# newer revision. Freeze it before any LXD database or instance is created.
snap refresh --hold=forever lxd

getent group lxd >/dev/null || groupadd --system lxd
usermod -aG lxd vagrant
snap start lxd
lxd waitready

install -d -m 0755 /var/lib/easymesh-vagrant
printf '%s\n' 'base-ready' > /var/lib/easymesh-vagrant/base.status
