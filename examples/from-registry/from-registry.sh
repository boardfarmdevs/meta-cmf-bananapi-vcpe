#!/bin/bash
#
# Pull an OCI image from a registry (Docker Hub, ghcr, quay, ...) and produce
# a DAC bundle deployable via `dsmcli du.install`.
#
# Uses docker on the host (already installed) — no skopeo/umoci required.
#
# Usage:
#   ./from-registry.sh                            # default: hello-world:latest
#   ./from-registry.sh busybox:latest
#   ./from-registry.sh i386/alpine:3.18
#   ./from-registry.sh ghcr.io/foo/bar:tag /tmp/my-out
#
# Output:  <out-dir>/<image-basename>.tar         (flat DAC bundle layout)

set -euo pipefail

IMAGE=${1:-hello-world:latest}
OUT_DIR=${2:-$(cd "$(dirname "$0")" && pwd)/out}
PLATFORM=${PLATFORM:-linux/386}                  # vCPE is i686

NAME=$(basename "${IMAGE%:*}")                   # ghcr.io/foo/bar:tag -> bar
TAG=${IMAGE##*:}; [ "$TAG" = "$IMAGE" ] && TAG=latest

mkdir -p "$OUT_DIR"
work=$(mktemp -d)
trap 'rm -rf "$work"; docker rm "$cid" 2>/dev/null || true' EXIT

# 1. Pull at target platform
echo ">> docker pull --platform $PLATFORM $IMAGE"
docker pull --platform "$PLATFORM" "$IMAGE" >/dev/null
arch=$(docker inspect "$IMAGE" --format '{{.Architecture}}')
[ "$arch" = "386" ] || { echo "WARNING: pulled arch '$arch' (wanted 386). vCPE may not run it."; }

# 2. Inspect image metadata for entrypoint / cmd / env / workdir
ep=$(docker inspect "$IMAGE" --format '{{json .Config.Entrypoint}}')
cmd=$(docker inspect "$IMAGE" --format '{{json .Config.Cmd}}')
env=$(docker inspect "$IMAGE" --format '{{json .Config.Env}}')
wd=$(docker inspect  "$IMAGE" --format '{{.Config.WorkingDir}}')

if   [ "$ep" = "null" ]; then args="$cmd"
elif [ "$cmd" = "null" ]; then args="$ep"
else args=$(jq -nc --argjson a "$ep" --argjson b "$cmd" '$a + $b')
fi
[ "$env" = "null" ] && env='["PATH=/usr/sbin:/usr/bin:/sbin:/bin","TERM=xterm"]'
[ -z "$wd" ] && wd="/"

echo ">> args: $args"
echo ">> env : $env"
echo ">> cwd : $wd"

# 3. Export the rootfs (`docker export` gives a flat fs, no layer logic)
cid=$(docker create --platform "$PLATFORM" "$IMAGE")
mkdir -p "$work/$NAME/rootfs"
echo ">> exporting rootfs"
docker export "$cid" | tar -xf - -C "$work/$NAME/rootfs"

# 4. Render config.json — uses ociVersion 1.0.2-dobby so Dobby loads the
#    Logging plugin and stdout is captured to journald.
cat > "$work/$NAME/config.json" <<EOF
{
  "ociVersion": "1.0.2-dobby",
  "process": {
    "terminal": false,
    "user": { "uid": 0, "gid": 0 },
    "args": $args,
    "env": $env,
    "cwd": "$wd",
    "capabilities": {
      "bounding":    ["CAP_AUDIT_WRITE","CAP_KILL","CAP_NET_BIND_SERVICE"],
      "effective":   ["CAP_AUDIT_WRITE","CAP_KILL","CAP_NET_BIND_SERVICE"],
      "inheritable": ["CAP_AUDIT_WRITE","CAP_KILL","CAP_NET_BIND_SERVICE"],
      "permitted":   ["CAP_AUDIT_WRITE","CAP_KILL","CAP_NET_BIND_SERVICE"],
      "ambient":     ["CAP_AUDIT_WRITE","CAP_KILL","CAP_NET_BIND_SERVICE"]
    },
    "rlimits": [{ "type": "RLIMIT_NOFILE", "hard": 1024, "soft": 1024 }],
    "noNewPrivileges": true
  },
  "root": { "path": "rootfs", "readonly": true },
  "hostname": "$NAME",
  "mounts": [
    { "destination": "/proc", "type": "proc", "source": "proc" },
    { "destination": "/dev",  "type": "tmpfs", "source": "tmpfs",
      "options": ["nosuid","strictatime","mode=755","size=65536k"] },
    { "destination": "/dev/pts", "type": "devpts", "source": "devpts",
      "options": ["nosuid","noexec","newinstance","ptmxmode=0666","mode=0620","gid=5"] },
    { "destination": "/dev/shm", "type": "tmpfs", "source": "shm",
      "options": ["nosuid","noexec","nodev","mode=1777","size=65536k"] },
    { "destination": "/sys",  "type": "sysfs", "source": "sysfs",
      "options": ["nosuid","noexec","nodev","ro"] },
    { "destination": "/tmp",  "type": "tmpfs", "source": "tmpfs",
      "options": ["nosuid","nodev","mode=1777","size=65536k"] }
  ],
  "linux": {
    "resources": { "devices": [ { "allow": false, "access": "rwm" } ] },
    "namespaces": [
      { "type": "pid" },
      { "type": "ipc" },
      { "type": "uts" },
      { "type": "mount" }
    ],
    "maskedPaths": [
      "/proc/acpi","/proc/asound","/proc/kcore","/proc/keys",
      "/proc/latency_stats","/proc/timer_list","/proc/timer_stats",
      "/proc/sched_debug","/sys/firmware","/proc/scsi"
    ],
    "readonlyPaths": [
      "/proc/bus","/proc/fs","/proc/irq","/proc/sys","/proc/sysrq-trigger"
    ]
  },
  "rdkPlugins": {
    "logging": {
      "required": true,
      "data": { "sink": "journald", "journaldOptions": { "priority": "LOG_INFO" } }
    }
  }
}
EOF

# 5. Pack to flat DAC bundle layout (./rootfs/ + ./config.json)
tar -C "$work/$NAME" -cf "$OUT_DIR/$NAME.tar" rootfs config.json

echo
echo ">> built: $OUT_DIR/$NAME.tar ($(du -h "$OUT_DIR/$NAME.tar" | cut -f1))"
echo
cat <<EOF
Deploy to DAC:
  cp $OUT_DIR/$NAME.tar \\
    $(cd "$OUT_DIR/../.." && pwd)/hello-app/out/$NAME.tar
  lxc exec vcpe-002 -- bash -c '
    export DSM_CONFIG_FILE=/etc/dsm.config
    dsmcli du.install default http://192.168.2.150:8888/$NAME.tar
    sleep 3
    EU=\$(dsmcli eu.list 2>&1 | tr , "\\n" | grep -oE "\"[^\"]+\"" | tr -d "\"" | tail -1)
    echo "EU=\$EU"
    dsmcli eu.start "\$EU"
    sleep 2
    journalctl --since "30 sec ago" SYSLOG_IDENTIFIER="\$EU" --no-pager | tail
  '
EOF
