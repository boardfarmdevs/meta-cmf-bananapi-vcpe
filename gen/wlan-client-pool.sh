#!/usr/bin/env bash
# Provision deterministic private and IoT WLAN client cohorts.
#
# The small profile is the current acceptance target: ten private clients plus
# ten IoT clients. Medium/stress are named now so scenarios and CI do not
# hardcode 20, but require separate capacity acceptance before use.
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
    local index name cohort ordinal band security
    printf 'PROFILE\t%s\n' "$PROFILE"
    printf 'CLIENTS\tprivate=%d\tiot=%d\ttotal=%d\n' \
        "$PRIVATE_COUNT" "$IOT_COUNT" "$TOTAL"
    printf 'HWSIM\trequired=%d\tpool=%s\n' \
        "$required_radios" "$(radio_plan)"
    printf 'INDEX\tCONTAINER\tCOHORT\tORDINAL\tSSID\tSECURITY\tBAND\n'
    for index in $(seq 0 $((TOTAL - 1))); do
        name=$(container_name "$index")
        if [ "$index" -lt "$PRIVATE_COUNT" ]; then
            cohort=private; ordinal=$((index + 1))
            band=auto; security=wpa2
            [ "$ordinal" -ne "$((PRIVATE_COUNT - 1))" ] || band=2.4
            if [ "$ordinal" -eq "$PRIVATE_COUNT" ]; then
                band=6; security=sae
            fi
            printf '%d\t%s\t%s\t%d\t%s\t%s\t%s\n' \
                "$index" "$name" "$cohort" "$ordinal" "$PRIVATE_SSID" "$security" "$band"
        else
            cohort=iot; ordinal=$((index - PRIVATE_COUNT + 1))
            printf '%d\t%s\t%s\t%d\t%s\t%s\t%s\n' \
                "$index" "$name" "$cohort" "$ordinal" "$IOT_SSID" wpa2 auto
        fi
    done
}

client_ready() {
    local name=$1 cohort=$2 ordinal=$3 ssid=$4 security=$5 band=$6 configured_band freq
    [ "$(lxc info "$name" 2>/dev/null | sed -n 's/^Status: //p')" = RUNNING ] || return 1
    [ "$(lxc config get "$name" user.easymesh.cohort 2>/dev/null)" = "$cohort" ] || return 1
    [ "$(lxc config get "$name" user.easymesh.ordinal 2>/dev/null)" = "$ordinal" ] || return 1
    [ "$(lxc config get "$name" user.easymesh.ssid 2>/dev/null)" = "$ssid" ] || return 1
    [ "$(lxc config get "$name" user.easymesh.security 2>/dev/null)" = "$security" ] || return 1
    configured_band=$(lxc config get "$name" user.easymesh.band 2>/dev/null)
    [ "$configured_band" = "$band" ] \
        || { [ "$band" = auto ] && [ -z "$configured_band" ]; } \
        || return 1
    lxc exec "$name" -- iw dev wlan0 link 2>/dev/null | grep -Fq "SSID: $ssid" || return 1
    freq=$(lxc exec "$name" -- iw dev wlan0 link 2>/dev/null | awk '/freq:/ {print $2; exit}')
    freq=${freq%%.*}
    case "$band" in
        auto) ;;
        2.4) [ "$freq" -ge 2400 ] 2>/dev/null && [ "$freq" -lt 2500 ] || return 1 ;;
        5)   [ "$freq" -ge 5000 ] 2>/dev/null && [ "$freq" -lt 5955 ] || return 1 ;;
        6)   [ "$freq" -ge 5955 ] 2>/dev/null && [ "$freq" -le 7115 ] || return 1 ;;
        *) return 1 ;;
    esac
    lxc exec "$name" -- ip -4 -o addr show wlan0 2>/dev/null | grep -q 'inet '
}

enable_metrics_reporting() {
    local interval=${METRICS_REPORTING_INTERVAL:-5}
    local response topology wireless fresh attempt
    [[ "$interval" =~ ^[1-9][0-9]*$ ]] \
        || { echo "METRICS_REPORTING_INTERVAL must be positive" >&2; return 1; }

    response=$(curl -fsS --max-time 60 -X POST \
        http://127.0.0.1:8888/api/v1/metricsreporting/enable \
        -H 'Content-Type: application/json' \
        -d "{\"interval\":$interval}")
    jq -e '.success == true and .devices >= 1 and .radios >= 1' \
        <<<"$response" >/dev/null
    echo "metrics reporting enabled: interval=${interval}s devices=$(jq -r .devices <<<"$response") radios=$(jq -r .radios <<<"$response")"

    for attempt in $(seq 1 12); do
        topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology 2>/dev/null || true)
        read -r wireless fresh < <(jq -r '
            [.edges[]? | select(.mediaType == "Wireless LAN")] as $edges |
            [$edges | length,
             [$edges[] | select(.signal.status == "fresh")] | length] | @tsv
        ' <<<"$topology" 2>/dev/null || printf '0\t0\n')
        echo "backhaul signal gate $attempt/12: fresh=${fresh:-0}/${wireless:-0}"
        if [[ "$wireless" =~ ^[1-9][0-9]*$ ]] && [ "$fresh" = "$wireless" ]; then
            return 0
        fi
        sleep 5
    done
    echo "wireless backhaul signals did not become fresh" >&2
    return 1
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
    needs_provisioning=0
    probe_parallelism=${CLIENT_PROBE_PARALLELISM:-8}
    [[ "$probe_parallelism" =~ ^[1-9][0-9]*$ ]] \
        || { echo "CLIENT_PROBE_PARALLELISM must be positive" >&2; exit 2; }
    declare -a healthy=() probe_pids=() probe_indices=()
    collect_probes() {
        local position index
        for position in "${!probe_pids[@]}"; do
            index=${probe_indices[$position]}
            if wait "${probe_pids[$position]}"; then
                healthy[$index]=1
            else
                healthy[$index]=0
                needs_provisioning=1
            fi
        done
        probe_pids=()
        probe_indices=()
    }
    # Read-only LXD probes dominate resume time. Run a bounded batch while
    # retaining deterministic result indexes; eight is also the accepted
    # inventory fan-out and avoids flooding LXD at 50/100-client scale.
    for index in $(seq 0 $((TOTAL - 1))); do
        name=$(container_name "$index")
        if [ "$index" -lt "$PRIVATE_COUNT" ]; then
            cohort=private; ordinal=$((index + 1)); ssid=$PRIVATE_SSID
            band=auto; security=wpa2
            [ "$ordinal" -ne "$((PRIVATE_COUNT - 1))" ] || band=2.4
            if [ "$ordinal" -eq "$PRIVATE_COUNT" ]; then
                band=6; security=sae
            fi
        else
            cohort=iot; ordinal=$((index - PRIVATE_COUNT + 1)); ssid=$IOT_SSID; security=wpa2; band=auto
        fi
        client_ready "$name" "$cohort" "$ordinal" "$ssid" "$security" "$band" &
        probe_pids+=("$!")
        probe_indices+=("$index")
        if [ "${#probe_pids[@]}" -ge "$probe_parallelism" ]; then
            collect_probes
        fi
    done
    [ "${#probe_pids[@]}" -eq 0 ] || collect_probes
    restore_medium() {
        if [ "$medium_pending" = 1 ]; then
            medium_pending=0
            SNR="${SNR:-40}" "$medium_helper" up
        fi
    }
    if [ -x "$medium_helper" ] && [ "$needs_provisioning" = 1 ]; then
        "$medium_helper" down
        medium_pending=1
        trap restore_medium EXIT INT TERM
    elif [ -x "$medium_helper" ]; then
        medium_pidfile=${WMEDIUMD_PIDFILE:-/run/meta-cmf-wmediumd/wmediumd.pid}
        if [ ! -s "$medium_pidfile" ] \
           || ! sudo kill -0 "$(cat "$medium_pidfile" 2>/dev/null)" 2>/dev/null; then
            medium_pending=1
            trap restore_medium EXIT INT TERM
        fi
    fi
    for index in $(seq 0 $((TOTAL - 1))); do
        args=()
        [ "$index" -eq 0 ] || args=(-i "$index")
        name=$(container_name "$index")
        if [ "$index" -lt "$PRIVATE_COUNT" ]; then
            ordinal=$((index + 1))
            cohort=private; ssid=$PRIVATE_SSID; psk=$PRIVATE_PSK
            band=auto; security=wpa2
            [ "$ordinal" -ne "$((PRIVATE_COUNT - 1))" ] || band=2.4
            if [ "$ordinal" -eq "$PRIVATE_COUNT" ]; then
                band=6; security=sae
            fi
        else
            ordinal=$((index - PRIVATE_COUNT + 1))
            cohort=iot; ssid=$IOT_SSID; psk=$IOT_PSK; security=wpa2; band=auto
        fi
        if [ "${healthy[$index]:-0}" = 1 ]; then
            echo "$name: already healthy on $ssid; keeping existing radio and identity"
        else
            "$HERE/wlan-client.sh" "${args[@]}" --cohort "$cohort" --security "$security" --band "$band" \
                up "$ssid" "$psk"
        fi
        lxc config set "$name" user.easymesh.ordinal "$ordinal"
        lxc config set "$name" user.easymesh.band "$band"
        lxc config set "$name" boot.autostart false
    done
    restore_medium
    trap - EXIT INT TERM
    # The live topology provides the authoritative, SSID-qualified fronthaul
    # counts.  STAList also contains one associated mesh_backhaul station for
    # each live extender, so its unqualified count must be a lower-bound check
    # rather than an exact client count.
    expected_associated=$TOTAL
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
            && [[ "$associated" =~ ^[0-9]+$ ]] \
            && [ "$associated" -ge "$expected_associated" ]; then
            enable_metrics_reporting
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
    printf 'CONTAINER\tSTATE\tCOHORT\tORDINAL\tSSID\tSECURITY\tBAND\tFREQ_MHZ\n'
    while read -r name; do
        [ -n "$name" ] || continue
        state=$(lxc info "$name" 2>/dev/null | sed -n 's/^Status: //p')
        freq=$(lxc exec "$name" -- iw dev wlan0 link 2>/dev/null \
            | awk '/freq:/ {print $2; exit}')
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$name" "${state:-UNKNOWN}" \
            "$(lxc config get "$name" user.easymesh.cohort 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.ordinal 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.ssid 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.security 2>/dev/null)" \
            "$(lxc config get "$name" user.easymesh.band 2>/dev/null)" \
            "${freq:-N/A}"
    done < <(lxc list -c n --format csv | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
    ;;
*)
    usage >&2
    exit 2
    ;;
esac
