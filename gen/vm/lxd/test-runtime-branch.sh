#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
meta_workspace="$temporary/workspace"
meta_bundle="$temporary/source.bundle"
runtime_branch=codex/0905-clean
mkdir -p "$meta_workspace"
git init -q "$temporary/source"
git -C "$temporary/source" symbolic-ref HEAD refs/heads/lxd-appliance-export
git -C "$temporary/source" config user.name 'Runtime branch test'
git -C "$temporary/source" config user.email 'runtime-test@example.invalid'
printf 'original\n' > "$temporary/source/payload"
git -C "$temporary/source" add payload
git -C "$temporary/source" -c commit.gpgsign=false commit -qm initial
expected_meta_head=$(git -C "$temporary/source" rev-parse HEAD)
git -C "$temporary/source" bundle create "$meta_bundle" lxd-appliance-export
awk '
    /^if \[ ! -d "\$meta_workspace/ {active=1}
    /^clone_pinned_repo\(\)/ {exit}
    active {print}
' "$root/gen/vm/scripts/20-prepare-lab-host.sh" > "$temporary/checkout.sh"
test -s "$temporary/checkout.sh"

sudo() {
    test "$1" = -u && test "$2" = easymesh
    shift 2
    "$@"
}
export -f sudo

checkout_runtime() {
    export meta_workspace meta_bundle runtime_branch expected_meta_head
    bash -eu "$temporary/checkout.sh" >/dev/null 2>&1
}

assert_identity() {
    test "$(git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" = "$expected_meta_head"
    test "$(git -C "$meta_workspace/meta-cmf-bananapi-vcpe" symbolic-ref --short HEAD)" = "$runtime_branch"
}

checkout_runtime
assert_identity
checkout_runtime
assert_identity
git -C "$meta_workspace/meta-cmf-bananapi-vcpe" checkout -q --detach
checkout_runtime
assert_identity
git -C "$meta_workspace/meta-cmf-bananapi-vcpe" checkout -q lxd-appliance-export
printf 'uncommitted\n' >> "$meta_workspace/meta-cmf-bananapi-vcpe/payload"
if checkout_runtime; then
    echo 'runtime branch reconciliation accepted a dirty checkout' >&2
    exit 1
fi
test "$(git -C "$meta_workspace/meta-cmf-bananapi-vcpe" symbolic-ref --short HEAD)" = lxd-appliance-export
grep -Fx uncommitted "$meta_workspace/meta-cmf-bananapi-vcpe/payload" >/dev/null
printf 'PASS: fresh, existing and detached runtime checkouts use the canonical branch without discarding changes\n'
