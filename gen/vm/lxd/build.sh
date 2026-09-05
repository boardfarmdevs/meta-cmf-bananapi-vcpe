#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
# shellcheck source=profile.sh
source "$root/gen/vm/lxd/profile.sh"
release_id=${EASYMESH_RELEASE_ID:-0905}
case "$release_id" in
    [0-9][0-9][0-9][0-9]) ;;
    *) echo "invalid EASYMESH_RELEASE_ID: $release_id" >&2; exit 2 ;;
esac
default_host_address=$(ip -4 route get 1.1.1.1 2>/dev/null \
    | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')
default_host_address=${default_host_address:-127.0.0.1}
profile=$(easymesh_profile_name "${EASYMESH_LAB_PROFILE:-20}")
profile_clients=$(easymesh_profile_clients "$profile")
profile_radios=$(easymesh_profile_radios "$profile")
release_name=$(easymesh_profile_release_name "$profile")
name=${EASYMESH_LXD_NAME:-$release_name}
image=${EASYMESH_LXD_IMAGE:-ubuntu:24.04}
cpus=${EASYMESH_LXD_CPUS:-$(easymesh_profile_cpus "$profile")}
memory=${EASYMESH_LXD_MEMORY:-$(easymesh_profile_memory "$profile")}
disk=${EASYMESH_LXD_DISK:-$(easymesh_profile_disk "$profile")}
kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
network=${EASYMESH_LXD_NETWORK:-lxdbr0}
storage=${EASYMESH_LXD_STORAGE:-}
guest_ipv4=${EASYMESH_LXD_IPV4:-}
webui_address=${EASYMESH_WEBUI_HOST_IP:-$default_host_address}
webui_port=${EASYMESH_WEBUI_PORT:-18889}
console_address=${WMEDIUMD_CONSOLE_HOST_IP:-$webui_address}
console_port=${WMEDIUMD_CONSOLE_PORT:-18890}
room_address=${EASYMESH_ROOM_DEMO_HOST_IP:-$webui_address}
room_port=${EASYMESH_ROOM_DEMO_PORT:-18891}
http_ready_timeout=${EASYMESH_LXD_HTTP_READY_TIMEOUT:-240}
boardfarm_commit=${EASYMESH_BOARDFARM_COMMIT:-ddb5a2b9e1707562595afc7e4000a3b8efa3cd81}
boardfarm_source=${EASYMESH_BOARDFARM_SOURCE:-git@github.com:robvogelaar/boardfarm-lab-staging.git}
controller_image=${EASYMESH_CONTROLLER_IMAGE:-}
extender_image=${EASYMESH_EXTENDER_IMAGE:-}
export_dir=${EASYMESH_LXD_EXPORT_DIR:-$root/gen/vm/lxd/artifacts}
runtime_branch=${EASYMESH_RUNTIME_BRANCH:-$(git -C "$root" symbolic-ref --short HEAD)}

usage() {
    cat <<EOF
usage: $0 COMMAND

Commands:
  build       create, provision, reboot and accept a native LXD VM
  start       start an existing appliance VM
  stop        stop it cleanly
  restart     restart it and wait for the EasyMesh service gate
  status      show VM and lab status
  check       run the complete lab acceptance audit
  snapshot    replace the accepted snapshot after a passing check
  export      check, stop and export a portable LXD VM backup bundle
  export-thin check, remove provisioned nodes and export the universal offline bundle
  delete      delete only the named appliance VM after showing its identity

Build inputs:
  EASYMESH_CONTROLLER_IMAGE=/path/to/controller.rootfs.lxc.tar.bz2
  EASYMESH_EXTENDER_IMAGE=/path/to/extender.rootfs.lxc.tar.bz2

Common overrides:
  EASYMESH_LAB_PROFILE=$profile_clients (20, 50 or 100)
  EASYMESH_LXD_NAME=$name
  EASYMESH_LXD_CPUS=$cpus
  EASYMESH_LXD_MEMORY=$memory
  EASYMESH_LXD_NETWORK=$network
  EASYMESH_LXD_STORAGE=<destination pool; default is LXD default pool>
  EASYMESH_LXD_IPV4=<automatic static address>
  EASYMESH_WEBUI_HOST_IP=$webui_address
  EASYMESH_WEBUI_PORT=$webui_port
  WMEDIUMD_CONSOLE_PORT=$console_port
  EASYMESH_ROOM_DEMO_PORT=$room_port
  EASYMESH_LXD_HTTP_READY_TIMEOUT=$http_ready_timeout
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "required command is missing: $1" >&2
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

make_bundle() {
    local repo=$1 commit=$2 output=$3 ref=refs/heads/lxd-appliance-export
    test -d "$repo/.git"
    test -z "$(git -C "$repo" status --porcelain)"
    git -C "$repo" cat-file -e "$commit^{commit}"
    git -C "$repo" update-ref "$ref" "$commit"
    git -C "$repo" bundle create "$output" "$ref"
    git -C "$repo" update-ref -d "$ref"
    git bundle verify "$output" >/dev/null
}

prepare_assets() {
    local stage=$1 assets=$stage/assets boardfarm_repo=$stage/boardfarm-source
    local meta_commit
    install -d "$assets"
    meta_commit=$(git -C "$root" rev-parse HEAD)
    test -z "$(git -C "$root" status --porcelain)"
    make_bundle "$root" "$meta_commit" "$assets/meta-cmf-bananapi-vcpe.bundle"

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
            meta-cmf-bananapi-vcpe.bundle > SHA256SUMS
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
    for file in 00-base.sh 10-install-linux-7.sh 20-prepare-lab-host.sh \
        30-boardfarm-wan.sh 40-deploy-easymesh.sh 50-runtime-service.sh \
        55-scale-topology.sh 70-health-audit.sh; do
        lxc file push --mode 0755 "$root/gen/vm/scripts/$file" \
            "$name$provision/$file"
    done

    declare -A guest_assets=(
        [easymesh-lxd-docker-forward]=gen/vm/scripts/guest/easymesh-lxd-docker-forward
        [easymesh-lxd-docker-forward.service]=gen/vm/scripts/guest/easymesh-lxd-docker-forward.service
        [boardfarm-lab-rebuild]=gen/vm/scripts/guest/boardfarm-lab-rebuild
        [boardfarm-lab.service]=gen/vm/scripts/guest/boardfarm-lab.service
        [easymesh-lab-runtime]=gen/vm/scripts/guest/easymesh-lab-runtime
        [easymesh-lab.service]=gen/vm/scripts/guest/easymesh-lab.service
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
    lxc exec "$name" -- env EASYMESH_KERNEL="$kernel" \
        EASYMESH_RUNTIME_BRANCH="$runtime_branch" "$@"
}

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

build_vm() {
    local stage meta_commit controller_name extender_name appliance_ipv4 proxy_check_address wmediumd_sha
    local -a init_args
    require_command git
    require_command lxc
    require_command curl
    require_command sha256sum
    [ -n "$controller_image" ] || { echo 'set EASYMESH_CONTROLLER_IMAGE' >&2; exit 2; }
    [ -n "$extender_image" ] || { echo 'set EASYMESH_EXTENDER_IMAGE' >&2; exit 2; }
    instance_exists && {
        echo "$name already exists; delete it explicitly before a clean build" >&2
        exit 1
    }

    stage=$(mktemp -d /tmp/easymesh-lxd-build.XXXXXX)
    trap 'rm -rf -- "$stage"' EXIT
    meta_commit=$(prepare_assets "$stage" | tail -n 1)
    wmediumd_sha=$(sha256sum "$root/gen/wmediumd/wmediumd.patched" | awk '{print $1}')
    controller_name=$(basename "$controller_image")
    extender_name=$(basename "$extender_image")

    init_args=(lxc init "$image" "$name" --vm
        --config limits.cpu="$cpus" --config limits.memory="$memory")
    if [ -n "$storage" ]; then
        lxc storage show "$storage" >/dev/null 2>&1 || {
            echo "LXD storage pool does not exist: $storage" >&2
            exit 1
        }
        init_args+=(--storage "$storage")
    fi
    "${init_args[@]}" </dev/null
    # The appliance builds the narrowly-scoped multichannel hwsim module from
    # the exact Ubuntu source package. Disable guest Secure Boot before first
    # boot so that this locally-built module can load after installation.
    configure_no_secure_boot
    set_root_disk_size
    appliance_ipv4=$(select_guest_ipv4)
    lxc config device override "$name" eth0 network="$network" \
        ipv4.address="$appliance_ipv4"
    lxc config set "$name" boot.autostart true
    add_proxy easymesh-webui "$webui_address" "$webui_port" 8888 "$appliance_ipv4"
    add_proxy wmediumd-console "$console_address" "$console_port" 8890 "$appliance_ipv4"
    add_proxy room-demo-viewer "$room_address" "$room_port" 8891 "$appliance_ipv4"
    lxc start "$name"
    wait_agent
    push_inputs "$stage"

    run_root bash /home/easymesh/easymesh-provision/00-base.sh
    run_root bash /home/easymesh/easymesh-provision/10-install-linux-7.sh
    lxc restart "$name" --timeout 300
    wait_agent
    test "$(lxc exec "$name" -- uname -r)" = "$kernel"

    run_root env EASYMESH_RUNTIME_COMMIT="$meta_commit" \
        HWSIM_RADIOS="$profile_radios" \
        bash /home/easymesh/easymesh-provision/20-prepare-lab-host.sh
    run_root bash /home/easymesh/easymesh-provision/30-boardfarm-wan.sh
    # Nested LXD is a snap. A non-login `sudo -u` process launched through the
    # outer VM agent cannot be tracked by snapd, so appliance lifecycle runs as
    # root. Source checkout operations remain explicitly scoped to easymesh.
    run_root env HOME=/home/easymesh \
        CONTROLLER_IMAGE="/home/easymesh/easymesh-assets/$controller_name" \
        EXTENDER_IMAGE="/home/easymesh/easymesh-assets/$extender_name" \
        EXPECTED_REPO_HEAD="$meta_commit" \
        EXPECTED_WMEDIUMD_SHA256="$wmediumd_sha" \
        bash /home/easymesh/easymesh-provision/40-deploy-easymesh.sh
    run_root env HOME=/home/easymesh \
        EXTENDER_IMAGE="/home/easymesh/easymesh-assets/$extender_name" \
        EASYMESH_SCALE_PROFILE="$profile" \
        bash /home/easymesh/easymesh-provision/55-scale-topology.sh
    run_root env EASYMESH_SCALE_PROFILE="$profile" \
        HEALTH_EXPECT_CLIENTS="$profile_clients" \
        bash /home/easymesh/easymesh-provision/50-runtime-service.sh
    run_root bash /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/wmediumd/observer/install.sh --start
    # A VM NAT proxy connects to the guest NIC, not to guest loopback. Keep the
    # Console's normal package default private, but bind its appliance instance
    # to the isolated guest interface so the host-side proxy can reach it.
    run_root sed -i \
        's/^WMEDIUMD_CONSOLE_LISTEN=.*/WMEDIUMD_CONSOLE_LISTEN=0.0.0.0:8890/' \
        /etc/default/wmediumd-console
    run_root systemctl restart wmediumd-console.service
    run_root systemctl enable easymesh-lab.service wmediumd-console.service

    lxc restart "$name" --timeout 300
    wait_agent
    run_root systemctl start easymesh-lab.service
    run_root env HEALTH_EXPECT_CLIENTS="$profile_clients" \
        /usr/local/sbin/easymesh-labctl check
    proxy_check_address=$webui_address
    [ "$proxy_check_address" != 0.0.0.0 ] || proxy_check_address=$default_host_address
    wait_http_ready "EasyMesh WebUI proxy" \
        "http://$proxy_check_address:$webui_port/api/v1/topology"
    wait_http_ready "wmediumd Console proxy" \
        "http://$proxy_check_address:$console_port/api/v1/health"
    # Export reruns the complete acceptance gate and excludes snapshots. Do
    # not duplicate a full VM disk automatically on non-copy-on-write pools.
    lxc config show "$name" --expanded
    trap - EXIT
    rm -rf -- "$stage"
}

start_vm() {
    instance_exists
    [ "$(instance_state)" = RUNNING ] || lxc start "$name"
    wait_agent
    run_root systemctl start easymesh-lab.service
}

stop_vm() {
    instance_exists
    [ "$(instance_state)" != RUNNING ] || lxc stop "$name" --timeout 300
}

status_vm() {
    lxc list "$name" -c nst4m --format table
    if [ "$(instance_state)" = RUNNING ]; then
        wait_agent
        run_root /usr/local/sbin/easymesh-labctl status
    fi
}

check_vm() {
    local host_commit guest_commit
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
    run_root /usr/local/sbin/easymesh-labctl check
}

snapshot_vm() {
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
    install -d "$export_dir"
    check_vm
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
    bundle="$export_dir/rdkeasymesh-${profile_clients}-${release_id}-${short}-lxd"
    output="$bundle/rdkeasymesh-${profile_clients}-${release_id}-${short}-lxd.tar.zst"
    rm -rf -- "$bundle"
    install -d "$bundle"
    if ! lxc export "$name" "$output" --instance-only --compression zstd </dev/null; then
        configure_no_secure_boot
        return 1
    fi
    printf 'archive_bytes=%s\n' "$(stat -c %s "$output")" >> "$trim_report"
    # Restore the release-builder instance. The exported archive intentionally
    # remains firmware-neutral until import.sh selects the target-LXD key.
    configure_no_secure_boot
    install -m 0755 "$root/gen/vm/lxd/import.sh" "$bundle/import.sh"
    install -m 0755 "$root/gen/vm/lxd/install-host.sh" "$bundle/install-host.sh"
    install -m 0755 "$root/gen/vm/lxd/package-release.sh" "$bundle/package-release.sh"
    sed "s/@EASYMESH_RELEASE_ID@/${release_id}/g" \
        "$root/gen/vm/lxd/README.md" > "$bundle/README.md"
    chmod 0644 "$bundle/README.md"
    install -m 0644 "$root/doc/easymesh/release-notes.md" "$bundle/RELEASE-NOTES.md"
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
        sha256sum "$(basename "$output")" import.sh install-host.sh \
            package-release.sh README.md RELEASE-NOTES.md release.env release.json trim-report.txt \
            > SHA256SUMS
    )
    ls -lh "$bundle"/*
}

export_thin_vm() {
    local short bundle output created actual_cpus actual_memory actual_disk actual_storage
    local trim_report controller_name extender_name meta_commit wmediumd_sha assets
    require_command jq
    install -d "$export_dir"
    [ -n "$controller_image" ] || { echo 'set EASYMESH_CONTROLLER_IMAGE' >&2; exit 2; }
    [ -n "$extender_image" ] || { echo 'set EASYMESH_EXTENDER_IMAGE' >&2; exit 2; }
    check_vm
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
    wmediumd_sha=$(sha256sum "$root/gen/wmediumd/wmediumd.patched" | awk '{print $1}')
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
    if ! lxc export "$name" "$output" --instance-only --compression zstd </dev/null; then
        configure_no_secure_boot
        return 1
    fi
    printf 'archive_bytes=%s\n' "$(stat -c %s "$output")" >> "$trim_report"
    configure_no_secure_boot
    install -m 0755 "$root/gen/vm/lxd/import.sh" "$bundle/import.sh"
    install -m 0755 "$root/gen/vm/lxd/install-host.sh" "$bundle/install-host.sh"
    install -m 0755 "$root/gen/vm/lxd/package-release.sh" "$bundle/package-release.sh"
    sed "s/@EASYMESH_RELEASE_ID@/${release_id}/g" "$root/gen/vm/lxd/README.md" \
        > "$bundle/README.md"
    chmod 0644 "$bundle/README.md"
    install -m 0644 "$root/doc/easymesh/release-notes.md" "$bundle/RELEASE-NOTES.md"
    install -m 0644 "$trim_report" "$bundle/trim-report.txt"
    rm -f -- "$trim_report"
    cat > "$bundle/release.env" <<EOF
LAB_STACK=rdkeasymesh
LAB_RELEASE_ID=$release_id
LAB_PROFILE_SELECTABLE=true
LAB_SUPPORTED_PROFILES=20,50,100
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
        '{schema_version:2,stack:$stack,release_id:$release_id,profile_selectable:true,
          supported_profiles:[20,50,100],source_commit:$source_commit,created_at:$created_at,
          archive:$archive,release_flavor:"thin",first_boot_provisioning:true,
          profiles:{"20":{name:"small",instance:("rdkeasymesh-20-"+$release_id),clients:20,hwsim_radios:32,cpus:6,memory:"8GiB"},
                    "50":{name:"medium",instance:("rdkeasymesh-50-"+$release_id),clients:50,hwsim_radios:64,cpus:8,memory:"12GiB"},
                    "100":{name:"stress",instance:("rdkeasymesh-100-"+$release_id),clients:100,hwsim_radios:128,cpus:12,memory:"20GiB"}},
          defaults:{disk:$disk},
          build:{storage_pool:$build_storage},trim:{applied:true,report:"trim-report.txt"},
          status:"candidate"}' > "$bundle/release.json"
    (
        cd "$bundle"
        sha256sum "$(basename "$output")" import.sh install-host.sh \
            package-release.sh README.md RELEASE-NOTES.md release.env release.json trim-report.txt \
            > SHA256SUMS
    )
    ls -lh "$bundle"/*
}

delete_vm() {
    instance_exists
    lxc list "$name" -c nst4m --format table
    echo "deleting only LXD appliance instance: $name"
    lxc delete "$name" --force
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
    delete) delete_vm ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
