#!/usr/bin/env bash
set -euo pipefail

source_dir=$(cd "$(dirname "$0")" && pwd)
thin_dir=$(realpath "${1:?usage: bash build.sh EXTRACTED_RDK_THIN_BUNDLE OUTPUT_DIRECTORY}")
output=$(realpath -m "${2:?missing output directory}")
if [[ "$output" = "$source_dir" || "$output" = "$source_dir/"* ]]; then
    echo 'The output directory must be outside the adapter source directory.' >&2
    exit 1
fi
[ "$(id -u)" -ne 0 ] || { echo 'Run as the VirtualBox user, not root; sudo is used only for the copied disk.' >&2; exit 1; }
for dependency in VBoxManage qemu-img qemu-nbd jq python3 sha256sum tar flock growpart resize2fs e2fsck; do
    command -v "$dependency" >/dev/null || { echo "Missing build dependency: $dependency (see README.md)." >&2; exit 1; }
done
sudo -n true
jq -e '.stack == "rdkeasymesh" and .release_flavor == "thin" and .profile_selectable == true' \
    "$thin_dir/release.json" >/dev/null
(cd "$thin_dir"; sha256sum -c SHA256SUMS)
archive=$(jq -r .archive "$thin_dir/release.json")
[ "$(basename "$archive")" = "$archive" ] && test -f "$thin_dir/$archive"
release_id=$(jq -r .release_id "$thin_dir/release.json")
[[ "$release_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
box=rdkeasymesh-$release_id-virtualbox.box
name=${EASYMESH_VBOX_BUILDER_NAME:-rdkeasymesh-$release_id-box-builder}
if VBoxManage showvminfo "$name" >/dev/null 2>&1; then
    echo "Refusing to replace an existing VirtualBox machine: $name" >&2
    exit 1
fi
mkdir -p "$output"
test ! -e "$output/$box"
work=$(mktemp -d "$output/build.XXXXXX")
root=$work/root
nbd=
nbd_connected=false
registered=false
unmount_guest() {
    local target attempt
    for target in "$root/boot/efi" "$root/boot" "$root"; do
        for attempt in $(seq 1 15); do
            mountpoint -q "$target" || break
            sudo umount "$target" && break
            sleep 2
        done
        if mountpoint -q "$target"; then
            echo "Copied guest filesystem is still busy: $target" >&2
            return 1
        fi
    done
}
cleanup() {
    local result=$?
    if ! unmount_guest; then
        echo "Build work retained at $work; mounted disk left connected for safe recovery." >&2
        exit 1
    fi
    if [ "$nbd_connected" = true ]; then sudo qemu-nbd --disconnect "$nbd"; fi
    if [ "$registered" = true ]; then VBoxManage unregistervm "$name"; fi
    echo "Build work/evidence retained at $work (exit $result)"
    exit "$result"
}
trap cleanup EXIT
mkdir "$root" "$work/box"
cp "$thin_dir/release.json" "$output/source-release.json"
adapter_files=(Vagrantfile README.md build.sh prepare-guest.sh package-release.sh \
    guest/netplan.yaml guest/sshd.conf guest/vagrant.pub \
    guest/easymesh-vbox-identity.service guest/easymesh-vagrant-up)
(cd "$source_dir"; sha256sum "${adapter_files[@]}") > "$output/adapter-files.sha256"
tar -czf "$output/adapter-source.tar.gz" -C "$source_dir" "${adapter_files[@]}"
jq -n --slurpfile source "$thin_dir/release.json" \
    --arg box "$box" --arg archive_sha256 "$(sha256sum "$thin_dir/$archive" | awk '{print $1}')" \
    --arg adapter_sha256 "$(sha256sum "$output/adapter-files.sha256" | awk '{print $1}')" \
    --arg virtualbox "$(VBoxManage --version)" \
    '{schema_version:1,stack:"rdkeasymesh",provider:"virtualbox",architecture:"amd64",
      release_id:$source[0].release_id,box:$box,source_commit:$source[0].source_commit,
      source_archive:$source[0].archive,source_archive_sha256:$archive_sha256,
      adapter_manifest_sha256:$adapter_sha256,virtualbox_builder_version:$virtualbox,
      clients:20,physical_mesh_devices:5,logical_mesh_roles:6,cpus:6,memory_mb:8192,
      initial_nested_instances:0,status:"candidate"}' > "$output/release.json"
tar -xOf "$thin_dir/$archive" backup/virtual-machine.img \
    | dd of="$work/source.img" bs=4M conv=sparse status=none
format=$(qemu-img info --output=json "$work/source.img" | jq -r .format)
case "$format" in raw|qcow2) ;; *) echo "Unsupported source disk format: $format" >&2; exit 1 ;; esac
disk=$work/appliance.qcow2
qemu-img convert -p -f "$format" -O qcow2 "$work/source.img" "$disk"
test "$(qemu-img info --output=json "$disk" | jq -r '."virtual-size"')" -le 103079215104
qemu-img resize "$disk" 96G
sudo modprobe nbd max_part=16
exec 9> /tmp/rdkeasymesh-virtualbox-nbd.lock
flock -x 9
for candidate in /sys/class/block/nbd*; do
    if [ ! -e "$candidate/pid" ] && [ "$(cat "$candidate/size")" = 0 ]; then
        nbd=/dev/$(basename "$candidate")
        break
    fi
done
[ -n "$nbd" ] || { echo 'No unused NBD device is available.' >&2; exit 1; }
sudo qemu-nbd --format=qcow2 --discard=unmap --connect="$nbd" "$disk"
nbd_connected=true
sudo udevadm settle
partition() {
    lsblk -pnro NAME,LABEL "$nbd" | awk -v label="$1" '$2 == label {print $1}'
}
for attempt in $(seq 1 30); do
    [ -n "$(partition cloudimg-rootfs)" ] && break
    sleep 1
done
root_partition=$(partition cloudimg-rootfs)
test -b "$root_partition"
partition_number=$(cat "/sys/class/block/$(basename "$root_partition")/partition")
if ! growth=$(sudo growpart "$nbd" "$partition_number" 2>&1); then
    grep -q '^NOCHANGE:' <<< "$growth" || { echo "$growth" >&2; exit 1; }
fi
echo "$growth"
check_status=0
sudo e2fsck -p -f "$root_partition" || check_status=$?
[ "$check_status" -le 1 ] || exit "$check_status"
sudo resize2fs "$root_partition"
sudo mount "$root_partition" "$root"
sudo mount "$(partition BOOT)" "$root/boot"
sudo mount "$(partition UEFI)" "$root/boot/efi"
sudo bash "$source_dir/prepare-guest.sh" "$root" "$output/release.json"
sudo fstrim "$root" || true
unmount_guest
sudo qemu-nbd --disconnect "$nbd"
nbd_connected=false
nbd=
flock -u 9
qemu-img check "$disk"
qemu-img convert -p -f qcow2 -O vmdk -o subformat=monolithicSparse "$disk" "$work/appliance.vmdk"
VBoxManage createvm --name "$name" --ostype Ubuntu_64 --basefolder "$work" --register
registered=true
VBoxManage modifyvm "$name" --memory 8192 --cpus 6 --ioapic on --acpi on \
    --firmware efi64 --rtc-use-utc on --nic1 nat --nic-type1 virtio \
    --nested-hw-virt off --paravirt-provider kvm --autostart-enabled off \
    --boot1 disk --boot2 none --boot3 none --boot4 none --graphicscontroller vmsvga
VBoxManage storagectl "$name" --name SATA --add sata --controller IntelAhci --portcount 1
VBoxManage storageattach "$name" --storagectl SATA --port 0 --device 0 --type hdd \
    --medium "$work/appliance.vmdk" --nonrotational on --discard on
mac=$(VBoxManage showvminfo "$name" --machinereadable | sed -n 's/^macaddress1="\([A-Fa-f0-9]*\)"$/\1/p')
[[ "$mac" =~ ^[A-Fa-f0-9]{12}$ ]]
VBoxManage export "$name" --output "$work/box/box.ovf" --ovf20
printf '{"provider":"virtualbox","architecture":"amd64"}\n' > "$work/box/metadata.json"
printf 'Vagrant.configure("2") do |config|\n  config.vm.base_mac = "%s"\n  config.ssh.username = "vagrant"\n  config.vm.synced_folder ".", "/vagrant", disabled: true\nend\n' \
    "$mac" > "$work/box/Vagrantfile"
cp "$output/release.json" "$work/box/info.json"
tar -cf "$output/$box" -C "$work/box" .
cp "$source_dir/Vagrantfile" "$source_dir/package-release.sh" "$output/"
sed -e "s/rdkeasymesh-0908/rdkeasymesh-${release_id}/g" \
    -e "s/rdk-0908/rdk-${release_id}/g" \
    -e "s/rdk-virtualbox-0908/rdk-virtualbox-${release_id}/g" \
    -e 's/replacement 0908 download/replacement release download/g' \
    "$source_dir/README.md" > "$output/README.md"
(cd "$output"; sha256sum "$box" > "$box.sha256"; \
    sha256sum "$box" "$box.sha256" Vagrantfile README.md release.json \
        source-release.json adapter-files.sha256 adapter-source.tar.gz package-release.sh > SHA256SUMS)
VBoxManage unregistervm "$name"
registered=false
echo "Created $output/$box. Qualify an actual vagrant up before publishing."
