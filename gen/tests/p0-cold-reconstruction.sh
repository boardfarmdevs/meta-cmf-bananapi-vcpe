#!/usr/bin/env bash
# Run the P0 cold-reconstruction acceptance repeatedly against an installed lab.
# Existing LXD instances and persistent /nvram identities are retained, while
# every run stops all WLAN participants, reclaims transient hwsim VAPs, and
# reconstructs controller -> extenders -> clients -> wmediumd in dependency
# order. This is deliberately the same runtime used by the distributable VM.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
# shellcheck source=lib/observer-status.sh
source "$here/lib/observer-status.sh"
runtime="$repo/gen/vm/scripts/guest/easymesh-lab-runtime"
lab_user=${EASYMESH_LAB_USER:-$(id -un)}
lab_group=${EASYMESH_LAB_GROUP:-$(id -gn "$lab_user")}
lab_home=${EASYMESH_LAB_HOME:-$(getent passwd "$lab_user" | cut -d: -f6)}
runs=${1:-3}
result_root=${P0_COLD_RESULT_ROOT:-$repo/tmp/test-results/p0-cold-reconstruction}
campaign=$(date -u +%Y%m%dT%H%M%SZ)
campaign_dir="$result_root/$campaign"

if ! [[ "$runs" =~ ^[1-9][0-9]*$ ]]; then
    echo "usage: $0 [positive-run-count]" >&2
    exit 2
fi

command -v lxc >/dev/null
command -v docker >/dev/null
[ -r "$runtime" ]
install -d "$campaign_dir"

runtime_env=(
    "EASYMESH_LAB_USER=$lab_user"
    "EASYMESH_LAB_GROUP=$lab_group"
    "EASYMESH_LAB_HOME=$lab_home"
    "EASYMESH_GEN=$repo/gen"
    "EASYMESH_ACCEPTANCE_STATE=$campaign_dir/runtime-evidence"
    "EASYMESH_MEDIUM_BACKEND=${EASYMESH_MEDIUM_BACKEND:-userspace}"
)

printf 'campaign=%s runs=%s host=%s kernel=%s revision=%s medium_backend=%s\n' \
    "$campaign" "$runs" "$(hostname)" "$(uname -r)" \
    "$(git -C "$repo" rev-parse HEAD)" \
    "${EASYMESH_MEDIUM_BACKEND:-userspace}" | tee "$campaign_dir/campaign.txt"

passed=0
status_section "Managed cold-reconstruction campaign"
status_note "Running $runs complete stop/reconstruct/acceptance cycle(s) with preserved identities."
for run in $(seq 1 "$runs"); do
    run_log=$(printf '%s/run-%02d.log' "$campaign_dir" "$run")
    started=$(date +%s)
    status_action "Cold reconstruction $run/$runs: stopping participants and rebuilding the complete lab."
    echo "P0 cold reconstruction $run/$runs starting at $(date -Ins)" | tee "$run_log"
    if sudo env "${runtime_env[@]}" bash "$runtime" start 2>&1 | tee -a "$run_log"; then
        elapsed=$(($(date +%s) - started))
        printf 'run=%s outcome=PASS elapsed_seconds=%s completed=%s\n' \
            "$run" "$elapsed" "$(date -Ins)" | tee -a "$campaign_dir/campaign.txt" "$run_log"
        passed=$((passed + 1))
        status_pass "Run $run/$runs passed in ${elapsed}s."
    else
        rc=${PIPESTATUS[0]}
        elapsed=$(($(date +%s) - started))
        printf 'run=%s outcome=FAIL rc=%s elapsed_seconds=%s completed=%s\n' \
            "$run" "$rc" "$elapsed" "$(date -Ins)" | tee -a "$campaign_dir/campaign.txt" "$run_log"
        echo "P0 cold reconstruction stopped after $passed/$runs passes; artifacts=$campaign_dir" >&2
        exit "$rc"
    fi
done

status_pass "P0 cold reconstruction passed $passed/$runs; artifacts=$campaign_dir"
