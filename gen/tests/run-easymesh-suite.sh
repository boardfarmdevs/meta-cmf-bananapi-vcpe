#!/usr/bin/env bash
set -uo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
sections=()
yes_act=false
install_browser=false
soak_duration=43200
expected_clients=auto
output_root=

usage() {
    cat <<'EOF'
usage: gen/tests/run-easymesh-suite.sh [all|static|webui|browser|live|rooms|rf|soak] [options]

Run one or more EasyMesh qualification sections. `all` runs every section,
including the duration-bound soak, and requires --yes-act.
The rf section runs focused RF contracts and two bounded new-room checks.

Options:
  --yes-act                 Permit tests that change room RF or associations.
  --soak-duration SECONDS   P0 churn-soak duration; default: 43200 (12 hours).
  --expected-clients COUNT  Provisioned lab client profile; default: auto-detect.
  --output DIRECTORY        Store logs and scorecard here.
  --install-browser-deps    Install Playwright and Chromium below .cache/.
  -h, --help                Show this help.

Environment:
  EASYMESH_LXD_NAME         Running appliance name; default: easymesh.
  EASYMESH_HOST_ADDRESS     Host address for VM proxy checks; default: 127.0.0.1.
  EASYMESH_SSH_HOST         SSH host used by room browser tests; default: localhost.
  EASYMESH_EXPECTED_CLIENTS Override the auto-detected lab client profile.
  WEBUI_STATIC_DIR          Built unified-wifi-mesh static directory.
  PUBLIC_VIEWER_URL         Published static viewer base URL for its browser test.
  NODE_PATH, PLAYWRIGHT_MODULE, CHROMIUM_PATH
                            Existing browser-tool installation, if not using
                            --install-browser-deps.
EOF
}

while (($#)); do
    case "$1" in
        all|static|webui|browser|live|rooms|rf|soak) sections+=("$1") ;;
        --yes-act) yes_act=true ;;
        --install-browser-deps) install_browser=true ;;
        --soak-duration) shift; soak_duration=${1:-} ;;
        --expected-clients) shift; expected_clients=${1:-} ;;
        --output) shift; output_root=${1:-} ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option or section: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if ((${#sections[@]} == 0)); then sections=(all); fi
if [[ " ${sections[*]} " == *' all '* ]]; then sections=(static webui browser live rooms soak); fi
[[ "$soak_duration" =~ ^[1-9][0-9]*$ ]] || { echo '--soak-duration must be a positive integer' >&2; exit 2; }
expected_clients=${EASYMESH_EXPECTED_CLIENTS:-$expected_clients}
[[ "$expected_clients" == auto || "$expected_clients" =~ ^[1-9][0-9]*$ ]] || {
    echo '--expected-clients must be a positive integer or auto' >&2
    exit 2
}
if [[ " ${sections[*]} " == *' live '* || " ${sections[*]} " == *' rooms '* || " ${sections[*]} " == *' rf '* || " ${sections[*]} " == *' soak '* ]] && ! "$yes_act"; then
    echo 'live, rooms, rf and soak change the live lab; rerun with --yes-act' >&2
    exit 2
fi

lab_name=${EASYMESH_LXD_NAME:-${EASYMESH_LAB_NAME:-easymesh}}
source "$root/doc/easymesh/build/scripts/lab-config.sh" "$lab_name"
vm=$EASYMESH_LXD_NAME
host_address=${EASYMESH_HOST_ADDRESS:-127.0.0.1}
ssh_host=${EASYMESH_SSH_HOST:-localhost}
ssh_host_explicit=${EASYMESH_SSH_HOST:+true}
webui_url="http://$host_address:$EASYMESH_WEBUI_PORT"
room_url="http://$host_address:$EASYMESH_ROOM_DEMO_PORT"
guest_repo=${EASYMESH_GUEST_REPO:-/home/easymesh/git/meta-cmf-bananapi-vcpe}
room_service_was_active=false
room_service_stopped=false
room_service_guarded=false
full_profile_reset=false
stamp=$(date -u +%Y%m%dT%H%M%SZ)
output_root=${output_root:-"$root/test-results/$stamp-$vm"}
mkdir -p "$output_root/logs"
results=$output_root/results.tsv
printf 'section\ttest\tresult\tseconds\tlog\tcommand\n' > "$results"

passed=0
failed=0
skipped=0

record() {
    local section=$1 name=$2 outcome=$3 started=$4 log=$5 command=$6 elapsed
    elapsed=$(( $(date +%s) - started ))
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$section" "$name" "$outcome" "$elapsed" "$log" "$command" >> "$results"
    case "$outcome" in passed) ((passed += 1)) ;; failed) ((failed += 1)) ;; skipped) ((skipped += 1)) ;; esac
    printf '%-8s %-42s %s (%ss)\n' "[$outcome]" "$section/$name" "$outcome" "$elapsed"
}

run() {
    local section=$1 name=$2 command=$3 started log status
    started=$(date +%s)
    log=$output_root/logs/"$section-$name.log"
    printf '\n== %s / %s ==\n%s\n' "$section" "$name" "$command" | tee "$log"
    if bash -o pipefail -c "$command" 2>&1 | tee -a "$log"; then status=passed; else status=failed; fi
    record "$section" "$name" "$status" "$started" "$log" "$command"
    [[ $status == passed ]]
}

skip() {
    local section=$1 name=$2 reason=$3 started log
    started=$(date +%s)
    log=$output_root/logs/"$section-$name.log"
    printf 'SKIPPED: %s\n' "$reason" | tee "$log"
    record "$section" "$name" skipped "$started" "$log" "$reason"
}

have_command() { command -v "$1" >/dev/null 2>&1; }
have_modern_node() { have_command node && node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; }

webui_static_dir() {
    if [[ -n ${WEBUI_STATIC_DIR:-} && -f $WEBUI_STATIC_DIR/script.js ]]; then
        printf '%s\n' "$WEBUI_STATIC_DIR"
        return
    fi
    find "$root/.." -path '*/unified-wifi-mesh/*/src/rdkb-cli/static/script.js' -type f -print -quit 2>/dev/null |
        xargs -r dirname
}

prepare_browser() {
    local tools=$root/.cache/easymesh-browser-tools chromium
    if ! have_modern_node || ! have_command npm; then
        echo 'Browser tests require Node 22+ and npm on PATH.' >&2
        return 1
    fi
    if ! node -e "require.resolve('playwright-core')" >/dev/null 2>&1; then
        if ! "$install_browser"; then return 1; fi
        npm install --prefix "$tools" playwright
        export NODE_PATH="$tools/node_modules${NODE_PATH:+:$NODE_PATH}"
    fi
    export PLAYWRIGHT_MODULE=${PLAYWRIGHT_MODULE:-playwright-core}
    if [[ -z ${CHROMIUM_PATH:-} ]]; then
        chromium=$(node -e "const {chromium}=require('playwright-core'); process.stdout.write(chromium.executablePath())")
        if [[ ! -x $chromium ]]; then
            if ! "$install_browser"; then return 1; fi
            npx --prefix "$tools" playwright install chromium
            chromium=$(node -e "const {chromium}=require('playwright-core'); process.stdout.write(chromium.executablePath())")
        fi
        export CHROMIUM_PATH=$chromium
    fi
    [[ -x $CHROMIUM_PATH ]]
}

webui_browser_fixture() {
    local static=$1 fixture="$output_root/webui-browser-fixture"
    local vendor="$root/recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/web-vendor.tar.gz"
    [ -f "$vendor" ] || return 1
    rm -rf "$fixture"
    mkdir -p "$fixture"
    cp -a "$static/." "$fixture/"
    tar -xzf "$vendor" -C "$fixture"
    [ -f "$fixture/vendor/d3-7.9.0.min.js" ] || return 1
    printf '%s\n' "$fixture"
}

guest_command() {
    local command=$1
    printf 'lxc exec %q -- env EASYMESH_REPO=%q bash -lc %q' "$vm" "$guest_repo" "cd '$guest_repo' && $command"
}

prepare_lab() {
    have_command lxc || return 1
    lxc info "$vm" >/dev/null 2>&1 || return 1
    lxc exec "$vm" -- test -d "$guest_repo" >/dev/null 2>&1
}

select_room_ssh_host() {
    local fallback
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" true >/dev/null 2>&1; then return 0; fi
    [ -z "$ssh_host_explicit" ] || return 1
    fallback=$(hostname -s)
    [ "$fallback" != "$ssh_host" ] || return 1
    ssh -o BatchMode=yes -o ConnectTimeout=5 "$fallback" true >/dev/null 2>&1 || return 1
    ssh_host=$fallback
    printf 'Using local SSH host %s for room acceptance.\n' "$ssh_host"
}

restore_room_service() {
    if ! "$room_service_stopped" && ! "$room_service_guarded"; then return 0; fi
    if "$room_service_guarded"; then
        lxc exec "$vm" -- bash -s -- release < "$root/gen/tests/lib/suite-room-guard.sh" || return
        room_service_guarded=false
    fi
    if "$room_service_was_active"; then
        printf 'Restoring easymesh-room-demo.service.\n'
        lxc exec "$vm" -- systemctl reset-failed easymesh-room-demo.service || return
        lxc exec "$vm" -- systemctl start easymesh-room-demo.service || return
    fi
    room_service_stopped=false
}

trap 'status=$?; trap - EXIT; restore_room_service || status=1; exit "$status"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_for_live_clients() {
    local expected=$1 actual attempt
    for attempt in $(seq 1 60); do
        actual=$(lxc exec "$vm" -- bash -lc "curl -fsS http://127.0.0.1:8888/api/v1/clients | jq 'if type == \"array\" then length else (.clients // [] | length) end'" 2>/dev/null || true)
        printf 'Waiting for %s live clients: %s/60 observed=%s\n' "$expected" "$attempt" "${actual:-unavailable}"
        [[ $actual == "$expected" ]] && return 0
        sleep 2
    done
    return 1
}

archive_rebuilt_room_recovery() {
    local expected=$1
    lxc exec "$vm" -- env HEALTH_EXPECT_CLIENTS="$expected" bash -lc '
        set -euo pipefail
        /usr/local/sbin/easymesh-labctl check
        recovery=/run/easymesh-room-demo/recovery.json
        [ -e "$recovery" ] || exit 0
        archive=/home/easymesh/easymesh-evidence/recovery-archives
        stamp=$(date -u +%Y%m%dT%H%M%SZ)
        mkdir -p "$archive"
        target="$archive/$stamp-$(sha256sum "$recovery" | awk "{print substr(\$1, 1, 12)}").json"
        cp -p -- "$recovery" "$target"
        {
            printf "replaced_by_clean_lab_reconstruction=true\\n"
            printf "archived_at=%s\\n" "$stamp"
            printf "expected_clients=%s\\n" "$HEALTH_EXPECT_CLIENTS"
            printf "source=%s\\n" "$recovery"
            printf "archive=%s\\n" "$target"
            sha256sum "$target"
        } > "$target.receipt"
        rm -f -- "$recovery"
        printf "Archived stale room recovery record: %s\\n" "$target"
    '
}

prepare_full_client_profile() {
    local expected=$1 state
    [[ $expected == 100 ]] || return 0
    if ! "$room_service_stopped"; then
        state=$(lxc exec "$vm" -- systemctl show easymesh-room-demo.service -p ActiveState --value)
        room_service_was_active=false
        if [[ $state == active || $state == activating || $state == failed ]]; then
            room_service_was_active=true
        fi
        printf 'Isolating the shared 100-client profile from easymesh-room-demo.service.\n'
        lxc exec "$vm" -- bash -s -- acquire < "$root/gen/tests/lib/suite-room-guard.sh" || return
        room_service_guarded=true
        lxc exec "$vm" -- systemctl stop easymesh-room-demo.service || return
        room_service_stopped=true
    fi
    if ! "$full_profile_reset"; then
        printf 'Reconstructing the clean 100-client lab state for live qualification.\n'
        lxc exec "$vm" -- systemctl restart easymesh-lab.service || return
        full_profile_reset=true
    fi
    wait_for_live_clients "$expected" || return
    archive_rebuilt_room_recovery "$expected"
}

qualify_client_profile() {
    local section=$1 expected=$2 started log outcome
    started=$(date +%s)
    log=$output_root/logs/"$section-client-profile.log"
    if prepare_full_client_profile "$expected" > "$log" 2>&1; then outcome=passed; else outcome=failed; fi
    cat "$log"
    record "$section" client-profile "$outcome" "$started" "$log" "establish $expected clients with exclusive room guard"
    [[ $outcome == passed ]]
}

lab_client_count() {
    if [[ $expected_clients != auto ]]; then
        printf '%s\n' "$expected_clients"
        return
    fi
    lxc exec "$vm" -- lxc list -c n --format csv | awk '
        $0 == "wlan-client" || $0 ~ /^wlan-client-[0-9]{3}$/ { count++ }
        END { if (count > 0) print count; else exit 1 }
    '
}

run_static() {
    local test
    if have_command python3 && have_command pytest; then
        run static documentation "cd '$root' && python3 gen/tests/test_documentation.py"
        run static python "cd '$root' && PYTHONPATH='$root/gen/wmediumd/configurator:$root/gen/optimizer:$root/gen/demo:$root/gen/demo/tests:$root/gen/tests' python3 -m pytest --import-mode=importlib gen/wmediumd/configurator/tests gen/optimizer/tests gen/demo/tests gen/tests"
    else
        skip static python 'install python3 and pytest for Python and documentation tests'
    fi
    if have_modern_node; then
        run static console-ng-model "cd '$root' && node --test gen/wmediumd/observer/web/ng/model.test.mjs"
        for test in "$root"/gen/tests/viewer-*-test.js "$root"/gen/tests/test-*.js "$root"/gen/tests/fullscreen-control-test.js "$root"/gen/tests/signal-meter-test.js; do
            case $(basename "$test") in
                *browser-test.js|viewer-sidebar-layout-test.js) continue ;;
            esac
            run static "$(basename "${test%.js}")" "cd '$root' && node '$test'"
        done
    else
        skip static node-units 'Node 22+ is required on PATH'
    fi
}

run_webui() {
    local static
    have_modern_node || { skip webui node 'Node 22+ is required on PATH'; return; }
    static=$(webui_static_dir)
    [[ -n $static && -f $static/script.js && -f $static/room-topology.js && -f $static/steering-cues.js ]] || {
        skip webui artifact 'set WEBUI_STATIC_DIR to the built unified-wifi-mesh static directory'; return;
    }
    for test in webui-extender-signal-test.js webui-independent-refresh-test.js webui-mesh-device-signal-test.js webui-metrics-reporting-test.js webui-topology-fit-test.js webui-topology-label-test.js webui-topology-layout-test.js webui-room-follow-test.js; do
        run webui "${test%.js}" "cd '$root' && node gen/tests/$test '$static/script.js'"
    done
    run webui rf-hover "cd '$root' && node gen/tests/webui-rf-hover-test.js '$static/room-topology.js'"
    run webui steering-cues "cd '$root' && node gen/tests/steering-cues-test.js '$static/steering-cues.js'"
}

run_browser() {
    local static fixture d3
    prepare_browser || { skip browser prerequisites 'install node/npm and Playwright/Chromium, or rerun with --install-browser-deps'; return; }
    for test in pane-divider-browser-test.js viewer-room-convergence-browser-test.js viewer-room-guide-browser-test.js viewer-sidebar-layout-test.js viewer-steering-resume-browser-test.js wmediumd-console-ng-browser-test.js; do
        run browser "${test%.js}" "cd '$root' && node gen/tests/$test"
    done
    static=$(webui_static_dir)
    if [[ -n $static && -f $static/steering-cues.js ]]; then
        fixture=$(webui_browser_fixture "$static") || {
            skip browser webui-fixtures 'the packaged WebUI vendor assets are unavailable'
            return
        }
        d3=$(find "$fixture" -name 'd3-*.min.js' -type f -print -quit)
        if [[ -n $d3 ]]; then run browser steering-cues "cd '$root' && node gen/tests/steering-cues-browser-test.js '$fixture/steering-cues.js' '$d3'"; else skip browser steering-cues 'the WebUI fixture has no D3 asset'; fi
        run browser room-follow "cd '$root' && node gen/tests/webui-room-follow-browser-test.js '$fixture'"
    else
        skip browser webui-fixtures 'set WEBUI_STATIC_DIR to run WebUI browser fixtures'
    fi
    if [[ -n ${PUBLIC_VIEWER_URL:-} ]]; then
        run browser public-viewer "cd '$root' && node gen/tests/viewer-public-site-browser-test.js '$PUBLIC_VIEWER_URL'"
    else
        skip browser public-viewer 'set PUBLIC_VIEWER_URL to the published viewer base URL'
    fi
}

run_live() {
    local clients optimizer_policy
    prepare_lab || { skip live prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    clients=$(lab_client_count) || { skip live client-profile 'set --expected-clients to the provisioned client count'; return; }
    printf 'Using %s-client lab profile for live checks.\n' "$clients"
    qualify_client_profile live "$clients" || {
        skip live dependents "failed to establish $clients live clients; see client-profile log"
        return
    }
    run live vm-check "cd '$root' && EASYMESH_LXD_NAME='$vm' EASYMESH_WEBUI_PORT='$EASYMESH_WEBUI_PORT' WMEDIUMD_CONSOLE_PORT='$WMEDIUMD_CONSOLE_PORT' EASYMESH_ROOM_DEMO_PORT='$EASYMESH_ROOM_DEMO_PORT' gen/vm/lxd/build.sh check" || {
        skip live dependents 'VM provenance/baseline check failed; do not qualify a different or unhealthy deployment'
        return
    }
    run live health "$(guest_command "HEALTH_EXPECT_CLIENTS='$clients' bash gen/tests/health-audit.sh")"
    run live hwsim-profiles "$(guest_command 'bash gen/tests/verify-hwsim-profile-uniqueness.sh')"
    optimizer_policy='/tmp/easymesh-optimizer-live-policy.yaml'
    run live optimizer "$(guest_command "sed 's/^expected_clients: .*/expected_clients: $clients/' gen/optimizer/configs/threshold-policy.yaml > '$optimizer_policy' && python3 gen/tests/optimizer-live-smoke.py --cycles 5 --interval 1 --policy '$optimizer_policy'; status=\$?; rm -f '$optimizer_policy'; exit \$status")"
    run live candidate-rcpi "$(guest_command 'python3 gen/tests/candidate-rcpi-test.py')"
    run live medium-idle "$(guest_command "python3 gen/tests/wmediumd-performance.py --mode idle --duration 30 --output '$guest_repo/test-results-wmediumd-idle.json'")"
    run live medium-ping "$(guest_command "python3 gen/tests/wmediumd-performance.py --mode ping --duration 30 --output '$guest_repo/test-results-wmediumd-ping.json'")"
    run live steering-matrix "$(guest_command 'bash gen/tests/steering-matrix.sh 1 --ssid private_ssid && bash gen/tests/steering-matrix.sh 1 --ssid iot_ssid')"
}

run_rooms() {
    local worlds=$root/gen/wmediumd/configurator/worlds/golden
    prepare_lab || { skip rooms prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    prepare_browser || { skip rooms browser 'install Playwright/Chromium before running room acceptance'; return; }
    if ! select_room_ssh_host; then
        skip rooms ssh "SSH host $ssh_host must execute 'lxc exec $vm' without a password"
        return
    fi
    run rooms guest-audit "lxc exec --mode non-interactive '$vm' -- install -m 0644 /dev/stdin /tmp/room-feature-guest-audit.py < '$root/gen/tests/room-feature-guest-audit.py'" || {
        skip rooms dependents 'Could not install the native guest audit; room qualification cannot proceed'
        return
    }
    run rooms default-readiness "cd '$root' && python3 gen/tests/room-final-readiness.py --room-url '$room_url' --require-absolute-best --output '$output_root/default-readiness'"
    run rooms catalog "cd '$root' && node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk --host '$ssh_host' --vm '$vm' --room-url '$room_url' --topology-url '$webui_url' --worlds '$worlds' --output '$output_root/catalog'"
    run rooms geometry "cd '$root' && node gen/tests/room-backhaul-features.js --yes-act true --flavor rdk --host '$ssh_host' --vm '$vm' --room-url '$room_url' --topology-url '$webui_url' --output '$output_root/geometry'"
    run rooms rf-hover "cd '$root' && node gen/tests/webui-rf-hover-browser-test.js '$webui_url' '$output_root/rf-hover'"
    run rooms rf-access "cd '$root' && python3 gen/tests/rf-access-smoke.py --room-url '$room_url' --output '$output_root/rf-access.json'"
    run rooms rf-properties "cd '$root' && python3 gen/tests/rf-property-rooms-smoke.py --yes-act --room-url '$room_url' --host '$ssh_host' --vm '$vm' --output '$output_root/rf-properties.json'"
    run rooms world-switch "$(guest_command "python3 gen/tests/room-world-switch-smoke.py --yes-act --all-worlds --output '$guest_repo/test-results-world-switch-$stamp'")"
    run rooms restore-default "$(guest_command 'python3 gen/tests/room-world-switch-smoke.py --yes-act --world home-a-private-client-room-walk --skip-presence --output /tmp/easymesh-default-restore')"
}

run_rf() {
    run rf contracts "cd '$root' && PYTHONPATH='$root/gen/wmediumd/configurator:$root/gen/optimizer:$root/gen/demo:$root/gen/demo/tests:$root/gen/tests' python3 -m pytest --import-mode=importlib -o addopts='' -q gen/optimizer/tests/test_counter_guard.py gen/optimizer/tests/test_counter_shadow.py gen/tests/test_native_retry_counters.py gen/optimizer/tests/test_load_policy.py gen/optimizer/tests/test_policy.py gen/optimizer/tests/test_owner_observation.py gen/optimizer/tests/test_rf_observations.py gen/demo/tests/test_rf_property_coverage.py gen/demo/tests/test_rf_rooms.py gen/demo/tests/test_world_switch.py gen/demo/tests/test_traffic_experiment.py gen/demo/tests/test_rf_observation.py gen/tests/test_rf_property_rooms_smoke.py gen/tests/test_counter_guard_room_smoke.py gen/tests/test_frequency_slot_allocation.py gen/tests/test_console_ng_contract.py gen/wmediumd/configurator/tests/test_rf_contract.py" || return
    run rf viewer "cd '$root' && node gen/tests/viewer-room-guide-test.js" || return
    run rf inspector "cd '$root' && node gen/tests/viewer-rf-inspector-test.js" || return
    run rf documentation "cd '$root' && python3 gen/tests/test_documentation.py" || return
    run rf rooms "cd '$root' && python3 gen/tests/rf-property-rooms-smoke.py --yes-act --room-url '$room_url' --host '$ssh_host' --vm '$vm' --output '$output_root/rf-properties.json'" || return
    run rf counter-manifest "ssh '$ssh_host' lxc exec '$vm' -- python3 '$guest_repo/gen/tests/counter-guard-room-smoke.py' --stack rdk --yes-change-lab --output '/tmp/rf-counter-manifest-$stamp'" || return
    run rf counter-shadow "ssh '$ssh_host' lxc exec '$vm' -- env PYTHONPATH='$guest_repo/gen/optimizer:$guest_repo/gen/wmediumd/configurator' python3 '$guest_repo/gen/tests/native-retry-counter-acceptance.py' --stack rdk --yes-change-lab --seconds 8 --shadow-counter-policy '$guest_repo/gen/optimizer/configs/load-counter-guard-policy.yaml' --output '/tmp/rf-counter-shadow-$stamp'"
}

run_soak() {
    local clients
    prepare_lab || { skip soak prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    clients=$(lab_client_count) || { skip soak client-profile 'set --expected-clients to the provisioned client count'; return; }
    printf 'Using %s-client lab profile for P0 churn soak.\n' "$clients"
    qualify_client_profile soak "$clients" || {
        skip soak dependents "failed to establish $clients live clients; see client-profile log"
        return
    }
    run soak p0-churn "$(guest_command "python3 gen/tests/p0-churn-soak.py --duration '$soak_duration' --expected-clients '$clients' --output-root '$guest_repo/test-results-p0-soak-$stamp'")"
}

for section_group in 'static webui browser rooms rf' 'live soak'; do
    for section in "${sections[@]}"; do
        [[ " $section_group " == *" $section "* ]] || continue
        printf '\n===== EasyMesh %s section =====\n' "$section"
        case "$section" in
            static) run_static ;;
            webui) run_webui ;;
            browser) run_browser ;;
            live) run_live ;;
            rooms) run_rooms ;;
            rf) run_rf ;;
            soak) run_soak ;;
        esac
    done
done

if "$room_service_stopped" || "$room_service_guarded"; then
    cleanup_started=$(date +%s)
    if restore_room_service > "$output_root/logs/cleanup-room-service.log" 2>&1; then
        cleanup_result=passed
    else
        cleanup_result=failed
    fi
    cat "$output_root/logs/cleanup-room-service.log"
    record cleanup room-service "$cleanup_result" "$cleanup_started" "$output_root/logs/cleanup-room-service.log" 'restore prior room service state'
fi

python3 - "$results" "$output_root/summary.json" "$passed" "$failed" "$skipped" <<'PY'
import json
import pathlib
import sys

rows = []
for line in pathlib.Path(sys.argv[1]).read_text().splitlines()[1:]:
    section, name, outcome, seconds, log, command = line.split('\t', 5)
    rows.append({'section': section, 'test': name, 'outcome': outcome,
                 'seconds': int(seconds), 'log': log, 'command': command})
pathlib.Path(sys.argv[2]).write_text(json.dumps({'passed': int(sys.argv[3]), 'failed': int(sys.argv[4]),
    'skipped': int(sys.argv[5]), 'tests': rows}, indent=2) + '\n')
PY

printf '\n===== EasyMesh suite summary =====\n'
printf 'passed: %d  failed: %d  skipped: %d\n' "$passed" "$failed" "$skipped"
printf 'results: %s\nsummary: %s\n' "$results" "$output_root/summary.json"
((failed == 0))
