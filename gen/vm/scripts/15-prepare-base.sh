#!/usr/bin/env bash
set -euo pipefail

# The lab host's part that does not depend on the commit being built: Boardfarm's
# workspace, nested LXD and its client image, and the patched radio module. Together with
# 00-base.sh, 10-install-linux-7.sh and 30-boardfarm-wan.sh it is what a base VM image
# holds (gen/vm/lxd/build.sh, EASYMESH_BASE_IMAGE). The commit's part is
# 20-prepare-lab-host.sh.

# LXC commands opportunistically parse non-terminal stdin as YAML. Isolate the
# complete host setup from any outer VM-agent input.
exec </dev/null

expected_kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
assets=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
boardfarm_workspace=/home/easymesh/boardfarm-open-0406
alpine_remote=${EASYMESH_ALPINE_REMOTE:-images:alpine/3.22/amd64}
nested_storage_driver=${EASYMESH_NESTED_LXD_STORAGE_DRIVER:-btrfs}

case "$nested_storage_driver" in
    btrfs)
        command -v mkfs.btrfs >/dev/null 2>&1 && modinfo btrfs >/dev/null 2>&1 || {
            echo 'nested Btrfs storage is unavailable; set EASYMESH_NESTED_LXD_STORAGE_DRIVER=dir to use the compatibility backend' >&2
            exit 1
        }
        ;;
    dir) ;;
    *) echo "unsupported EASYMESH_NESTED_LXD_STORAGE_DRIVER: $nested_storage_driver" >&2; exit 2 ;;
esac

if [ "$(uname -r)" != "$expected_kernel" ]; then
    echo "expected $expected_kernel after reboot, found $(uname -r)" >&2
    exit 1
fi

# Ubuntu's extras the lab does not use go (easymesh-resources lab-storage W12, ~545 MiB): the
# cloud image's own kernel with its headers, modules, tools and meta-packages (the VM runs
# $expected_kernel, and GRUB_DEFAULT=0 boots the newest), the kernel accessories (bpftrace,
# bcc, LLVM) and sosreport (boto). Their autoremoval also takes ubuntu-server and Python
# packages no lab code imports (netaddr, dateutil, pexpect, magic); Boardfarm has a venv of
# its own. The running kernel's headers stay: build.sh update builds the radio module here.
# dpkg-query exits 1 when a name matches nothing installed (a fresh VM has no meta-package or
# sosreport at this point): that is no error here, and pipefail would end the script on it.
extras=$({ dpkg-query -W -f '${db:Status-Abbrev} ${Package}\n' 'linux-image-*' 'linux-modules-*' \
        'linux-headers-*' 'linux-tools-*' linux-virtual linux-generic ubuntu-kernel-accessories sosreport \
        2>/dev/null || true; } | awk -v kept="${expected_kernel%-generic}" \
        '$1 == "ii" && index($2, kept) == 0 {print $2}')
if [ -n "$extras" ]; then
    # shellcheck disable=SC2086 # one package name per word
    apt-get purge -y --autoremove $extras
fi

install -d -o easymesh -g easymesh "$boardfarm_workspace"

clone_pinned_repo() {
    local name=$1 branch=$2 expected=$3
    local destination="$boardfarm_workspace/$name"
    if [ ! -d "$destination/.git" ]; then
        sudo -u easymesh git clone "$assets/$name.bundle" "$destination"
    fi
    sudo -u easymesh git -C "$destination" checkout -B "$branch" "$expected"
    test -z "$(sudo -u easymesh git -C "$destination" \
        status --porcelain --untracked-files=no)"
    test "$(sudo -u easymesh git -C "$destination" rev-parse HEAD)" = "$expected"
}

clone_pinned_repo boardfarm-lab-staging codex/0905-clean ddb5a2b9e1707562595afc7e4000a3b8efa3cd81

if [ ! -x "$boardfarm_workspace/.venv/bin/python" ]; then
    sudo -H -u easymesh /snap/bin/uv venv --python 3.13.15 \
        --prompt bf-venv "$boardfarm_workspace/.venv"
fi
sudo -H -u easymesh env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip install -e "$boardfarm_workspace/boardfarm-lab-staging"
sudo -H -u easymesh env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip check
test "$($boardfarm_workspace/.venv/bin/python -c 'import platform; print(platform.python_version())')" = 3.13.15

printf '%s\n' \
    'BF_LAB_CONFIG=ca-desk6.json' \
    'BF_INVENTORY=ca-desk6.json' \
    "BOARDFARM_WORKSPACE=$boardfarm_workspace" \
    > /etc/default/boardfarm-lab
printf '%s\n' \
    'export BF_LAB_CONFIG=ca-desk6.json' \
    'export BF_INVENTORY=ca-desk6.json' \
    "export PATH=$boardfarm_workspace/.venv/bin:\$PATH" \
    > /etc/profile.d/boardfarm-lab.sh

if ! lxc storage show default >/dev/null 2>&1; then
    # LXD 6.7 may consume outer agent input after --auto and try to decode it
    # as a storage-pool YAML update even though initialization succeeded.
    lxd init --auto --storage-backend dir </dev/null
fi
if ! lxc storage show bpi-lab >/dev/null 2>&1; then
    lxc storage create bpi-lab "$nested_storage_driver"
fi

if ! lxc image info alpine >/dev/null 2>&1 \
    && [ -f "$assets/alpine-3.19-amd64-meta.tar.xz" ] \
    && [ -f "$assets/alpine-3.19-amd64-rootfs.tar.xz" ]; then
    lxc image import \
        "$assets/alpine-3.19-amd64-meta.tar.xz" \
        "$assets/alpine-3.19-amd64-rootfs.tar.xz" \
        --alias alpine
fi
if ! lxc image info alpine >/dev/null 2>&1; then
    # Alpine 3.19 is retained for reproducible offline bundles, but its public
    # image-server alias has expired. Use a maintained, architecture-qualified
    # image when the build has no bundled client image.
    lxc image copy "$alpine_remote" local: --alias alpine
fi
lxc image info alpine >/dev/null

# Stock Linux 7 deliberately rejects HWSIM_CMD_REGISTER when channels > 1.
# Build the repository's narrowly-scoped registration patch against the exact
# installed Ubuntu source package. Keep source repositories supplemental so
# the normal binary repository configuration remains owned by cloud-init.
if [ ! -f /etc/apt/sources.list.d/easymesh-ubuntu-src.sources ]; then
    sed 's/^Types: deb$/Types: deb-src/' \
        /etc/apt/sources.list.d/ubuntu.sources \
        > /etc/apt/sources.list.d/easymesh-ubuntu-src.sources
fi
apt-get update
# The medium the lab pins, from its bundle: only its radio module is built here; the
# lab's own checkout of it (20-prepare-lab-host.sh) comes with the commit.
medium=$(mktemp -d /tmp/easymesh-medium.XXXXXX)
trap 'rm -rf -- "$medium"' EXIT
git clone -q "$assets/easymesh-medium.bundle" "$medium/easymesh-medium"
git -C "$medium/easymesh-medium" checkout -q --detach origin/lxd-appliance-export
REFETCH=1 "$medium/easymesh-medium/hwsim/build-hwsim.sh" --6ghz --install
hwsim_module=$(modinfo -k "$expected_kernel" -F filename mac80211_hwsim)
case "$hwsim_module" in
    "/lib/modules/$expected_kernel/updates/mac80211_hwsim.ko") ;;
    *) echo "patched hwsim module is not selected: $hwsim_module" >&2; exit 1 ;;
esac
grep -aq 'EXPERIMENTAL wmediumd' "$hwsim_module"
sha256sum "$hwsim_module" \
    > /var/lib/easymesh-lab/mac80211_hwsim.sha256
git -C "$medium/easymesh-medium" rev-parse HEAD:hwsim \
    > /var/lib/easymesh-lab/mac80211_hwsim.source

# Start a tri-band pool only after installing the multichannel registration
# patch and confirming that no copied runtime state is present in this guest.
hwsim_radios=${HWSIM_RADIOS:-128}
case "$hwsim_radios" in
    ''|*[!0-9]*|0) echo "HWSIM_RADIOS must be a positive integer" >&2; exit 2 ;;
esac
printf 'options mac80211_hwsim radios=%s channels=3 regtest=5\n' "$hwsim_radios" \
    > /etc/modprobe.d/easymesh-hwsim.conf
printf '%s\n' 'mac80211_hwsim' > /etc/modules-load.d/easymesh-hwsim.conf
if [ ! -d /sys/module/mac80211_hwsim ]; then
    modprobe mac80211_hwsim
fi
# Never reload a live pool: LXD physical NICs move their entire wiphy into
# container namespaces and do not reliably keep modprobe -r from succeeding.
# Reloading here silently removes Wi-Fi from already-running lab nodes.
test "$(cat /sys/module/mac80211_hwsim/parameters/radios)" = "$hwsim_radios"
test "$(cat /sys/module/mac80211_hwsim/parameters/channels)" = 3
test "$(cat /sys/module/mac80211_hwsim/parameters/regtest)" = 5

printf '%s\n' 'base-host-ready' > /var/lib/easymesh-lab/base-host.status
