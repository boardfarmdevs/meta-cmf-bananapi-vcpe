#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
# shellcheck source=profile.sh
source "$root/gen/vm/lxd/profile.sh"
grep -Fq 'RELEASE-NOTES.md' "$root/gen/vm/lxd/build.sh"

check() {
    local input=$1 name=$2 clients=$3 radios=$4 release_name=$5
    test "$(easymesh_profile_name "$input")" = "$name"
    test "$(easymesh_profile_clients "$input")" = "$clients"
    test "$(easymesh_profile_radios "$input")" = "$radios"
    test "$(easymesh_profile_release_name "$input")" = "$release_name"
}

check 20 small 20 32 rdkeasymesh-20-0904
check small small 20 32 rdkeasymesh-20-0904
check 50 medium 50 64 rdkeasymesh-50-0904
check medium medium 50 64 rdkeasymesh-50-0904
check 100 stress 100 128 rdkeasymesh-100-0904
check stress stress 100 128 rdkeasymesh-100-0904
test "$(easymesh_thin_release_name)" = rdkeasymesh-0904-thin
test "$(EASYMESH_RELEASE_ID=0901 easymesh_profile_release_name 20)" = \
    rdkeasymesh-20-0901
test "$(EASYMESH_RELEASE_ID=0901 easymesh_thin_release_name)" = \
    rdkeasymesh-0901-thin
if easymesh_profile_name 21 >/dev/null 2>&1; then
    echo 'invalid profile was accepted' >&2
    exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/test-release"
printf '{}\n' > "$tmp/test-release/release.json"
printf 'payload\n' > "$tmp/test-release/payload"
(
    cd "$tmp/test-release"
    sha256sum payload > SHA256SUMS
)
"$root/gen/vm/lxd/package-release.sh" "$tmp/test-release" "$tmp/test-release-bundle.tar" >/dev/null
(
    cd "$tmp"
    sha256sum -c test-release-bundle.tar.sha256 >/dev/null
)
if grep -q / "$tmp/test-release-bundle.tar.sha256"; then
    echo 'outer checksum contains a host-specific path' >&2
    exit 1
fi

mv "$tmp/test-release" "$tmp/rdkeasymesh-0831-thin"
"$root/gen/vm/lxd/package-release.sh" "$tmp/rdkeasymesh-0831-thin" >/dev/null
test -f "$tmp/rdkeasymesh-0831-thin.tar"
test -f "$tmp/rdkeasymesh-0831-thin.tar.sha256"
mv "$tmp/rdkeasymesh-0831-thin" "$tmp/rdkeasymesh-0901-thin"
"$root/gen/vm/lxd/package-release.sh" "$tmp/rdkeasymesh-0901-thin" >/dev/null
test -f "$tmp/rdkeasymesh-0901-thin.tar"
test -f "$tmp/rdkeasymesh-0901-thin.tar.sha256"

for clients in 20 50 100; do
    case "$clients" in
        20) expected_profile=small; expected_radios=32 ;;
        50) expected_profile=medium; expected_radios=64 ;;
        100) expected_profile=stress; expected_radios=128 ;;
    esac
    state="$tmp/state-$clients"
    defaults="$tmp/defaults-$clients"
    modprobe_conf="$tmp/modprobe-$clients.conf"
    mkdir -p "$state"
    printf 'THIN_INITIAL_INSTANCES=0\nEASYMESH_REPO=/test/repo\n' \
        > "$state/thin-firstboot.template.env"
    : > "$state/thin-profile-selection.required"
    EASYMESH_PROFILE_STATE_DIR="$state" \
    EASYMESH_PROFILE_DEFAULTS="$defaults" \
    EASYMESH_PROFILE_MODPROBE_CONF="$modprobe_conf" \
    EASYMESH_PROFILE_TEST_MODE=true \
        "$root/gen/vm/scripts/guest/easymesh-select-thin-profile" "$clients" \
        >/dev/null
    grep -Fx "EASYMESH_SCALE_PROFILE=$expected_profile" "$defaults" >/dev/null
    grep -Fx "HEALTH_EXPECT_CLIENTS=$clients" "$defaults" >/dev/null
    grep -Fx "options mac80211_hwsim radios=$expected_radios channels=3 regtest=5" \
        "$modprobe_conf" >/dev/null
    grep -Fx "HEALTH_EXPECT_CLIENTS=$clients" \
        "$state/thin-profile.lock.env" >/dev/null
    grep -Fx "HWSIM_RADIOS=$expected_radios" \
        "$state/thin-firstboot.env" >/dev/null
    test ! -e "$state/thin-profile-selection.required"

    # Repeating the same choice is idempotent; changing it is forbidden.
    EASYMESH_PROFILE_STATE_DIR="$state" \
    EASYMESH_PROFILE_DEFAULTS="$defaults" \
    EASYMESH_PROFILE_MODPROBE_CONF="$modprobe_conf" \
    EASYMESH_PROFILE_TEST_MODE=true \
        "$root/gen/vm/scripts/guest/easymesh-select-thin-profile" "$clients" \
        >/dev/null
    different=20
    [ "$clients" != 20 ] || different=50
    if EASYMESH_PROFILE_STATE_DIR="$state" \
        EASYMESH_PROFILE_DEFAULTS="$defaults" \
        EASYMESH_PROFILE_MODPROBE_CONF="$modprobe_conf" \
        EASYMESH_PROFILE_TEST_MODE=true \
        "$root/gen/vm/scripts/guest/easymesh-select-thin-profile" "$different" \
            >/dev/null 2>&1; then
        echo "locked $clients-client thin profile changed to $different" >&2
        exit 1
    fi
done

mkdir "$tmp/universal-import"
install -m 0755 "$root/gen/vm/lxd/import.sh" "$tmp/universal-import/import.sh"
printf 'LAB_PROFILE_SELECTABLE=true\nLAB_SUPPORTED_PROFILES=20,50,100\n' \
    > "$tmp/universal-import/release.env"
if "$tmp/universal-import/import.sh" >"$tmp/missing-profile.out" 2>&1; then
    echo 'universal import accepted a missing profile' >&2
    exit 1
fi
grep -F 'requires --profile 20, 50 or 100' "$tmp/missing-profile.out" >/dev/null
if "$tmp/universal-import/import.sh" --profile 21 \
    >"$tmp/invalid-profile.out" 2>&1; then
    echo 'universal import accepted an invalid profile' >&2
    exit 1
fi
grep -F 'requires --profile 20, 50 or 100' "$tmp/invalid-profile.out" >/dev/null

echo 'PASS: RDK EasyMesh portable profiles'
