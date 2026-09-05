#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
build=$root/gen/vm/lxd/build.sh
stage=$(mktemp -d /tmp/easymesh-http-ready.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
log=$stage/curl.log

# Exercise the exact helper from build.sh without provisioning a VM.
eval "$(sed -n '/^wait_http_ready()/,/^}/p' "$build")"

curl() {
    {
        printf '%q ' "$@"
        printf '\n'
    } >> "$log"
    attempts=$((attempts + 1))
    if [ "$attempts" -le "${EASYMESH_TEST_TRANSIENT_FAILURES:-0}" ]; then
        return 22
    fi
    return "${EASYMESH_TEST_CURL_RC:-0}"
}

sleep() {
    SECONDS=$((SECONDS + $1))
}

http_ready_timeout=240
attempts=0
: > "$log"
wait_http_ready "test endpoint" "http://192.0.2.1:18889/api/v1/topology"
test "$attempts" = 1
! grep -F -- '--retry-all-errors' "$log" >/dev/null
grep -F -- '--connect-timeout 2' "$log" >/dev/null
grep -F -- '--max-time 10' "$log" >/dev/null
grep -F -- 'http://192.0.2.1:18889/api/v1/topology' "$log" >/dev/null

attempts=0
EASYMESH_TEST_TRANSIENT_FAILURES=2
wait_http_ready "eventually ready" "http://192.0.2.1/ready"
test "$attempts" = 3
EASYMESH_TEST_TRANSIENT_FAILURES=0

attempts=0
http_ready_timeout=3
EASYMESH_TEST_CURL_RC=22
if wait_http_ready "failed endpoint" "http://192.0.2.2:18889/api/v1/topology" \
    2>/dev/null; then
    echo 'wait_http_ready accepted a failed HTTP probe' >&2
    exit 1
fi
test "$attempts" = 2
grep -F -- '--max-time 1' "$log" >/dev/null

http_ready_timeout=invalid
if wait_http_ready "invalid timeout" "http://192.0.2.3/" 2>/dev/null; then
    echo 'wait_http_ready accepted an invalid timeout' >&2
    exit 1
fi

echo 'PASS: portable HTTP retries, eventual readiness and a bounded overall deadline'
