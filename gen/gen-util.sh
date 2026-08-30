#!/bin/bash


check_lxd_version() {
    if command -v lxd &> /dev/null; then
        lxd_version=$(lxd --version)
        major_version=$(echo "$lxd_version" | cut -d. -f1)
        if [[ $major_version -eq 4 ]] || [[ $major_version -eq 5 ]]; then
            #echo "LXD is installed with version $lxd_version."
            :
        else
            #echo "LXD is installed, but the version is not 4 or 5. Current version: $lxd_version."
            :
        fi
    else
        echo "LXD is not installed."
        exit 1
    fi
}


check_network() {
    echo "Waiting for network..."
    attempt=0
    max_attempts=10
    while ! lxc exec $1 -- ping -c 4 8.8.8.8 > /dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ $attempt -ge $max_attempts ]; then
            echo "Network check failed after $max_attempts attempts."
            exit 1
        fi
        #echo "Ping failed, retrying in 1 second..."
        sleep 1
    done
    echo "Network is up."
}


check_devuan_chimaera() {
    # non ubuntu images are no longer (early '24) publically served
    #
    # posted the image on dropbox
    #
    # https://www.dropbox.com/scl/fi/i1amx0tvbd4lygg29o4st/devuan-chimaera.tar.gz?rlkey=9q0mrda1eaohfr85xj2l8zryh&dl=0
    # wget 'https://dl.dropboxusercontent.com/scl/fi/i1amx0tvbd4lygg29o4st/devuan-chimaera.tar.gz?rlkey=9q0mrda1eaohfr85xj2l8zryh&dl=0' -O devuan-chimaera.tar.gz
    # Check if the LXD image with a specific alias exists
    if lxc image list | grep -q "devuan-chimaera-base"; then
        :
        #echo "Image with alias 'devuan-chimaera-base' exists."
    else
        echo "Creating devuan-chimaera-base image"
        url="https://dl.dropboxusercontent.com/scl/fi/i1amx0tvbd4lygg29o4st/devuan-chimaera.tar.gz?rlkey=9q0mrda1eaohfr85xj2l8zryh&dl=0"
        file="$M_ROOT/tmp/devuan-chimaera.tar.gz"
        [ -e "$encfile" ] || curl -L -o "$file" "$url"
        tar xzf $file -C $M_ROOT/tmp
        lxc image import $M_ROOT/tmp/devuan-chimaera $M_ROOT/tmp/devuan-chimaera.root --alias devuan-chimaera-base
    fi
}


# Validates version string format: name-release-customerid[-index]
# where name=mv1|mv2plus|mv3|mv27|mv37, release=r21|r22, customerid=7|9|20, index=001-099
# Returns unique hash 701-4020 or -1 if invalid
# Hash format: name(1-5)release(0-4)custid(0-2)index(00-99)

validate_and_hash() {

    local input="$1"
    local regex="^(mv1|mv2plus|mv3|mv27|mv37|bpibroadband|bpiap|bpi-ap|bpi)(-[0-9]{4})?(-0(0[1-9]|[1-9][0-9]))?$"
    # Initial validation: <type>-<MMDD>[-0NN]
    if [[ ! "$input" =~ $regex ]]; then
        echo "-1"
        return 1
    fi
    # Deterministic VLAN in 1..4094 derived from the full container name. The
    # old scheme packed name/release/bng into disjoint numeric ranges, but the
    # name is now <type>-<datestamp> so we just hash it. This value is only used
    # for the default VLAN-filtered lan-pN bridges (when -l is omitted); a custom
    # -l bridge attaches untagged and ignores it entirely.
    local h
    h=$(printf '%s' "$input" | cksum | cut -d' ' -f1)
    echo $(( (h % 4094) + 1 ))
    return 0
}


hash_to_string() {
    local hash="$1"

    # Subtract 1 from hash (as per original function)
    ((hash--))

    # Extract components. name_val must be split off first via / and % against
    # the 700 multiplier (not a power of ten, so it doesn't sit cleanly above
    # the other fields' decimal digits the way the old 1000 multiplier did) --
    # the remainder is then the same release/cust/index sub-encoding as before.
    local name_val=$((hash / 700))
    local remainder=$((hash % 700))
    local index_num=$((remainder % 10))
    local cust_position=$(((remainder / 10) % 10))
    local release_position=$(((remainder / 100) % 10))

    # Validate ranges
    if [ $name_val -lt 1 ] || [ $name_val -gt 5 ] ||
       [ $release_position -gt 4 ] ||
       [ $cust_position -gt 2 ] ||
       [ $index_num -gt 99 ]; then
        echo "Invalid hash"
        return 1
    fi

    # Convert name_val back to string
    local name
    case "$name_val" in
        1) name="mv1" ;;
        2) name="mv2plus" ;;
        3) name="mv3" ;;
        4) name="mv27" ;;
        5) name="mv37" ;;
        *) echo "Invalid hash"
           return 1 ;;
    esac

    # Convert release_position back to release number
    local release
    case "$release_position" in
        0) release="r21" ;;
        1) release="r22" ;;
        2) release="r23" ;;
        3) release="r24" ;;
        4) release="r25" ;;
        *) echo "Invalid hash"
           return 1 ;;
    esac

    # Convert cust_position back to customer_id
    local customer_id
    case "$cust_position" in
        0) customer_id="7" ;;
        1) customer_id="9" ;;
        2) customer_id="20" ;;
        *) echo "Invalid hash"
           return 1 ;;
    esac

    # Build the final string
    local result="$name-$release-$customer_id"

    # Add index if present (non-zero)
    if [ $index_num -ne 0 ]; then
        # Format index with leading zeros
        printf -v formatted_index "%02d" $index_num
        result="$result-$formatted_index"
    fi

    echo "$result"
    return 0
}


# Validate container name format
validate_container_name() {
    local name=$1
    local regex="^(mv1|mv2plus|mv3|mv27|mv37|bpibroadband|bpiap|bpi-ap|bpi)(-[0-9]{4})?(-0(0[1-9]|[1-9][0-9]))?$"
    [[ $name =~ $regex ]]
    return $?
}


# Generate first MAC address with fixed OUI
generate_mac1() {
    local container_name=$1
    local fixed_oui="00:60:2F"

    # Use md5sum and take first 6 characters
    local hash=$(echo -n "$container_name" | md5sum | cut -c1-6)

    # Convert hash to MAC address format (last 3 bytes)
    local nic_part=$(echo $hash | sed 's/\(..\)/:\1/g' | sed 's/^://')

    # Combine OUI and NIC parts
    echo "${fixed_oui}:${nic_part}"
}


# Generate second MAC address with same OUI but different hash approach
generate_mac2() {
    local container_name=$1
    local fixed_oui="00:60:2F"

    # Use sha256sum and take characters 7-12 for different hash result
    local hash=$(echo -n "$container_name:secondary" | md5sum | cut -c7-12)

    # Convert hash to MAC address format (last 3 bytes)
    local nic_part=$(echo $hash | sed 's/\(..\)/:\1/g' | sed 's/^://')

    # Combine OUI and NIC parts
    echo "${fixed_oui}:${nic_part}"
}


check_and_create_lxdbr1() {

    bridge_name="lxdbr1"
    # Check if the network bridge exists
    if ! lxc network list | grep -q "^| ${bridge_name} "; then
        echo "Bridge ${bridge_name} does not exist. Creating it..."
        # Create the network bridge
        lxc network create ${bridge_name}
    else
        echo "Bridge ${bridge_name} exists. Reapplying settings..."
    fi
    # Set the IPv4 address and disable DHCP
    lxc network set ${bridge_name} ipv4.address "10.10.10.1/24"
    lxc network set ${bridge_name} ipv4.dhcp "false"
    #lxc network set ${bridge_name} ipv4.dhcp.ranges "10.10.10.100-10.10.10.150"
    # Set the IPv6 address and disable DHCP
    lxc network set ${bridge_name} ipv6.address "2001:dbf:0:1::1/64"
    lxc network set ${bridge_name} ipv6.dhcp "false"
    #lxc network set ${bridge_name} ipv6.dhcp.ranges "2001:dbf:0:1::100-2001:dbf:0:1::254"
    lxc network set ${bridge_name} ipv6.dhcp.stateful "true"
    if true; then
        # We need NAT, as this provides the ability to connect to internet from ACS
        # and BNG containers.
        # However we do not want NAT for wan interface on BNG as this prevents ACS
        # connecting to MVx, the 107. address would be replaced by the ip address of
        # the gateway interface.
        # setting nat to true using lxd, would enable NAT for any outgoing interface
        # Create a custom NAT rule that disables NAT for wan interface
        lxc network set ${bridge_name} ipv4.nat "false"
        lxc network set ${bridge_name} ipv6.nat "false"
        ## # Define the rule components
        ## SOURCE_IP="10.10.10.0/24"
        ## OUT_INTERFACE="wan"
        ## TARGET="MASQUERADE"
        ## # Check if the rule exists
        ## if sudo iptables -t nat -C POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE -j $TARGET 2>/dev/null; then
        ##     echo "Bridge ${bridge_name}: NAT rule exists."
        ## else
        ##     echo "Bridge ${bridge_name}: NAT rule does not exist. adding it."
        ##     sudo iptables -t nat -A POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE -j $TARGET
        ## fi
        # Define the rule components
        SOURCE_IP="10.10.10.0/24"
        OUT_INTERFACE="wan"
        TARGET="MASQUERADE"
        DEST_IP="10.10.10.0/24"
        # Check if the rule exists
        if sudo iptables -t nat -C POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE ! -d $DEST_IP -j $TARGET 2>/dev/null; then
            echo "Bridge ${bridge_name}: NAT rule exists."
        else
            echo "Bridge ${bridge_name}: NAT rule does not exist. Adding it."
            sudo iptables -t nat -A POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE ! -d $DEST_IP -j $TARGET
        fi
        #ipv6..
    else
        lxc network set ${bridge_name} ipv4.nat "true"
        lxc network set ${bridge_name} ipv6.nat "true"
    fi
}


check_lxdbr0() {

    # Check for the specific LXD comment
    if sudo iptables -t nat -L -v | grep -q "generated for LXD network lxdbr0"; then
        echo "LXD network rule for lxdbr0 found"
    else
        echo "LXD network rule for lxdbr0 not found"
    fi
}


check_and_create_wan_bridge() {

    bridge_name=$1

    if ! ip link show type bridge | grep -q "^.* ${bridge_name}:"; then
        echo "Creating bridge: ${bridge_name}"

        if ! sudo ip link add name ${bridge_name} type bridge; then
            echo "Failed to create bridge ${bridge_name}"
            ret=1
        fi
        # Disable IPv6 router advertisements
        if ! sudo sysctl -w net.ipv6.conf.${bridge_name}.accept_ra=0 > /dev/null 2>&1; then
            echo "Warning: Failed to disable IPv6 RA on ${bridge_name}"
        fi
        # Bring bridge up
        if ! sudo ip link set ${bridge_name} up; then
            echo "Failed to bring up bridge ${bridge_name}"
            ret=1
        fi
        # Optional: Enable promiscuous mode and STP
        #sudo ip link set dev "${bridge_name}" promisc on
        #sudo bridge stp "${bridge_name}" on

    else
        echo "Bridge ${bridge_name} exists, flushing IP addresses"
        # Flush existing IP addresses
        if ! sudo ip addr flush dev ${bridge_name}; then
            echo "Warning: Failed to flush IP addresses from ${bridge_name}"
        fi
    fi
}


check_and_create_lan_bridge() {

    bridge_name=$1

    if ! ip link show type bridge | grep -q "^.* ${bridge_name}:"; then
        echo "Creating bridge: ${bridge_name}"

        # Create VLAN-aware bridge
        if ! sudo ip link add name ${bridge_name} type bridge \
            vlan_filtering 1 \
            vlan_default_pvid 1; then
            echo "Failed to create VLAN-aware bridge ${bridge_name}"
            ret=1
        fi
        # Bring bridge up
        if ! sudo ip link set ${bridge_name} up; then
            echo "Failed to bring up bridge ${bridge_name}"
            ret=1
        fi
        # Verify VLAN filtering is enabled
        if ! grep -q "1" /sys/class/net/${bridge_name}/bridge/vlan_filtering 2>/dev/null; then
            echo "Warning: VLAN filtering might not be enabled on ${bridge_name}"
        fi

    else
        echo "Bridge ${bridge_name} exists, flushing IP addresses"
        # Flush existing IP addresses
        if ! sudo ip addr flush dev ${bridge_name}; then
            echo "Warning: Failed to flush IP addresses from ${bridge_name}"
        fi
        # For existing LAN bridges, ensure VLAN filtering is enabled
        if ! grep -q "1" /sys/class/net/${bridge_name}/bridge/vlan_filtering 2>/dev/null; then
            echo "Enabling VLAN filtering on existing bridge ${bridge_name}"
            sudo ip link set ${bridge_name} down
            sudo ip link set ${bridge_name} type bridge vlan_filtering 1
            sudo ip link set ${bridge_name} up
        else
            echo "VLAN filtering is enabled on existing bridge ${bridge_name}"
        fi
    fi
}


check_bridges() {
    local ret=0

    for bridge_name in $bridges; do
        # Check if bridge exists using ip link - silent if exists
        if ! ip link show dev "$bridge_name" &>/dev/null; then
            echo "Bridge $bridge_name does not exist"
            ret=1
        fi
    done

    # Check lxdbr0 - silent if exists
    if ! ip link show dev "lxdbr0" &>/dev/null; then
        echo "Bridge lxdbr0 does not exist"
        ret=1
    fi

    return $ret
}


check_and_create_bridges() {

    for bridge_name in $bridges; do
        case "$bridge_name" in

            # lxdbr1
            lxdbr1)
                echo '------------------------------------------------------'
                check_and_create_lxdbr1
                ;;

            # WAN bridges
            wan|cm)
                echo '------------------------------------------------------'
                check_and_create_wan_bridge $bridge_name
                ;;

            # LAN bridges with VLAN support
            lan-p[1-4]|br-wlan[0-1]|wanoe)
                echo '------------------------------------------------------'
                check_and_create_lan_bridge $bridge_name
                # sudo bridge vlan show dev $bridge_name
                ;;

            *)
                echo '------------------------------------------------------'
                echo "Error: Unsupported bridge name: ${bridge_name}"
                ret=1
                continue
                ;;
        esac
    done

    echo '------------------------------------------------------'

    #check_lxdbr0
    #echo '------------------------------------------------------'

    return $ret
}


# Function to verify bridge configuration
verify_bridge_config() {
    local bridge_name="$1"
    # Check if bridge exists
    if ! ip link show type bridge | grep -q "^.* ${bridge_name}:"; then
        return 1
    fi
    # For LAN bridges, verify VLAN filtering
    if [[ "$bridge_name" =~ ^(lan-p[1-4]|wlan[0-1])$ ]]; then
        if ! grep -q "1" /sys/class/net/${bridge_name}/bridge/vlan_filtering 2>/dev/null; then
            return 1
        fi
    fi
    return 0
}


remove_bridge() {

    bridge_name=$1
    if [[ "$bridge_name" == "lxdbr1" ]]; then
        if lxc network delete "${bridge_name}"; then
            echo "Bridge ${bridge_name} deleted successfully."
        else
            echo "Error: Failed to delete bridge ${bridge_name}."
            lxc network show ${bridge_name}
        fi
    elif ip link show type bridge | grep -q "^.* ${bridge_name}:"; then
        sudo ip link set ${bridge_name} down
        sudo ip link delete ${bridge_name} type bridge
        echo "Bridge ${bridge_name} deleted successfully."
    fi
    if [[ "$bridge_name" == "lxdbr1" ]]; then
        # Define the rule components
        SOURCE_IP="10.10.10.0/24"
        OUT_INTERFACE="wan"
        TARGET="MASQUERADE"
        DEST_IP="10.0.0.0/24"
        # Check if the rule exists
        if sudo iptables -t nat -C POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE ! -d $DEST_IP -j $TARGET 2>/dev/null; then
            echo "Bridge ${bridge_name}: NAT rule exists. Deleting the rule."
            sudo iptables -t nat -D POSTROUTING -s $SOURCE_IP ! -o $OUT_INTERFACE ! -d $DEST_IP -j $TARGET
        else
            echo "Bridge ${bridge_name}: NAT rule does not exist."
        fi
    fi
}


# Function to get parent bridge for a network device in a profile
get_parent_bridge() {
    local profile_name="$1"
    local eth_device="$2"

    # Check if profile exists
    if ! lxc profile show "$profile_name" >/dev/null 2>&1; then
        echo "Error: Profile '$profile_name' not found" >&2
        return 1
    fi

    # Get the parent bridge using yaml path
    local parent
    parent=$(lxc profile show "$profile_name" | awk -v dev="$eth_device" '
        BEGIN { found=0; in_device=0 }
        $1 == "devices:" { in_devices=1 }
        in_devices && $1 == dev":" { found=1; next }
        found && $1 == "parent:" { print $2; exit }
    ')

    if [ -z "$parent" ]; then
        echo "Error: Device '$eth_device' not found in profile '$profile_name' or parent not defined" >&2
        return 1
    fi

    echo "$parent"
    return 0
}

get_eth_interface() {
    local mvstring="$1"
    # Extract MV version and P number using expanded regex to include vcpe
    if [[ "$mvstring" =~ ^(mv[123]|mv2plus|mv27|mv37)-.*-p([1-4])$ || "$mvstring" =~ ^(vcpe)-p([1-4])$ ]]; then
        local mv_type="${BASH_REMATCH[1]}"
        local p_num="${BASH_REMATCH[2]}"
        # Convert p_num to zero-based index for array access
        local idx=$((p_num - 1))

        # Handle different device types
        if [ "$mv_type" = "mv3" ] || [ "$mv_type" = "mv37" ]; then
            # For mv3/mv37, eth1..4 based on p1..p4 (mv37 mirrors mv3's
            # interface layout -- eth0 is wan, eth1..4 are the lan ports)
            echo "eth$((idx + 1))"
        elif [ "$mv_type" = "vcpe" ]; then
            # For vcpe, same as mv3: eth1..4 based on p1..p4
            echo "eth$((idx + 1))"
        else
            # For mv1/mv2plus/mv27, eth0..3 based on p1..p4
            echo "eth$idx"
        fi
        return 0
    else
        echo "Error: Invalid format. Expected format like mv1-r21-7-p1, mv2plus-r21-7-001-p3, mv3-r21-9-002-p4, mv27-r25-7-p1, or vcpe-p1" >&2
        return 1
    fi
}


ensure_lxd_lab_pool() {
    # Keep short-lived hwsim lab roots off the host's default storage backend.
    # In particular, loop-backed ZFS can serialize image/container mutations for
    # minutes after repeated lab teardown. The dir driver is sufficient here and
    # gives deterministic create/delete latency. One pool is shared by BPI nodes
    # and WLAN clients; override the name only with another dir-backed pool.
    local pool="${LAB_LXD_POOL:-bpi-lab}" driver
    if ! lxc storage show "$pool" > /dev/null 2>&1; then
        if [ "$pool" != "bpi-lab" ]; then
            echo "ERROR LXD: LAB_LXD_POOL '$pool' does not exist" >&2
            return 1
        fi
        lxc storage create "$pool" dir > /dev/null || {
            echo "ERROR LXD: could not create directory-backed pool '$pool'" >&2
            return 1
        }
    fi
    driver=$(lxc storage show "$pool" | sed -n 's/^driver: *//p' | head -1)
    if [ "$driver" != "dir" ]; then
        echo "ERROR LXD: lab pool '$pool' uses '$driver', expected 'dir'" >&2
        return 1
    fi
    printf '%s\n' "$pool"
}


check_and_create_virt_wlan() {
    # Define the expected interfaces
    local interfaces=("virt-wlan0" "virt-wlan1" "virt-wlan2" "virt-wlan3")
    local missing=0

    # Check each interface
    for iface in "${interfaces[@]}"; do
        if ! ip link show "$iface" &>/dev/null; then
            missing=$((missing + 1))
        fi
    done

    # POOL MODEL: load the module ONCE with HWSIM_POOL_SIZE radios and never
    # reload if it is already loaded. (The old logic reloaded to 4 radios
    # whenever any virt-wlan0..3 was absent from the host -- but a radio that has
    # been allocated into a container is legitimately absent, so that reload
    # destroyed every running container's Wi-Fi. mv.sh's hwsim_attach_radios
    # hands free pool radios to containers as LXD physical NICs; they return to
    # the pool automatically on container delete.)
    local size
    if [ -n "${HWSIM_POOL_SIZE:-}" ]; then
        size="$HWSIM_POOL_SIZE"
    elif [ -r /sys/module/mac80211_hwsim/parameters/radios ]; then
        # An already-running medium or large profile is authoritative. Reusing
        # the live size keeps one-client operations from rejecting a valid
        # 64-radio pool merely because the fresh-install default is 32.
        size=$(cat /sys/module/mac80211_hwsim/parameters/radios)
    else
        size=32
    fi
    # Freeze the supported runtime defaults by kernel generation. Linux 7.0 is
    # the tri-band platform: it needs three concurrent channel contexts plus
    # custom_03 (regtest=5) so 6 GHz is IR-capable. Linux 6.8 remains the
    # dual-band regression platform. Environment variables still permit an
    # explicit experimental override.
    local kgen chans regtest
    kgen=$(uname -r | sed -E 's/^([0-9]+\.[0-9]+).*/\1/')
    if [ -n "${HWSIM_CHANNELS:-}" ]; then
        chans="$HWSIM_CHANNELS"
    elif [ "$kgen" = "7.0" ]; then
        chans=3
    else
        chans=2
    fi
    if [ -n "${HWSIM_REGTEST:-}" ]; then
        regtest="$HWSIM_REGTEST"
    elif [ "$kgen" = "7.0" ] && [ "$chans" -ge 3 ]; then
        regtest=5
    else
        regtest=0
    fi
    if [ ! -d /sys/module/mac80211_hwsim ]; then
        echo "Loading mac80211_hwsim with ${size} radios, ${chans} channels${regtest:+, regtest=${regtest}}..."
        local args=(radios="$size" channels="$chans")
        args+=(regtest="$regtest")
        sudo modprobe mac80211_hwsim "${args[@]}"
        sleep 1
    else
        # Already loaded, and we deliberately never reload (that would destroy the
        # Wi-Fi of every running container). Refuse a mismatched pool instead of
        # silently launching a dual-band node into the tri-band experiment.
        local live live_radios live_regtest
        live=$(cat /sys/module/mac80211_hwsim/parameters/channels 2>/dev/null)
        live_radios=$(cat /sys/module/mac80211_hwsim/parameters/radios 2>/dev/null)
        live_regtest=$(cat /sys/module/mac80211_hwsim/parameters/regtest 2>/dev/null)
        if [ "$live" != "$chans" ] || [ "$live_radios" != "$size" ] || [ "$live_regtest" != "$regtest" ]; then
            echo "ERROR hwsim: running pool radios=${live_radios:-unknown}, channels=${live:-unknown}, regtest=${live_regtest:-none}; want radios=${size}, channels=${chans}, regtest=${regtest:-none}." >&2
            echo "ERROR hwsim: stop all hwsim containers, unload the module, and retry." >&2
            exit 1
        fi
    fi
    # stable names: hwsim wlanN -> virt-wlanN (real wifi wlp*/eth* untouched)
    local _p _nd
    for _p in /sys/class/ieee80211/phy*; do
        _nd=$(ls "$_p/device/net" 2>/dev/null | head -1)
        case "$_nd" in
            wlan[0-9]*) sudo ip link set "$_nd" down 2>/dev/null
                        sudo ip link set "$_nd" name "virt-$_nd" 2>/dev/null
                        sudo ip link set "virt-$_nd" up 2>/dev/null;;
        esac
    done
    return 0
}


banner() {
    local text="$1"
    local color="${2:-white}"  # Default to white if no color specified

    case "$color" in
        "grey")   color_code="\e[30m" ;;
        "red")    color_code="\e[31m" ;;
        "white")  color_code="\e[37m" ;;
        "blue")   color_code="\e[34m" ;;
        "green")  color_code="\e[32m" ;;
        "yellow") color_code="\e[33m" ;;
        *)        color_code="\e[37m" ;; # Default to white
    esac

    echo -e "${color_code}${text}\e[0m"
}

validate_lan_port() {
    local port_num=$1
    local lan_var="lan_p${port_num}"
    local vlan_var="lan_p${port_num}_vlan"

    [[ -n "${!lan_var}" && "${!lan_var}" != "wanoe" && "${!lan_var}" != "wan" ]] && {
        declare -g ${vlan_var}="$(validate_and_hash "${!lan_var}")" &&
        [[ "${!vlan_var}" == "-1" ]] && {
            echo "cannot determine unique vlan for ${lan_var} ${!lan_var}"
            exit 1
        }
    }
}


main() {
    M_ROOT="$( dirname "$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )" )"

    if [[ ! "$PWD" == "$M_ROOT"* ]]; then
        SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
        echo "Error: Script(s) are being run from outside the current directory !" >&2
        echo "Current directory: $PWD" >&2
        echo "PATH             : $SCRIPT_PATH" >&2
        echo "Please change the current directory or update PATH." >&2
        exit 1
    fi

    export M_ROOT

    mkdir -p $M_ROOT/tmp

    check_lxd_version

    bridges="
            lxdbr1 \
            wan \
            cm \
            wanoe \
            lan-p1 lan-p2 lan-p3 lan-p4 \
            br-wlan0 br-wlan1
        "


    check_bridges
    if [ $? -eq 1 ]; then
        echo -e "Required bridges are missing. Creating bridges now...\n"
        check_and_create_bridges
    fi

    check_and_create_virt_wlan

}

main

# ==== mac80211_hwsim radio pool for the vCPE Wi-Fi HAL (hal-wifi-hwsim) ====
# Pre-sized pool: load the module once; radios cycle host<->container via LXD
# physical NICs and return to the host automatically on container delete. A
# radio is "free" iff its virt-wlan* netdev is present in the HOST netns.
HWSIM_POOL_SIZE="${HWSIM_POOL_SIZE:-$(cat /sys/module/mac80211_hwsim/parameters/radios 2>/dev/null || echo 32)}"
# The pool is ensured by check_and_create_virt_wlan (idempotent, defined above,
# called from main). The helpers below are the per-container allocator for mv.sh.

hwsim_free_radios() {
    # free radios = virt-wlan* resident in the HOST netns (in-container ones are absent)
    #
    # A phy only counts as free if that virt-wlan* is its ONLY netdev. Moving a
    # wireless netdev into a container moves the whole wiphy, so any leftover vif
    # riding along lands in the container too -- and if one of them holds the name
    # LXD wants, the move fails with "Failed to rename network device ... to
    # wlan0: File exists" and the container will not start. Leftovers accumulate
    # when a container is deleted without tearing its VAPs down first, so this is
    # not rare. Testing only `ls | head -1` could not tell the two apart: it
    # returned the virt-wlan* name whenever that sorted first, which is how a phy
    # carrying nine stale vifs was handed out as free on 2026-08-06.
    local p nds n vw
    for p in /sys/class/ieee80211/phy*; do
        nds=$(ls "$p/device/net" 2>/dev/null)
        # match the pool name anywhere in the list, not just first: a stray vif
        # may sort either side of it (junkvif0 before, wlan1 after)
        vw=$(printf '%s\n' "$nds" | grep -m1 '^virt-wlan[0-9]')
        [ -n "$vw" ] || continue
        n=$(printf '%s\n' "$nds" | grep -c .)
        if [ "$n" -eq 1 ]; then
            echo "$vw"
        else
            echo "WARN hwsim: $(basename $p) carries $n netdevs, skipping $vw: $(echo $nds | tr '\n' ' ')" >&2
        fi
    done | sort -V
}

# A host-resident radio is not necessarily available for a new profile. When
# every lab container is stopped, every phy returns to the host namespace, but
# existing LXD profiles still reserve their parent=virt-wlanN assignment for
# the next start. Treat those profile references as allocations too; otherwise
# an image redeploy can give a stopped controller's radio to an extender and
# both instances then fail to coexist.
hwsim_reserved_radios() {
    local profile device parent
    while read -r profile; do
        [ -n "$profile" ] || continue
        while read -r device; do
            [ -n "$device" ] || continue
            parent=$(lxc profile device get "$profile" "$device" parent 2>/dev/null || true)
            case "$parent" in
                virt-wlan[0-9]*) echo "$parent" ;;
            esac
        done < <(lxc profile device list "$profile" 2>/dev/null)
    done < <(lxc profile list --format csv -c n 2>/dev/null)
}

# Reclaim "dirty" pool phys: when a container is deleted, its wiphy returns to the
# host with the VAPs it created (wifi0, wifi0.1, ... wifi1.3) still attached, so
# hwsim_free_radios skips it and the radio drains from the pool. Those leftover
# vifs belong to a gone container (the phy is host-resident again, proven by its
# virt-wlan* being in the host netns), so tear them down, leaving only virt-wlan*
# -- which makes the radio free again. Idempotent; only touches pool phys.
hwsim_reclaim_dirty_phys() {
    local p nds vw nd
    for p in /sys/class/ieee80211/phy*; do
        nds=$(ls "$p/device/net" 2>/dev/null)
        vw=$(printf '%s\n' "$nds" | grep -m1 '^virt-wlan[0-9]')
        [ -n "$vw" ] || continue                       # not a host-resident pool phy
        printf '%s\n' "$nds" | grep -vxF "$vw" | grep -v '^$' | while read -r nd; do
            sudo iw dev "$nd" del 2>/dev/null \
                && echo "  hwsim: reclaimed stale vif $nd on $(basename $p) (-> $vw free)" >&2
        done
    done
}

# attach N free hwsim radios to a profile as physical NICs (named wlan0..N-1).
hwsim_attach_radios() {
    local profile="$1" count="${2:-3}" candidate reserved_radio
    [ "$count" -gt 0 ] || return 0
    check_and_create_virt_wlan
    hwsim_reclaim_dirty_phys           # return stale-VAP radios to the pool first
    local reserved=($(hwsim_reserved_radios)) free=() i=0
    while read -r candidate; do
        [ -n "$candidate" ] || continue
        for reserved_radio in "${reserved[@]}"; do
            [ "$candidate" != "$reserved_radio" ] || continue 2
        done
        free+=("$candidate")
    done < <(hwsim_free_radios)
    if [ "${#free[@]}" -lt "$count" ]; then
        echo "WARN hwsim: only ${#free[@]} unreserved free radios, need $count (raise HWSIM_POOL_SIZE, reload at idle)"
    fi
    while [ "$i" -lt "$count" ] && [ "$i" -lt "${#free[@]}" ]; do
        lxc profile device add "$profile" "wlan${i}" nic \
            nictype=physical parent="${free[$i]}" name="wlan${i}" 1>/dev/null 2>&1 \
            && echo "  hwsim: wlan${i} <- ${free[$i]}"
        i=$((i+1))
    done
}
