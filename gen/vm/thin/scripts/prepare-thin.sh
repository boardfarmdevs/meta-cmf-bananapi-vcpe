#!/usr/bin/env bash
set -euo pipefail

kernel=7.0.0-28-generic
archive=/tmp/linux-7.0.0-28-hwsim.tar.zst
expected=0cc52c6ae26c0e71e45334461690c46f7d8494b50152d15f739a7a7a4edbb799

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git lvm2 zstd

echo "$expected  $archive" | sha256sum -c -
tar --zstd -C / -xf "$archive"
depmod -a "$kernel"
if [ -e "/boot/initrd.img-$kernel" ]; then
    update-initramfs -u -k "$kernel"
else
    update-initramfs -c -k "$kernel"
fi
update-grub

# Bento's virtual disk is already 64 GB, but its root logical volume initially
# uses only half of the volume group. Give the online installation the rest.
root_lv=$(findmnt -n -o SOURCE /)
free_extents=$(vgs --noheadings -o vg_free_count | tr -d ' ')
if [ "$free_extents" -gt 0 ]; then
    lvextend -r -l +100%FREE "$root_lv"
fi

rm -f "$archive"
apt-get clean
journalctl --vacuum-size=32M >/dev/null
fstrim -av || true
