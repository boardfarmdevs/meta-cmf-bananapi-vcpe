#!/usr/bin/env bash
set -euo pipefail

# Sequentially qualify the fixed five-node lab with 20, 50 and 100 clients.
# The campaign owns the hwsim pool while it runs and records every transition
# before entering the duration-bound RF churn soak for that profile.

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root inside the EasyMesh host or appliance VM" >&2
    exit 1
fi

repo=${EASYMESH_REPO:-/home/easymesh/git/meta-cmf-bananapi-vcpe}
runtime=${EASYMESH_RUNTIME:-/usr/local/sbin/easymesh-lab-runtime}
duration=${EASYMESH_SOAK_PROFILE_SECONDS:-43200}
sample_interval=${EASYMESH_SOAK_SAMPLE_SECONDS:-60}
settle=${EASYMESH_SOAK_SETTLE_SECONDS:-30}
output_root=${EASYMESH_SOAK_OUTPUT_ROOT:-/home/easymesh/easymesh-evidence/scale-soak}
if [ "$#" -eq 0 ]; then
    profiles=(small medium stress)
else
    profiles=("$@")
fi

case "$duration:$sample_interval:$settle" in
    *[!0-9.:]*) echo "soak durations must be numeric" >&2; exit 2 ;;
esac

profile_clients() {
    case "$1" in
        small) printf '20\n' ;;
        medium) printf '50\n' ;;
        stress) printf '100\n' ;;
        *) echo "unknown client profile: $1" >&2; exit 2 ;;
    esac
}

profile_radios() {
    case "$1" in
        small) printf '32\n' ;;
        medium) printf '64\n' ;;
        stress) printf '128\n' ;;
        *) echo "unknown client profile: $1" >&2; exit 2 ;;
    esac
}

profile_cli_limit() {
    case "$1" in
        small) printf '192\n' ;;
        medium) printf '320\n' ;;
        stress) printf '512\n' ;;
    esac
}

for profile in "${profiles[@]}"; do
    profile_clients "$profile" >/dev/null
done
[ -x "$runtime" ] || { echo "runtime helper is missing: $runtime" >&2; exit 1; }
[ -x "$repo/gen/wlan-client-pool.sh" ] || { echo "invalid repository: $repo" >&2; exit 1; }
# gen-util deliberately rejects lifecycle calls made from outside the source
# tree. systemd services start in /, so establish the accepted repository as
# the campaign working directory before invoking any provisioning helper.
cd "$repo"

exec {campaign_lock}>/run/easymesh-scale-soak.lock
flock -n "$campaign_lock" || {
    echo "another EasyMesh scale campaign is active" >&2
    exit 75
}

stamp=$(date -u +%Y%m%dT%H%M%SZ)
campaign="$output_root/$stamp"
install -d -o easymesh -g easymesh "$campaign"
events="$campaign/events.jsonl"

record() {
    local event=$1
    shift
    jq -cn --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg event "$event" --arg detail "$*" \
        '{at:$at,event:$event,detail:$detail}' | tee -a "$events"
}

stop_lab() {
    systemctl stop easymesh-lab.service 2>/dev/null || true
    "$runtime" stop
}

resize_hwsim() {
    local radios=$1 loaded
    loaded=$(cat /sys/module/mac80211_hwsim/parameters/radios 2>/dev/null || true)
    if [ "$loaded" = "$radios" ]; then
        record hwsim_reuse "radios=$radios"
        return
    fi

    record hwsim_resize_begin "from=${loaded:-unloaded} to=$radios"
    # runtime stop returns every wiphy and removes all dynamic VAPs before the
    # module is replaced. No node identity or LXD profile is regenerated.
    modprobe -r mac80211_hwsim || return
    printf 'options mac80211_hwsim radios=%s channels=3 regtest=5\n' "$radios" \
        > /etc/modprobe.d/easymesh-hwsim.conf || return
    modprobe mac80211_hwsim || return
    systemctl reset-failed easymesh-hwsim-pool.service 2>/dev/null || true
    /usr/local/sbin/easymesh-hwsim-pool || return
    test "$(cat /sys/module/mac80211_hwsim/parameters/radios)" = "$radios" \
        || return
    test "$(find /sys/class/net -mindepth 1 -maxdepth 1 -name 'virt-wlan*' | wc -l)" \
        -eq "$radios" || return
    record hwsim_resize_complete "radios=$radios"
}

prepare_profile() {
    local profile=$1 expected=$2 radios=$3 current
    stop_lab || return
    resize_hwsim "$radios" || return

    # First reconstruct the currently provisioned roster. The pool helper can
    # then add only the missing clients while the APs are available, register
    # one complete medium matrix, and retain every established identity.
    "$runtime" start || return
    "$repo/gen/wlan-client-pool.sh" up --profile "$profile" || return
    current=$(lxc list -c n --format csv \
        | grep -Ec '^wlan-client(-[0-9]{3})?$' || true)
    [ "$current" -eq "$expected" ] || {
        echo "profile $profile provisioned $current clients; expected $expected" >&2
        return 1
    }

    # A clean stop/start proves the complete profile is reconstructible and
    # establishes fresh zero-restart baselines for the soak.
    "$runtime" stop || return
    "$runtime" start || return
    HEALTH_EXPECT_CLIENTS="$expected" "$repo/gen/tests/health-audit.sh" \
        > "$campaign/$profile-health.log" 2>&1 || return
    record profile_ready "profile=$profile clients=$expected radios=$radios"
}

campaign_result=running
cleanup() {
    status=$?
    chown -R easymesh:easymesh "$campaign" 2>/dev/null || true
    if [ "$campaign_result" = running ]; then
        record campaign_stopped "status=$status result=$campaign_result"
    fi
}
trap cleanup EXIT

source_commit=$(git -c safe.directory="$repo" -C "$repo" rev-parse HEAD \
    2>/dev/null || printf 'unknown')
record campaign_start \
    "profiles=${profiles[*]} seconds_per_profile=$duration source=$source_commit"

failed_profiles=()
for profile in "${profiles[@]}"; do
    expected=$(profile_clients "$profile")
    radios=$(profile_radios "$profile")
    record profile_start "profile=$profile clients=$expected radios=$radios"
    if prepare_profile "$profile" "$expected" "$radios"; then
        :
    else
        status=$?
        failed_profiles+=("$profile")
        record profile_fail \
            "profile=$profile phase=prepare status=$status"
        continue
    fi

    profile_root="$campaign/$profile"
    install -d -o easymesh -g easymesh "$profile_root"
    status=0
    python3 "$repo/gen/tests/p0-churn-soak.py" \
            --duration "$duration" \
            --sample-interval "$sample_interval" \
            --settle "$settle" \
            --expected-clients "$expected" \
            --max-cli-rss-mib "$(profile_cli_limit "$profile")" \
            --output-root "$profile_root" \
            > "$profile_root/campaign.log" 2>&1 || status=$?
    summary=$(find "$profile_root" -mindepth 2 -maxdepth 2 -name summary.json \
        -type f | sort | tail -1)
    if [ "$status" -eq 0 ] && [ -n "$summary" ] \
            && jq -e '.outcome == "passed"' "$summary" >/dev/null; then
        record profile_pass "profile=$profile summary=$summary"
    else
        failed_profiles+=("$profile")
        record profile_fail \
            "profile=$profile phase=soak status=$status summary=${summary:-missing}"
    fi
done

if [ "${#failed_profiles[@]}" -ne 0 ]; then
    campaign_result=failed
    record campaign_fail "profiles=${failed_profiles[*]}"
    printf '%s\n' "$campaign"
    exit 1
fi

campaign_result=passed
record campaign_pass "profiles=${profiles[*]}"
printf '%s\n' "$campaign"
