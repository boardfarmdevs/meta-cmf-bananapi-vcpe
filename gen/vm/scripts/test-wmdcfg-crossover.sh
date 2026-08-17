#!/bin/bash
# Exercise a compiled wmdcfg plan while sampling client association and traffic.
set -euo pipefail

META_DIR=${META_DIR:-/home/vagrant/git/meta-cmf-bananapi-vcpe}
PLAN=${PLAN:-/tmp/wmdcfg-crossover-plan.json}
OUTPUT_ROOT=${OUTPUT_ROOT:-/tmp/wmdcfg-live-crossover}
CLIENT=${CLIENT:-wlan-client}
PING_TARGET=${PING_TARGET:-10.0.0.1}
PING_COUNT=${PING_COUNT:-1400}
SAMPLE_COUNT=${SAMPLE_COUNT:-70}
STEER_TARGET=${STEER_TARGET:-}
STEER_AFTER=${STEER_AFTER:-42}
STEER_CONTAINER=${STEER_CONTAINER:-bpibroadband}
STA_MAC=${STA_MAC:-02:00:00:00:03:00}

case "$OUTPUT_ROOT" in
    /tmp/wmdcfg-*) ;;
    *)
        echo "refusing unsafe OUTPUT_ROOT: $OUTPUT_ROOT" >&2
        exit 2
        ;;
esac

daemon_pattern='^/home/.*/gen/wmediumd/wmediumd\.patched '
before_pid=$(pgrep -fo "$daemon_pattern")
rm -rf -- "$OUTPUT_ROOT"
rm -f -- /tmp/wmdcfg-crossover-ping.txt /tmp/wmdcfg-crossover-assoc.txt
rm -f -- /tmp/wmdcfg-crossover-steer.txt

lxc exec "$CLIENT" -- ping -n -i 0.05 -c "$PING_COUNT" "$PING_TARGET" \
    > /tmp/wmdcfg-crossover-ping.txt 2>&1 &
ping_pid=$!

(
    for _ in $(seq 0 "$SAMPLE_COUNT"); do
        printf '%s ' "$(date +%s%3N)"
        lxc exec "$CLIENT" -- iw dev wlan0 link 2>/dev/null \
            | sed -n 's/^Connected to \([^ ]*\).*/\1/p'
        sleep 1
    done
) > /tmp/wmdcfg-crossover-assoc.txt &
assoc_pid=$!

steer_pid=
if [ -n "$STEER_TARGET" ]; then
    (
        sleep "$STEER_AFTER"
        lxc exec "$STEER_CONTAINER" -- /usr/bin/steer.sh \
            "$STA_MAC" "$STEER_TARGET"
    ) > /tmp/wmdcfg-crossover-steer.txt 2>&1 &
    steer_pid=$!
fi

set +e
(
    cd "$META_DIR"
    PYTHONPATH=gen/wmediumd/configurator \
        python3 -m wmdcfg.cli run "$PLAN" --output-root "$OUTPUT_ROOT"
)
run_rc=$?
wait "$ping_pid"
ping_rc=$?
wait "$assoc_pid"
assoc_rc=$?
steer_rc=0
if [ -n "$steer_pid" ]; then
    wait "$steer_pid"
    steer_rc=$?
fi
set -e

after_pid=$(pgrep -fo "$daemon_pattern")
printf 'runner_rc=%s ping_rc=%s assoc_rc=%s steer_rc=%s before_pid=%s after_pid=%s\n' \
    "$run_rc" "$ping_rc" "$assoc_rc" "$steer_rc" "$before_pid" "$after_pid"
tail -n 3 /tmp/wmdcfg-crossover-ping.txt
if [ -n "$STEER_TARGET" ]; then
    cat /tmp/wmdcfg-crossover-steer.txt
fi
find "$OUTPUT_ROOT" -maxdepth 2 -type f -print

exit "$run_rc"
