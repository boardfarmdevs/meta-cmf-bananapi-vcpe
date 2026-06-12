#!/bin/sh
# Build a minimal OCI bundle ("hello") that is binary-compatible with the
# qemux86bpibroadband vCPE LXC image (i686 / glibc).
#
# Sources busybox + ld-linux + libc straight out of the built target rootfs
# tarball so it can't diverge from what the container is running.
#
# Output:  hello.tar  (drop into /home/root/repo/ on the container)
#
# Usage:   ./build-bundle.sh [path-to-rootfs.tar.gz] [output-dir]
#          Defaults pick the newest X86EMLTRBPIBB_*.rootfs.tar.gz under
#          ../../../build-qemux86bpibroadband/tmp/deploy/images/qemux86bpibroadband/.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
rootfs_tar=${1:-}
out_dir=${2:-$here/out}

if [ -z "${rootfs_tar}" ]; then
    deploy="$here/../../../build-qemux86bpibroadband/tmp/deploy/images/qemux86bpibroadband"
    rootfs_tar=$(ls -1t "$deploy"/X86EMLTRBPIBB_*.rootfs.tar.gz 2>/dev/null | head -n1 || true)
fi
if [ -z "${rootfs_tar}" ] || [ ! -f "${rootfs_tar}" ]; then
    echo "ERROR: no rootfs tarball found. Pass one as the first argument." >&2
    exit 1
fi

echo ">> using rootfs: $rootfs_tar"
mkdir -p "$out_dir"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

bundle="$work/hello"
mkdir -p "$bundle/rootfs/bin" "$bundle/rootfs/lib" \
         "$bundle/rootfs/proc" "$bundle/rootfs/sys" "$bundle/rootfs/dev" \
         "$bundle/rootfs/tmp" "$bundle/rootfs/etc"

# Pull i686 busybox + glibc loader/libc out of the target rootfs tar.
# Use a stripped path list so we only pay for what we need.
tar -xzf "$rootfs_tar" -C "$work" \
    ./bin/busybox.nosuid \
    ./lib/ld-linux.so.2 \
    ./lib/libc.so.6 \
    ./lib/libm.so.6

install -m 0755 "$work/bin/busybox.nosuid" "$bundle/rootfs/bin/busybox"
install -m 0755 "$work/lib/ld-linux.so.2"  "$bundle/rootfs/lib/ld-linux.so.2"
install -m 0755 "$work/lib/libc.so.6"      "$bundle/rootfs/lib/libc.so.6"
install -m 0755 "$work/lib/libm.so.6"      "$bundle/rootfs/lib/libm.so.6"

# Common busybox applet symlinks (just what we need to be useful)
for a in sh ls cat echo sleep ps hostname uname env mount printf ash; do
    ln -s busybox "$bundle/rootfs/bin/$a"
done

# OCI runtime config
install -m 0644 "$here/config.json" "$bundle/config.json"

# DSM extracts hello.tar INTO /home/root/destination/hello/ and then looks
# for config.json at the top of that dir.  So the archive itself must contain
# config.json and rootfs/ at the top level -- not nested under a "hello/" dir.
# (The upstream README's "[package-name]/rootfs & [package-name]/config.json"
# layout is wrong for this implementation.)
tar -C "$bundle" -cf "$out_dir/hello.tar" .

echo
echo ">> built: $out_dir/hello.tar"
ls -la "$out_dir/hello.tar"
echo
echo "Next steps:"
echo "  scp $out_dir/hello.tar root@<lxc-ip>:/home/root/repo/"
echo "  lxc exec vcpe-002 -- dsmcli du.install default hello"
echo "  lxc exec vcpe-002 -- dsmcli eu.list"
echo "  lxc exec vcpe-002 -- dsmcli eu.start <uid>"
echo "  lxc exec vcpe-002 -- DobbyTool list"
