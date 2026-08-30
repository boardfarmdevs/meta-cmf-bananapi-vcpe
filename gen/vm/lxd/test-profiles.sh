#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
# shellcheck source=profile.sh
source "$root/gen/vm/lxd/profile.sh"

check() {
    local input=$1 name=$2 clients=$3 radios=$4
    test "$(easymesh_profile_name "$input")" = "$name"
    test "$(easymesh_profile_clients "$input")" = "$clients"
    test "$(easymesh_profile_radios "$input")" = "$radios"
}

check 20 small 20 32
check small small 20 32
check 50 medium 50 64
check medium medium 50 64
check 100 stress 100 128
check stress stress 100 128
if easymesh_profile_name 21 >/dev/null 2>&1; then
    echo 'invalid profile was accepted' >&2
    exit 1
fi

echo 'PASS: RDK EasyMesh portable profiles'
