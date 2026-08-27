#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: association-ownership-regression.sh [options] STA CLIENT TARGET [TARGET...]

Options:
  --rounds N             repeat the target sequence (default: 1)
  --convergence SEC      physical/API convergence deadline (default: 45)
  --stability SEC        post-convergence consistency window (default: 30)
  --results FILE         CSV result path
  -h, --help             show this help

Example:
  ./gen/tests/association-ownership-regression.sh \
    --rounds 2 sta-09 wlan-client extender-2 extender-3 extender-1
EOF
}

rounds=1
convergence=45
stability=30
results=
while [ $# -gt 0 ]; do
    case "$1" in
        --rounds) rounds=$2; shift 2 ;;
        --convergence) convergence=$2; shift 2 ;;
        --stability) stability=$2; shift 2 ;;
        --results) results=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
        *) break ;;
    esac
done

[ $# -ge 3 ] || { usage >&2; exit 2; }
sta=$1
client=$2
shift 2
targets=("$@")
for value in "$rounds" "$convergence" "$stability"; do
    [[ "$value" =~ ^[1-9][0-9]*$ ]] \
        || { echo "rounds and timeouts must be positive integers" >&2; exit 2; }
done

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
steer="$repo/gen/steer.sh"
results=${results:-$repo/tmp/test-results/association-ownership.csv}
mkdir -p "$(dirname "$results")"

mac=$(lxc exec "$client" -- iw dev wlan0 info 2>/dev/null |
    awk '/addr/ {print tolower($2); exit}')
[ -n "$mac" ] || { echo "cannot read wlan0 MAC from $client" >&2; exit 1; }

api_bssid() {
    curl -fsS http://127.0.0.1:8888/api/v1/clients 2>/dev/null |
        jq -r --arg mac "$mac" '(.clients // .)[]? |
            select((.mac | ascii_downcase) == $mac) | .connected_bssid' |
        head -1 | tr '[:upper:]' '[:lower:]'
}

physical_bssid() {
    lxc exec "$client" -- iw dev wlan0 link 2>/dev/null |
        awk '/Connected to/ {print tolower($3); exit}'
}

[ -n "$(api_bssid)" ] \
    || { echo "$sta/$mac is not present in the controller client API" >&2; exit 1; }

printf '%s\n' \
    'round,target,target_bssid,convergence_seconds,stability_seconds,result' >"$results"
passes=0
total=$((rounds * ${#targets[@]}))

for round in $(seq 1 "$rounds"); do
    for target in "${targets[@]}"; do
        dry_run=$($steer --dry-run "$sta" "$target" 2>&1) || {
            echo "$dry_run" >&2
            exit 1
        }
        target_bssid=$(sed -n 's/.*target_BSSID=\([^ ]*\).*/\1/p' <<<"$dry_run" |
            head -1 | tr '[:upper:]' '[:lower:]')
        [ -n "$target_bssid" ] \
            || { echo "cannot resolve target BSSID from: $dry_run" >&2; exit 1; }

        echo "round $round: $sta/$mac -> $target ($target_bssid)"
        $steer "$sta" "$target"

        converged=-1
        for second in $(seq 0 "$convergence"); do
            physical=$(physical_bssid || true)
            api=$(api_bssid || true)
            if [ "$physical" = "$target_bssid" ] && [ "$api" = "$target_bssid" ]; then
                converged=$second
                break
            fi
            [ "$second" -eq "$convergence" ] || sleep 1
        done
        if [ "$converged" -lt 0 ]; then
            printf '%s,%s,%s,%s,%s,FAIL_CONVERGENCE\n' \
                "$round" "$target" "$target_bssid" -1 0 >>"$results"
            echo "ownership did not converge: physical=${physical:-missing} api=${api:-missing}" >&2
            exit 1
        fi

        for second in $(seq 1 "$stability"); do
            sleep 1
            physical=$(physical_bssid || true)
            api=$(api_bssid || true)
            if [ "$physical" != "$target_bssid" ] || [ "$api" != "$target_bssid" ]; then
                printf '%s,%s,%s,%s,%s,FAIL_REVERSION\n' \
                    "$round" "$target" "$target_bssid" "$converged" "$second" >>"$results"
                echo "ownership reverted at ${second}s: physical=${physical:-missing} api=${api:-missing}" >&2
                exit 1
            fi
        done

        printf '%s,%s,%s,%s,%s,PASS\n' \
            "$round" "$target" "$target_bssid" "$converged" "$stability" >>"$results"
        passes=$((passes + 1))
        echo "PASS: converged in ${converged}s; stable for ${stability}s"
    done
done

echo "association ownership regression PASSED $passes/$total; results=$results"
