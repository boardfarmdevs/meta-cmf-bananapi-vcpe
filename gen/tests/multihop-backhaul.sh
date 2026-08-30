#!/usr/bin/env bash
# Build and verify deterministic EasyMesh backhaul trees in the LXD lab.
#
# The 5 GHz mesh STA is Device.WiFi.STA.2 / wifi1.3 and the corresponding
# backhaul AP is Device.WiFi.AccessPoint.14 / wifi1.1 in the current tri-band
# BPI image.  BSSIDs are discovered at run time; no generated radio identity is
# embedded in this script.
set -euo pipefail

exec </dev/null

topology_url=${TOPOLOGY_URL:-http://127.0.0.1:8888/api/v1/topology}
result_root=${MULTIHOP_RESULT_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)/tmp/test-results/multihop}
gateway=bpibroadband
anchor=bpiap-003
extenders=(bpiap-003 bpiap-002 bpiap-001 bpiap)
wait_link_seconds=${MULTIHOP_LINK_TIMEOUT:-90}
wait_model_seconds=${MULTIHOP_MODEL_TIMEOUT:-180}
wait_parent_seconds=${MULTIHOP_PARENT_TIMEOUT:-60}
wait_onboard_seconds=${MULTIHOP_ONBOARD_TIMEOUT:-240}
minimum_clients=${MULTIHOP_MIN_CLIENTS:-1}

usage() {
    cat <<'EOF'
Usage:
  ./gen/tests/multihop-backhaul.sh apply star|branch|chain
  ./gen/tests/multihop-backhaul.sh verify star|branch|chain
  ./gen/tests/multihop-backhaul.sh test star|branch|chain
  ./gen/tests/multihop-backhaul.sh cold-test star|branch|chain
  ./gen/tests/multihop-backhaul.sh restore
  ./gen/tests/multihop-backhaul.sh status

Profiles:
  star    Agent-1 -> {bpiap-003,bpiap-002,bpiap-001,bpiap}
  chain   Agent-1 -> bpiap-003 -> bpiap-002 -> bpiap-001 -> bpiap
  branch  Agent-1 -> bpiap-003 -> {bpiap-002,bpiap-001}; bpiap-002 -> bpiap

The script discovers each parent's live 5 GHz backhaul AP BSSID, enables a
parent extender's lazy backhaul AP with AccessPoint.14.ForceApply, and writes
the selected BSSID to the child's Device.WiFi.STA.2.Bssid through RBUS. OneWifi
then performs the real wifi1.3 association; the EasyMesh agents publish it to
the controller model and topology API. This is not a WebUI-only relationship
and it does not use wmediumd attenuation to simulate a parent.

"apply" changes the live associations. "verify" checks physical links,
parent-side stations, forwarding, topology edges, signal telemetry, clients
and the controller database. "test" applies and verifies. "cold-test" also
controls extender/service startup order. "restore" returns to the star.
EOF
}

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

normalize_mac() {
    printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]'
}

compact_mac() {
    normalize_mac "$1" | tr -d ':'
}

container_running() {
    [ "$(lxc info "$1" 2>/dev/null | awk '/^Status:/{print $2; exit}')" = RUNNING ]
}

require_lab() {
    need lxc
    need curl
    need jq
    for container in "$gateway" "${extenders[@]}"; do
        container_running "$container" || fail "$container is not running"
    done
    curl -fsS "$topology_url" >/dev/null || fail "topology API is unavailable: $topology_url"
}

mesh_ap_bssid() {
    local container=$1
    timeout 15 lxc exec "$container" -- sh -c \
        "iw dev wifi1.1 info 2>/dev/null | awk '/addr/{print \$2; exit}'" \
        | tr '[:upper:]' '[:lower:]'
}

mesh_ap_ready() {
    local container=$1
    timeout 15 lxc exec "$container" -- sh -c '
        iw dev wifi1.1 info 2>/dev/null |
            awk '\''/ssid mesh_backhaul/{ssid=1} END{exit !ssid}'\'' &&
        ip link show wifi1.1 2>/dev/null | grep -q "UP"'
}

mesh_sta_bssid() {
    local container=$1
    timeout 15 lxc exec "$container" -- sh -c \
        "iw dev wifi1.3 link 2>/dev/null | awk '/Connected to/{print \$3; exit}'" \
        | tr '[:upper:]' '[:lower:]'
}

mesh_sta_mac() {
    local container=$1
    timeout 15 lxc exec "$container" -- sh -c \
        "iw dev wifi1.3 info 2>/dev/null | awk '/addr/{print \$2; exit}'" \
        | tr '[:upper:]' '[:lower:]'
}

# The container image persists an AL base identity ending in :00.  ieee1905-em
# uses the same five leading octets and the EasyMesh AL offset :20.
container_al_mac() {
    local container=$1 base last prefix
    base=$(timeout 15 lxc exec "$container" -- cat /nvram/em_al_base_mac 2>/dev/null \
        | tr '[:upper:]' '[:lower:]' | tr -d '\r\n')
    [[ "$base" =~ ^([0-9a-f]{2}:){5}[0-9a-f]{2}$ ]] \
        || fail "$container has no valid /nvram/em_al_base_mac"
    prefix=${base%:*}
    last=${base##*:}
    printf '%s:%02x\n' "$prefix" "$((16#$last + 0x20))"
}

controller_bss_count() {
    local container=$1 al
    al=$(container_al_mac "$container")
    curl -fsS "$topology_url" | jq -er --arg al "$al" '
        ([.nodes[]? |
          select(((.id // "") | ascii_downcase) == $al) |
          .haulTypes[]?.BSSList[]?] | length) // 0'
}

# Service activation only says that the local processes have started.  WSC,
# topology publication and controller model construction finish later.  Cold
# multi-hop onboarding must serialize on that model convergence; otherwise a
# burst of simultaneous M1/M2 exchanges can leave registered zero-BSS nodes.
wait_for_onboarding() {
    local container=$1 start now count=0 last_count=-1
    start=$(date +%s)
    while :; do
        count=$(controller_bss_count "$container" 2>/dev/null || printf '0\n')
        if [ "$count" -ge 9 ]; then
            echo "onboarding_ready container=$container bss_records=$count elapsed_s=$(( $(date +%s) - start ))"
            return 0
        fi
        now=$(date +%s)
        if [ "$count" != "$last_count" ]; then
            echo "onboarding_wait container=$container bss_records=$count elapsed_s=$((now - start))"
            last_count=$count
        fi
        [ $((now - start)) -lt "$wait_onboard_seconds" ] \
            || fail "$container did not publish a complete controller model (bss_records=$count)"
        sleep 2
    done
}

force_mesh_ap() {
    local container=$1 bssid="" attempt
    if mesh_ap_ready "$container"; then
        bssid=$(mesh_ap_bssid "$container")
        echo "backhaul_ap_ready parent=$container bssid=$bssid already_active=true"
        printf '%s\n' "$bssid"
        return 0
    fi
    echo "force_backhaul_ap parent=$container"
    timeout 20 lxc exec "$container" -- rbuscli setvalues \
        Device.WiFi.AccessPoint.14.ForceApply boolean true >/dev/null
    for attempt in $(seq 1 60); do
        bssid=$(mesh_ap_bssid "$container" || true)
        if [[ "$bssid" =~ ^([0-9a-f]{2}:){5}[0-9a-f]{2}$ ]] \
            && mesh_ap_ready "$container"; then
            echo "backhaul_ap_ready parent=$container bssid=$bssid elapsed_s=$attempt"
            printf '%s\n' "$bssid"
            return 0
        fi
        sleep 1
    done
    fail "$container mesh-backhaul AP did not become ready"
}

wait_for_link() {
    local child=$1 parent=$2 target=$3 start now actual="" child_sta stable=0
    child_sta=$(mesh_sta_mac "$child")
    start=$(date +%s)
    while :; do
        actual=$(mesh_sta_bssid "$child" || true)
        if [ "$actual" = "$target" ] &&
                parent_has_child "$parent" "$child_sta" &&
                timeout 10 lxc exec "$child" -- ping -q -c 1 -W 2 10.0.0.1 >/dev/null; then
            stable=$((stable + 1))
            if [ "$stable" -ge 3 ]; then
                echo "link_ready child=$child parent=$parent bssid=$actual authenticated=true stable_checks=$stable elapsed_s=$(( $(date +%s) - start ))"
                return 0
            fi
        else
            stable=0
        fi
        now=$(date +%s)
        [ $((now - start)) -lt "$wait_link_seconds" ] \
            || fail "$child did not associate with $target (actual=${actual:-none})"
        sleep 1
    done
}

set_parent() {
    local child=$1 parent=$2 target output
    if [ "$parent" = "$gateway" ]; then
        target=$(mesh_ap_bssid "$gateway")
        [ -n "$target" ] || fail "gateway mesh-backhaul BSSID is unavailable"
    else
        # ForceApply creates this intentionally lazy VAP.  Do not write it
        # again when the AP is already active: that is a real VAP reload, not
        # an idempotent read-modify operation, and disrupts existing children.
        force_mesh_ap "$parent" >/dev/null
        target=$(mesh_ap_bssid "$parent")
    fi
    echo "select_parent child=$child parent=$parent bssid=$target"
    output=$(timeout 20 lxc exec "$child" -- rbuscli setvalues \
        Device.WiFi.STA.2.Bssid bytes "$(compact_mac "$target")" 2>&1) || {
        printf '%s\n' "$output" >&2
        fail "BSSID selection failed for $child"
    }
    printf '%s\n' "$output" | grep -Eiq 'set(values)? succeeded|set successful' || {
        printf '%s\n' "$output" >&2
        fail "BSSID selection was not accepted for $child"
    }
    wait_for_link "$child" "$parent" "$target"
}

profile_pairs() {
    case "$1" in
        star)
            cat <<EOF
$anchor $gateway
bpiap-002 $gateway
bpiap-001 $gateway
bpiap $gateway
EOF
            ;;
        chain)
            cat <<EOF
$anchor $gateway
bpiap-002 $anchor
bpiap-001 bpiap-002
bpiap bpiap-001
EOF
            ;;
        branch)
            cat <<EOF
$anchor $gateway
bpiap-002 $anchor
bpiap-001 $anchor
bpiap bpiap-002
EOF
            ;;
        *) fail "unknown profile: $1" ;;
    esac
}

apply_profile() {
    local profile=$1 child parent pair
    local -a pairs
    require_lab
    echo "apply_profile=$profile"
    mapfile -t pairs < <(profile_pairs "$profile")
    for pair in "${pairs[@]}"; do
        read -r child parent <<< "$pair"
        set_parent "$child" "$parent"
    done
}

parent_has_child() {
    local parent=$1 child_sta=$2 interface
    while read -r interface; do
        timeout 10 lxc exec "$parent" -- iw dev "$interface" station dump </dev/null 2>/dev/null \
            | awk '/^Station /{print tolower($2)}' \
            | grep -qx "$child_sta" && return 0
    done < <(timeout 15 lxc exec "$parent" -- sh -c \
        "iw dev 2>/dev/null | awk '/Interface wifi1[.]1[.]sta/{print \$2}'")
    return 1
}

wait_for_parent_station() {
    local parent=$1 child_sta=$2 start
    start=$(date +%s)
    while ! parent_has_child "$parent" "$child_sta"; do
        [ $(( $(date +%s) - start )) -lt "$wait_parent_seconds" ] || return 1
        sleep 1
    done
}

api_has_edge() {
    local parent_al=$1 child_al=$2 target=$3
    curl -fsS "$topology_url" | jq -e \
        --arg from "$parent_al" --arg to "$child_al" --arg bssid "$target" \
        'any(.edges[]?; ((.from | ascii_downcase) == $from and
                         (.to | ascii_downcase) == $to and
                         (.upstreamBSSID | ascii_downcase) == $bssid))' >/dev/null
}

gateway_agent_al() {
    local gateway_bssid
    gateway_bssid=$(mesh_ap_bssid "$gateway")
    curl -fsS "$topology_url" | jq -er --arg bssid "$gateway_bssid" '
        first(.nodes[]? | select(any(.haulTypes[]?.BSSList[]?;
            ((.BSSID // "") | ascii_downcase) == $bssid)) | .id) |
        ascii_downcase'
}

api_edge_json() {
    local parent=$1 child=$2 target=$3 parent_al child_al
    if [ "$parent" = "$gateway" ]; then
        parent_al=$(gateway_agent_al)
    else
        parent_al=$(container_al_mac "$parent")
    fi
    child_al=$(container_al_mac "$child")
    curl -fsS "$topology_url" | jq -ec \
        --arg from "$parent_al" --arg to "$child_al" --arg bssid "$target" '
        [.edges[]? | select((.from | ascii_downcase) == $from and
                            (.to | ascii_downcase) == $to and
                            (.upstreamBSSID | ascii_downcase) == $bssid)] | first'
}

wait_for_api_edge() {
    local parent=$1 child=$2 target=$3 parent_al child_al start
    if [ "$parent" = "$gateway" ]; then
        parent_al=$(gateway_agent_al)
    else
        parent_al=$(container_al_mac "$parent")
    fi
    child_al=$(container_al_mac "$child")
    start=$(date +%s)
    while ! api_has_edge "$parent_al" "$child_al" "$target"; do
        [ $(( $(date +%s) - start )) -lt "$wait_model_seconds" ] \
            || fail "controller did not publish $parent -> $child ($target)"
        sleep 2
    done
    echo "model_ready parent=$parent child=$child upstream_bssid=$target elapsed_s=$(( $(date +%s) - start ))"
}

parent_child_rssi() {
    local parent=$1 child_sta=$2 interface signal=""
    while read -r interface; do
        signal=$(timeout 10 lxc exec "$parent" -- iw dev "$interface" station dump </dev/null 2>/dev/null |
            awk -v sta="$child_sta" '
                /^Station / {match_sta=(tolower($2) == sta)}
                match_sta && /^[[:space:]]*signal:/ {print int($2); exit}')
        [ -n "$signal" ] && { printf '%s\n' "$signal"; return 0; }
    done < <(timeout 15 lxc exec "$parent" -- sh -c \
        "iw dev 2>/dev/null | awk '/Interface wifi1[.]1[.]sta/{print \$2}'")
    return 1
}

wait_for_api_signal() {
    local parent=$1 child=$2 target=$3 child_sta=$4 start edge api_rssi api_rcpi physical_rssi expected_rcpi
    start=$(date +%s)
    while :; do
        edge=$(api_edge_json "$parent" "$child" "$target" 2>/dev/null || true)
        if [ -n "$edge" ]; then
            read -r api_rssi api_rcpi < <(jq -r '[.rssi // "", .rcpi // ""] | @tsv' <<< "$edge")
            if [[ "$api_rssi" =~ ^-[0-9]+$ ]] && [[ "$api_rcpi" =~ ^[0-9]+$ ]] &&
                    [ "$api_rcpi" -gt 0 ] && [ "$api_rcpi" -le 220 ]; then
                physical_rssi=$(parent_child_rssi "$parent" "$child_sta" || true)
                [ -n "$physical_rssi" ] || fail "cannot read parent-side RSSI for $parent -> $child"
                expected_rcpi=$((2 * (physical_rssi + 110)))
                [ "$expected_rcpi" -lt 0 ] && expected_rcpi=0
                [ "$expected_rcpi" -gt 220 ] && expected_rcpi=220
                if [ $((api_rssi - physical_rssi)) -lt -4 ] ||
                        [ $((api_rssi - physical_rssi)) -gt 4 ]; then
                    fail "backhaul RSSI mismatch $parent -> $child: iw=$physical_rssi api=$api_rssi"
                fi
                if [ $((api_rcpi - expected_rcpi)) -lt -8 ] ||
                        [ $((api_rcpi - expected_rcpi)) -gt 8 ]; then
                    fail "backhaul RCPI mismatch $parent -> $child: expected=$expected_rcpi api=$api_rcpi"
                fi
                echo "signal_ready parent=$parent child=$child rssi_dbm=$api_rssi rcpi=$api_rcpi"
                return 0
            fi
        fi
        [ $(( $(date +%s) - start )) -lt "$wait_model_seconds" ] \
            || fail "controller did not publish live signal for $parent -> $child"
        sleep 2
    done
}

enable_metrics_reporting() {
    local response
    response=$(curl -fsS -X POST "${topology_url%/topology}/metricsreporting/enable" \
        -H 'Content-Type: application/json' -d '{"interval":5}') \
        || fail "could not enable metrics reporting"
    jq -e '.success == true and .devices >= 1 and .radios >= 1' <<< "$response" >/dev/null \
        || fail "metrics reporting was not accepted: $response"
    echo "metrics_reporting_ready interval_s=5 devices=$(jq -r .devices <<< "$response") radios=$(jq -r .radios <<< "$response")"
}

verify_clients() {
    local client connected=0 reachable=0 failures=0
    local -a clients

    mapfile -t clients < <(lxc list --format csv -c n,s | awk -F, '
        $1 ~ /^wlan-client(-[0-9]+)?$/ && $2 == "RUNNING" {print $1}')
    [ "${#clients[@]}" -ge "$minimum_clients" ] \
        || fail "found ${#clients[@]} running WLAN clients; require at least $minimum_clients"

    for client in "${clients[@]}"; do
        # Consume the complete lxc output.  A short-circuiting grep -q closes
        # the pipe early and can make lxc report a false transport failure.
        if timeout 10 lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/^Connected to /{found=1} END{exit !found}'; then
            connected=$((connected + 1))
        else
            echo "client_not_associated client=$client" >&2
            failures=$((failures + 1))
            continue
        fi
        if timeout 10 lxc exec "$client" -- ping -q -c 2 -W 2 10.0.0.1 >/dev/null; then
            reachable=$((reachable + 1))
        else
            echo "client_forwarding_failed client=$client" >&2
            failures=$((failures + 1))
        fi
    done

    echo "client_acceptance running=${#clients[@]} associated=$connected gateway_reachable=$reachable"
    [ "$failures" -eq 0 ] || fail "client acceptance reported $failures failure(s)"
}

controller_db_counts() {
    timeout 15 lxc exec "$gateway" -- mysql -N -ubpi -proot OneWifiMesh -e '
        select
            (select count(*) from DeviceList),
            (select count(*) from RadioList),
            (select count(*) from BSSList),
            (select count(*) from STAList where Associated=1);' 2>/dev/null
}

verify_controller_db() {
    local expected_devices expected_radios expected_bss minimum_associated
    local start counts="" devices=0 radios=0 bss=0 associated=0
    expected_devices=$((1 + ${#extenders[@]}))
    expected_radios=$((3 * expected_devices))
    expected_bss=$((10 * expected_devices))
    minimum_associated=$((minimum_clients + ${#extenders[@]}))
    start=$(date +%s)

    while :; do
        counts=$(controller_db_counts || true)
        if read -r devices radios bss associated <<< "$counts" &&
                [ "$devices" -eq "$expected_devices" ] &&
                [ "$radios" -eq "$expected_radios" ] &&
                [ "$bss" -eq "$expected_bss" ] &&
                [ "$associated" -ge "$minimum_associated" ]; then
            echo "database_ready devices=$devices radios=$radios bss=$bss associated=$associated"
            return 0
        fi
        [ $(( $(date +%s) - start )) -lt "$wait_model_seconds" ] ||
            fail "controller database did not converge: actual=${devices}/${radios}/${bss}/${associated} expected=${expected_devices}/${expected_radios}/${expected_bss}/>=${minimum_associated}"
        sleep 2
    done
}

verify_profile() {
    local profile=$1 child parent pair target actual child_sta gateway_bssid failures=0
    local -a pairs
    require_lab
    enable_metrics_reporting
    gateway_bssid=$(mesh_ap_bssid "$gateway")
    echo "verify_profile=$profile gateway_bssid=$gateway_bssid"
    mapfile -t pairs < <(profile_pairs "$profile")
    for pair in "${pairs[@]}"; do
        read -r child parent <<< "$pair"
        if [ "$parent" = "$gateway" ]; then
            target=$gateway_bssid
        else
            target=$(mesh_ap_bssid "$parent")
        fi
        actual=$(mesh_sta_bssid "$child" || true)
        child_sta=$(mesh_sta_mac "$child")
        if [ "$actual" != "$target" ]; then
            echo "link_mismatch child=$child parent=$parent expected=$target actual=${actual:-none}" >&2
            failures=$((failures + 1))
            continue
        fi
        if [ "$parent" != "$gateway" ] && [ "$actual" = "$gateway_bssid" ]; then
            echo "direct_gateway_link child=$child bssid=$actual" >&2
            failures=$((failures + 1))
        fi
        # mac80211 can report the child's association before the parent's
        # dynamic AP/VLAN station interface has appeared.  Treat that short
        # propagation interval as convergence, not a failed topology.
        if ! wait_for_parent_station "$parent" "$child_sta"; then
            echo "parent_station_missing parent=$parent child=$child sta=$child_sta" >&2
            failures=$((failures + 1))
        else
            echo "parent_station_ready parent=$parent child=$child sta=$child_sta"
        fi
        if ! timeout 15 lxc exec "$child" -- ping -q -c 3 -W 2 10.0.0.1 >/dev/null; then
            echo "forwarding_failed child=$child parent=$parent" >&2
            failures=$((failures + 1))
        else
            echo "forwarding_ready child=$child parent=$parent"
        fi
        wait_for_api_edge "$parent" "$child" "$target" || failures=$((failures + 1))
        wait_for_api_signal "$parent" "$child" "$target" "$child_sta" || failures=$((failures + 1))
    done

    [ "$failures" -eq 0 ] || fail "$profile verification reported $failures failure(s)"
    verify_clients
    verify_controller_db
    echo "PASS profile=$profile"
}

restore_direct() {
    local child
    require_lab
    echo "restore_profile=direct"
    for child in "${extenders[@]}"; do
        timeout 15 lxc exec "$child" -- systemctl unmask em_agent ieee1905_em_agent \
            >/dev/null 2>&1 || true
        set_parent "$child" "$gateway"
        timeout 15 lxc exec "$child" -- systemctl start ieee1905_em_agent em_agent \
            >/dev/null 2>&1 || true
    done
}

status() {
    local container actual sta ap
    require_lab
    printf '%-12s %-17s %-17s %-17s\n' CONTAINER AL_MAC UPSTREAM_BSSID LOCAL_BH_AP
    for container in "${extenders[@]}"; do
        actual=$(mesh_sta_bssid "$container" || true)
        sta=$(container_al_mac "$container")
        ap=$(mesh_ap_bssid "$container" || true)
        printf '%-12s %-17s %-17s %-17s\n' "$container" "$sta" "${actual:-not-connected}" "${ap:-not-active}"
    done
    echo
    curl -fsS "$topology_url" | jq -r '
        .edges[] | select(.mediaType == "Wireless LAN") |
        [.from, .to, .upstreamBSSID, (.channel|tostring), (.band|tostring)] | @tsv' \
        | awk 'BEGIN {printf "%-17s %-17s %-17s %-7s %s\n", "FROM_AL", "TO_AL", "UPSTREAM_BSSID", "CHANNEL", "BAND"}
               {printf "%-17s %-17s %-17s %-7s %s\n", $1, $2, $3, $4, $5}'
}

unmask_all() {
    local container
    for container in "${extenders[@]}"; do
        container_running "$container" || continue
        timeout 15 lxc exec "$container" -- systemctl unmask em_agent ieee1905_em_agent \
            >/dev/null 2>&1 || true
    done
}

cold_test() {
    local profile=$1 child parent pair
    local -a pairs
    require_lab
    echo "cold_onboarding_profile=$profile"
    trap unmask_all EXIT
    mapfile -t pairs < <(profile_pairs "$profile")

    # Keep the anchor's normal boot path. Mask the EasyMesh protocol services
    # on every other node so onboarding is serialized. OneWifi remains
    # available to establish the requested parent before its agent starts.
    for pair in "${pairs[@]}"; do
        read -r child parent <<< "$pair"
        [ "$child" = "$anchor" ] && continue
        timeout 20 lxc exec "$child" -- systemctl mask --now em_agent ieee1905_em_agent \
            >/dev/null
    done

    # Stop the upstream anchor first. Leaving it alive while its children are
    # being torn down lets the old controller/agent session keep exchanging WSC
    # and topology traffic, which can overlap the next cold transaction. Once
    # the anchor is quiescent, stop the remaining nodes from upstream to
    # downstream and wait for every instance to reach STOPPED before rebuilding
    # the tree.
    for child in "$anchor" bpiap-002 bpiap-001 bpiap; do
        # Give OneWifi/hostapd time to remove their VAPs before LXD returns the
        # physical hwsim wiphy to the host.  A forced stop can leave a second
        # netdev on that phy; the next LXD start then cannot rename its device
        # to wlan0.  Retain force only as the bounded fallback.
        lxc stop "$child" --timeout 20 >/dev/null 2>&1 ||
            lxc stop "$child" --force >/dev/null
    done
    for child in "${extenders[@]}"; do
        for _ in $(seq 1 30); do
            [ "$(lxc info "$child" 2>/dev/null | awk '/^Status:/{print $2; exit}')" = STOPPED ] \
                && break
            sleep 1
        done
        [ "$(lxc info "$child" 2>/dev/null | awk '/^Status:/{print $2; exit}')" = STOPPED ] \
            || fail "$child did not stop cleanly before cold onboarding"
    done

    lxc start "$anchor"
    for _ in $(seq 1 120); do
        timeout 10 lxc exec "$anchor" -- systemctl is-active --quiet onewifi 2>/dev/null \
            && break
        sleep 1
    done
    set_parent "$anchor" "$gateway"
    force_mesh_ap "$anchor" >/dev/null
    wait_for_onboarding "$anchor"

    for pair in "${pairs[@]}"; do
        read -r child parent <<< "$pair"
        [ "$child" = "$anchor" ] && continue
        lxc start "$child"
        for _ in $(seq 1 120); do
            timeout 10 lxc exec "$child" -- systemctl is-active --quiet onewifi 2>/dev/null \
                && break
            sleep 1
        done
        set_parent "$child" "$parent"
        timeout 20 lxc exec "$child" -- systemctl unmask em_agent ieee1905_em_agent >/dev/null
        timeout 20 lxc exec "$child" -- systemctl start --no-block \
            ieee1905_em_agent em_agent >/dev/null
        for _ in $(seq 1 90); do
            if timeout 10 lxc exec "$child" -- systemctl is-active --quiet \
                    ieee1905_em_agent 2>/dev/null &&
                    timeout 10 lxc exec "$child" -- systemctl is-active --quiet \
                    em_agent 2>/dev/null; then
                break
            fi
            sleep 1
        done
        timeout 10 lxc exec "$child" -- systemctl is-active --quiet \
            ieee1905_em_agent 2>/dev/null &&
            timeout 10 lxc exec "$child" -- systemctl is-active --quiet \
            em_agent 2>/dev/null || fail "$child EasyMesh services did not become active"
        force_mesh_ap "$child" >/dev/null
        wait_for_onboarding "$child"
    done

    verify_profile "$profile"
    trap - EXIT
    unmask_all
}

main() {
    local action=${1:-} profile=${2:-}
    case "$action" in
        apply)
            [ -n "$profile" ] || { usage; exit 2; }
            apply_profile "$profile"
            status
            ;;
        verify)
            [ -n "$profile" ] || { usage; exit 2; }
            verify_profile "$profile"
            ;;
        test)
            [ -n "$profile" ] || { usage; exit 2; }
            mkdir -p "$result_root"
            apply_profile "$profile"
            verify_profile "$profile" 2>&1 | tee "$result_root/${profile}-$(date -u +%Y%m%dT%H%M%SZ).log"
            ;;
        cold-test)
            [ -n "$profile" ] || { usage; exit 2; }
            mkdir -p "$result_root"
            cold_test "$profile" 2>&1 | tee "$result_root/${profile}-cold-$(date -u +%Y%m%dT%H%M%SZ).log"
            ;;
        restore) restore_direct; status ;;
        status) status ;;
        -h|--help|help|'') usage ;;
        *) usage; exit 2 ;;
    esac
}

main "$@"
