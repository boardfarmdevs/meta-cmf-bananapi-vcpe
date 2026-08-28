#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
# Package upgrades can otherwise restart the VirtualBox guest service and
# detach /vagrant and /vagrant-artifacts while the one-time installer is still
# consuming them.  Report pending restarts but defer them to the optional VM
# reboot after installation.
export NEEDRESTART_MODE=l
assets=${EASYMESH_ASSETS:-/home/vagrant/easymesh-assets}
lxd_channel=${EASYMESH_LXD_CHANNEL:-latest/stable}

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

cd "$assets"
if [ -f SHA256SUMS ]; then
    sha256sum -c SHA256SUMS
fi

# Offline appliance builds provide assertion-backed, pinned snap payloads.
# A native LXD appliance build may instead install from the store and records
# the resolved versions in its build evidence.
if [ -f "$assets/astral-uv_1662.assert" ] \
    && [ -f "$assets/astral-uv_1662.snap" ]; then
    if ! snap list astral-uv 2>/dev/null | awk 'NR == 2 {exit !($3 == 1662)}'; then
        snap remove astral-uv --purge >/dev/null 2>&1 || true
        snap ack "$assets/astral-uv_1662.assert"
        snap install "$assets/astral-uv_1662.snap" --classic
    fi
    test "$(/snap/bin/uv --version | awk '{print $1, $2}')" = "uv 0.12.3"
elif ! snap list astral-uv >/dev/null 2>&1; then
    snap install astral-uv --classic
fi
/snap/bin/uv --version

# The accepted native lab uses LXD 6.7 revision 38768. Install that exact snap
# instead of following a channel which can advance between appliance builds.
if [ -f "$assets/lxd_38768.assert" ] \
    && [ -f "$assets/lxd_38768.snap" ] \
    && snap list lxd >/dev/null 2>&1; then
    installed_revision=$(snap list lxd | awk 'NR == 2 {print $3}')
    if [ "$installed_revision" != 38768 ]; then
        # A newer LXD may already have migrated its database. Reverting only
        # the snap then leaves revision 38768 unable to read that database.
        # This appliance is constructed from immutable inputs, so discard the
        # generated LXD state and let later provisioners recreate it.
        snap remove lxd --purge
    fi
fi
if [ -f "$assets/lxd_38768.assert" ] \
    && [ -f "$assets/lxd_38768.snap" ] \
    && ! snap list lxd 2>/dev/null | awk 'NR == 2 {exit !($3 == 38768)}'; then
    # Preserve the store assertion as well as the snap payload. Installing the
    # payload with --dangerous turns it into an unasserted sideload and prevents
    # LXD's privileged interfaces from auto-connecting during activation.
    snap ack "$assets/lxd_38768.assert"
    snap install "$assets/lxd_38768.snap"
fi
elif ! snap list lxd >/dev/null 2>&1; then
    snap install lxd --channel="$lxd_channel"
fi
# Freeze the selected revision before any LXD database or instance is created.
snap refresh --hold=forever lxd

getent group lxd >/dev/null || groupadd --system lxd
usermod -aG lxd vagrant
snap start lxd
lxd waitready
lxc version

install -d -m 0755 /var/lib/easymesh-vagrant
printf '%s\n' 'base-ready' > /var/lib/easymesh-vagrant/base.status
