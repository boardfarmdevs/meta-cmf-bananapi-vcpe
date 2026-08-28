#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
name=${EASYMESH_LXD_NAME:-easymesh-lab-0828}
image=${EASYMESH_LXD_IMAGE:-ubuntu:24.04}
cpus=${EASYMESH_LXD_CPUS:-6}
memory=${EASYMESH_LXD_MEMORY:-6GiB}
disk=${EASYMESH_LXD_DISK:-64GiB}
kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
webui_address=${EASYMESH_WEBUI_HOST_IP:-127.0.0.1}
webui_port=${EASYMESH_WEBUI_PORT:-18889}
console_address=${WMEDIUMD_CONSOLE_HOST_IP:-$webui_address}
console_port=${WMEDIUMD_CONSOLE_PORT:-18890}
boardfarm_commit=${EASYMESH_BOARDFARM_COMMIT:-eeb4803c00dc1cae2dda05eb6e1b52c06ad79aa8}
boardfarm_source=${EASYMESH_BOARDFARM_SOURCE:-git@github.com:robvogelaar/boardfarm-lab-staging.git}
controller_image=${EASYMESH_CONTROLLER_IMAGE:-}
extender_image=${EASYMESH_EXTENDER_IMAGE:-}
export_dir=${EASYMESH_LXD_EXPORT_DIR:-$root/gen/vm/lxd/artifacts}

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
  export      stop, publish and export a portable LXD image
  delete      delete only the named appliance VM after showing its identity

Build inputs:
  EASYMESH_CONTROLLER_IMAGE=/path/to/controller.rootfs.lxc.tar.bz2
  EASYMESH_EXTENDER_IMAGE=/path/to/extender.rootfs.lxc.tar.bz2

Common overrides:
  EASYMESH_LXD_NAME=$name
  EASYMESH_LXD_CPUS=$cpus
  EASYMESH_LXD_MEMORY=$memory
  EASYMESH_WEBUI_HOST_IP=$webui_address
  EASYMESH_WEBUI_PORT=$webui_port
  WMEDIUMD_CONSOLE_PORT=$console_port
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

add_proxy() {
    local device=$1 address=$2 host_port=$3 guest_port=$4
    if lxc config device get "$name" "$device" listen >/dev/null 2>&1; then
        lxc config device remove "$name" "$device"
    fi
    lxc config device add "$name" "$device" proxy \
        listen="tcp:$address:$host_port" connect="tcp:127.0.0.1:$guest_port"
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
    local stage=$1 assets=$stage/assets provision=/home/vagrant/easymesh-provision
    local file
    lxc exec "$name" -- bash -eu -c '
        id vagrant >/dev/null 2>&1 || useradd -m -s /bin/bash vagrant
        install -d -o vagrant -g vagrant /home/vagrant/easymesh-assets
        install -d -o vagrant -g vagrant /home/vagrant/easymesh-provision
        install -m 0440 /dev/null /etc/sudoers.d/easymesh-vagrant
        printf "%s\n" "vagrant ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/easymesh-vagrant
    '
    for file in "$assets"/*; do
        lxc file push "$file" "$name/home/vagrant/easymesh-assets/$(basename "$file")"
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
        [easymesh-health-audit]=gen/tests/health-audit.sh
        [easymesh-package-cleanup]=gen/vm/scripts/guest/easymesh-package-cleanup
    )
    for file in "${!guest_assets[@]}"; do
        lxc file push --mode 0755 "$root/${guest_assets[$file]}" \
            "$name/home/vagrant/easymesh-assets/$file"
    done
    lxc file push --mode 0755 "$root/gen/vm/scripts/60-scale-steering-test.sh" \
        "$name/home/vagrant/scale-steering-test.sh"
    lxc file push --mode 0755 "$root/gen/vm/scripts/55-scale-topology.sh" \
        "$name/home/vagrant/scale-topology.sh"
    lxc file push --mode 0755 "$root/gen/vm/scripts/61-return-steering-regression.sh" \
        "$name/home/vagrant/return-steering-test.sh"
    lxc file push --mode 0755 "$root/gen/tests/health-audit.sh" \
        "$name/home/vagrant/health-audit.sh"
    lxc exec "$name" -- chown -R vagrant:vagrant \
        /home/vagrant/easymesh-assets /home/vagrant/easymesh-provision \
        /home/vagrant/scale-steering-test.sh /home/vagrant/scale-topology.sh \
        /home/vagrant/return-steering-test.sh /home/vagrant/health-audit.sh
}

run_root() {
    lxc exec "$name" -- env EASYMESH_KERNEL="$kernel" \
        EASYMESH_RUNTIME_BRANCH=codex/0828-clean "$@"
}

run_vagrant() {
    lxc exec "$name" -- sudo -H -u vagrant env EASYMESH_KERNEL="$kernel" \
        EASYMESH_RUNTIME_BRANCH=codex/0828-clean "$@"
}

build_vm() {
    local stage meta_commit controller_name extender_name
    require_command git
    require_command lxc
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
    controller_name=$(basename "$controller_image")
    extender_name=$(basename "$extender_image")

    lxc init "$image" "$name" --vm \
        --config limits.cpu="$cpus" --config limits.memory="$memory"
    lxc config device override "$name" root size="$disk"
    lxc config set "$name" boot.autostart true
    add_proxy easymesh-webui "$webui_address" "$webui_port" 8888
    add_proxy wmediumd-console "$console_address" "$console_port" 8890
    lxc start "$name"
    wait_agent
    push_inputs "$stage"

    run_root bash /home/vagrant/easymesh-provision/00-base.sh
    run_root bash /home/vagrant/easymesh-provision/10-install-linux-7.sh
    lxc restart "$name" --timeout 300
    wait_agent
    test "$(lxc exec "$name" -- uname -r)" = "$kernel"

    run_root env EASYMESH_RUNTIME_COMMIT="$meta_commit" \
        bash /home/vagrant/easymesh-provision/20-prepare-lab-host.sh
    run_root bash /home/vagrant/easymesh-provision/30-boardfarm-wan.sh
    run_vagrant env \
        CONTROLLER_IMAGE="/home/vagrant/easymesh-assets/$controller_name" \
        EXTENDER_IMAGE="/home/vagrant/easymesh-assets/$extender_name" \
        EXPECTED_REPO_HEAD="$meta_commit" \
        bash /home/vagrant/easymesh-provision/40-deploy-easymesh.sh
    run_vagrant env EXTENDER_IMAGE="/home/vagrant/easymesh-assets/$extender_name" \
        bash /home/vagrant/easymesh-provision/55-scale-topology.sh
    run_root bash /home/vagrant/easymesh-provision/50-runtime-service.sh
    run_root bash /home/vagrant/git/meta-cmf-bananapi-vcpe/gen/wmediumd/observer/install.sh --start
    run_root systemctl enable easymesh-lab.service wmediumd-console.service

    lxc restart "$name" --timeout 300
    wait_agent
    run_root systemctl start easymesh-lab.service
    run_root /usr/local/sbin/easymesh-labctl check
    lxc snapshot "$name" accepted
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
    start_vm
    run_root /usr/local/sbin/easymesh-labctl check
}

snapshot_vm() {
    check_vm
    if lxc info "$name/accepted" >/dev/null 2>&1; then
        lxc delete "$name/accepted"
    fi
    lxc snapshot "$name" accepted
}

export_vm() {
    local alias=${EASYMESH_LXD_ALIAS:-easymesh-lab-0828} stamp output
    check_vm
    stop_vm
    if lxc image info "$alias" >/dev/null 2>&1; then
        lxc image delete "$alias"
    fi
    lxc publish "$name" --alias "$alias"
    install -d "$export_dir"
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    output="$export_dir/${alias}-${stamp}"
    lxc image export "$alias" "$output"
    sha256sum "$output"* | tee "$output.SHA256SUMS"
    ls -lh "$output"*
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
    delete) delete_vm ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
