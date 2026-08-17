#!/usr/bin/env bash
set -euo pipefail

kernel=7.0.0-28-generic
assets=/home/vagrant/easymesh-assets

cd "$assets"
sha256sum -c SHA256SUMS

tar --zstd -C / -xf "$assets/linux-7.0.0-28-hwsim.tar.zst"
depmod -a "$kernel"

if [ -e "/boot/initrd.img-$kernel" ]; then
    update-initramfs -u -k "$kernel"
else
    update-initramfs -c -k "$kernel"
fi
update-grub

test "$(sha256sum "/lib/modules/$kernel/updates/mac80211_hwsim.ko" | awk '{print $1}')" = \
    c7c9e49d7198e84de33be893532c68591f4bb54aaed7f8319d2bf7c22a7360bb

printf '%s\n' "$kernel" > /var/lib/easymesh-vagrant/installed-kernel
