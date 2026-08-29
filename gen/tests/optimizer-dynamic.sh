#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
mode=${1:-recommend}
client=${2:-wlan-client-007}
target=${3:-bpiap-001}
case "$mode" in
    recommend|act) ;;
    *) echo "usage: $0 [recommend|act] [wlan-client-NNN] [bpibroadband|bpiap-NNN]" >&2; exit 2 ;;
esac

inventory=$(mktemp /tmp/rdk-optimizer-inventory.XXXXXX.json)
plan=$(mktemp /tmp/rdk-optimizer-plan.XXXXXX.json)
journal=$(mktemp /tmp/rdk-optimizer-journal.XXXXXX.jsonl)
scenario_log=$(mktemp /tmp/rdk-optimizer-scenario.XXXXXX.log)
optimizer_log=$(mktemp /tmp/rdk-optimizer-output.XXXXXX.log)
scenario_pid=
medium_backend=${EASYMESH_MEDIUM_BACKEND:-}
if [[ -z $medium_backend && -r /etc/default/easymesh-lab ]]; then
    medium_backend=$(sed -n 's/^[[:space:]]*EASYMESH_MEDIUM_BACKEND=//p' \
        /etc/default/easymesh-lab | tail -1 | tr -d "'\"")
fi
medium_backend=${medium_backend:-userspace}
case "$medium_backend" in
    userspace) scenario_command=(python3 -m wmdcfg.cli run) ;;
    kernel) scenario_command=(sudo -n python3 -m wmdcfg.cli run) ;;
    *) echo "unsupported medium backend: $medium_backend" >&2; exit 2 ;;
esac

cleanup()
{
    if [ -n "$scenario_pid" ] && kill -0 "$scenario_pid" 2>/dev/null; then
        kill -TERM "$scenario_pid" 2>/dev/null || true
        wait "$scenario_pid" 2>/dev/null || true
    fi
    rm -f "$inventory" "$plan"
}
trap cleanup EXIT

cd "$root/gen/wmediumd/configurator"
python3 -m wmdcfg.cli inventory -o "$inventory"

readarray -t binding < <(python3 - "$inventory" "$client" "$target" <<'PY'
import json
import sys

inventory = json.load(open(sys.argv[1], encoding="utf-8"))
client_name, target_name = sys.argv[2:]
by_name = {item["container"]: item for item in inventory["radios"]}
client = by_name.get(client_name)
target = by_name.get(target_name)
if not client or client.get("kind") != "station":
    raise SystemExit(f"unknown station container: {client_name}")
if not target or target.get("kind") != "mesh":
    raise SystemExit(f"unknown mesh target: {target_name}")
source_bssid = client.get("associated_bssid")
if not source_bssid:
    raise SystemExit(f"{client_name} is not associated")

def band(frequency):
    return "2.4" if frequency < 2500 else "5" if frequency < 5925 else "6"

def bss_owner(bssid):
    for item in inventory["radios"]:
        if item.get("kind") != "mesh":
            continue
        for interface in item.get("interfaces", []):
            if str(interface.get("mac", "")).lower() == bssid.lower():
                return item["container"]

source = bss_owner(source_bssid)
if not source:
    raise SystemExit(f"cannot map serving BSSID {source_bssid}")
if source == target_name:
    raise SystemExit(f"{client_name} is already served by {target_name}")
others = sorted(
    item["container"] for item in inventory["radios"]
    if item.get("kind") == "mesh" and item["container"] not in {source, target_name}
)
if len(others) != 3:
    raise SystemExit(f"five-node profile required; found {2 + len(others)} mesh nodes")
wlan = next(
    (item for item in client.get("interfaces", []) if item.get("name") == "wlan0"),
    None,
)
if not wlan or not wlan.get("frequency_mhz"):
    raise SystemExit(f"cannot determine {client_name} operating band")
client_band = band(int(wlan["frequency_mhz"]))
ssid = client.get("ssid")
target_bssid = next(
    (item.get("mac") for item in target.get("interfaces", [])
     if item.get("ssid") == ssid
     and item.get("frequency_mhz")
     and band(int(item["frequency_mhz"])) == client_band),
    None,
)
if not target_bssid:
    raise SystemExit(f"no {client_band} GHz {ssid} BSS on {target_name}")
for value in [source, target_name, str(target_bssid).lower(), *others]:
    print(value)
PY
)
source=${binding[0]}
target=${binding[1]}
target_bssid=${binding[2]}

python3 -m wmdcfg.cli compile scenarios/optimizer-five-ap-crossover.wmd \
    --inventory "$inventory" \
    --bind "client=$client" \
    --bind "source=$source" \
    --bind "target=$target" \
    --bind "alternate_1=${binding[3]}" \
    --bind "alternate_2=${binding[4]}" \
    --bind "alternate_3=${binding[5]}" \
    -o "$plan"

echo "optimizer stimulus: $client $source -> $target ($target_bssid)"
"${scenario_command[@]}" "$plan" --backend "$medium_backend" \
    >"$scenario_log" 2>&1 &
scenario_pid=$!
sleep 2

cd "$root/gen/optimizer"
args=(
    "$mode" --base-url http://127.0.0.1:8888
    --candidate-provider controller --allow-simulated-candidates
    --candidate-attempts 2
    --policy configs/threshold-policy.yaml --journal "$journal"
    # One RDK controller candidate transaction spans roughly 20 seconds. Six
    # samples cover the policy hold while keeping this acceptance bounded by
    # the 130-second stimulus rather than continuing long after restoration.
    --count 6 --interval 1
)
if [ "$mode" = act ]; then
    args+=(--yes-act --max-actions 1)
fi
if ! python3 -m optimizer.cli "${args[@]}" >"$optimizer_log"; then
    tail -n 40 "$optimizer_log" >&2
    exit 1
fi
wait "$scenario_pid"
scenario_pid=

if [ "$mode" = recommend ]; then
    observed=$(jq -r '
        select(.kind == "evaluation")
        | .payload.decisions[]
        | select(.action == "steer")
        | .target_bssid' "$journal" | tail -1)
    [ "$observed" = "$target_bssid" ] || {
        echo "optimizer did not recommend expected target $target_bssid (got ${observed:-none})" >&2
        tail -n 40 "$optimizer_log" >&2
        exit 1
    }
else
    jq -e 'select(.kind == "action" and .payload.success == true)' "$journal" >/dev/null
    jq -e 'select(.kind == "verification" and .payload.success == true)' "$journal" >/dev/null
fi

summary=$(tail -1 "$scenario_log")
jq -e '.outcome == "passed" and .restored == true' "$summary/summary.json" >/dev/null
echo "PASS: RDK dynamic $mode used controller candidate metrics; scenario restored"
echo "journal: $journal"
echo "scenario: $summary"
echo "optimizer output: $optimizer_log"
