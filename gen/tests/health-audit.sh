#!/usr/bin/env bash
set -euo pipefail

exec </dev/null
repo=${EASYMESH_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
# shellcheck source=lib/observer-status.sh
source "$repo/gen/tests/lib/observer-status.sh"
results=${RESULTS_FILE:-$repo/tmp/test-results/steering-scale.csv}
ping_count=${HEALTH_PING_COUNT:-10}
ping_interval=${HEALTH_PING_INTERVAL:-1}
ping_max_loss=${HEALTH_PING_MAX_LOSS:-0}
ping_exec_attempts=${HEALTH_PING_EXEC_ATTEMPTS:-2}
ping_exec_timeout=${HEALTH_PING_EXEC_TIMEOUT:-20}
# A lab just built, started or restored can still be reconfiguring its radios: a round that
# loses packets is reported and the lab measured again after a pause; only the last round
# decides, at the same loss bar (rdk-1001, 1 Oct: one client lost 4 of 10 pings in its
# build's round, then every later check passed).
ping_rounds=${HEALTH_PING_ROUNDS:-2}
ping_settle=${HEALTH_PING_SETTLE_SECONDS:-30}
# A failed traffic check keeps the medium's state beside it: once the medium restarts (a
# redeploy, a reproduction) the run's record is gone (image 18's first audit on rdk-1004,
# 8 October, could not be explained afterwards). The last five are kept.
medium_runtime=${HEALTH_MEDIUM_RUNTIME:-/run/meta-cmf-wmediumd}
medium_telemetry=${HEALTH_MEDIUM_TELEMETRY_URL:-http://127.0.0.1:8890/api/v1/telemetry}
medium_evidence_root=${HEALTH_MEDIUM_EVIDENCE_DIR:-$repo/tmp/test-results/medium-evidence}
audit_start=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)    # the medium's refusals counted from here (traffic_rounds)
medium_evidence() {    # the medium's telemetry, configuration and logs (each bounded by -L) now
    local dir file old saved=
    dir=$medium_evidence_root/$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -p "$dir" || return 0
    if curl -fsS --max-time 10 "$medium_telemetry" > "$dir/telemetry.json" 2>/dev/null; then
        saved="telemetry.json"
    else
        rm -f "$dir/telemetry.json"
    fi
    for file in wmediumd.cfg wmediumd.log wmediumd.log.1 wmediumd.log.prev wmediumd.log.prev.1; do
        [ -r "$medium_runtime/$file" ] && cp "$medium_runtime/$file" "$dir/" 2>/dev/null &&
            saved="$saved $file"
    done
    while IFS= read -r old; do rm -rf -- "$old"; done < <(
        find "$medium_evidence_root" -mindepth 1 -maxdepth 1 -type d -name '20*Z' | sort | head -n -5)
    echo "MEDIUM_EVIDENCE $dir (${saved# })"
}
# The lab's extenders on a wired backhaul (gen/wired-extender.sh): one more device each,
# with three radios and ten BSSes, but no backhaul station association and no Wi-Fi edge.
wired=$(for c in $(lxc list -c n --format csv | grep -E '^bpiap-[0-9]{3}$' | sort -V); do
    [ "$(lxc config get "$c" user.easymesh.backhaul)" = wired ] && echo "$c"; done || true)
wired_count=$(printf '%s\n' $wired | sed '/^$/d' | wc -l)
mesh_containers="bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003 $wired"
expected_devices=${HEALTH_EXPECT_DEVICES:-$((5 + wired_count))}
expected_radios=${HEALTH_EXPECT_RADIOS:-$((3 * expected_devices))}
expected_bsses=${HEALTH_EXPECT_BSSES:-$((10 * expected_devices))}
expected_clients=${HEALTH_EXPECT_CLIENTS:-20}
expected_associated=$((expected_clients + expected_devices - 1 - wired_count))

[[ "$ping_count" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_COUNT must be a positive integer" >&2; exit 2; }
[[ "$ping_interval" =~ ^[0-9]+([.][0-9]+)?$ ]] \
    || { echo "HEALTH_PING_INTERVAL must be a non-negative number" >&2; exit 2; }
[[ "$ping_max_loss" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
    || { echo "HEALTH_PING_MAX_LOSS must be an integer from 0 through 100" >&2; exit 2; }
[[ "$ping_exec_attempts" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_EXEC_ATTEMPTS must be a positive integer" >&2; exit 2; }
[[ "$ping_exec_timeout" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_EXEC_TIMEOUT must be a positive integer" >&2; exit 2; }
[[ "$ping_rounds" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_ROUNDS must be a positive integer" >&2; exit 2; }
[[ "$ping_settle" =~ ^[0-9]+$ ]] \
    || { echo "HEALTH_PING_SETTLE_SECONDS must be a non-negative integer" >&2; exit 2; }

status_section "Topology and controller model"
status_action "Reading the live WebUI topology."
echo TOPOLOGY
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq -r '
    .nodes[] | [.name, .id, ([.haulTypes[]?.BSSList[]?] | length),
    (.STAList | length)] | @tsv'
# The lab's own mesh is counted, as its runtime counts it (easymesh-lab-runtime): OpenSync pods
# through EMOSA ('OpenSync via EMOSA') are not among the expected devices, nor their radios,
# BSSes and backhaul stations; the clients on the lab's pods are its clients. Devices the room
# does not own (/etc/easymesh-lab/foreign-devices, physical pods on the controller) and the
# stations on their BSSes are left out.
emosa="'OpenSync via EMOSA'"
al="substring_index(substring_index(ID,'@',2),'@',-1)"
pod_al="select $al from DeviceList where Manufacturer = $emosa"
foreign=$(sed 's/#.*//' /etc/easymesh-lab/foreign-devices 2>/dev/null | tr -d ' \t' | tr '[:upper:]' '[:lower:]' \
    | grep -E '^[0-9a-f]{2}(:[0-9a-f]{2}){5}$' || true)
# shellcheck disable=SC2086 # one MAC per word
foreign_sql=$(printf "'%s'," $foreign | sed 's/,$//')
foreign_stations=''
[ -z "$foreign" ] || foreign_stations=" and coalesce(s.BSSID,'') not in (select BSSID from BSSList where $al in ($foreign_sql) and BSSID is not null)"
echo MODEL
model=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
    "select (select count(*) from DeviceList where Manufacturer <> $emosa),
    (select count(*) from RadioList where $al not in ($pod_al)),
    (select count(*) from BSSList where $al not in ($pod_al)),
    (select count(*) from STAList s where s.Associated = 1 and not (s.BSSID in
        (select BSSID from BSSList where SSID = 'mesh_backhaul') and s.MACAddress not in
        (select BackhaulSTA from DeviceList where Manufacturer <> $emosa))$foreign_stations)" 2>/dev/null)
echo "$model"
read -r devices radios bsses associated <<<"$model"
model_fail=0
if [ "$devices/$radios/$bsses/$associated" != \
    "$expected_devices/$expected_radios/$expected_bsses/$expected_associated" ]; then
    model_fail=1
fi
echo LIVE_CLIENTS
topology_json=$(mktemp)
curl -fsS http://127.0.0.1:8888/api/v1/topology >"$topology_json"
# shellcheck disable=SC2086 # one MAC per word
foreign_json=$(printf '%s\n' $foreign | jq -R . | jq -sc 'map(select(length > 0))')
live_clients=$(jq -r --argjson foreign "$foreign_json" '[.nodes[] | select((.id | ascii_downcase) as $id
    | $foreign | index($id) | not) | .STAList[]?.staMAC] | unique | length' "$topology_json")
echo "$live_clients"
[ "$live_clients" = "$expected_clients" ] || model_fail=1

# the lab's own Wi-Fi backhauls: not a pod's (EMOSA's) nor a foreign device's
echo BACKHAUL_SIGNALS
read -r wireless_edges fresh_edges < <(jq -r '
    [.nodes[] | select(.kind == "opensync-pod") | .id] as $pods |
    [.edges[]? | select(.mediaType == "Wireless LAN" and (.to as $to | $pods | index($to) | not))] as $edges |
    [$edges | length,
     [$edges[] | select(.signal.status == "fresh")] | length] | @tsv
' "$topology_json")
echo "fresh=$fresh_edges/$wireless_edges"
[ "$wireless_edges" = "$((expected_devices - 1 - wired_count))" ] || model_fail=1
[ "$fresh_edges" = "$wireless_edges" ] || model_fail=1

echo WIRED_BACKHAUL
# each wired extender an Ethernet child of the controller, and never a Wi-Fi child
for container in $wired; do
    # the AL MAC is eth1_virt_peer's address, as for every bpiap extender
    al=$(lxc exec "$container" -- cat /sys/class/net/eth1_virt_peer/address 2>/dev/null |
        tr '[:upper:]' '[:lower:]')
    media=$(jq -r --arg al "$al" '[.edges[]? | select((.to | ascii_downcase) == $al) | .mediaType] | join(",")' \
        "$topology_json")
    bridged=$(lxc exec "$container" -- sh -c 'basename "$(readlink /sys/class/net/eth1/master)"' 2>/dev/null || true)
    stations=$(lxc exec "$container" -- sh -c 'for n in /sys/class/net/*; do [ -e "$n/phy80211" ] || continue
        iw dev "${n##*/}" info 2>/dev/null | grep -q "type managed" || continue
        [ "$(cat "$n/operstate")" = down ] || echo "${n##*/}"; done' 2>/dev/null || true)
    if [ "$media" = Ethernet ] && [ "$bridged" = brlan0 ] && [ -z "$stations" ]; then
        echo "$container al=$al edge=$media eth1=$bridged OK"
    else
        echo "$container al=${al:-?} edge=${media:-none} eth1=${bridged:-none} stations_up=${stations:-none} FAIL"
        model_fail=1
    fi
done

status_section "Identity persistence"
status_action "Checking every mesh node's preserved NVRAM binding."
echo NVRAM_BINDINGS
nvram_fail=0
for container in $mesh_containers; do
    nvram_source=$(lxc config show "$container" --expanded 2>/dev/null |
        awk '
            /^  nvram:$/ {in_nvram=1; next}
            in_nvram && /^    source:/ {sub(/^    source: /, ""); print; exit}
            in_nvram && /^  [^ ]/ {in_nvram=0}
        ')
    if [ -z "$nvram_source" ] || [ ! -d "$nvram_source" ] \
        || ! find "$nvram_source" -mindepth 1 -maxdepth 2 -type f \
            -print -quit 2>/dev/null | grep -q .; then
        echo "$container source=${nvram_source:-missing} FAIL"
        nvram_fail=1
    else
        echo "$container source=$nvram_source OK"
    fi
done

status_section "Client ownership"
status_action "Comparing each physical association with controller/WebUI ownership."
echo ASSOCIATION_OWNERSHIP
clients_json=$(mktemp)
trap 'rm -f "$clients_json" "$topology_json"' EXIT
curl -fsS http://127.0.0.1:8888/api/v1/clients >"$clients_json"
ownership_fail=0
while read -r client; do
    mac=$(lxc exec "$client" -- cat /sys/class/net/wlan0/address </dev/null 2>/dev/null |
        tr '[:upper:]' '[:lower:]')
    physical=$(lxc exec "$client" -- iw dev wlan0 link </dev/null 2>/dev/null |
        awk '/^Connected to / && !found {bssid=tolower($3); found=1}
             END {if (found) print bssid}')
    api=$(jq -r --arg mac "$mac" '(.clients // .)[]? |
        select((.mac | ascii_downcase) == $mac) | .connected_bssid' \
        "$clients_json" | head -1 | tr '[:upper:]' '[:lower:]')
    if [ -n "$physical" ] && [ "$physical" = "$api" ]; then
        echo "$client $mac $physical OK"
    else
        echo "$client $mac physical=${physical:-missing} api=${api:-missing} MISMATCH"
        ownership_fail=1
    fi
done < <(lxc list -c n --format csv |
    grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)

status_action "Checking that every WLAN client owns one unique IPv4 address."
echo IPV4_OWNERSHIP
ipv4_fail=0
declare -A ipv4_owner=()
while read -r client; do
    addresses=$(lxc exec "$client" -- ip -4 -o address show \
        dev wlan0 scope global </dev/null 2>/dev/null | awk '{print $4}')
    address_count=$(wc -w <<< "$addresses")
    if [ "$address_count" -ne 1 ]; then
        echo "$client count=$address_count addresses=${addresses:-none} FAIL"
        ipv4_fail=1
        continue
    fi
    address=${addresses%/*}
    if [ -n "${ipv4_owner[$address]+present}" ]; then
        echo "$client address=$address duplicates=${ipv4_owner[$address]} FAIL"
        ipv4_fail=1
    else
        ipv4_owner[$address]=$client
        echo "$client address=$address OK"
    fi
done < <(lxc list -c n --format csv |
    grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)

status_section "Service stability"
status_action "Checking EasyMesh and OneWifi restart counters."
echo RESTARTS
restart_fail=0
for container in $mesh_containers; do
    for unit in onewifi em_agent; do
        restarts=$(lxc exec "$container" -- systemctl show "$unit" \
            -p NRestarts --value)
        echo "$container $unit=$restarts"
        [ "$restarts" = 0 ] || restart_fail=1
    done
done
for unit in em_ctrl em_cli; do
    restarts=$(lxc exec bpibroadband -- systemctl show "$unit" \
        -p NRestarts --value)
    echo "bpibroadband $unit=$restarts"
    [ "$restarts" = 0 ] || restart_fail=1
done

status_section "End-to-end traffic"
status_wait "Sending $ping_count packets from every client in parallel; maximum allowed loss is ${ping_max_loss}%."
echo CONNECTIVITY
traffic_fail=0
[[ "$expected_clients" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_EXPECT_CLIENTS must be a positive integer" >&2; exit 2; }
if ! traffic_inventory=$(lxc list -c n --format csv </dev/null); then
    echo "FAIL: unable to enumerate clients for traffic audit" >&2
    exit 1
fi
mapfile -t traffic_clients < <(printf '%s\n' "$traffic_inventory" \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
if [ "${#traffic_clients[@]}" -ne "$expected_clients" ]; then
    echo "FAIL: traffic roster has ${#traffic_clients[@]} clients; expected $expected_clients" >&2
    exit 1
fi
for ((client_index = 0; client_index < expected_clients; client_index++)); do
    expected_client=wlan-client
    if [ "$client_index" -gt 0 ]; then
        printf -v expected_client 'wlan-client-%03d' "$client_index"
    fi
    if [ "${traffic_clients[$client_index]}" != "$expected_client" ]; then
        echo "FAIL: traffic roster expected $expected_client; found ${traffic_clients[$client_index]}" >&2
        exit 1
    fi
done
# Each round's times, the medium's netlink refusals before and during it (its timed log,
# easymesh-medium 0038) and every client's link as it starts: a first round lossy right after a
# bring-up (rdk-1004, 9 October 13:18Z: 44 of 100 clients, none 30 s later, the loss behind every
# agent) is told apart by them from a fault, convergence (clients just (re)associated, radios
# scanning: cmd 2) from loss on settled links.
stamp() { date -u +%Y-%m-%dT%H:%M:%S.%6NZ; }
medium_counts() {    # medium_counts FROM TO: the medium's cmd 2 and cmd 3 refusals between two stamps
    { cat "${medium_runtime:-/run/meta-cmf-wmediumd}/wmediumd.log.1" \
        "${medium_runtime:-/run/meta-cmf-wmediumd}/wmediumd.log" 2>/dev/null || true; } |
        awk -v from="$1" -v to="$2" '$1 >= from && $1 <= to {
            if ($0 ~ /cmd 2,/) c2++; else if ($0 ~ /cmd 3,/) c3++ }
            END { printf "cmd2=%d cmd3=%d", c2, c3 }'
}
traffic_round() {    # traffic_round ROUND: one parallel round; fails if any client exceeds the loss bar
    local client pid fail=0 completed=0
    local -a pids=()
    for client in "${traffic_clients[@]}"; do
        (
            # its AP and how long it has been associated to it, as the round starts
            link=$(timeout "$ping_exec_timeout" lxc exec "$client" -- iw dev wlan0 station dump \
                </dev/null 2>/dev/null | awk '/^Station/ {b = $2} /connected time/ {c = $3}
                END {printf "bssid=%s connected=%s", b ? b : "none", c != "" ? c "s" : "-"}') || true
            ping_output=
            for ((attempt = 1; attempt <= ping_exec_attempts; attempt++)); do
                if ping_output=$(timeout "$ping_exec_timeout" \
                    lxc exec "$client" -- ping -q -c "$ping_count" \
                    -i "$ping_interval" -W 2 10.0.0.1 </dev/null 2>/dev/null); then
                    break
                fi
                ping_output=
            done
            loss=$(sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p' <<<"$ping_output")
            echo "$client ${loss:-FAIL}"
            echo "LINK round=$1 $client $link"
            loss_value=${loss%%%}
            [[ "$loss_value" =~ ^[0-9]+$ ]] \
                && [ "$loss_value" -le "$ping_max_loss" ]
        ) &
        pids+=("$!")
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || fail=1
        completed=$((completed + 1))
    done
    printf 'TRAFFIC_COVERAGE expected=%s scheduled=%s completed=%s\n' \
        "$expected_clients" "${#pids[@]}" "$completed"
    [ "${#pids[@]}" -eq "$expected_clients" ] && [ "$completed" -eq "$expected_clients" ] || fail=1
    return "$fail"
}
traffic_rounds() {    # up to ping_rounds rounds, a pause after each lossy one; the last decides
    local round start end mark rc
    mark=${audit_start:-$(stamp)}
    for ((round = 1; round <= ping_rounds; round++)); do
        [ "$round" = 1 ] || echo "ROUND $round"
        start=$(stamp)
        rc=0
        traffic_round "$round" || rc=1
        end=$(stamp)
        echo "ROUND_TIME round=$round start=$start end=$end" \
            "medium_before $(medium_counts "$mark" "$start") medium_during $(medium_counts "$start" "$end")"
        mark=$end
        [ "$rc" = 1 ] || return 0
        [ "$round" -lt "$ping_rounds" ] || return 1
        echo "SETTLE: packets lost in round $round; measuring again in ${ping_settle}s"
        sleep "$ping_settle"
    done
}
traffic_fail=0
traffic_rounds || traffic_fail=1

if [ -s "$results" ]; then
    echo MATRIX
    awk -F, 'NR > 1 {
        gsub(/%/, "", $11)
        n++; pass += ($12 == "PASS")
        sl += $8; sd += $9; sa += $10; loss += $11
        if (($8 + 0) > ml) ml = $8 + 0
        if (($9 + 0) > md) md = $9 + 0
        if (($10 + 0) > ma) ma = $10 + 0
        if (($11 + 0) > mx) mx = $11 + 0
    } END {
        if (!n) { print "no steering samples"; exit }
        printf "pass=%d/%d link_avg=%.0fms link_max=%dms db_avg=%.0fms db_max=%dms api_avg=%.0fms api_max=%dms loss_avg=%.1f%% loss_max=%d%%\n", pass, n, sl/n, ml, sd/n, md, sa/n, ma, loss/n, mx
    }' "$results"
fi

[ "$traffic_fail" = 0 ] || medium_evidence

echo MEMORY
free -h | sed -n '1,2p'

[ "$restart_fail" = 0 ] || {
    echo "FAIL: one or more monitored services restarted" >&2
    exit 1
}
[ "$model_fail" = 0 ] || {
    echo "FAIL: topology model is not the expected $expected_devices/$expected_radios/$expected_bsses/$expected_associated with $expected_clients clients" >&2
    exit 1
}
[ "$ownership_fail" = 0 ] || {
    echo "FAIL: physical and controller serving-BSSID ownership differ" >&2
    exit 1
}
[ "$ipv4_fail" = 0 ] || {
    echo "FAIL: each WLAN client must own exactly one unique IPv4 address" >&2
    exit 1
}
[ "$traffic_fail" = 0 ] || {
    echo "FAIL: one or more WLAN clients exceeded ${ping_max_loss}% packet loss" >&2
    exit 1
}
[ "$nvram_fail" = 0 ] || {
    echo "FAIL: one or more BPI NVRAM bind sources are missing or empty" >&2
    exit 1
}
status_pass "Health audit passed: model, identities, ownership, services and traffic are coherent."
