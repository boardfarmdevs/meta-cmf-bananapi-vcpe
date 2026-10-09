#!/usr/bin/env bash
# The audit's traffic rounds: a lossy round is measured again after a pause, only the last
# round decides, and the loss bar stays the same.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
eval "$(sed -n '/^stamp() /p;/^medium_counts()/,/^}/p;/^medium_snapshot()/,/^}/p;/^medium_round()/,/^}/p;
    /^radio_drops_snapshot()/,/^}/p;/^radio_drops_round()/,/^}/p;
    /^traffic_round()/,/^}/p;/^traffic_rounds()/,/^}/p' "$root/gen/tests/health-audit.sh")"
medium_runtime=$temporary    # no medium log: its refusals count 0
curl() { return 7; }         # no medium telemetry: each round says so

# lxc exec CLIENT -- ping ...: the loss of this round for the client, from a script of rounds;
# lxc list: no devices, so no radios' drops: each round says so
lxc() {
    local round loss
    [ "$1" != list ] || return 0
    round=$(cat "$temporary/round")
    loss=$(sed -n "${round}p" "$temporary/losses")
    case " $loss " in *" $2 "*) echo "10 packets transmitted, 6 received, 40% packet loss" ;;
        *) echo "10 packets transmitted, 10 received, 0% packet loss" ;; esac
}
timeout() { shift; "$@"; }
sleep() { echo $(( $(cat "$temporary/round") + 1 )) > "$temporary/round"; }
traffic_clients=(wlan-client wlan-client-001 wlan-client-002)
expected_clients=3 ping_count=10 ping_interval=1 ping_max_loss=0 ping_exec_attempts=1 ping_exec_timeout=5
ping_settle=30

run() {    # ROUNDS LOSSES...: one line of lossy clients per round
    ping_rounds=$1; shift
    echo 1 > "$temporary/round"
    printf '%s\n' "$@" > "$temporary/losses"
    traffic_rounds > "$temporary/out" 2>&1
}

run 2 "wlan-client-001" ""                       # lossy, then settled: passes
grep -q '^SETTLE: packets lost in round 1' "$temporary/out"
grep -q '^wlan-client-001 40%' "$temporary/out"
# each round its times and the medium's refusals, each client its link
for round in 1 2; do
    grep -Eq "^ROUND_TIME round=$round start=[0-9T:.-]+Z end=[0-9T:.-]+Z medium_before cmd2=0 cmd3=0 medium_during cmd2=0 cmd3=0$" "$temporary/out"
    test "$(grep -c "^LINK round=$round wlan-client" "$temporary/out")" = 3
    grep -qx "MEDIUM_ROUND round=$round medium unavailable" "$temporary/out"
    grep -qx "RADIO_DROPS round=$round unavailable" "$temporary/out"
done
if run 2 "wlan-client-001" "wlan-client-002"; then # lossy twice: fails
    echo 'two lossy rounds must fail' >&2; exit 1
fi
test "$(grep -c '^SETTLE' "$temporary/out")" = 1
if run 1 "wlan-client"; then                         # one round only: the old bar
    echo 'a lossy single round must fail' >&2; exit 1
fi
! grep -q '^SETTLE' "$temporary/out"
run 2 "" "wlan-client"                               # clean at once: no second round
! grep -q '^ROUND 2' "$temporary/out"
echo 'PASS: a lossy traffic round is measured again after settling; the last round decides at the same bar'
