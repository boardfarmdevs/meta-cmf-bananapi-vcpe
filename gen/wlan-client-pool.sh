#!/usr/bin/env bash
# Provision deterministic private and IoT WLAN client cohorts.
#
# The small profile is the current acceptance target: ten private clients plus
# ten WPA3-SAE IoT clients. Medium/stress are named now so scenarios and CI do
# not hardcode 20, but require separate capacity acceptance before use.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ACTION=${1:-plan}
[ $# -eq 0 ] || shift

PROFILE=small
PRIVATE_COUNT=
IOT_COUNT=
PRIVATE_SSID=${PRIVATE_SSID:-private_ssid}
PRIVATE_PSK=${PRIVATE_PSK:-test-fronthaul}
IOT_SSID=${IOT_SSID:-iot_ssid}
IOT_PSK=${IOT_PSK:-test-backhaul}

usage() {
    cat <<'EOF'
Usage: wlan-client-pool.sh {plan|up|down|status} [options]

  --profile small|medium|stress  20, 50 or 100 total clients (default: small)
  --private COUNT                override the private cohort size
  --iot COUNT                    override the IoT cohort size

Examples:
  ./wlan-client-pool.sh plan --profile small
  ./wlan-client-pool.sh up --private 10 --iot 10
  ./wlan-client-pool.sh status

Small is the current acceptance target. Medium and stress deliberately use the
same naming/cohort model, but must pass their own hwsim, wmediumd, memory and
controller scale gates before they are declared supported. The 100-client
stress profile also needs a validated way around mac80211_hwsim's stock static
100-radio limit because five additional radios are used by the mesh nodes.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --profile) PROFILE=$2; shift 2 ;;
        --private) PRIVATE_COUNT=$2; shift 2 ;;
        --iot) IOT_COUNT=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$PROFILE" in
    small)  default_private=10; default_iot=10 ;;
    medium) default_private=25; default_iot=25 ;;
    stress) default_private=50; default_iot=50 ;;
    *) echo "unknown profile: $PROFILE" >&2; exit 2 ;;
esac
PRIVATE_COUNT=${PRIVATE_COUNT:-$default_private}
IOT_COUNT=${IOT_COUNT:-$default_iot}
for value in "$PRIVATE_COUNT" "$IOT_COUNT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "client counts must be non-negative integers" >&2; exit 2; }
done
TOTAL=$((PRIVATE_COUNT + IOT_COUNT))
[ "$TOTAL" -gt 0 ] || { echo "at least one client is required" >&2; exit 2; }
[ "$TOTAL" -le 100 ] || { echo "this naming scheme is bounded to 100 clients" >&2; exit 2; }

container_name() {
    local index=$1
    if [ "$index" -eq 0 ]; then
        printf '%s\n' wlan-client
    else
        printf 'wlan-client-%03d\n' "$index"
    fi
}

next_power_of_two() {
    local value=$1 result=1
    while [ "$result" -lt "$value" ]; do result=$((result * 2)); done
    [ "$result" -ge 32 ] || result=32
    printf '%s\n' "$result"
}

required_radios=$((TOTAL + 5))

radio_plan() {
    if [ "$required_radios" -gt 100 ]; then
        printf 'dynamic-required'
    else
        next_power_of_two "$((required_radios + 4))"
    fi
}

print_plan() {
    local index name cohort ordinal
    printf 'PROFILE\t%s\n' "$PROFILE"
    printf 'CLIENTS\tprivate=%d\tiot=%d\ttotal=%d\n' \
        "$PRIVATE_COUNT" "$IOT_COUNT" "$TOTAL"
    printf 'HWSIM\trequired=%d\tpool=%s\n' \
        "$required_radios" "$(radio_plan)"
    printf 'INDEX\tCONTAINER\tCOHORT\tORDINAL\tSSID\tSECURITY\n'
    for index in $(seq 0 $((TOTAL - 1))); do
        name=$(container_name "$index")
        if [ "$index" -lt "$PRIVATE_COUNT" ]; then
            cohort=private; ordinal=$((index + 1))
            printf '%d\t%s\t%s\t%d\t%s\t%s\n' \
                "$index" "$name" "$cohort" "$ordinal" "$PRIVATE_SSID" wpa2
        else
            cohort=iot; ordinal=$((index - PRIVATE_COUNT + 1))
            printf '%d\t%s\t%s\t%d\t%s\t%s\n' \
                "$index" "$name" "$cohort" "$ordinal" "$IOT_SSID" sae
        fi
    done
}

case "$ACTION" in
plan)
    print_plan
    ;;
up)
    loaded=$(cat /sys/module/mac80211_hwsim/parameters/radios 2>/dev/null || true)
    if [ "$required_radios" -gt 100 ]; then
        echo "$TOTAL clients need $required_radios radios including the mesh nodes" >&2
        echo "the stock static hwsim pool is limited to 100; this profile is planned, not runnable" >&2
        exit 1
    fi
    if ! [[ "$loaded" =~ ^[0-9]+$ ]] || [ "$loaded" -lt "$required_radios" ]; then
        echo "hwsim pool has ${loaded:-0} radios; $required_radios are required for five mesh nodes and $TOTAL clients" >&2
        echo "reload the idle lab with HWSIM_RADIOS=$(radio_plan) before provisioning" >&2
        exit 1
    fi
    # wmediumd registers a fixed radio matrix. Refreshing that matrix after
    # every new client is correct for the one-client helper but quadratic work
    # for a pool. Let mac80211_hwsim's built-in medium carry the bounded
    # association/export gates, then register the complete matrix once. The
    # EXIT trap restores wmediumd even if provisioning stops part way through.
    medium_helper="$HERE/wmediumd/wmediumd-up.sh"
    medium_pending=0
    restore_medium() {
        if [ "$medium_pending" = 1 ]; then
            medium_pending=0
            SNR="${SNR:-40}" "$medium_helper" up
        fi
    }
    if [ -x "$medium_helper" ]; then
        "$medium_helper" down
        medium_pending=1
        trap restore_medium EXIT INT TERM
    fi
    for index in $(seq 0 $((TOTAL - 1))); do
        args=()
        [ "$index" -eq 0 ] || args=(-i "$index")
        if [ "$index" -lt "$PRIVATE_COUNT" ]; then
            "$HERE/wlan-client.sh" "${args[@]}" --cohort private --security wpa2 \
                up "$PRIVATE_SSID" "$PRIVATE_PSK"
            ordinal=$((index + 1))
        else
            "$HERE/wlan-client.sh" "${args[@]}" --cohort iot --security sae \
                up "$IOT_SSID" "$IOT_PSK"
            ordinal=$((index - PRIVATE_COUNT + 1))
        fi
        name=$(container_name "$index")
        lxc config set "$name" user.easymesh.ordinal "$ordinal"
        lxc config set "$name" boot.autostart false
    done
    restore_medium
    trap - EXIT INT TERM
    expected_associated=$((TOTAL + 4))
    for attempt in $(seq 1 60); do
        topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology 2>/dev/null || true)
        private_live=$(jq -r --arg ssid "$PRIVATE_SSID" \
            '[.nodes[].STAList[]? | select(.ssid == $ssid) | .staMAC] | unique | length' \
            <<<"$topology" 2>/dev/null || true)
        iot_live=$(jq -r --arg ssid "$IOT_SSID" \
            '[.nodes[].STAList[]? | select(.ssid == $ssid) | .staMAC] | unique | length' \
            <<<"$topology" 2>/dev/null || true)
        associated=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh \
            -e 'select count(*) from STAList where Associated=1' 2>/dev/null || true)
        echo "client cohort gate $attempt/60: private=${private_live:-?}/$PRIVATE_COUNT iot=${iot_live:-?}/$IOT_COUNT associated=${associated:-?}/$expected_associated"
        if [ "$private_live" = "$PRIVATE_COUNT" ] \
            && [ "$iot_live" = "$IOT_COUNT" ] \
            && [ "$associated" = "$expected_associated" ]; then
            exit 0
        fi
        sleep 5
    done
    echo "mixed client cohorts did not converge" >&2
    exit 1
    ;;
down)
    for index in $(seq $((TOTAL - 1)) -1 0); do
        if [ "$index" -eq 0 ]; then
            "$HERE/wlan-client.sh" down
        else
            "$HERE/wlan-client.sh" -i "$index" down
        fi
    done
    ;;
status)
    printf 'CONTAINER\tSTATE\tCOHORT\tORDINAL\tSSID\tSECURITY\n'
    while read -r name; do
        [ -n "$name" ] || continue
        state=$(lxc info "$name" 2>/dev/null | sed -n 's/^Status: //p')
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$name" "${state:-UNKNOWN}" \
            "$(lxc config get "$name" user.easymesh.cohort 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.ordinal 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.ssid 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.security 2>/dev/null)"
    done < <(lxc list -c n --format csv | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
    ;;
*)
    usage >&2
    exit 2
    ;;
esac
