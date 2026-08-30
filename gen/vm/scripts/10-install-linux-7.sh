#!/usr/bin/env bash
set -euo pipefail

kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
assets=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
kernel_archive=${EASYMESH_KERNEL_ARCHIVE:-$assets/linux-${kernel%-generic}-hwsim.tar.zst}

cd "$assets"
if [ -f SHA256SUMS ]; then
    sha256sum -c SHA256SUMS
fi

if [ -f "$kernel_archive" ]; then
    tar --zstd -C / -xf "$kernel_archive"
    depmod -a "$kernel"
else
    apt-get update
    apt-get install -y --no-install-recommends \
        "linux-headers-$kernel" \
        "linux-image-$kernel" \
        "linux-modules-$kernel"
fi

if [ -e "/boot/initrd.img-$kernel" ]; then
    update-initramfs -u -k "$kernel"
else
    update-initramfs -c -k "$kernel"
fi
update-grub

modinfo -k "$kernel" mac80211_hwsim | grep -q '^parm:.*channels:'
modinfo -k "$kernel" mac80211_hwsim | grep -q '^parm:.*regtest:'

if [ -n "${EASYMESH_HWSIM_SHA256:-}" ]; then
    hwsim_path=$(modinfo -k "$kernel" -F filename mac80211_hwsim)
    test "$(sha256sum "$hwsim_path" | awk '{print $1}')" = \
        "$EASYMESH_HWSIM_SHA256"
fi

printf '%s\n' "$kernel" > /var/lib/easymesh-lab/installed-kernel
