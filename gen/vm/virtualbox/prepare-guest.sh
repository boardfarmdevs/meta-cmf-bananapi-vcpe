#!/usr/bin/env bash
set -euo pipefail

root=${1:?usage: sudo bash prepare-guest.sh MOUNTED_ROOT RELEASE_JSON}
release=${2:?missing release metadata}
source_dir=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" -eq 0 ] || { echo 'Guest preparation requires root.' >&2; exit 1; }
root=$(realpath "$root")
[ "$root" != / ] && mountpoint -q "$root"
test -f "$root/var/lib/easymesh-lab/thin-profile-selection.required"
test -f "$root/usr/local/sbin/easymesh-select-thin-profile"
test -f "$root/boot/efi/EFI/BOOT/BOOTX64.EFI"
test "$(chroot "$root" dpkg --print-architecture)" = amd64
test ! -d "$root/opt/easymesh-observability/secrets"

find "$root/etc/netplan" -maxdepth 1 -type f -name '*.yaml' -delete
install -m 0600 "$source_dir/guest/netplan.yaml" "$root/etc/netplan/01-virtualbox.yaml"
touch "$root/etc/cloud/cloud-init.disabled"
find "$root/var/lib/cloud" -mindepth 1 -delete
find "$root/var/lib/systemd/network" -maxdepth 1 -type f -delete 2>/dev/null || true
printf 'rdk-easymesh\n' > "$root/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 rdk-easymesh\n::1 localhost ip6-localhost ip6-loopback\n' > "$root/etc/hosts"
truncate -s 0 "$root/etc/machine-id"
find "$root/var/lib/dbus" -maxdepth 1 -name machine-id -delete
ln -s /etc/machine-id "$root/var/lib/dbus/machine-id"
find "$root/var/lib/systemd" -maxdepth 1 -name random-seed -delete
find "$root/etc/ssh" -maxdepth 1 -type f -name 'ssh_host_*' -delete
for account in root home/ubuntu home/easymesh; do
    find "$root/$account/.ssh" -maxdepth 1 -type f -name authorized_keys -delete 2>/dev/null || true
done
find "$root/var/snap/lxd/common/lxd" -maxdepth 1 -type f \
    \( -name server.crt -o -name server.key \) -delete

if ! chroot "$root" id vagrant >/dev/null 2>&1; then
    chroot "$root" useradd --create-home --shell /bin/bash --groups sudo,lxd --password '*' vagrant
fi
install -d -m 0700 "$root/home/vagrant/.ssh"
install -m 0600 "$source_dir/guest/vagrant.pub" "$root/home/vagrant/.ssh/authorized_keys"
chroot "$root" chown -R vagrant:vagrant /home/vagrant/.ssh
printf 'vagrant ALL=(ALL) NOPASSWD: ALL\n' > "$root/etc/sudoers.d/99-vagrant"
chmod 0440 "$root/etc/sudoers.d/99-vagrant"
chroot "$root" visudo -cf /etc/sudoers.d/99-vagrant
install -m 0644 "$source_dir/guest/sshd.conf" "$root/etc/ssh/sshd_config.d/00-vagrant.conf"
install -m 0755 "$source_dir/guest/easymesh-vagrant-up" "$root/usr/local/sbin/easymesh-vagrant-up"
install -m 0644 "$source_dir/guest/easymesh-vbox-identity.service" \
    "$root/etc/systemd/system/easymesh-vbox-identity.service"
install -d "$root/etc/systemd/system/ssh.service.d"
printf '[Unit]\nRequires=easymesh-vbox-identity.service\nAfter=easymesh-vbox-identity.service\n' \
    > "$root/etc/systemd/system/ssh.service.d/virtualbox-identity.conf"
find "$root/etc/systemd/system/ssh.socket.d" -maxdepth 1 -name virtualbox-identity.conf -delete 2>/dev/null || true
systemctl --root="$root" enable easymesh-vbox-identity.service
systemctl --root="$root" mask lxd-agent.service
install -m 0644 "$release" "$root/var/lib/easymesh-lab/virtualbox-release.json"
chroot "$root" netplan generate
echo 'Prepared the copied thin guest for VirtualBox; no nested lab was provisioned.'
