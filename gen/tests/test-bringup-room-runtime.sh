#!/usr/bin/env bash
# lab-bringup's room step and the lab's runtime: the room service requires easymesh-lab.service,
# so with the runtime not active, starting the room service ran the runtime's whole cold start
# first without a word (rdk-1004, 9 October). The step now says so and starts the runtime on
# its own, before the room service; with the runtime active it starts only the room service.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
eval "$(sed -n '/^room()/,/^}/p' "$root/gen/lab-bringup.sh")"

# shellcheck disable=SC2034 # read by the room step taken from the script
ROOM_UNIT=easymesh-room-service.service
log() { echo "LOG $*" >> "$temporary/calls"; }
die() { echo "DIE $*" >> "$temporary/calls"; exit 1; }
pool_online() { :; }
room_settled() { echo settled; }
sleep() { :; }
grep() { [ "${*: -2:1}" = HEALTH_EXPECT_CLIENTS=100 ] || command grep "$@"; }
systemctl() {
    echo "systemctl $*" >> "$temporary/calls"
    case "$*" in
        "is-active --quiet easymesh-lab.service") [ "$(cat "$temporary/runtime")" = active ] ;;
        "is-active easymesh-lab.service") cat "$temporary/runtime"; [ "$(cat "$temporary/runtime")" = active ] ;;
        "start easymesh-lab.service") [ "$(cat "$temporary/start")" = ok ] && echo active > "$temporary/runtime" ;;
        *) return 0 ;;
    esac
}

run() {    # run RUNTIME START: the runtime's state, whether its start succeeds
    echo "$1" > "$temporary/runtime"
    echo "$2" > "$temporary/start"
    : > "$temporary/calls"
    (room) || true
}

run failed ok
command grep -q "^LOG the lab's runtime is failed: its cold start first" "$temporary/calls"
runtime=$(command grep -n "^systemctl start easymesh-lab.service$" "$temporary/calls" | cut -d: -f1)
room=$(command grep -n "^systemctl start easymesh-room-service.service$" "$temporary/calls" | cut -d: -f1)
if [ -z "$runtime" ] || [ -z "$room" ] || [ "$runtime" -ge "$room" ]; then
    echo "FAIL: the runtime is not started before the room service" >&2
    cat "$temporary/calls" >&2
    exit 1
fi
command grep -q "^LOG room settled" "$temporary/calls"

run failed fails
command grep -q "^DIE the lab's runtime did not start" "$temporary/calls"
if command grep -q "^systemctl start easymesh-room-service.service$" "$temporary/calls"; then
    echo "FAIL: the room service started after the runtime failed" >&2
    exit 1
fi

run active ok
if command grep -q -e "^systemctl start easymesh-lab.service$" -e "^LOG the lab's runtime" "$temporary/calls"; then
    echo "FAIL: an active runtime started again" >&2
    exit 1
fi
command grep -q "^systemctl start easymesh-room-service.service$" "$temporary/calls"

echo "PASS: the room step starts a runtime that is not active on its own and says so, never through the room service"
