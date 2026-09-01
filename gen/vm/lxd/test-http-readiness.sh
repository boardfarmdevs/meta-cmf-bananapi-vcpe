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
    return "${EASYMESH_TEST_CURL_RC:-0}"
}

http_ready_timeout=240
: > "$log"
wait_http_ready "test endpoint" "http://192.0.2.1:18889/api/v1/topology"
grep -F -- '--retry-all-errors' "$log" >/dev/null
grep -F -- '--retry-max-time 240' "$log" >/dev/null
grep -F -- '--connect-timeout 2' "$log" >/dev/null
grep -F -- '--max-time 10' "$log" >/dev/null
grep -F -- 'http://192.0.2.1:18889/api/v1/topology' "$log" >/dev/null

EASYMESH_TEST_CURL_RC=22
if wait_http_ready "failed endpoint" "http://192.0.2.2:18889/api/v1/topology" \
    2>/dev/null; then
    echo 'wait_http_ready accepted a failed HTTP probe' >&2
    exit 1
fi

http_ready_timeout=invalid
if wait_http_ready "invalid timeout" "http://192.0.2.3/" 2>/dev/null; then
    echo 'wait_http_ready accepted an invalid timeout' >&2
    exit 1
fi

echo 'PASS: bounded post-reboot HTTP readiness'
