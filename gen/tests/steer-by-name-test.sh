#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
fixture=$(mktemp)
fakebin=$(mktemp -d)
trap 'rm -f "$fixture"; rm -rf "$fakebin"' EXIT

cat >"$fixture" <<'EOF'
{"nodes":[
 {"name":"Controller","STAList":[],"haulTypes":[]},
 {"name":"Agent-1","STAList":[],"haulTypes":[{"name":"Fronthaul","ssid":"private_ssid","BSSList":[{"BSSID":"02:00:00:aa:aa:01","Band":1,"ssid":"private_ssid","STAList":[]}]}]},
 {"name":"Extender-2","STAList":[{"staMAC":"02:00:00:00:03:00","band":1,"ssid":"private_ssid"}],"haulTypes":[{"name":"Fronthaul","ssid":"private_ssid","BSSList":[{"BSSID":"02:00:00:bb:bb:00","Band":0,"ssid":"private_ssid","STAList":[]},{"BSSID":"02:00:00:bb:bb:01","Band":1,"ssid":"private_ssid","STAList":[{"staMAC":"02:00:00:00:03:00"}]},{"BSSID":"02:00:00:bb:bb:03","Band":3,"ssid":"private_ssid","STAList":[]}]}]}
]}
EOF

cat >"$fakebin/curl" <<EOF
#!/bin/sh
cat '$fixture'
EOF
cat >"$fakebin/lxc" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod +x "$fakebin/curl" "$fakebin/lxc"

run() {
    PATH="$fakebin:$PATH" "$repo/gen/steer.sh" --dry-run "$@"
}

output=$(run sta-03 agent-1)
grep -q 'STA=02:00:00:00:03:00 target_BSSID=02:00:00:aa:aa:01 SSID=private_ssid band=1' <<<"$output"
grep -q '/usr/bin/steer.sh 02:00:00:00:03:00 02:00:00:aa:aa:01' <<<"$output"

output=$(run --band 6 sta-03 extender-2)
grep -q 'target_BSSID=02:00:00:bb:bb:03 SSID=private_ssid band=3' <<<"$output"

set +e
output=$(run sta-03 extender-2 2>&1)
rc=$?
set -e
[[ $rc -eq 1 ]]
grep -q "already on Extender-2" <<<"$output"

set +e
output=$(run sta-03 controller 2>&1)
rc=$?
set -e
[[ $rc -eq 1 ]]
grep -q "the Controller node has no WLAN BSS" <<<"$output"

echo 'steer-by-name tests: PASS'
