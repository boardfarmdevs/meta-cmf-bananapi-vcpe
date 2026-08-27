#!/bin/bash

source gen-util.sh

# Parse -b/-l flags out of the argument list first, wherever they appear,
# leaving the remaining positional arguments (url, and the legacy extra-id /
# lan-pN=value slots) untouched for the parsing further below -- these coexist
# with that positional syntax rather than replacing it.
wan_bridge=""
lan_bridge=""
instance_index=""
fresh=""
_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        -b)
            wan_bridge="$2"
            shift 2
            ;;
        -l)
            lan_bridge="$2"
            shift 2
            ;;
        -i)
            instance_index="$2"
            shift 2
            ;;
        -F|--fresh)
            # Wipe the persistent nvram volume so the node gets a fresh identity
            # (new AL-MAC + RUID set). Without this a redeploy REUSES the old
            # radio RUIDs from /nvram under a new AL-MAC, which the EasyMesh
            # controller treats as a stale-device / RUID collision and the fresh
            # node never onboards. Use for a clean baseline / replacement node;
            # omit to restart the same logical device with its identity preserved.
            fresh="1"
            shift
            ;;
        *)
            _args+=("$1")
            shift
            ;;
    esac
done
set -- "${_args[@]}"

usage() {
    local script_name=$(basename "$0")
    cat << EOF
Usage: ${script_name} [-b wan-bridge] [-l lan-bridge] [-i instance] [-F|--fresh] <url/path/pattern to bpi rootfs image>

   -F, --fresh  wipe the container's persistent nvram volume so it gets a fresh
               identity (new AL-MAC + RUID set). Use it for a clean baseline or a
               replacement node. A plain redeploy now PRESERVES a coherent
               identity: the extender AL-MAC base is persisted in /nvram
               (em_al_base_mac) alongside the RUIDs, so the whole {AL-MAC,
               RUID-set} tuple is reused as a unit and stays stable even if the
               hwsim pool hands the container a different phy. -F regenerates the
               tuple as a unit (wipes /nvram => AL-MAC re-seeds from the radio and
               RUIDs regenerate together). Omit for a same-node restart.

   -i <n>  launch an additional instance of the same image as <mv>-<datestamp>-0NN
           (independent nvram/VLAN/MAC/cloud-identity); e.g. a mesh leaf node.

  bpi* -b/-l are opt-in rather than overrides: the container connects to nothing
  unless asked, and always gets a single hwsim radio (FEATURE_SINGLE_PHY) unless
  HWSIM_RADIOS says otherwise.
    ${script_name} <BPIBB image> -b br-wan105 -l br-lan205   controller: WAN + LAN       -> container "bpibroadband"
    ${script_name} <BPIAP image>                             extender: no eth0, no eth1  -> container "bpiap"

EOF
    exit 1
}

# Check minimum argument count (image is required)
if [ $# -lt 1 ]; then
    usage
fi

# Get URL from first argument
url="$1"

# Initialize variables
extraindex=""
lan_p1=""
lan_p2=""
lan_p3=""
lan_p4=""

# Check maximum arguments
if [ $# -gt 4 ]; then
    echo "Error: Too many arguments" >&2
    usage
fi

# Parse optional arguments
if [ $# -ge 3 ]; then
    if [[ "${3}" =~ ^0[0-9][0-9]$ ]] && [ "${3}" != "000" ]; then
        extraindex="-${3}"
    elif [[ "${3}" =~ ^lan-p[1-4]=.+$ ]]; then
        port_num="${3:5:1}"
        value="${3#*=}"
        eval "lan_p${port_num}=\"$value\""
    else
        echo "Error: Invalid argument: ${3}" >&2
        usage
    fi
fi

if [ $# -eq 4 ]; then
    if [[ "${4}" =~ ^lan-p[1-4]=.+$ ]]; then
        port_num="${4:5:1}"
        value="${4#*=}"
        eval "lan_p${port_num}=\"$value\""
    else
        echo "Error: Invalid argument: ${4}" >&2
        usage
    fi
fi

# -i <n> instance index: give a second (third, ...) instance of the same image a
# distinct name (<mv>-<datestamp>-0NN) so it does not replace the first. Every
# per-container resource (nvram volume, VLAN, MACs, and thus the OpenSync/cloud
# node identity) derives from the container name, so each instance is fully
# independent. Same effect as the positional extra-id, but without the retired
# bng-id placeholder -- e.g. a mesh leaf: bpi.sh <img> -i 2 -l br-lan205
if [ -n "${instance_index}" ]; then
    if [ -n "${extraindex}" ]; then
        echo "Error: use either -i or the positional extra-id, not both" >&2
        usage
    fi
    if [[ "${instance_index}" =~ ^[0-9]+$ ]] && [ "${instance_index}" -ge 1 ] && [ "${instance_index}" -le 99 ]; then
        extraindex=$(printf -- "-%03d" "${instance_index}")
    else
        echo "Error: -i instance index must be a number 1..99" >&2
        usage
    fi
fi

# -l only applies to the first LAN port, not all four -- every product's
# LAN ports are already bridged together internally (brlan0), so
# connecting all four to the same external bridge is a guaranteed L2
# loop (four redundant parallel paths between the container's internal
# switch and that bridge). One connection per container matches how
# these bridges are meant to be used (e.g. boardfarm: one br-lan<N> per
# CPE slot). -l still wins over an explicit lan-p1=value, same as
# before; ports 2-4 are untouched by -l either way.
if [ -n "${lan_bridge}" ]; then
    lan_p1=""
fi


# Validate first argument (url/path)
# bananapi RDK-B vCPEs: full LXD image tarballs that get a fixed type/release +
# 1GiB limits. The two variants are told apart by the build dir / artifact prefix:
#   .../build-qemux86bpiap/...X86EMLTRBPIAP_rdk-next_<stamp>...        -> bpiap
#   .../build-qemux86bpibroadband/...X86EMLTRBPIBB_rdk-next_<stamp>... -> bpibroadband
# Match bpiap first: "bpibroadband" and "bpiap" both contain "bpi".
if [[ "$1" =~ (bpiap|bpi-ap|BPIAP) ]]; then
    mv="bpiap"
    rel="r25"
    rootsize=1024MiB
    memorylimit=1024MiB
    cpulimit="2"
elif [[ "$1" =~ (bpibroadband|BPIBB) ]]; then
    mv="bpibroadband"
    rel="r25"
    rootsize=1024MiB
    memorylimit=1024MiB
    cpulimit="2"
else
    echo "Error: image is not a bpibroadband/bpiap image" >&2
    exit 1
fi


# Datestamp (MMDD) from the image file's own 14-digit build stamp -- this
# names the image (e.g. ofw-bpiap-0804). For a remote rev@host:/path image the
# symlink is resolved and the stamp read over ssh (mtime fallback); local/https
# paths are handled too.
get_image_datestamp() {
    local u="$1" h p real stamp epoch
    if [[ "$u" == *@*:* ]]; then
        h="${u%%:*}"; p="${u#*:}"
        real=$(ssh -o BatchMode=yes "$h" "readlink -f \"$p\"" 2>/dev/null)
        stamp=$(printf '%s' "$real" | grep -oE '[0-9]{14}' | head -1)
        if [ -z "$stamp" ]; then
            epoch=$(ssh -o BatchMode=yes "$h" "stat -c %Y \"$p\"" 2>/dev/null)
            [ -n "$epoch" ] && stamp=$(date -d "@$epoch" +%Y%m%d%H%M%S)
        fi
    elif [[ "$u" == http* ]]; then
        stamp=$(printf '%s' "$u" | grep -oE '[0-9]{14}' | head -1)
    else
        real=$(readlink -f "$u" 2>/dev/null)
        stamp=$(printf '%s' "$real" | grep -oE '[0-9]{14}' | head -1)
        [ -z "$stamp" ] && [ -e "$u" ] && stamp=$(date -d "@$(stat -c %Y "$u")" +%Y%m%d%H%M%S)
    fi
    # "<MMDD> <full 14-digit stamp>" -- MMDD names the image, the full stamp is
    # recorded on the container as user.build (one resolve, not two).
    [ -n "$stamp" ] && printf '%s %s' "${stamp:4:4}" "$stamp"
}
read -r datestamp buildstamp <<< "$(get_image_datestamp "$url")"
if [[ ! "$datestamp" =~ ^[0-9]{4}$ ]]; then
    echo "Error: could not determine image datestamp (MMDD) from: $url" >&2
    exit 1
fi

# The CONTAINER name is stable (bpibroadband, bpiap) while the IMAGE keeps the
# datestamp (ofw-bpiap-0806). A name that changed every rebuild churned far more
# than cosmetics: the inventory files reference it, and -- because the MACs and
# the reported serial derive from it -- every rebuild silently changed the CPE's
# OpenSync/Plume node identity, killing an existing cloud claim. Stable name =>
# write the inventory once, claim the node once. Which build is actually running
# is recorded on the container as user.build (see below); two builds of one
# product side by side use -i <n> (bpiap-002).
base="${mv}"
imagename="ofw-${mv}-${datestamp}"

containername="${base}${extraindex}"
! validate_container_name "$containername" && echo "Invalid container name : $containername" && exit 1

# Profile replacement and instance creation are one transaction from this
# script's point of view, but separate asynchronous operations inside LXD. Two
# concurrent deploys can otherwise rewrite profiles or mutate the shared image
# store while an earlier `lxc init` is unpacking. Lock the script inode itself:
# unlike a writable file in sticky /tmp, this remains usable when provisioning
# alternates between an unprivileged LXD user and root. The checkout-wide lock
# deliberately serializes every BPI deployment made by this tool.
exec {deploy_lock_fd}<"${BASH_SOURCE[0]}" || exit 1
if ! flock -n "${deploy_lock_fd}"; then
    echo "Error: another bpi.sh deployment is already running" >&2
    exit 1
fi

profilename="${containername}"
volumename="${containername}-nvram"
nvram_root="${BPI_NVRAM_ROOT:-$M_ROOT/tmp/bpi-nvram}"

vlan="$(validate_and_hash "${profilename}")"
[[ "$vlan" == "-1" ]] && { echo "cannot determine unique vlan"; exit 1; }

# -l points at a bridge outside meta-lxd's own VLAN-filtered lan-p1..4
# bridge (e.g. a boardfarm-managed bridge, which is a plain flat L2
# network dedicated to one slot, not VLAN-aware) -- attach untagged in
# that case. Default (-l not given) still tags with this container's
# own vlan on the shared lan-pN bridges, same as always.
lan_vlan_arg=""
[ -z "${lan_bridge}" ] && lan_vlan_arg="vlan=${vlan}"


# Validate all four ports
for i in {1..4}; do
    validate_lan_port $i
done


mac1=$(generate_mac1 "$containername")
mac2=$(generate_mac2 "$containername")

if false; then
    echo imagename      = $imagename
    echo containername  = $containername
    echo profilename    = $profilename
    echo volumename     = $volumename
    echo mac1           = $mac1
    echo mac2           = $mac2
    echo lan_p1=$lan_p1
    echo lan_p2=$lan_p2
    echo lan_p3=$lan_p3
    echo lan_p4=$lan_p4
fi


mvrootfstarball="ofw-exm-qemux86-${mv}.tar.bz2"
mvdbgrootfstarball="ofw-exm-qemux86-${mv}-dbg.tar.bz2"

# Check if the path matches https://
#
if [[ "$1" =~ ^https://[^[:space:]]+ ]]; then
    if ! curl -f "$1" -o /dev/null 2>/dev/null; then
        echo "Error: Failed to download from $1" >&2
        exit 1
    fi

    curl --progress-bar "$1" > "$M_ROOT/tmp/$mvrootfstarball" || {
        rm -f "$mvrootfstarball"
        echo "Error: Failed to download content" >&2
        exit 1
    }
    echo "Successfully downloaded to $mvrootfstarball"

# Check if the path matches SCP syntax
#
elif [[ "$1" =~ ^([^@]+@)?[^:]+: ]]; then
    # Check if it ends with an extension, indicating it's likely a file
    if [[ "$1" =~ \.[^/]+$ ]]; then
        #echo "$1 is a remote file path."
        scp -p $1 $M_ROOT/tmp/${mvrootfstarball}
        exit_status=$?
        if [ $exit_status -ne 0 ]; then
            echo "scp -p $1 $M_ROOT failed with exit status $exit_status"
            exit 1
        fi
    else
        #echo "$1 is a remote directory path."
        scp -p $1/${mvrootfstarball} $M_ROOT/tmp/${mvrootfstarball}

        exit_status=$?
        if [ $exit_status -ne 0 ]; then
            echo "scp -p $1/${mvrootfstarball} $M_ROOT failed with exit status $exit_status"
            exit 1
        fi
    fi

# Check if the path matches a local path
#
elif [[ "$1" =~ \.[^/]+$ ]]; then
    # This is a local path.
    # Force-overwrite (-f, not -n): the staged copy in $M_ROOT/tmp keeps the
    # generic image name ($mvrootfstarball, e.g. ofw-exm-qemux86-bpiap.tar.bz2),
    # so a *rebuilt* image with the same name would otherwise be silently
    # skipped by cp -n (which also exits 0, so the check below never catches
    # it) and the previous build's rootfs would be redeployed instead.
    cp -f $1 $M_ROOT/tmp/${mvrootfstarball}
    exit_status=$?
    if [ $exit_status -ne 0 ]; then
        echo "cp $1 $M_ROOT failed with exit status $exit_status"
        exit 1
    fi

else
    usage
    exit 1
fi


if [[ "$mv" == bpi* ]]; then
    # bananapi ships a unified LXD image (metadata.yaml + rootfs in one tarball).
    # LXD 6.9 can import that archive but then hang forever while materializing
    # an instance from it. Import the exact same content as the standard split
    # metadata/rootfs form on that release. Keep the source archive hash as an
    # image property because a split image has a different LXD fingerprint.
    #
    # Do not delete and reimport an unchanged image on every redeploy: on a ZFS
    # root pool that is expensive storage churn and can serialize the NVRAM
    # operation that follows.
    staged_image="$M_ROOT/tmp/${mvrootfstarball}"
    archive_fingerprint=$(sha256sum "${staged_image}" | awk '{print $1}')
    lxd_server_version=$(lxc version 2>/dev/null \
        | sed -n 's/^Server version: *//p' | head -1)
    split_import=""
    case "${BPI_LXD_IMAGE_IMPORT:-auto}" in
        auto)
            [[ "${lxd_server_version}" == 6.9* ]] && split_import="1"
            ;;
        split)
            split_import="1"
            ;;
        unified)
            ;;
        *)
            echo "Error: BPI_LXD_IMAGE_IMPORT must be auto, split or unified" >&2
            exit 1
            ;;
    esac

    installed_fingerprint=$(lxc image info "${imagename}" 2>/dev/null \
        | sed -n 's/^Fingerprint: *//p' | head -1)
    installed_source_fingerprint=$(lxc image info "${imagename}" 2>/dev/null \
        | sed -n 's/^    user.source_sha256: *//p' | head -1)
    installed_import_format=$(lxc image info "${imagename}" 2>/dev/null \
        | sed -n 's/^    user.import_format: *//p' | head -1)
    image_matches=""
    if [ -n "${split_import}" ]; then
        [ "${installed_source_fingerprint}" = "${archive_fingerprint}" ] \
            && [ "${installed_import_format}" = split ] \
            && image_matches="1"
    elif [ "${installed_fingerprint}" = "${archive_fingerprint}" ] \
        || [ "${installed_source_fingerprint}" = "${archive_fingerprint}" ]; then
        image_matches="1"
    fi

    if [ -n "${image_matches}" ]; then
        echo "Image ${imagename} already matches ${archive_fingerprint}; skipping import"
    else
        [ -z "${installed_fingerprint}" ] || lxc image delete "${imagename}" || exit 1
        if [ -n "${split_import}" ]; then
            command -v fakeroot > /dev/null 2>&1 || {
                echo "Error: fakeroot is required for LXD ${lxd_server_version} split-image import" >&2
                exit 1
            }
            split_dir=$(mktemp -d "$M_ROOT/tmp/${imagename}.split.XXXXXX") || exit 1
            if ! fakeroot -- sh -eu -c '
                mkdir -p "$1/unified"
                tar -xjf "$2" -C "$1/unified"
                test -f "$1/unified/metadata.yaml"
                test -d "$1/unified/rootfs"
                tar --numeric-owner -C "$1/unified" -czf "$1/metadata.tar.gz" metadata.yaml
                tar --numeric-owner -C "$1/unified/rootfs" -czf "$1/rootfs.tar.gz" .
            ' sh "${split_dir}" "${staged_image}"; then
                rm -rf -- "${split_dir}"
                echo "Error: failed to convert ${staged_image} to a split LXD image" >&2
                exit 1
            fi
            if ! lxc image import "${split_dir}/metadata.tar.gz" \
                    "${split_dir}/rootfs.tar.gz" --alias "${imagename}"; then
                rm -rf -- "${split_dir}"
                exit 1
            fi
            rm -rf -- "${split_dir}"
            lxc image set-property "${imagename}" user.source_sha256 \
                "${archive_fingerprint}" || exit 1
            lxc image set-property "${imagename}" user.import_format split || exit 1
        elif lxc image info "${archive_fingerprint}" > /dev/null 2>&1; then
            # The content is already installed under a different alias.
            lxc image alias create "${imagename}" "${archive_fingerprint}" || exit 1
        else
            lxc image import "${staged_image}" --alias "${imagename}" || exit 1
        fi
    fi
fi

lab_pool=$(ensure_lxd_lab_pool) || exit 1

echo "Configuring ${containername}"

# BPI NVRAM is a host directory bind-mounted into the privileged container.
# This keeps LXD custom-volume mutation completely out of the deploy path. An
# ordinary redeploy reuses the profile's active directory; --fresh switches to
# a new empty generation and clears the prior one through the old container.
retired_nvram_dir=""
if [[ "$mv" == bpi* ]]; then
    active_nvram_dir=$(lxc profile device get "${profilename}" nvram source 2>/dev/null)
    active_nvram_pool=$(lxc profile device get "${profilename}" nvram pool 2>/dev/null)
    if [ -n "$fresh" ]; then
        nvram_source="${nvram_root}/${containername}-$(date +%s%N)"
        if [ -z "${active_nvram_pool}" ] && [[ "${active_nvram_dir}" == /* ]]; then
            retired_nvram_dir="${active_nvram_dir}"
        fi
    elif [ -z "${active_nvram_pool}" ] && [[ "${active_nvram_dir}" == /* ]]; then
        nvram_source="${active_nvram_dir}"
    else
        nvram_source="${nvram_root}/${containername}"
    fi
    mkdir -p "${nvram_source}" || { echo "Error: could not create ${nvram_source}" >&2; exit 1; }
fi

if lxc info "${containername}" > /dev/null 2>&1; then
    # Let OneWifi/hostapd remove VAPs before LXD returns the physical hwsim phy
    # to the host. A forced delete can leave TX work queued without a channel,
    # producing kernel warnings and a dirty radio that stalls the next attach.
    lxc stop "${containername}" --timeout 20 > /dev/null 2>&1 \
        || lxc stop "${containername}" --force > /dev/null 2>&1 \
        || true
    lxc delete "${containername}" --force > /dev/null 2>&1
fi

lxc profile delete ${profilename} > /dev/null 2>&1

if [ -n "$fresh" ]; then
    # Non-BPI products retain the legacy delete behavior. BPI uses the new
    # generation selected above, so pre_start sees empty /nvram and regenerates
    # a coherent {AL-MAC, RUID-set} without a same-name delete/create race.
    if [[ "$mv" != bpi* ]]; then
        lxc storage volume delete default "${volumename}" > /dev/null 2>&1
    fi
fi

lxc profile copy default ${profilename} > /dev/null 2>&1


# https://documentation.ubuntu.com/lxd/en/stable-5.0/reference/instance_options/

##    lxc.cgroup.devices.allow = a
##    lxc.cgroup2.devices.allow = a
##    lxc.rootfs.options = rw
##    lxc.cap.drop =
##    lxc.cgroup.devices.allow =
##    lxc.cgroup.devices.deny =
##    lxc.mount.auto = proc:mixed sys:mixed cgroup:rw:force
##
##  security.nesting: "true"

##  devices:
##    loop-control:
##      path: /dev/loop-control
##      type: unix-char
##  
##    loop1:
##      path: /dev/loop1
##      type: unix-block
##    loop2:
##      path: /dev/loop2
##      type: unix-block
##    loop3:
##      path: /dev/loop3
##      type: unix-block
##    loop4:
##      path: /dev/loop4
##      type: unix-block
##    loop5:
##      path: /dev/loop5
##      type: unix-block



## config:
##  security.syscalls.intercept.netlink: "true"
##  raw.lxc: |
##    lxc.cap.drop=
##    lxc.cap.keep=CAP_NET_ADMIN CAP_SYS_PTRACE CAP_SYS_ADMIN
##    lxc.mount.auto=proc:rw sys:rw
##    lxc.apparmor.profile=unconfined
##    lxc.mount.auto=proc:rw sys:rw cgroup:rw
##    lxc.mount.entry=proc proc proc rw,nosuid,nodev,noexec,relatime 0 0

cat << EOF | lxc profile edit ${profilename}
name: ${containername}
description: "${containername}"
config:
    boot.autostart: "false"
    security.privileged: "true"
    security.nesting: "true"
    limits.memory: ${memorylimit}
    limits.memory.swap: "false"
    limits.cpu: "${cpulimit}"
devices:
    root:
        path: /
        pool: ${lab_pool}
        type: disk
        size: ${rootsize}
EOF

# out of the box
# /proc/sys/fs/mqueue/msg_default         10
# /proc/sys/fs/mqueue/msg_max             100
# /proc/sys/fs/mqueue/msgsize_default     8192
# /proc/sys/fs/mqueue/msgsize_max         8192
# /proc/sys/fs/mqueue/queues_max          256

# sudo sysctl -w fs.mqueue.msg_max=1024
# sudo sysctl -w fs.mqueue.msgsize_max=4096
# sudo sysctl -w fs.mqueue.queues_max=1024


if [[ "$mv" == bpi* ]]; then

    # bananapi RDK-B broadband vCPE: eth0 = WAN uplink (RDK renames it to
    # erouter0), eth1 = LAN (RDK bridges it into brlan0). Deterministic MACs so
    # the RDK serial -- which the image derives from eth0's MAC -- is stable
    # across relaunches.
    eth0_mac=$(generate_mac1 "$containername")
    eth1_mac=$(generate_mac2 "$containername")

    # Unlike the mvx products below, bpi* wires up NOTHING by default: -b and -l
    # are opt-in, and without them the container gets no eth0 and no eth1 at all.
    # The meta-lxd "wan" bridge is vestigial (the BNG that served it is retired --
    # it is DOWN, memberless and has no IPv4), so defaulting eth0 to it only gave
    # RDK's WAN manager something to retry against forever. And lan-p1 is the
    # wrong default for an EasyMesh pair specifically: the two nodes are joined by
    # the wireless backhaul, so a second, wired path between their brlan0s is a
    # plain L2 loop. An EasyMesh extender wants neither leg -- see doc/easymesh in
    # meta-cmf-bananapi-vcpe.
    if [ -n "$wan_bridge" ]; then
        lxc profile device add ${profilename} eth0 nic nictype=bridged parent=${wan_bridge} hwaddr=${eth0_mac} name=eth0 1>/dev/null
    fi

    if [ -n "$lan_bridge" ]; then
        if [[ "$lan_bridge" == lan-p* ]]; then
            # meta-lxd VLAN-filtered LAN bridge -> tag with the per-CPE vlan
            sudo bridge vlan add vid ${vlan} dev ${lan_bridge} self
            lxc profile device add ${profilename} eth1 nic nictype=bridged parent=${lan_bridge} hwaddr=${eth1_mac} name=eth1 vlan=${vlan} 1>/dev/null
        else
            # custom -l bridge (e.g. br-lan205) -> untagged
            lxc profile device add ${profilename} eth1 nic nictype=bridged parent=${lan_bridge} hwaddr=${eth1_mac} name=eth1 1>/dev/null
        fi
    fi

    # RDK derives Device.DeviceInfo.SerialNumber from eth0's MAC. Pin it as env,
    # which is also what keeps the serial stable when there is no eth0 at all --
    # the MAC above is generated from the container name either way.
    lxc profile set ${profilename} environment.SERIAL_NUMBER="$(echo ${eth0_mac//:/} | tr '[:lower:]' '[:upper:]')"

    # RDK-B keeps persistent identity and configuration at /nvram. Bind the
    # selected host directory directly; LXD does not need to create, delete, or
    # clone a storage-pool object for these small files.
    lxc profile device add "${profilename}" nvram disk source="${nvram_source}" path=/nvram 1>/dev/null

    # Candidate-link measurements come from a protocol-enforced read-only
    # wmediumd endpoint.  Mount it outside /run: systemd overlays /run with a
    # tmpfs during every container boot, which hides a profile disk mounted
    # there and breaks candidate collection after an ordinary restart.  This
    # rootfs mount remains present across cold starts and restarts.  Never
    # expose the scenario writer socket to a CPE container.
    wmediumd_metrics_source=${WMEDIUMD_METRICS_DIR:-/run/meta-cmf-wmediumd/metrics}
    sudo install -d -m 0755 -o root -g root "${wmediumd_metrics_source}"
    lxc profile device add "${profilename}" wmediumd-metrics disk \
        source="${wmediumd_metrics_source}" path=/wmediumd-metrics \
        readonly=true 1>/dev/null || exit 1

    # The controller's LAN address is deliberately 10.0.0.1, which commonly
    # collides with (and is hidden by) the host's existing default-LAN route.
    # Publish em_cli through LXD's namespace-aware proxy so operators can always
    # use http://<lab-host>:8888 without adding host routes or giving the RDK-B
    # image a management interface. Extra controller instances must opt in with
    # a distinct EM_CLI_HOST_PORT to avoid an implicit host-port collision.
    if [ "${mv}" = "bpibroadband" ] && { [ "${containername}" = "bpibroadband" ] || [ -n "${EM_CLI_HOST_PORT:-}" ]; }; then
        em_cli_host_port="${EM_CLI_HOST_PORT:-8888}"
        if ! [[ "${em_cli_host_port}" =~ ^[0-9]+$ ]] \
                || [ "${em_cli_host_port}" -lt 1 ] \
                || [ "${em_cli_host_port}" -gt 65535 ]; then
            echo "Error: EM_CLI_HOST_PORT must be a TCP port in 1..65535" >&2
            exit 1
        fi
        lxc profile device add "${profilename}" emcli proxy \
            listen="tcp:0.0.0.0:${em_cli_host_port}" \
            connect="tcp:127.0.0.1:8888" 1>/dev/null || exit 1
    fi

fi


lxc profile set ${profilename} environment.TZ $(date +%z | awk '{printf("PST8PDT,M3.2.0,M11.1.0")}')
lxc profile set ${profilename} environment.HOME /home/root

lxc profile set ${profilename} environment.CONTAINER_NAME ${containername}
lxc profile set ${profilename} environment.SERIAL_NUMBER ${containername}
lxc profile set ${profilename} environment.STORED_MAC1 ${mac1}
lxc profile set ${profilename} environment.STORED_MAC2 ${mac2}

# disable expanded logging
lxc profile set ${profilename} environment.rssfree_logging false
lxc profile set ${profilename} environment.syscfg_logging false
lxc profile set ${profilename} environment.sysevent_logging false
lxc profile set ${profilename} environment.rbus_logging false
lxc profile set ${profilename} environment.logmaxsize "" #150000000
lxc profile set ${profilename} environment.haltrace false
lxc profile set ${profilename} environment.halbacktrace false

lxc profile set ${profilename} environment.dbg_rootfs_url $1/${mvdbgrootfstarball}
lxc profile set ${profilename} environment.dbg_rootfs_user ${USER}


if false; then
    lxc profile set ${profilename} environment.runner "" # comma separated commands
    lxc profile set ${profilename} environment.runner_delay "" # in seconds (default = 1)
    lxc profile set ${profilename} environment.runner_interval "" # in seconds (default = 1)
    lxc profile set ${profilename} environment.pcap "" #"eth0"
    lxc profile set ${profilename} environment.sniff "" #"eth0"
    lxc profile set ${profilename} environment.interfacesv4 false # true
    lxc profile set ${profilename} environment.interfacesv6 false # true
    lxc profile set ${profilename} environment.routesv4 "" # "255,254,100,200"
    lxc profile set ${profilename} environment.routesv6 "" # "255,254,100,200"
    lxc profile set ${profilename} environment.rulesv4 false #true
    lxc profile set ${profilename} environment.rulesv6 false #true
    lxc profile set ${profilename} environment.files "" #"/etc/resolv.conf"
    lxc profile set ${profilename} environment.bindmounts false
fi

# ==== hwsim Wi-Fi radios: allocate free pool radios as LXD physical NICs ====
# (radio0/1 = home 2.4/5 for the hal-wifi-hwsim HAL, + 1 backhaul). They return
# to the host pool automatically on container delete. Override count HWSIM_RADIOS,
# disable with HWSIM_RADIOS=0.
#
# bpi wants exactly ONE. The bananapi build is FEATURE_SINGLE_PHY: rdk-wifi-hal
# replicates a single phy into three radio slots (wifi0/wifi1/wifi2) itself, so
# handing it three separate hwsim phys does not give it three radios, it gives it
# two spares its InterfaceMap has no slot for. Deduced from the image rather than
# left to the caller, since it is a property of the build, not of the deployment.
hwsim_default_radios=1
# LXD 6.7 can stall image materialization when a physical WLAN device is already
# present in the profile. Create the stopped instance first, add the radio to its
# profile second, and only then start it. This ordering is deterministic and the
# device is present before container init/OneWifi runs.
lxc init "${imagename}" "${containername}" -p "${profilename}" || exit 1
hwsim_attach_radios "${profilename}" "${HWSIM_RADIOS:-$hwsim_default_radios}"
lxc start "${containername}" || exit 1

# Build provenance: the container name no longer carries the datestamp, so record
# which image it was launched from. `lxc list -c n,config:user.build` then answers
# "what is running?" without the name having to churn.
lxc config set ${containername} user.build "${buildstamp}" 2>/dev/null
lxc config set ${containername} user.image "${url}" 2>/dev/null

# The new generation is live and deleting the old container has unmounted its
# /nvram/rdkssa eCryptfs mount. Clear only a path resolved beneath this
# container's NVRAM namespace; -F explicitly requested destruction of this old
# identity. Doing this while the old container was running always left rdkssa
# behind because an active mount point cannot be removed.
if [ -n "${retired_nvram_dir}" ] && [ "${retired_nvram_dir}" != "${nvram_source}" ]; then
    nvram_root_real=$(readlink -m "${nvram_root}")
    retired_nvram_real=$(readlink -m "${retired_nvram_dir}")
    case "${retired_nvram_real}" in
        "${nvram_root_real}/${containername}"|"${nvram_root_real}/${containername}-"*) ;;
        *)
            echo "Error: refusing to clear unexpected retired NVRAM path: ${retired_nvram_real}" >&2
            exit 1
            ;;
    esac
    sudo find "${retired_nvram_real}" -xdev -mindepth 1 -delete \
        && sudo rmdir "${retired_nvram_real}" \
        || echo "WARN: could not remove retired NVRAM directory: ${retired_nvram_real}" >&2
fi
