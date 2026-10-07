#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
# shellcheck source=profile.sh
source "$root/gen/vm/lxd/profile.sh"
source "$root/gen/vm/lxd/instance-config.sh"
# shellcheck source-path=SCRIPTDIR source=../../build/artifact-store.sh
source "$root/gen/build/artifact-store.sh"
release_id=${EASYMESH_RELEASE_ID:-dev}
case "$release_id" in
    [a-zA-Z0-9][a-zA-Z0-9._-]*) ;;
    *) echo "invalid EASYMESH_RELEASE_ID: $release_id" >&2; exit 2 ;;
esac
default_host_address=$(ip -4 route get 1.1.1.1 2>/dev/null \
    | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')
default_host_address=${default_host_address:-127.0.0.1}
profile=$(easymesh_profile_name "${EASYMESH_LAB_PROFILE:-unified}")
profile_clients=$(easymesh_profile_clients "$profile")
profile_radios=$(easymesh_profile_radios "$profile")
name=$(easymesh_instance_name)
release_name=$name
image=${EASYMESH_LXD_IMAGE:-ubuntu:24.04}
cpus=${EASYMESH_LXD_CPUS:-$(easymesh_profile_cpus "$profile")}
memory=${EASYMESH_LXD_MEMORY:-$(easymesh_profile_memory "$profile")}
disk=${EASYMESH_LXD_DISK:-$(easymesh_profile_disk "$profile")}
kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
network=${EASYMESH_LXD_NETWORK:-lxdbr0}
storage=$(easymesh_instance_storage "$name")
port_base=$(easymesh_instance_port_base "$name")
guest_ipv4=${EASYMESH_LXD_IPV4:-}
webui_address=${EASYMESH_WEBUI_HOST_IP:-$default_host_address}
webui_port=${EASYMESH_WEBUI_PORT:-$((port_base + 0))}
console_address=${WMEDIUMD_CONSOLE_HOST_IP:-$webui_address}
console_port=${WMEDIUMD_CONSOLE_PORT:-$((port_base + 1))}
room_address=${EASYMESH_ROOM_DEMO_HOST_IP:-$webui_address}
room_port=${EASYMESH_ROOM_DEMO_PORT:-$((port_base + 2))}
http_ready_timeout=${EASYMESH_LXD_HTTP_READY_TIMEOUT:-240}
boardfarm_commit=${EASYMESH_BOARDFARM_COMMIT:-ddb5a2b9e1707562595afc7e4000a3b8efa3cd81}
boardfarm_source=${EASYMESH_BOARDFARM_SOURCE:-git@github.com:robvogelaar/boardfarm-lab-staging.git}
controller_image=${EASYMESH_CONTROLLER_IMAGE:-}
extender_image=${EASYMESH_EXTENDER_IMAGE:-}
export_dir=${EASYMESH_LXD_EXPORT_DIR:-$root/gen/vm/lxd/artifacts}
runtime_branch=${EASYMESH_RUNTIME_BRANCH:-$(git -C "$root" symbolic-ref --short HEAD)}
client_create_parallelism=${CLIENT_CREATE_PARALLELISM:-8}
wired_extenders=${EASYMESH_WIRED_EXTENDERS:-1}
emosa=${EASYMESH_EMOSA:-0}
emosa_lab=${EMOSA_LAB:-$(cd "$root/.." && pwd)/emosa-lab}
emosa_pin=$(sed -n 's/^EMOSA_LAB_COMMIT=//p' "$root/gen/vm/lxd/emosa-lab.env")
emosa_pod_image=${EMOSA_POD_IMAGE:-}
# where EMOSA's fleet and agents run: emosa-lab's adapter container, or the gateway, from the
# controller image's own package (an image built with BUILD_EMOSA=1, its adapter in C)
emosa_in=${EASYMESH_EMOSA_IN:-container}
if [ "$emosa_in" = gateway ]; then emosa_agent=${EASYMESH_EMOSA_AGENT:-c}; else emosa_agent=${EASYMESH_EMOSA_AGENT:-python}; fi
base_mode=${EASYMESH_BASE_IMAGE:-auto}
case "$base_mode" in auto|off|rebuild) ;; *) echo 'EASYMESH_BASE_IMAGE must be auto, off or rebuild' >&2; exit 2 ;; esac
# A development lab: fewer clients (half private, half IoT), quicker to build and lighter
# to run; no room service (it needs the full roster), never snapshot as accepted or exported.
dev_clients=${EASYMESH_DEV_CLIENTS:-}
if [ -n "$dev_clients" ] && { [[ ! $dev_clients =~ ^[1-9][0-9]$ ]] || [ $((dev_clients % 2)) -ne 0 ]; }; then
    echo "EASYMESH_DEV_CLIENTS must be an even number from 10 to 98 (the full lab has $profile_clients)" >&2
    exit 2
fi
lab_clients=${dev_clients:-$profile_clients}
[[ "$emosa" =~ ^[01]$ ]] || { echo 'EASYMESH_EMOSA must be 0 or 1' >&2; exit 2; }
[[ "$emosa_agent" =~ ^(python|c)$ ]] || { echo 'EASYMESH_EMOSA_AGENT must be python or c' >&2; exit 2; }
[[ "$emosa_in" =~ ^(container|gateway)$ ]] || { echo 'EASYMESH_EMOSA_IN must be container or gateway' >&2; exit 2; }
[ "$emosa_in" = container ] || [ "$emosa_agent" = c ] || {
    echo 'EASYMESH_EMOSA_IN=gateway runs the image'"'"'s adapter, in C: EASYMESH_EMOSA_AGENT=c' >&2
    exit 2
}
[[ "$client_create_parallelism" =~ ^[1-9][0-9]*$ ]] || {
    echo 'CLIENT_CREATE_PARALLELISM must be a positive integer' >&2
    exit 2
}

usage() {
    cat <<EOF
usage: $0 COMMAND

Commands:
  build       create, provision, reboot and accept a native LXD VM
  start       start an existing appliance VM and bring its lab up in order (gen/lab-bringup.sh)
  stop        stop it cleanly
  restart     restart it and wait for the EasyMesh service gate
  status      show VM and lab status
  check       run the complete lab acceptance audit
  snapshot    replace the accepted snapshot after a passing check
  export      check, stop and export a portable LXD VM backup bundle
  export-thin check, remove provisioned nodes and export the universal offline bundle
  update      move the accepted VM forward to this checkout's commit in place, without a
              build: its checkout and submodules (the medium, the optimizer) follow, the room
              service restarts and settles; when the commit changes what a build installs
              (the medium's daemon, console or radio module, the guest's services and
              tools) the update makes and installs that too and restarts the VM
  delete      delete only the named appliance VM after showing its identity (its evidence
              volume stays)
  copy NEW    copy the VM as NEW in its storage pool (seconds on btrfs or zfs), with its own
              identities, address and port block (EASYMESH_COPY_PORT_BASE overrides) and a
              copy of its evidence volume; left stopped: EASYMESH_LXD_NAME=NEW $0 start
              brings it up
  evidence    give a running lab built before its evidence had a volume one: attached and
              mounted, the evidence so far moved onto it, no restart (between suites)
  emosa       turn the EMOSA option on in the accepted lab VM: emosa-lab stages its adapter
              kit and the OpenSync pod image, then runs its option (EMOSA, fleet, the pods'
              gateway, two pods, telemetry, their Wi-Fi backhaul, the rooms with the pods)

Build inputs:
  EASYMESH_CONTROLLER_IMAGE=/path/to/controller.rootfs.lxc.tar.bz2
  EASYMESH_EXTENDER_IMAGE=/path/to/extender.rootfs.lxc.tar.bz2

Common overrides:
  EASYMESH_LAB_PROFILE=$profile_clients (fixed capacity: 100 clients)
  EASYMESH_DEV_CLIENTS=20 (a development lab: that many clients, no room service; never
              snapshot as accepted or exported)
  EASYMESH_LAB_NAME=$name
  EASYMESH_LXD_NAME=$name
  EASYMESH_LXD_CPUS=$cpus
  EASYMESH_LXD_MEMORY=$memory
  EASYMESH_LXD_NETWORK=$network
  EASYMESH_LXD_STORAGE=$storage (the host's ZFS pool for lab VMs, created if absent:
    EASYMESH_LXD_STORAGE_DRIVER zfs, EASYMESH_LXD_STORAGE_SIZE 500GiB; dir for a pool of
    the lab's own; an existing lab stays in the pool it is in)
  EASYMESH_EVIDENCE_SIZE=${EASYMESH_EVIDENCE_SIZE:-20GiB} (the room evidence on a volume of its own,
    $name-evidence in the lab's pool at $easymesh_evidence_path, kept when
    the lab is deleted; 0: none, the evidence on the VM's disk)
  EASYMESH_PORT_BASE=$port_base (WebUI, Console and room use base, base+1 and base+2)
  EASYMESH_LXD_IPV4=<automatic static address>
  EASYMESH_WEBUI_HOST_IP=$webui_address
  EASYMESH_WEBUI_PORT=$webui_port
  WMEDIUMD_CONSOLE_PORT=$console_port
  EASYMESH_ROOM_DEMO_PORT=$room_port
  EASYMESH_LXD_HTTP_READY_TIMEOUT=$http_ready_timeout
  CLIENT_CREATE_PARALLELISM=$client_create_parallelism (fresh-roster workers; default: 8)
  EASYMESH_SHARED_HOST=${EASYMESH_SHARED_HOST:-0} (1: build and check although another lab VM
    runs on this host; its load can cost the 100-client traffic check packets)
  EASYMESH_WIRED_EXTENDERS=$wired_extenders (extenders on a wired backhaul next to the four
    Wi-Fi extenders: 1, bpiap-004, the rooms with it; 0, the Wi-Fi extenders only)

The EMOSA option (emosa-lab, on the lab's wired LAN port; needs the wired extender):
  EASYMESH_EMOSA=$emosa (1: build turns it on once the lab is accepted, as emosa does)
  EMOSA_LAB=$emosa_lab (the emosa-lab checkout, clean at the commit gen/vm/lxd/emosa-lab.env
    pins, ${emosa_pin:0:10}; EMOSA_LAB_UNPINNED=1 takes another)
  EASYMESH_EMOSA_AGENT=$emosa_agent (the adapter's implementation: python, the reference, or c,
    its fleet, GTP and agents in C with no Python installed; lab.sh agent POD python|c in
    the VM swaps one pod's agent later)
  EASYMESH_EMOSA_IN=$emosa_in (container: EMOSA's fleet and agents in emosa-lab's adapter
    container; gateway: then in the gateway, from the controller image's own package, its
    state on /nvram: an image from gen/build/build-images.sh with BUILD_EMOSA=1, the adapter
    in C, EASYMESH_EMOSA_AGENT=c)
  EMOSA_POD_IMAGE=<.../out/mvx-pod-STAMP> (the OpenSync pod image the easymesh-labs
    manifest pins, from opensync-lab's build-pod.sh)
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "required command is missing: $1" >&2
        exit 1
    }
}

# Lab VMs share a host badly: with prpl-1001 running next to it, 19 of rdk-1001's 100
# clients lost packets in its build's traffic check, alone one did and later checks passed
# (rev140, 1 Oct). A lab VM, RDK or prplMesh, is one with a wmediumd Console proxy.
other_running_labs() {
    lxc list --format json | python3 -c '
import json, sys
print(" ".join(i["name"] for i in json.load(sys.stdin) if i["name"] != sys.argv[1]
               and i["status"] == "Running" and "wmediumd-console" in (i.get("expanded_devices") or {})))' "$name"
}

require_host_to_itself() {
    local others
    [ "${EASYMESH_SHARED_HOST:-0}" = 1 ] && return
    others=$(other_running_labs)
    [ -z "$others" ] || {
        echo "another lab VM runs on this host ($others): stop it first, or set EASYMESH_SHARED_HOST=1" >&2
        echo "(its load can cost this lab's 100-client traffic check packets)" >&2
        exit 1
    }
}

instance_exists() {
    lxc info "$name" >/dev/null 2>&1
}

instance_state() {
    lxc info "$name" 2>/dev/null | sed -n 's/^Status: //p'
}

wait_agent() {
    local attempt
    for attempt in $(seq 1 120); do
        if lxc exec "$name" -- true >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "$name did not expose its LXD VM agent after 240 seconds" >&2
    return 1
}

wait_http_ready() {
    local label=$1 url=$2 deadline remaining request_timeout delay
    case "$http_ready_timeout" in
        ''|*[!0-9]*|0)
            echo "EASYMESH_LXD_HTTP_READY_TIMEOUT must be a positive integer" >&2
            return 2
            ;;
    esac
    # LXD's outer proxy may answer 503 briefly after the VM agent and the
    # guest-side service are ready. Bound the wait independently from each
    # connection/response attempt and require the real endpoint to return 2xx.
    deadline=$((SECONDS + http_ready_timeout))
    while [ "$SECONDS" -lt "$deadline" ]; do
        remaining=$((deadline - SECONDS))
        [ "$remaining" -gt 0 ] || break
        request_timeout=$remaining
        [ "$request_timeout" -le 10 ] || request_timeout=10
        if curl -fsS --connect-timeout 2 --max-time "$request_timeout" \
            "$url" >/dev/null; then
            printf '%s ready: %s\n' "$label" "$url"
            return 0
        fi
        remaining=$((deadline - SECONDS))
        [ "$remaining" -gt 0 ] || break
        delay=$remaining
        [ "$delay" -le 2 ] || delay=2
        sleep "$delay"
    done
    printf '%s did not become ready within %ss: %s\n' \
        "$label" "$http_ready_timeout" "$url" >&2
    return 1
}

select_guest_ipv4() {
    local cidr used
    if [ -n "$guest_ipv4" ]; then
        printf '%s\n' "$guest_ipv4"
        return
    fi
    cidr=$(lxc network get "$network" ipv4.address)
    used=$(lxc network list-leases "$network" --format csv \
        | awk -F, '$3 ~ /^[0-9]+\./ {print $3}' | paste -sd, -)
    python3 - "$cidr" "$used" <<'PY'
import ipaddress
import sys

network = ipaddress.ip_network(sys.argv[1], strict=False)
if network.num_addresses < 16:
    raise SystemExit(f"managed bridge is too small for an appliance address: {network}")
used = {ipaddress.ip_address(value) for value in sys.argv[2].split(",") if value}
for offset in range(5, min(network.num_addresses - 2, 256)):
    candidate = network.broadcast_address - offset
    if candidate not in used:
        print(candidate)
        break
else:
    raise SystemExit(f"no free appliance address found near the end of {network}")
PY
}

add_proxy() {
    local device=$1 address=$2 host_port=$3 guest_port=$4 guest_address=$5
    if lxc config device get "$name" "$device" listen >/dev/null 2>&1; then
        lxc config device remove "$name" "$device"
    fi
    # LXD VMs support proxy devices only in NAT mode. The static NIC address
    # lets LXD install direct host-to-guest forwarding rules without a helper
    # process or dependency on the VM agent after boot.
    lxc config device add "$name" "$device" proxy nat=true \
        listen="tcp:$address:$host_port" \
        connect="tcp:$guest_address:$guest_port"
}

# Build records: a build, an update or a copy writes its phases and their durations next
# to the BPI images' build evidence (the workspace's build-evidence/), as KIND-NAME-STAMP/:
# environment.txt, phases.tsv, summary.txt, exit-code (and failed-phase when one failed).
records_root=${EASYMESH_BUILD_RECORDS:-$(cd "$root/.." && pwd)/build-evidence}
record_dir=
phase_name=
phase_start=

record_open() {     # record_open KIND
    local kind=$1 stamp
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    record_dir=$records_root/$kind-$name-$stamp
    mkdir -p "$record_dir"
    printf 'phase\tstarted\tseconds\n' > "$record_dir/phases.tsv"
    {
        printf 'LAB=%s\nKIND=%s\nHOST=%s\nSTARTED=%s\n' "$name" "$kind" "$(hostname)" "$stamp"
        printf 'COMMIT=%s\n' "$(git -C "$root" rev-parse HEAD)"
        printf 'IMAGE=%s\nKERNEL=%s\nCPUS=%s\nMEMORY=%s\n' "$image" "$kernel" "$cpus" "$memory"
        printf 'STORAGE=%s\nSTORAGE_DRIVER=%s\n' "$(storage_pool)" "$(storage_driver)"
        printf 'CLIENT_CREATE_PARALLELISM=%s\nSHARED_HOST=%s\n' \
            "$client_create_parallelism" "${EASYMESH_SHARED_HOST:-0}"
    } > "$record_dir/environment.txt"
    ln -sfn "$(basename "$record_dir")" "$records_root/latest-$kind-$name"
    printf 'build record: %s\n' "$record_dir" >&2
}

phase() {           # phase NAME: end the running phase and start NAME ('' only ends it)
    local now
    now=$(date +%s)
    if [ -n "$phase_name" ] && [ -n "$record_dir" ]; then
        printf '%s\t%s\t%s\n' "$phase_name" "$phase_start" "$((now - phase_start))" \
            >> "$record_dir/phases.tsv"
        printf '[phase] %s: %ss\n' "$phase_name" "$((now - phase_start))" >&2
    fi
    phase_name=$1
    phase_start=$now
}

record_close() {    # record_close STATUS
    local status=$1 failed=$phase_name
    [ -n "$record_dir" ] || return 0
    phase ''
    printf '%s\n' "$status" > "$record_dir/exit-code"
    [ "$status" = 0 ] || printf '%s\n' "$failed" > "$record_dir/failed-phase"
    awk -F'\t' 'NR > 1 { printf "%-24s %6d s %6.1f min\n", $1, $3, $3 / 60; total += $3 }
        END { printf "%-24s %6d s %6.1f min\n", "total", total, total / 60 }' \
        "$record_dir/phases.tsv" > "$record_dir/summary.txt"
    cat "$record_dir/summary.txt" >&2
    record_dir=
}

# The base VM image: the build's stages that do not depend on the commit (00-base.sh,
# 10-install-linux-7.sh, 15-prepare-base.sh, 30-boardfarm-wan.sh: the OS and its
# packages, the kernel, nested LXD, Boardfarm and its WAN, the radio module) as an LXD
# image named by their inputs. A build starts from it when this host or the artifact store
# has it, and otherwise makes it on the way (EASYMESH_BASE_IMAGE=auto); off builds every
# stage; rebuild makes it anew.
base_image_key() {
    local file medium
    local -a inputs=("image=$image" "kernel=$kernel" "radios=$profile_radios"
        "boardfarm=$boardfarm_commit" "lxd=${EASYMESH_LXD_CHANNEL:-latest/stable}"
        "nested-storage=${EASYMESH_NESTED_LXD_STORAGE_DRIVER:-btrfs}"
        "alpine=${EASYMESH_ALPINE_REMOTE:-images:alpine/3.22/amd64}" "layout=1")
    for file in 00-base.sh 10-install-linux-7.sh 15-prepare-base.sh 30-boardfarm-wan.sh \
        guest/easymesh-lxd-docker-forward guest/easymesh-lxd-docker-forward.service \
        guest/boardfarm-lab-rebuild guest/boardfarm-lab.service \
        guest/boardfarm-lab-images.patch; do
        inputs+=("$file=$(git -C "$root" rev-parse "HEAD:gen/vm/scripts/$file")")
    done
    medium=$(git -C "$root" rev-parse HEAD:gen/medium)
    inputs+=("hwsim=$(git -C "$root/gen/medium" rev-parse "$medium:hwsim")")
    artifact_key "${inputs[@]}"
}

base_image_available() {    # base_image_available ALIAS KEY: on this host, or fetched
    local alias=$1 key=$2 fetched
    local -a files
    [ "$base_mode" = auto ] || return 1
    lxc image info "$alias" >/dev/null 2>&1 && return 0
    fetched=$(mktemp -d /tmp/easymesh-base-image.XXXXXX)
    if artifact_fetch rdk-base-vm "$key" "$fetched"; then
        mapfile -t files < <(find "$fetched" -maxdepth 1 -type f ! -name SHA256SUMS \
            ! -name provenance.env -printf '%s %p\n' | sort -n | cut -d' ' -f2-)
        lxc image import "${files[@]}" --alias "$alias" </dev/null
        rm -rf -- "$fetched"
        return 0
    fi
    rm -rf -- "$fetched"
    return 1
}

publish_base_image() {      # publish_base_image ALIAS KEY: the stopped-and-restarted build
    local alias=$1 key=$2 exported
    # shellcheck disable=SC2016 # the guest's shell expands these
    lxc exec "$name" -- sh -eu -c '
        rm -rf /home/easymesh/easymesh-assets/* /home/easymesh/easymesh-provision/*
        apt-get clean
        journalctl --rotate >/dev/null 2>&1 || true
        journalctl --vacuum-time=1s >/dev/null 2>&1 || true
        printf "%s\n" "$1" > /var/lib/easymesh-lab/base-image.key
        sync' sh "$key"
    lxc stop "$name" --timeout 300
    if lxc image info "$alias" >/dev/null 2>&1; then
        lxc image delete "$alias"
    fi
    lxc publish "$name" --alias "$alias" --compression zstd \
        description="EasyMesh RDK lab base VM ($key)" </dev/null
    lxc start "$name"
    wait_agent
    # Boardfarm reconstructs its WAN at boot (a minute or more): the build goes on from
    # the state 30-boardfarm-wan.sh left, as a lab from the base image does after it.
    run_root systemctl start boardfarm-lab.service easymesh-lxd-docker-forward.service
    if [ -n "${EASYMESH_ARTIFACT_PUBLISH:-}" ]; then
        exported=$(mktemp -d /tmp/easymesh-base-export.XXXXXX)
        lxc image export "$alias" "$exported/" </dev/null
        {
            printf 'KEY=%s\nCOMMIT=%s\nBUILT=%s\nHOST=%s\n' "$key" \
                "$(git -C "$root" rev-parse HEAD)" "$(date -u +%FT%TZ)" "$(hostname)"
            printf 'IMAGE=%s\nKERNEL=%s\nRADIOS=%s\n' "$image" "$kernel" "$profile_radios"
        } > "$exported/provenance.env"
        artifact_publish rdk-base-vm "$key" "$exported"
        rm -rf -- "$exported"
    fi
}

storage_pool() {    # the pool the instance is in (a copy's is its original's), or this lab's
    lxc config device get "$name" root pool 2>/dev/null | grep . || printf '%s\n' "$storage"
}

storage_driver() {  # the driver of that pool, or the one a build would create
    lxc storage show "$(storage_pool)" 2>/dev/null | awk '$1 == "driver:" {print $2; exit}' \
        | grep . || printf '%s\n' "${EASYMESH_LXD_STORAGE_DRIVER:-dir}"
}

# The lab's evidence volume (instance-config.sh) mounted in the running guest, its root as the
# directory's was, root's and readable (a new volume's is 0711). Nothing to do without one.
evidence_ready() {
    local tries=30
    lxc config device get "$name" evidence source >/dev/null 2>&1 || return 0
    until run_root mountpoint -q "$easymesh_evidence_path"; do
        tries=$((tries - 1))
        [ "$tries" -gt 0 ] || {
            echo "$name: the evidence volume is not mounted at $easymesh_evidence_path" >&2
            return 1
        }
        sleep 2
    done
    run_root chmod 0755 "$easymesh_evidence_path"
}

# lxc export of the stopped lab without its evidence volume: LXD refuses to import a backup
# with a custom volume attached ("More than one primary volume is defined in backup config"),
# and the volume is this host's. The device comes back after the export as it was.
export_instance() {     # export_instance OUTPUT
    local output=$1 pool='' volume='' status=0
    if volume=$(lxc config device get "$name" evidence source 2>/dev/null); then
        pool=$(lxc config device get "$name" evidence pool)
        lxc config device remove "$name" evidence </dev/null
    fi
    lxc export "$name" "$output" --instance-only --compression zstd </dev/null || status=$?
    [ -z "$volume" ] || lxc config device add "$name" evidence disk pool="$pool" \
        source="$volume" path="$easymesh_evidence_path" </dev/null
    return "$status"
}

# A lab of its own evidence: the volume attached to a running lab, the evidence it has so
# far moved onto it, no restart (the room service paused for the move, as for a check).
# Between suites: a run in progress loses what it writes during the move.
evidence_vm() (
    [ "${EASYMESH_EVIDENCE_SIZE:-20GiB}" != 0 ] || { echo 'EASYMESH_EVIDENCE_SIZE=0: no evidence volume' >&2; exit 2; }
    instance_exists
    [ "$(instance_state)" = RUNNING ] || { echo "$name is not running: start it first" >&2; exit 1; }
    wait_agent
    restore_room=false
    trap 'result=$?; if "$restore_room"; then run_root systemctl start easymesh-room-service.service || result=$?; fi; exit "$result"' EXIT
    case "$(run_root systemctl show easymesh-room-service.service -p ActiveState --value)" in
        active|activating) restore_room=true ;;
    esac
    run_root systemctl stop easymesh-room-service.service
    if ! lxc config device get "$name" evidence source >/dev/null 2>&1; then
        # the evidence so far aside; an unfinished earlier move's is already there
        run_root sh -eu -c 'dir=$1
            if [ -e "$dir.moving" ] && [ -e "$dir" ]; then
                echo "both $dir and $dir.moving: an earlier move did not finish; merge them" >&2
                exit 1
            fi
            [ ! -e "$dir" ] || mv -- "$dir" "$dir.moving"' sh "$easymesh_evidence_path"
        easymesh_attach_evidence "$name" "$(storage_pool)"
    fi
    evidence_ready
    run_root sh -eu -c 'dir=$1; if [ -d "$dir.moving" ]; then
            cp -a -- "$dir.moving/." "$dir/"; rm -rf -- "$dir.moving"; fi' sh "$easymesh_evidence_path"
    run_root df -h "$easymesh_evidence_path" | awk -v volume="$(lxc config device get "$name" evidence source)" \
        'NR == 2 {print "evidence: " $3 " of " $2 " on volume " volume}'
)

make_bundle() {
    local repo=$1 commit=$2 output=$3 ref=refs/heads/lxd-appliance-export
    git -C "$repo" rev-parse --git-dir >/dev/null  # a repository or a submodule
    test -z "$(git -C "$repo" status --porcelain)"
    git -C "$repo" cat-file -e "$commit^{commit}"
    git -C "$repo" update-ref "$ref" "$commit"
    git -C "$repo" bundle create "$output" "$ref"
    git -C "$repo" update-ref -d "$ref"
    git bundle verify "$output" >/dev/null
}

# The RF medium: easymesh-medium at the commit this lab pins (gen/medium). Its
# bundle becomes the guest's submodule; the daemon and the console are built here
# from that commit (the lab commits no binaries) and installed in the guest.
prepare_medium() {
    local stage=$1 assets=$1/assets medium=$root/gen/medium pinned
    pinned=$(git -C "$root" rev-parse HEAD:gen/medium)
    [ "$(git -C "$medium" rev-parse HEAD 2>/dev/null)" = "$pinned" ] || {
        echo "gen/medium is not at the pinned $pinned: git submodule update --init gen/medium" >&2
        exit 1
    }
    test -z "$(git -C "$medium" status --porcelain)"
    make_bundle "$medium" "$pinned" "$assets/easymesh-medium.bundle"
    "$medium/wmediumd/build-wmediumd.sh" --source "$stage/wmediumd-source" --output "$stage/wmediumd" >&2
    install -m 0755 "$stage/wmediumd/wmediumd" "$assets/wmediumd"
    install -m 0644 "$stage/wmediumd/wmediumd.provenance.env" "$assets/wmediumd.provenance.env"
    bash "$medium/observer/build.sh" "$assets/wmediumd-console" >&2
    test -z "$(git -C "$medium" status --porcelain)"
}

# The optimizer: easymesh-optimizer at the commit this lab pins (gen/optimizer). Its
# bundle becomes the guest's submodule, as the medium's.
prepare_optimizer() {
    local assets=$1/assets optimizer=$root/gen/optimizer pinned
    pinned=$(git -C "$root" rev-parse HEAD:gen/optimizer)
    [ "$(git -C "$optimizer" rev-parse HEAD 2>/dev/null)" = "$pinned" ] || {
        echo "gen/optimizer is not at the pinned $pinned: git submodule update --init gen/optimizer" >&2
        exit 1
    }
    make_bundle "$optimizer" "$pinned" "$assets/easymesh-optimizer.bundle"
}

prepare_assets() {
    local stage=$1 assets=$stage/assets boardfarm_repo=$stage/boardfarm-source
    local meta_commit
    install -d "$assets"
    meta_commit=$(git -C "$root" rev-parse HEAD)
    test -z "$(git -C "$root" status --porcelain)"
    make_bundle "$root" "$meta_commit" "$assets/meta-cmf-bananapi-vcpe.bundle"
    prepare_medium "$stage"
    prepare_optimizer "$stage"

    if [ -d "$boardfarm_source/.git" ]; then
        make_bundle "$boardfarm_source" "$boardfarm_commit" \
            "$assets/boardfarm-lab-staging.bundle"
    else
        git clone "$boardfarm_source" "$boardfarm_repo"
        git -C "$boardfarm_repo" checkout --detach "$boardfarm_commit"
        make_bundle "$boardfarm_repo" "$boardfarm_commit" \
            "$assets/boardfarm-lab-staging.bundle"
    fi

    test -f "$controller_image"
    test -f "$extender_image"
    cp --reflink=auto "$controller_image" "$assets/"
    cp --reflink=auto "$extender_image" "$assets/"
    (
        cd "$assets"
        sha256sum \
            "$(basename "$controller_image")" \
            "$(basename "$extender_image")" \
            boardfarm-lab-staging.bundle \
            meta-cmf-bananapi-vcpe.bundle \
            easymesh-medium.bundle easymesh-optimizer.bundle \
            wmediumd wmediumd.provenance.env wmediumd-console > SHA256SUMS
        sha256sum -c SHA256SUMS
    )
    printf '%s\n' "$meta_commit"
}

push_inputs() {
    local stage=$1 assets=$stage/assets provision=/home/easymesh/easymesh-provision
    local file
    lxc exec "$name" -- bash -eu -c '
        current_hostname=$(hostname)
        grep -Eq "^[^#]*[[:space:]]${current_hostname}([[:space:]]|$)" /etc/hosts || \
            printf "127.0.1.1 %s\n" "$current_hostname" >> /etc/hosts
        id easymesh >/dev/null 2>&1 || useradd -m -s /bin/bash easymesh
        install -d -o easymesh -g easymesh /home/easymesh/easymesh-assets
        install -d -o easymesh -g easymesh /home/easymesh/easymesh-provision
        install -m 0440 /dev/null /etc/sudoers.d/easymesh-lab
        printf "%s\n" "easymesh ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/easymesh-lab
    '
    for file in "$assets"/*; do
        lxc file push "$file" "$name/home/easymesh/easymesh-assets/$(basename "$file")"
    done
    for file in 00-base.sh 10-install-linux-7.sh 15-prepare-base.sh 20-prepare-lab-host.sh \
        30-boardfarm-wan.sh 40-deploy-easymesh.sh 50-runtime-service.sh \
        55-scale-topology.sh 56-wired-extenders.sh 70-health-audit.sh; do
        lxc file push --mode 0755 "$root/gen/vm/scripts/$file" \
            "$name$provision/$file"
    done

    declare -A guest_assets=(
        [easymesh-lxd-docker-forward]=gen/vm/scripts/guest/easymesh-lxd-docker-forward
        [easymesh-lxd-docker-forward.service]=gen/vm/scripts/guest/easymesh-lxd-docker-forward.service
        [boardfarm-lab-rebuild]=gen/vm/scripts/guest/boardfarm-lab-rebuild
        [boardfarm-lab.service]=gen/vm/scripts/guest/boardfarm-lab.service
        [boardfarm-lab-images.patch]=gen/vm/scripts/guest/boardfarm-lab-images.patch
        [easymesh-lab-runtime]=gen/vm/scripts/guest/easymesh-lab-runtime
        [easymesh-lab.service]=gen/vm/scripts/guest/easymesh-lab.service
        [easymesh-room-service.service]=gen/vm/scripts/guest/easymesh-room-service.service
        [easymesh-evidence-retention]=gen/vm/scripts/guest/easymesh-evidence-retention
        [easymesh-evidence-retention.service]=gen/vm/scripts/guest/easymesh-evidence-retention.service
        [easymesh-evidence-retention.timer]=gen/vm/scripts/guest/easymesh-evidence-retention.timer
        [easymesh-hwsim-pool]=gen/vm/scripts/guest/easymesh-hwsim-pool
        [easymesh-hwsim-pool.service]=gen/vm/scripts/guest/easymesh-hwsim-pool.service
        [lxd-easymesh-ordering.conf]=gen/vm/scripts/guest/lxd-easymesh-ordering.conf
        [easymesh-labctl]=gen/vm/scripts/guest/easymesh-labctl
        [easymesh-health-audit]=gen/vm/scripts/guest/easymesh-health-audit
        [easymesh-package-cleanup]=gen/vm/scripts/guest/easymesh-package-cleanup
        [easymesh-prepare-thin-package]=gen/vm/scripts/guest/easymesh-prepare-thin-package
        [easymesh-complete-thin-firstboot]=gen/vm/scripts/guest/easymesh-complete-thin-firstboot
        [easymesh-thin-firstboot]=gen/vm/scripts/guest/easymesh-thin-firstboot
        [easymesh-select-thin-profile]=gen/vm/scripts/guest/easymesh-select-thin-profile
        [easymesh-thin-firstboot.service]=gen/vm/scripts/guest/easymesh-thin-firstboot.service
    )
    for file in "${!guest_assets[@]}"; do
        lxc file push --mode 0755 "$root/${guest_assets[$file]}" \
            "$name/home/easymesh/easymesh-assets/$file"
    done
    lxc file push --mode 0755 "$root/gen/vm/scripts/60-scale-steering-test.sh" \
        "$name/home/easymesh/scale-steering-test.sh"
    lxc file push --mode 0755 "$root/gen/vm/scripts/55-scale-topology.sh" \
        "$name/home/easymesh/scale-topology.sh"
    lxc file push --mode 0755 "$root/gen/vm/scripts/61-return-steering-regression.sh" \
        "$name/home/easymesh/return-steering-test.sh"
    lxc file push --mode 0755 "$root/gen/vm/scripts/guest/easymesh-health-audit" \
        "$name/home/easymesh/health-audit.sh"
    lxc exec "$name" -- chown -R easymesh:easymesh \
        /home/easymesh/easymesh-assets /home/easymesh/easymesh-provision \
        /home/easymesh/scale-steering-test.sh /home/easymesh/scale-topology.sh \
        /home/easymesh/return-steering-test.sh /home/easymesh/health-audit.sh
}

run_root() {
    # Never a dialog in the guest: a build run from a terminal gives lxc exec one, and apt's
    # needrestart then stopped at "Pending kernel upgrade" (rev150, 6 October).
    lxc exec "$name" -- env EASYMESH_KERNEL="$kernel" \
        EASYMESH_RUNTIME_BRANCH="$runtime_branch" \
        DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1 "$@"
}

check_baseline() (
    restore_room=false
    trap 'result=$?; if "$restore_room"; then run_root systemctl start easymesh-room-service.service || result=$?; fi; exit "$result"' EXIT
    room_state=$(run_root systemctl show easymesh-room-service.service -p ActiveState --value)
    case "$room_state" in active|activating) restore_room=true ;; esac
    run_root systemctl stop easymesh-room-service.service || return
    run_root "$@" /usr/local/sbin/easymesh-labctl check
)

configure_no_secure_boot() {
    # LXD 6.9 exports boot.mode and rejects the retired
    # security.secureboot key during import.  Prefer the current spelling so
    # backups remain portable across maintained LXD releases; retain the old
    # key only for hosts old enough not to understand boot.mode.
    if lxc config set "$name" boot.mode uefi-nosecureboot 2>/dev/null; then
        lxc config unset "$name" security.secureboot 2>/dev/null || true
    else
        lxc config set "$name" security.secureboot false
    fi
}

set_root_disk_size() {
    if lxc config device show "$name" | grep -q '^root:'; then
        # Selecting --storage materializes root as a local instance device.
        lxc config device set "$name" root size "$disk"
    else
        # With the default pool, root is inherited from the default profile.
        lxc config device override "$name" root size="$disk"
    fi
}

clear_secure_boot_config() {
    # A backup must not contain either version-specific spelling.  The
    # importer sets the spelling supported by its own LXD before first boot.
    lxc config unset "$name" boot.mode 2>/dev/null || true
    lxc config unset "$name" security.secureboot 2>/dev/null || true
}

# The end of every build cleans up (easymesh-resources lab-storage W7): apt's lists and cache
# (every later install updates first), the VM's journal bounded at 256 MiB in 32 MiB files
# (W13; journald's default is 4 GiB on a 96 GiB disk, and the lab's own logs are in its
# containers and its evidence), Boardfarm's Docker build cache and dangling layers (again:
# the WAN step pruned them, W5, and its recovery path builds nothing), and the freed blocks
# returned to the host (the disk passes discard).
cleanup_vm() {
    run_root sh -eu -c '
        apt-get clean
        rm -rf /var/lib/apt/lists/*
        install -d /etc/systemd/journald.conf.d
        printf "[Journal]\nSystemMaxUse=256M\nSystemMaxFileSize=32M\n" > /etc/systemd/journald.conf.d/50-lab.conf
        systemctl restart systemd-journald
        journalctl -q --rotate || true
        journalctl -q --vacuum-size=256M || true
        if command -v docker >/dev/null; then
            docker builder prune -af >/dev/null || true
            docker image prune -f >/dev/null || true
        fi
        fstrim -a >/dev/null || true'
    lxc exec "$name" -- df -h / | awk 'NR == 2 {print "cleanup: the VM uses " $3 " of " $2}'
}

build_vm() {
    # stage is global: the EXIT trap that removes it runs after this function has returned
    local meta_commit controller_name extender_name appliance_ipv4 proxy_check_address wmediumd_sha
    local -a init_args
    require_command git
    require_command lxc
    require_command curl
    require_command sha256sum
    [ -n "$controller_image" ] || { echo 'set EASYMESH_CONTROLLER_IMAGE' >&2; exit 2; }
    [ -n "$extender_image" ] || { echo 'set EASYMESH_EXTENDER_IMAGE' >&2; exit 2; }
    [ "$emosa" = 0 ] || emosa_inputs
    require_host_to_itself
    instance_exists && {
        echo "$name already exists; delete it explicitly before a clean build" >&2
        exit 1
    }

    stage=$(mktemp -d /tmp/easymesh-lxd-build.XXXXXX)
    record_open build
    trap 'record_close "$?"; rm -rf -- "$stage"' EXIT
    phase assets
    meta_commit=$(prepare_assets "$stage" | tail -n 1)
    wmediumd_sha=$(sha256sum "$stage/assets/wmediumd" | awk '{print $1}')
    controller_name=$(basename "$controller_image")
    extender_name=$(basename "$extender_image")

    phase create
    base_key=$(base_image_key)
    base_alias=easymesh-rdk-base-$base_key
    from_base=false
    if base_image_available "$base_alias" "$base_key"; then
        from_base=true
    fi
    printf 'BASE_IMAGE=%s\nFROM_BASE_IMAGE=%s\nBASE_IMAGE_MODE=%s\nDEV_CLIENTS=%s\n' \
        "$base_alias" "$from_base" "$base_mode" "$dev_clients" >> "$record_dir/environment.txt"
    if "$from_base"; then
        init_args=(lxc init "$base_alias" "$name" --vm)
    else
        init_args=(lxc init "$image" "$name" --vm)
    fi
    init_args+=(--config limits.cpu="$cpus" --config limits.memory="$memory")
    easymesh_ensure_storage_pool "$storage"
    init_args+=(--storage "$storage")
    "${init_args[@]}" </dev/null
    # The appliance builds the narrowly-scoped multichannel hwsim module from
    # the exact Ubuntu source package. Disable guest Secure Boot before first
    # boot so that this locally-built module can load after installation.
    configure_no_secure_boot
    set_root_disk_size
    appliance_ipv4=$(select_guest_ipv4)
    lxc config device override "$name" eth0 network="$network" \
        ipv4.address="$appliance_ipv4"
    lxc config set "$name" boot.autostart false
    lxc config set "$name" user.easymesh.applied-commit "$meta_commit"
    # A lab from a base image shares the base's machine-id with every other one:
    # its address is pinned in the guest (pin_guest_address), as a copy's is.
    ! "$from_base" || lxc config set "$name" user.easymesh.pin-address true
    [ -z "$dev_clients" ] || lxc config set "$name" user.easymesh.dev-clients "$dev_clients"
    add_proxy easymesh-webui "$webui_address" "$webui_port" 8888 "$appliance_ipv4"
    add_proxy wmediumd-console "$console_address" "$console_port" 8890 "$appliance_ipv4"
    add_proxy room-demo-viewer "$room_address" "$room_port" 8891 "$appliance_ipv4"
    lxc start "$name"
    wait_agent
    pin_guest_address
    phase push-inputs
    push_inputs "$stage"

    if ! "$from_base"; then
        phase base-os
        run_root bash /home/easymesh/easymesh-provision/00-base.sh
        phase kernel
        run_root bash /home/easymesh/easymesh-provision/10-install-linux-7.sh
        lxc restart "$name" --timeout 300
        wait_agent
        test "$(lxc exec "$name" -- uname -r)" = "$kernel"

        phase base-host
        run_root env HWSIM_RADIOS="$profile_radios" \
            bash /home/easymesh/easymesh-provision/15-prepare-base.sh
        lxc restart "$name" --timeout 300
        wait_agent
    fi
    test "$(lxc exec "$name" -- uname -r)" = "$kernel"
    run_root bash -c 'test "$(cat /sys/module/cfg80211/version)" = lab-netns-owner-1'
    phase wan
    run_root bash /home/easymesh/easymesh-provision/30-boardfarm-wan.sh
    if ! "$from_base" && [ "$base_mode" != off ]; then
        phase base-image
        publish_base_image "$base_alias" "$base_key"
        push_inputs "$stage"
    fi

    phase lab-host
    # the room evidence on its volume from here on: the base image carries none
    easymesh_attach_evidence "$name" "$(storage_pool)"
    evidence_ready
    run_root env EASYMESH_RUNTIME_COMMIT="$meta_commit" \
        bash /home/easymesh/easymesh-provision/20-prepare-lab-host.sh
    # Nested LXD is a snap. A non-login `sudo -u` process launched through the
    # outer VM agent cannot be tracked by snapd, so appliance lifecycle runs as
    # root. Source checkout operations remain explicitly scoped to easymesh.
    phase mesh
    run_root env HOME=/home/easymesh \
        CONTROLLER_IMAGE="/home/easymesh/easymesh-assets/$controller_name" \
        EXTENDER_IMAGE="/home/easymesh/easymesh-assets/$extender_name" \
        EXPECTED_REPO_HEAD="$meta_commit" \
        EXPECTED_WMEDIUMD_SHA256="$wmediumd_sha" \
        bash /home/easymesh/easymesh-provision/40-deploy-easymesh.sh
    phase clients
    run_root env HOME=/home/easymesh \
        EXTENDER_IMAGE="/home/easymesh/easymesh-assets/$extender_name" \
        EASYMESH_SCALE_PROFILE="$profile" EASYMESH_DEV_CLIENTS="$dev_clients" \
        CLIENT_CREATE_PARALLELISM="$client_create_parallelism" \
        bash /home/easymesh/easymesh-provision/55-scale-topology.sh
    phase wired-extenders
    run_root env HOME=/home/easymesh EASYMESH_WIRED_EXTENDERS="$wired_extenders" \
        bash /home/easymesh/easymesh-provision/56-wired-extenders.sh
    phase runtime
    run_root env EASYMESH_SCALE_PROFILE="$profile" \
        HEALTH_EXPECT_CLIENTS="$lab_clients" \
        bash /home/easymesh/easymesh-provision/50-runtime-service.sh
    run_root bash /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/medium/observer/install.sh --start
    # A VM NAT proxy connects to the guest NIC, not to guest loopback. Keep the
    # Console's normal package default private, but bind its appliance instance
    # to the isolated guest interface so the host-side proxy can reach it.
    run_root sed -i \
        's/^WMEDIUMD_CONSOLE_LISTEN=.*/WMEDIUMD_CONSOLE_LISTEN=0.0.0.0:8890/' \
        /etc/default/wmediumd-console
    run_root systemctl restart wmediumd-console.service
    run_root systemctl enable easymesh-lab.service wmediumd-console.service

    phase cold-boot
    lxc restart "$name" --timeout 300
    wait_agent
    run_root systemctl start easymesh-lab.service
    phase acceptance
    check_baseline env HEALTH_EXPECT_CLIENTS="$lab_clients"
    proxy_check_address=$webui_address
    [ "$proxy_check_address" != 0.0.0.0 ] || proxy_check_address=$default_host_address
    wait_http_ready "EasyMesh WebUI proxy" \
        "http://$proxy_check_address:$webui_port/api/v1/topology"
    wait_http_ready "wmediumd Console NG proxy" \
        "http://$proxy_check_address:$console_port/api/v2/health"
    if [ -z "$dev_clients" ]; then
        wait_http_ready "Interactive room proxy" "http://$proxy_check_address:$room_port/healthz"
        run_root python3 /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/medium/observer/check-ready.py \
            --require-room --require-survey --timeout 120
    else
        # a development lab has no room service: the medium's telemetry is its gate
        run_root python3 /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/medium/observer/check-ready.py \
            --require-survey --timeout 120
    fi
    if [ "$emosa" != 0 ]; then
        phase emosa
        emosa_vm
    fi
    phase cleanup
    cleanup_vm
    # Export reruns the complete acceptance gate and excludes snapshots. Do
    # not duplicate a full VM disk automatically on non-copy-on-write pools.
    lxc config show "$name" --expanded
    trap - EXIT
    record_close 0
    rm -rf -- "$stage"
}

emosa_commit() {    # the emosa-lab checkout's commit, +dirty with tracked changes
    local commit
    commit=$(git -C "$emosa_lab" rev-parse HEAD 2>/dev/null) || return 1
    [ -z "$(git -C "$emosa_lab" status --porcelain --untracked-files=no)" ] || commit=$commit+dirty
    printf '%s\n' "$commit"
}

emosa_pinned() {    # EMOSA_LAB at the pinned commit, clean (EMOSA_LAB_UNPINNED=1: any, noted)
    local commit
    commit=$(emosa_commit) || { echo "no emosa-lab git checkout at $emosa_lab (EMOSA_LAB)" >&2; return 1; }
    [ "$commit" != "$emosa_pin" ] || return 0
    if [ "${EMOSA_LAB_UNPINNED:-0}" = 1 ]; then
        echo "note: emosa-lab ${commit:0:10}${commit:40}, not the pinned ${emosa_pin:0:10} (EMOSA_LAB_UNPINNED=1)" >&2
        return 0
    fi
    echo "emosa-lab at $emosa_lab is ${commit:0:10}${commit:40}, not the pinned" \
        "${emosa_pin:0:10} (gen/vm/lxd/emosa-lab.env): git -C $emosa_lab checkout $emosa_pin, or EMOSA_LAB_UNPINNED=1" >&2
    return 1
}

emosa_inputs() {
    [ "$wired_extenders" = 1 ] || {
        echo 'the EMOSA option needs the wired extender (EASYMESH_WIRED_EXTENDERS=1)' >&2
        exit 2
    }
    [ -x "$emosa_lab/deploy/rdk-lab/lab.sh" ] || {
        echo "no emosa-lab checkout at $emosa_lab (EMOSA_LAB)" >&2
        exit 2
    }
    emosa_pinned || exit 2
    [ -f "$emosa_pod_image.rootfs.tar.gz" ] && [ -f "$emosa_pod_image.metadata.tar.gz" ] || {
        echo 'set EMOSA_POD_IMAGE to the pinned OpenSync pod image (.../out/mvx-pod-STAMP)' >&2
        exit 2
    }
    # EMOSA in the gateway: the controller image must carry it, known before the build (its
    # listing read whole, about 15 s: grep -q would stop tar early, a failure under pipefail)
    if [ "$emosa_in" = gateway ] && [ -n "$controller_image" ] && ! instance_exists 2>/dev/null; then
        tar -tjf "$controller_image" 2>/dev/null | grep 'usr/bin/emosa-fleet-c$' >/dev/null || {
            echo "EASYMESH_EMOSA_IN=gateway: $controller_image has no EMOSA (build it with BUILD_EMOSA=1)" >&2
            exit 2
        }
    fi
}

emosa_vm() {
    # The EMOSA option, owned by emosa-lab: its host side stages the adapter kit and the pod
    # image into the VM, then its VM side runs every step (deploy/rdk-lab/vm/lab.sh up).
    emosa_inputs
    instance_exists
    [ "$(instance_state)" = RUNNING ] || { echo "$name is not running" >&2; exit 1; }
    [ "$(lxc exec "$name" -- lxc config get bpiap-004 user.easymesh.backhaul 2>/dev/null)" = wired ] || {
        echo "$name has no wired extender bpiap-004" >&2
        exit 1
    }
    if [ "$emosa_in" = gateway ]; then
        lxc exec "$name" -- lxc exec bpibroadband -- test -x /usr/bin/emosa-fleet-c || {
            echo "$name: its gateway has no EMOSA (EASYMESH_EMOSA_IN=gateway needs a BUILD_EMOSA=1 controller image)" >&2
            exit 1
        }
    fi
    EMOSA_VM=$name EMOSA_POD_IMAGE=$emosa_pod_image "$emosa_lab/deploy/rdk-lab/lab.sh" stage
    if [ "$emosa_in" = gateway ]; then
        EMOSA_VM=$name "$emosa_lab/deploy/rdk-lab/lab.sh" up "$emosa_agent" gateway
    else
        EMOSA_VM=$name "$emosa_lab/deploy/rdk-lab/lab.sh" up "$emosa_agent"
    fi
    lxc config set "$name" user.easymesh.emosa-lab "$(emosa_commit)"
    lxc config set "$name" user.easymesh.emosa-in "$emosa_in"
}

start_vm() {
    local started=false bringup=/home/easymesh/git/meta-cmf-bananapi-vcpe/gen/lab-bringup.sh
    instance_exists
    if [ "$(instance_state)" != RUNNING ]; then
        lxc start "$name"
        started=true
    fi
    wait_agent
    pin_guest_address
    # After a VM start an extender can come back with its backhaul or fronthaul down, or
    # registered with the controller without its BSSes (rdk-1001, 1 Oct, one BSS of ten):
    # the lab's ordered bring-up repairs that and waits for the room to settle. When the
    # runtime's own gate stops on it first (rdk-fast-c, 4 Oct: the wired extender's one BSS
    # of ten), the bring-up repairs and the runtime starts once more.
    if "$started" && emosa_option; then
        # A VM with the EMOSA option: its room service runs the rooms with the pods and
        # refuses to start until they operate, and the pods, the pods' GRE termination point
        # and EMOSA's containers do not autostart. So the bare bring-up would wait for a room
        # that cannot start (rdk-1004, 5 Oct); emosa-lab's step brings the pods back and runs
        # the lab's ordered bring-up itself (lab.sh rooms pods), then the runtime again.
        run_root systemctl start easymesh-lab.service ||
            echo "$name: the lab's runtime stopped at a gate; EMOSA's step, then the runtime again" >&2
        emosa_start || return 1
        run_root systemctl start easymesh-lab.service
        return
    fi
    if ! run_root systemctl start easymesh-lab.service; then
        "$started" && run_root test -x "$bringup" || return 1
        echo "$name: the lab's runtime stopped at a gate; ordered bring-up, then the runtime again" >&2
        run_root "$bringup" up
        run_root systemctl start easymesh-lab.service
        return
    fi
    if "$started" && run_root test -x "$bringup"; then
        run_root "$bringup" up
    fi
}

emosa_option() { [ -n "$(lxc config get "$name" user.easymesh.emosa-lab 2>/dev/null)" ]; }

emosa_start() {
    # emosa-lab's step again, from what is staged in the VM (as build.sh emosa ran it, no new
    # inputs needed). With EMOSA in the gateway its fleet already started the agents; this
    # brings the rest back: the pods' redirector address, EMOSA's containers, the GTP, the
    # gateway's forwarding, the pods and the rooms with them.
    local vm_lab=/opt/emosa-lab/deploy/rdk-lab/vm/lab.sh
    emosa_option || return 0
    run_root test -f "$vm_lab" || { echo "$name: the EMOSA option has no staged lab.sh; build.sh emosa" >&2; return 1; }
    if [ "$(lxc config get "$name" user.easymesh.emosa-in 2>/dev/null)" = gateway ]; then
        run_root bash "$vm_lab" up c gateway
    else
        run_root bash "$vm_lab" up
    fi
}

stop_vm() {
    instance_exists
    [ "$(instance_state)" != RUNNING ] || lxc stop "$name" --timeout 300
}

# The host side of the lab's storage (easymesh-resources lab-storage W9): the pool the lab is
# in and how full it is (a warning from 80 %), and whether LXD is held (W10: an LXD refresh
# restarts its daemon). Warnings only.
storage_status() {
    local pool used total pct
    pool=$(storage_pool)
    used=$(lxc storage info "$pool" --bytes 2>/dev/null | sed -n 's/^ *space used: "\{0,1\}\([0-9]*\)"\{0,1\}$/\1/p')
    total=$(lxc storage info "$pool" --bytes 2>/dev/null | sed -n 's/^ *total space: "\{0,1\}\([0-9]*\)"\{0,1\}$/\1/p')
    if [ -n "$used" ] && [ -n "$total" ] && [ "$total" -gt 0 ]; then
        pct=$((used * 100 / total))
        echo "storage: pool $pool ($(storage_driver)), $((used >> 30)) of $((total >> 30)) GiB used ($pct %)"
        [ "$pct" -lt 80 ] || echo "WARNING: pool $pool is $pct % full"
    fi
    if command -v snap >/dev/null && ! snap list lxd 2>/dev/null | awk 'NR == 2 {print $NF}' | grep -q held; then
        echo "WARNING: the LXD snap is not held: a refresh restarts its daemon (sudo snap refresh --hold lxd)"
    fi
}

status_vm() {
    lxc list "$name" -c nst4m --format table
    storage_status
    if [ "$(instance_state)" = RUNNING ]; then
        wait_agent
        run_root /usr/local/sbin/easymesh-labctl status
    fi
}

check_vm() {
    local host_commit guest_commit
    require_host_to_itself
    start_vm
    host_commit=$(git -C "$root" rev-parse HEAD)
    guest_commit=$(lxc exec "$name" -- sudo -H -u easymesh \
        git -C /home/easymesh/git/meta-cmf-bananapi-vcpe rev-parse HEAD)
    [ "$guest_commit" = "$host_commit" ] || {
        echo "$name contains source $guest_commit, expected $host_commit" >&2
        echo "rebuild or reprovision the appliance before release" >&2
        return 1
    }
    # Do not inject the expected scale here. A portable appliance must retain
    # its own profile in /etc/default/easymesh-lab so that a new operator can
    # run the exact same self-check without knowing a hidden environment flag.
    check_baseline
}

refuse_dev_lab() {      # a development lab is never accepted or exported
    local clients
    clients=$(lxc config get "$name" user.easymesh.dev-clients 2>/dev/null) || true
    [ -z "$clients" ] || {
        echo "$name is a development lab with $clients clients: build the full lab to accept or export it" >&2
        exit 1
    }
}

snapshot_vm() {
    refuse_dev_lab
    check_vm
    # `lxc info INSTANCE/SNAPSHOT` rejects the slash-qualified name on newer
    # LXD releases even when the snapshot exists. `lxc config show` supports
    # that identifier consistently, so use it to make replacement idempotent.
    if lxc config show "$name/accepted" >/dev/null 2>&1; then
        lxc delete "$name/accepted"
    fi
    lxc snapshot "$name" accepted </dev/null
}

export_vm() {
    local short bundle output created actual_cpus actual_memory actual_disk actual_storage trim_report
    require_command jq
    refuse_dev_lab
    install -d "$export_dir"
    check_vm
    run_root test ! -d /opt/easymesh-observability || { echo 'Remove monitoring credentials/data before exporting; see observability/README.md' >&2; exit 1; }
    actual_cpus=$(lxc config get "$name" limits.cpu)
    actual_memory=$(lxc config get "$name" limits.memory)
    actual_disk=$(lxc config device get "$name" root size)
    actual_storage=$(lxc config device get "$name" root pool)
    [ -n "$actual_cpus" ] && [ -n "$actual_memory" ] && [ -n "$actual_disk" ] \
        && [ -n "$actual_storage" ] || {
        echo "cannot determine actual resources for $name" >&2
        exit 1
    }
    if [ "$actual_cpus" != "$cpus" ] || [ "$actual_memory" != "$memory" ] || [ "$actual_disk" != "$disk" ]; then
        printf 'exporting actual resources rather than profile defaults: cpu=%s memory=%s disk=%s\n' \
            "$actual_cpus" "$actual_memory" "$actual_disk" >&2
    fi
    trim_report=$(mktemp "$export_dir/.${name}.trim.XXXXXX")
    run_root /usr/local/sbin/easymesh-package-cleanup | tee "$trim_report"
    stop_vm
    clear_secure_boot_config
    short=$(git -C "$root" rev-parse --short=7 HEAD)
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    bundle="$export_dir/rdkeasymesh-${release_id}-${short}-lxd"
    output="$bundle/rdkeasymesh-${release_id}-${short}-lxd.tar.zst"
    rm -rf -- "$bundle"
    install -d "$bundle"
    if ! export_instance "$output"; then
        configure_no_secure_boot
        return 1
    fi
    printf 'archive_bytes=%s\n' "$(stat -c %s "$output")" >> "$trim_report"
    # Restore the release-builder instance. The exported archive intentionally
    # remains firmware-neutral until import.sh selects the target-LXD key.
    configure_no_secure_boot
    install -m 0755 "$root/gen/vm/lxd/import.sh" "$bundle/import.sh"
    install -m 0755 "$root/gen/vm/lxd/instance-config.sh" "$bundle/instance-config.sh"
    cp -a "$root/gen/medium/lxd-monitoring" "$bundle/observability"    # easymesh-medium's, one copy for both labs
    rm -rf "$bundle/observability/tests"
    install -m 0755 "$root/gen/vm/lxd/install-host.sh" "$bundle/install-host.sh"
    install -m 0755 "$root/gen/vm/lxd/package-release.sh" "$bundle/package-release.sh"
    sed "s/@EASYMESH_RELEASE_ID@/${release_id}/g" \
        "$root/gen/vm/lxd/README.md" > "$bundle/README.md"
    chmod 0644 "$bundle/README.md"
    install -m 0644 "$root/docs/records/release-notes.md" "$bundle/RELEASE-NOTES.md"
    install -m 0644 "$trim_report" "$bundle/trim-report.txt"
    rm -f -- "$trim_report"
    cat > "$bundle/release.env" <<EOF
LAB_STACK=rdkeasymesh
LAB_PROFILE=$profile
LAB_CLIENTS=$profile_clients
LAB_HWSIM_RADIOS=$profile_radios
LAB_DEFAULT_NAME=$release_name
LAB_DEFAULT_CPUS=$actual_cpus
LAB_DEFAULT_MEMORY=$actual_memory
LAB_DEFAULT_DISK=$actual_disk
LAB_BUILD_STORAGE=$actual_storage
LAB_SOURCE_COMMIT=$(git -C "$root" rev-parse HEAD)
LAB_RELEASE_FLAVOR=ready
LAB_FIRST_BOOT_PROVISIONING=false
LAB_TRIMMED=true
EOF
    jq -n \
        --arg stack rdkeasymesh --arg profile "$profile" \
        --argjson clients "$profile_clients" --argjson radios "$profile_radios" \
        --arg source_commit "$(git -C "$root" rev-parse HEAD)" \
        --arg created_at "$created" --arg archive "$(basename "$output")" \
        --arg instance "$release_name" --arg cpus "$actual_cpus" --arg memory "$actual_memory" \
        --arg disk "$actual_disk" --arg build_storage "$actual_storage" \
        '{schema_version:1,stack:$stack,profile:$profile,clients:$clients,
          hwsim_radios:$radios,source_commit:$source_commit,created_at:$created_at,
          archive:$archive,defaults:{instance:$instance,cpus:$cpus,memory:$memory,disk:$disk},
          release_flavor:"ready",first_boot_provisioning:false,
          build:{storage_pool:$build_storage},
          trim:{applied:true,report:"trim-report.txt"},
          status:"candidate"}' > "$bundle/release.json"
    (
        cd "$bundle"
        sha256sum "$(basename "$output")" import.sh instance-config.sh install-host.sh \
            package-release.sh README.md RELEASE-NOTES.md release.env release.json trim-report.txt \
            > SHA256SUMS
        find observability -type f -print0 | sort -z | xargs -0 sha256sum >> SHA256SUMS
    )
    ls -lh "$bundle"/*
}

export_thin_vm() {
    local short bundle output created actual_cpus actual_memory actual_disk actual_storage
    local trim_report controller_name extender_name meta_commit wmediumd_sha assets
    require_command jq
    refuse_dev_lab
    install -d "$export_dir"
    [ -n "$controller_image" ] || { echo 'set EASYMESH_CONTROLLER_IMAGE' >&2; exit 2; }
    [ -n "$extender_image" ] || { echo 'set EASYMESH_EXTENDER_IMAGE' >&2; exit 2; }
    check_vm
    run_root test ! -d /opt/easymesh-observability || { echo 'Remove monitoring credentials/data before exporting; see observability/README.md' >&2; exit 1; }
    # One universal backup must have enough sparse logical capacity for the
    # stress roster.  Profile selection changes CPU, RAM and the active radio
    # pool at import; the common disk stays at the accepted maximum and only
    # consumes blocks that first-boot provisioning actually writes.
    lxc config device set "$name" root size 96GiB
    actual_cpus=$(lxc config get "$name" limits.cpu)
    actual_memory=$(lxc config get "$name" limits.memory)
    actual_disk=$(lxc config device get "$name" root size)
    actual_storage=$(lxc config device get "$name" root pool)
    [ -n "$actual_cpus" ] && [ -n "$actual_memory" ] && [ -n "$actual_disk" ] \
        && [ -n "$actual_storage" ] || {
        echo "cannot determine actual resources for $name" >&2
        exit 1
    }
    [ "$actual_disk" = 96GiB ] || {
        echo "universal thin root disk did not expand to 96GiB: $actual_disk" >&2
        exit 1
    }

    meta_commit=$(git -C "$root" rev-parse HEAD)
    # the daemon the running lab built from its pinned medium
    wmediumd_sha=$(lxc exec "$name" -- sha256sum /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/medium/wmediumd/build/wmediumd | awk '{print $1}')
    controller_name=$(basename "$controller_image")
    extender_name=$(basename "$extender_image")
    assets=/home/easymesh/easymesh-assets
    run_root install -d -o easymesh -g easymesh "$assets"
    lxc file push "$controller_image" "$name$assets/$controller_name"
    lxc file push "$extender_image" "$name$assets/$extender_name"
    lxc exec "$name" -- chown easymesh:easymesh \
        "$assets/$controller_name" "$assets/$extender_name"

    # Install from the accepted checkout as well as the staged copies. This
    # permits export-thin after a ready export removed the staging directory.
    run_root install -m 0755 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-prepare-thin-package \
        /usr/local/sbin/easymesh-prepare-thin-package
    run_root install -m 0755 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-thin-firstboot \
        /usr/local/sbin/easymesh-thin-firstboot
    run_root install -m 0755 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-select-thin-profile \
        /usr/local/sbin/easymesh-select-thin-profile
    run_root install -m 0755 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-complete-thin-firstboot \
        /usr/local/sbin/easymesh-complete-thin-firstboot
    run_root install -m 0644 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-thin-firstboot.service \
        /etc/systemd/system/easymesh-thin-firstboot.service
    run_root install -m 0644 \
        /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/scripts/guest/easymesh-lab.service \
        /etc/systemd/system/easymesh-lab.service
    run_root systemctl daemon-reload

    trim_report=$(mktemp "$export_dir/.${name}.thin-trim.XXXXXX")
    run_root env \
        EASYMESH_REPO=/home/easymesh/git/meta-cmf-bananapi-vcpe \
        CONTROLLER_IMAGE="$assets/$controller_name" \
        EXTENDER_IMAGE="$assets/$extender_name" \
        EXPECTED_REPO_HEAD="$meta_commit" \
        EXPECTED_WMEDIUMD_SHA256="$wmediumd_sha" \
        EASYMESH_THIN_PROFILE_SELECTABLE=true \
        /usr/local/sbin/easymesh-prepare-thin-package | tee "$trim_report"
    run_root /usr/local/sbin/easymesh-package-cleanup thin | tee -a "$trim_report"
    test "$(lxc exec "$name" -- lxc list -c n --format csv | awk '
        /^(bpibroadband|bpiap(-[0-9]{3})?|wlan-client(-[0-9]{3})?)$/ {n++}
        END {print n+0}')" = 0
    lxc exec "$name" -- test -f /var/lib/easymesh-lab/thin-firstboot.template.env
    lxc exec "$name" -- test -f /var/lib/easymesh-lab/thin-profile-selection.required
    lxc exec "$name" -- test ! -e /var/lib/easymesh-lab/thin-firstboot.env
    lxc exec "$name" -- lxc image info wlan-client-base >/dev/null

    stop_vm
    clear_secure_boot_config
    short=$(git -C "$root" rev-parse --short=7 HEAD)
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    bundle="$export_dir/rdkeasymesh-${release_id}-thin"
    output="$bundle/rdkeasymesh-${release_id}-${short}-thin-lxd.tar.zst"
    rm -rf -- "$bundle"
    install -d "$bundle"
    if ! export_instance "$output"; then
        configure_no_secure_boot
        return 1
    fi
    printf 'archive_bytes=%s\n' "$(stat -c %s "$output")" >> "$trim_report"
    configure_no_secure_boot
    install -m 0755 "$root/gen/vm/lxd/import.sh" "$bundle/import.sh"
    install -m 0755 "$root/gen/vm/lxd/instance-config.sh" "$bundle/instance-config.sh"
    cp -a "$root/gen/medium/lxd-monitoring" "$bundle/observability"    # easymesh-medium's, one copy for both labs
    rm -rf "$bundle/observability/tests"
    install -m 0755 "$root/gen/vm/lxd/install-host.sh" "$bundle/install-host.sh"
    install -m 0755 "$root/gen/vm/lxd/package-release.sh" "$bundle/package-release.sh"
    sed "s/@EASYMESH_RELEASE_ID@/${release_id}/g" "$root/gen/vm/lxd/README.md" \
        > "$bundle/README.md"
    chmod 0644 "$bundle/README.md"
    install -m 0644 "$root/docs/records/release-notes.md" "$bundle/RELEASE-NOTES.md"
    install -m 0644 "$trim_report" "$bundle/trim-report.txt"
    rm -f -- "$trim_report"
    cat > "$bundle/release.env" <<EOF
LAB_STACK=rdkeasymesh
LAB_RELEASE_ID=$release_id
LAB_PROFILE_SELECTABLE=false
LAB_CLIENT_CAPACITY=100
LAB_DEFAULT_ROOM_CLIENTS=20
LAB_DEFAULT_DISK=96GiB
LAB_BUILD_STORAGE=$actual_storage
LAB_SOURCE_COMMIT=$meta_commit
LAB_RELEASE_FLAVOR=thin
LAB_FIRST_BOOT_PROVISIONING=true
LAB_TRIMMED=true
EOF
    jq -n \
        --arg stack rdkeasymesh \
        --arg release_id "$release_id" \
        --arg source_commit "$meta_commit" --arg created_at "$created" \
        --arg archive "$(basename "$output")" \
        --arg disk 96GiB --arg build_storage "$actual_storage" \
        '{schema_version:2,stack:$stack,release_id:$release_id,profile_selectable:false,
          client_capacity:100,default_room_clients:20,source_commit:$source_commit,created_at:$created_at,
          archive:$archive,release_flavor:"thin",first_boot_provisioning:true,
          capacity:{instance:("rdkeasymesh-"+$release_id),clients:100,hwsim_radios:128,cpus:8,memory:"16GiB"},
          defaults:{disk:$disk},
          build:{storage_pool:$build_storage},trim:{applied:true,report:"trim-report.txt"},
          status:"candidate"}' > "$bundle/release.json"
    (
        cd "$bundle"
        sha256sum "$(basename "$output")" import.sh instance-config.sh install-host.sh \
            package-release.sh README.md RELEASE-NOTES.md release.env release.json trim-report.txt \
            > SHA256SUMS
        find observability -type f -print0 | sort -z | xargs -0 sha256sum >> SHA256SUMS
    )
    ls -lh "$bundle"/*
}

update_vm() (
    local repo=/home/easymesh/git/meta-cmf-bananapi-vcpe asset_dir=/home/easymesh/easymesh-assets
    local host_commit guest_commit applied commit guest_medium stage
    local medium_tools=false radio=false guest=false
    instance_exists
    [ "$(instance_state)" = RUNNING ] || { echo "$name is not running: $0 start" >&2; exit 1; }
    wait_agent
    host_commit=$(git -C "$root" rev-parse HEAD)
    test -z "$(git -C "$root" status --porcelain)"
    guest_commit=$(lxc exec "$name" -- sudo -H -u easymesh git -C "$repo" rev-parse HEAD)
    # What was last applied whole (by a build, or an update that finished its installs): an
    # update that stopped part-way leaves the checkout ahead of it, and its rerun redoes the
    # rest (prplMesh's prpl-fast-c, 4 Oct). A VM from before this record has its checkout.
    applied=$(lxc config get "$name" user.easymesh.applied-commit 2>/dev/null) || true
    applied=${applied:-$guest_commit}
    [ "$applied" != "$host_commit" ] || { echo "$name is at $host_commit already"; exit 0; }
    for commit in "$applied" "$guest_commit"; do
        git -C "$root" merge-base --is-ancestor "$commit" "$host_commit" || {
            echo "$name is at $commit, not an ancestor of $host_commit: build instead" >&2
            exit 1
        }
    done
    # What a build made from the checkout and installed: the medium's daemon and console
    # (made here), its radio module (made in the guest) and the guest's services and tools.
    # An update makes and installs what changed of them, then restarts the VM, as a build's
    # cold boot does.
    guest_medium=$(git -C "$root" rev-parse "$applied:gen/medium")
    git -C "$root/gen/medium" diff --quiet "$guest_medium" HEAD -- wmediumd observer \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || medium_tools=true
    git -C "$root/gen/medium" diff --quiet "$guest_medium" HEAD -- hwsim \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' || radio=true
    # The topology page comes with the controller image (gen/medium/topology-ui, assembled by
    # its recipe): a VM build would not change it either.
    git -C "$root/gen/medium" diff --quiet "$guest_medium" HEAD -- topology-ui \
        $(sed 's|^|configurator/worlds/viewer/|' "$root/gen/medium/topology-ui/shared-modules") \
        ':(exclude,glob)**/tests/**' ':(exclude,glob)**/*.md' ||
        echo "note: the medium's topology page changed since $guest_medium; the gateway serves its image's page until a controller image built from this checkout" >&2
    git -C "$root" diff --quiet "$applied" "$host_commit" -- gen/vm/scripts/guest \
        gen/vm/scripts/30-boardfarm-wan.sh gen/vm/scripts/50-runtime-service.sh \
        gen/vm/scripts/55-scale-topology.sh gen/vm/scripts/60-scale-steering-test.sh \
        gen/vm/scripts/61-return-steering-regression.sh || guest=true
    record_open update
    printf 'FROM=%s\nCHECKOUT=%s\nMEDIUM_TOOLS=%s\nRADIO_MODULE=%s\nGUEST=%s\n' "$applied" \
        "$guest_commit" "$medium_tools" "$radio" "$guest" >> "$record_dir/environment.txt"
    stage=$(mktemp -d)
    trap 'record_close "$?"; rm -rf "$stage"' EXIT
    phase inputs
    install -d "$stage/assets"
    make_bundle "$root" "$host_commit" "$stage/assets/meta-cmf-bananapi-vcpe.bundle"
    if "$medium_tools"; then
        prepare_medium "$stage"
    else
        make_bundle "$root/gen/medium" "$(git -C "$root" rev-parse HEAD:gen/medium)" \
            "$stage/assets/easymesh-medium.bundle"
    fi
    prepare_optimizer "$stage"
    push_inputs "$stage"
    phase checkout
    # A directory the commit turns into a submodule keeps only ignored files: bytecode,
    # some of it the root-run room service's, so root removes them.
    lxc exec "$name" -- env REPO="$repo" bash -euo pipefail -c '
        cd "$REPO"
        for path in gen/medium gen/optimizer; do
            [ ! -d "$path" ] || [ -e "$path/.git" ] || git -c safe.directory="$REPO" clean -q -fdX -- "$path"
        done
    '
    lxc exec "$name" -- sudo -H -u easymesh env REPO="$repo" ASSETS="$asset_dir" \
        COMMIT="$host_commit" bash -euo pipefail -c '
        cd "$REPO"
        test -z "$(git status --porcelain --untracked-files=no)"
        git fetch -q "$ASSETS/meta-cmf-bananapi-vcpe.bundle" refs/heads/lxd-appliance-export
        test "$(git rev-parse FETCH_HEAD)" = "$COMMIT"
        git merge -q --ff-only FETCH_HEAD
        for path in gen/medium gen/optimizer; do
            [ -e "$path/.git" ] || [ -z "$(ls -A "$path" 2>/dev/null)" ] || {
                echo "$path holds untracked files; it cannot become a submodule" >&2
                exit 1
            }
        done
        git config submodule.gen/medium.url "$ASSETS/easymesh-medium.bundle"
        git config submodule.gen/optimizer.url "$ASSETS/easymesh-optimizer.bundle"
        git -c protocol.file.allow=always submodule update --init gen/medium gen/optimizer
        for path in gen/medium gen/optimizer; do
            test "$(git -C "$path" rev-parse HEAD)" = "$(git rev-parse "HEAD:$path")"
        done
        echo "$(git rev-parse --short HEAD): medium $(git -C gen/medium rev-parse --short HEAD)," \
            "optimizer $(git -C gen/optimizer rev-parse --short HEAD)"
    '
    if "$medium_tools"; then
        # As 20-prepare-lab-host.sh installs them; the restart below starts them.
        phase medium-tools
        # shellcheck disable=SC2016 # the guest's shell expands these
        lxc exec "$name" -- sudo -H -u easymesh env REPO="$repo" ASSETS="$asset_dir" sh -eu -c '
            install -D -m 0755 "$ASSETS/wmediumd" "$REPO/gen/medium/wmediumd/build/wmediumd"
            install -m 0644 "$ASSETS/wmediumd.provenance.env" \
                "$REPO/gen/medium/wmediumd/build/wmediumd.provenance.env"
            install -m 0755 "$ASSETS/wmediumd-console" "$REPO/gen/medium/observer/wmediumd-console"'
        run_root sh "$repo/gen/medium/observer/install.sh"
    fi
    if "$radio"; then
        # As 15-prepare-base.sh builds it, from the medium's bundle in a scratch clone. A live
        # pool is never reloaded: the restart below loads the new module.
        phase radio-module
        # shellcheck disable=SC2016 # the guest's shell expands these
        run_root env ASSETS="$asset_dir" KERNEL="$kernel" bash -euo pipefail -c '
            medium=$(mktemp -d /tmp/easymesh-medium.XXXXXX)
            trap "rm -rf -- $medium" EXIT
            git clone -q "$ASSETS/easymesh-medium.bundle" "$medium/easymesh-medium"
            git -C "$medium/easymesh-medium" checkout -q --detach origin/lxd-appliance-export
            REFETCH=1 "$medium/easymesh-medium/hwsim/build-hwsim.sh" --6ghz --install
            module=$(modinfo -k "$KERNEL" -F filename mac80211_hwsim)
            test "$module" = "/lib/modules/$KERNEL/updates/mac80211_hwsim.ko"
            grep -aq "EXPERIMENTAL wmediumd" "$module"
            sha256sum "$module" > /var/lib/easymesh-lab/mac80211_hwsim.sha256
            git -C "$medium/easymesh-medium" rev-parse HEAD:hwsim \
                > /var/lib/easymesh-lab/mac80211_hwsim.source'
    fi
    if "$guest" || "$medium_tools"; then
        # The stages that install the guest's services and tools, again with the lab's own
        # settings; both leave a running lab as it is.
        phase guest
        run_root bash /home/easymesh/easymesh-provision/30-boardfarm-wan.sh
        run_root bash -euo pipefail -c 'set -a; . /etc/default/easymesh-lab; set +a
            exec bash /home/easymesh/easymesh-provision/50-runtime-service.sh'
    fi
    if "$medium_tools" || "$radio" || "$guest"; then
        phase restart
        stop_vm
        start_vm
    else
        phase room
        run_root bash "$repo/gen/lab-bringup.sh" room
    fi
    lxc config set "$name" user.easymesh.applied-commit "$host_commit"
    trap 'rm -rf "$stage"' EXIT
    record_close 0
)

# An instance made from another (a copy, or a lab built from a base image) gets
# identities of its own, as import.sh gives an imported appliance: LXD's uuid,
# cloud-init instance id, vsock id and MAC. Its address is then written into the
# guest's netplan at its first start (user.easymesh.pin-address), because the
# instances share a machine-id, and with it the DHCP client identity that would
# make two labs on one bridge swap leases.
reseed_identity() {     # reseed_identity INSTANCE (stopped)
    local instance=$1 uuid vsock
    uuid=$(cat /proc/sys/kernel/random/uuid)
    vsock=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
    lxc config unset "$instance" volatile.eth0.hwaddr
    lxc config set "$instance" volatile.uuid "$uuid"
    lxc config set "$instance" volatile.uuid.generation "$uuid"
    lxc config set "$instance" volatile.cloud-init.instance-id "$uuid"
    lxc config set "$instance" volatile.vsock_id "$vsock"
    lxc config set "$instance" user.easymesh.pin-address true
}

pin_guest_address() {   # the instance's reserved address, static in the guest (running)
    local address cidr mac interface netplan actual
    [ "$(lxc config get "$name" user.easymesh.pin-address)" = true ] || return 0
    address=$(lxc config device get "$name" eth0 ipv4.address)
    [ -n "$address" ] || return 0
    cidr=$(lxc network get "$network" ipv4.address)
    mac=$(lxc config get "$name" volatile.eth0.hwaddr | tr '[:upper:]' '[:lower:]')
    # shellcheck disable=SC2016 # the guest's shell expands these
    interface=$(lxc exec "$name" -- sh -eu -c '
        for file in /sys/class/net/*/address; do
            read -r value < "$file"
            [ "$value" = "$1" ] && { basename "$(dirname "$file")"; exit 0; }
        done
        exit 1' sh "$mac")
    netplan=$(printf '%s\n' 'network:' '  version: 2' '  ethernets:' \
        "    $interface:" '      dhcp4: false' '      accept-ra: true' '      addresses:' \
        "        - $address/${cidr#*/}" '      routes:' '        - to: default' \
        "          via: ${cidr%/*}" '      nameservers:' '        addresses:' \
        "          - ${cidr%/*}")
    if [ "$(lxc exec "$name" -- cat /etc/netplan/99-easymesh-lxd-site.yaml 2>/dev/null)" != "$netplan" ]; then
        printf '%s\n' "$netplan" | lxc exec "$name" -- sh -eu -c '
            umask 077
            cat > /etc/netplan/99-easymesh-lxd-site.yaml
            netplan generate
            netplan apply'
    fi
    for _ in $(seq 1 60); do
        actual=$(lxc exec "$name" -- ip -4 -o address show dev "$interface" scope global \
            | awk '$3 == "inet" {split($4, field, "/"); print field[1]; exit}')
        [ "$actual" = "$address" ] && return 0
        sleep 1
    done
    echo "$name: its address $address is not installed on $interface (has: ${actual:-none})" >&2
    return 1
}

# A copy of this lab, NEW, in the same storage pool: on a copy-on-write pool
# (btrfs, zfs) it takes seconds and shares the source's blocks. The copy gets
# its own identities, address and port block; it is left stopped, and its
# first start pins its address and brings its lab up.
copy_vm() {
    local target=${1:-} source=$name stamp snapshot='' device listen port address
    local target_ipv4 target_port_base volume pool
    case "$target" in
        [a-z0-9][a-z0-9-]*) ;;
        *) echo "usage: $0 copy NEW-NAME (lowercase letters, numbers and hyphens)" >&2; exit 2 ;;
    esac
    instance_exists || { echo "$source does not exist" >&2; exit 1; }
    ! lxc info "$target" >/dev/null 2>&1 || { echo "$target already exists" >&2; exit 1; }
    target_port_base=${EASYMESH_COPY_PORT_BASE:-$(EASYMESH_PORT_BASE='' \
        easymesh_instance_port_base "$target")}
    record_open copy
    trap 'record_close "$?"' EXIT
    phase copy
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    if [ "$(instance_state)" = RUNNING ]; then
        snapshot=copy-$stamp
        lxc snapshot "$source" "$snapshot" </dev/null
        lxc copy "$source/$snapshot" "$target" </dev/null
        lxc delete "$source/$snapshot"
    else
        lxc copy "$source" "$target" --instance-only </dev/null
    fi
    # the copy's own evidence volume, a copy of the original's (copy-on-write); a volume of an
    # earlier lab of the copy's name is kept and attached, as a rebuild would
    if volume=$(lxc config device get "$target" evidence source 2>/dev/null); then
        pool=$(lxc config device get "$target" evidence pool)
        lxc storage volume show "$pool" "$target-evidence" >/dev/null 2>&1 \
            || lxc storage volume copy "$pool/$volume" "$pool/$target-evidence" </dev/null
        lxc config device set "$target" evidence source="$target-evidence"
    fi
    phase configure
    reseed_identity "$target"
    target_ipv4=$(select_guest_ipv4)
    lxc config device unset "$target" eth0 ipv4.address
    lxc config device set "$target" eth0 ipv4.address "$target_ipv4"
    for device in easymesh-webui:0:8888 wmediumd-console:1:8890 room-demo-viewer:2:8891; do
        port=$((target_port_base + $(cut -d: -f2 <<<"$device")))
        listen=$(lxc config device get "$target" "${device%%:*}" listen)
        address=${listen#tcp:}
        address=${address%:*}
        lxc config device set "$target" "${device%%:*}" \
            listen="tcp:$address:$port" connect="tcp:$target_ipv4:${device##*:}"
    done
    lxc config set "$target" user.easymesh.copied-from "$source"
    lxc config set "$target" user.easymesh.copied-at "$stamp"
    trap - EXIT
    record_close 0
    printf '%s: a copy of %s, address %s, ports %s to %s; stopped\n' \
        "$target" "$source" "$target_ipv4" "$target_port_base" "$((target_port_base + 2))"
    printf 'start it with: EASYMESH_LXD_NAME=%s %s start\n' "$target" "$0"
}

delete_vm() {
    local volume pool
    instance_exists
    lxc list "$name" -c nst4m --format table
    echo "deleting only LXD appliance instance: $name"
    volume=$(lxc config device get "$name" evidence source 2>/dev/null) || volume=''
    [ -z "$volume" ] || pool=$(lxc config device get "$name" evidence pool)
    lxc delete "$name" --force
    [ -z "$volume" ] || printf 'kept: its evidence, volume %s in %s (a rebuild of %s attaches it again; lxc storage volume delete %s %s)\n' \
        "$volume" "$pool" "$name" "$pool" "$volume"
}

case "${1:-}" in
    build) build_vm ;;
    start) start_vm ;;
    stop) stop_vm ;;
    restart) stop_vm; start_vm ;;
    status) status_vm ;;
    check) check_vm ;;
    snapshot) snapshot_vm ;;
    export) export_vm ;;
    export-thin) export_thin_vm ;;
    update) update_vm ;;
    delete) delete_vm ;;
    copy) copy_vm "${2:-}" ;;
    evidence) evidence_vm ;;
    emosa) emosa_vm ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
