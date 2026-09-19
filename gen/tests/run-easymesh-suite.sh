#!/usr/bin/env bash
set -uo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
sections=()
yes_act=false
install_browser=false
soak_duration=43200
output_root=

usage() {
    cat <<'EOF'
usage: gen/tests/run-easymesh-suite.sh [all|static|webui|browser|live|rooms|soak] [options]

Run one or more EasyMesh qualification sections. `all` runs every section,
including the duration-bound soak, and requires --yes-act.

Options:
  --yes-act                 Permit tests that change room RF or associations.
  --soak-duration SECONDS   P0 churn-soak duration; default: 43200 (12 hours).
  --output DIRECTORY        Store logs and scorecard here.
  --install-browser-deps    Install Playwright and Chromium below .cache/.
  -h, --help                Show this help.

Environment:
  EASYMESH_LXD_NAME         Running appliance name; default: easymesh.
  EASYMESH_HOST_ADDRESS     Host address for VM proxy checks; default: 127.0.0.1.
  EASYMESH_SSH_HOST         SSH host used by room browser tests; default: localhost.
  WEBUI_STATIC_DIR          Built unified-wifi-mesh static directory.
  PUBLIC_VIEWER_URL         Published static viewer base URL for its browser test.
  NODE_PATH, PLAYWRIGHT_MODULE, CHROMIUM_PATH
                            Existing browser-tool installation, if not using
                            --install-browser-deps.
EOF
}

while (($#)); do
    case "$1" in
        all|static|webui|browser|live|rooms|soak) sections+=("$1") ;;
        --yes-act) yes_act=true ;;
        --install-browser-deps) install_browser=true ;;
        --soak-duration) shift; soak_duration=${1:-} ;;
        --output) shift; output_root=${1:-} ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option or section: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if ((${#sections[@]} == 0)); then sections=(all); fi
if [[ " ${sections[*]} " == *' all '* ]]; then sections=(static webui browser live rooms soak); fi
[[ "$soak_duration" =~ ^[1-9][0-9]*$ ]] || { echo '--soak-duration must be a positive integer' >&2; exit 2; }
if [[ " ${sections[*]} " == *' rooms '* || " ${sections[*]} " == *' soak '* ]] && ! "$yes_act"; then
    echo 'rooms and soak change the live lab; rerun with --yes-act' >&2
    exit 2
fi

lab_name=${EASYMESH_LXD_NAME:-${EASYMESH_LAB_NAME:-easymesh}}
source "$root/doc/easymesh/build/scripts/lab-config.sh" "$lab_name"
vm=$EASYMESH_LXD_NAME
host_address=${EASYMESH_HOST_ADDRESS:-127.0.0.1}
ssh_host=${EASYMESH_SSH_HOST:-localhost}
webui_url="http://$host_address:$EASYMESH_WEBUI_PORT"
room_url="http://$host_address:$EASYMESH_ROOM_DEMO_PORT"
guest_repo=${EASYMESH_GUEST_REPO:-/home/easymesh/git/meta-cmf-bananapi-vcpe}
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
}

skip() {
    local section=$1 name=$2 reason=$3 started log
    started=$(date +%s)
    log=$output_root/logs/"$section-$name.log"
    printf 'SKIPPED: %s\n' "$reason" | tee "$log"
    record "$section" "$name" skipped "$started" "$log" "$reason"
}

have_command() { command -v "$1" >/dev/null 2>&1; }

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
    if ! have_command node || ! have_command npm; then return 1; fi
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

guest_command() {
    local command=$1
    printf 'lxc exec %q -- env EASYMESH_REPO=%q bash -lc %q' "$vm" "$guest_repo" "cd '$guest_repo' && $command"
}

prepare_lab() {
    have_command lxc || return 1
    lxc info "$vm" >/dev/null 2>&1 || return 1
    lxc exec "$vm" -- test -d "$guest_repo" >/dev/null 2>&1
}

run_static() {
    local test
    if have_command python3 && have_command pytest; then
        run static documentation "cd '$root' && python3 gen/tests/test_documentation.py"
        run static python "cd '$root' && PYTHONPATH='$root/gen/wmediumd/configurator:$root/gen/optimizer:$root/gen/demo:$root/gen/demo/tests:$root/gen/tests' python3 -m pytest --import-mode=importlib gen/wmediumd/configurator/tests gen/optimizer/tests gen/demo/tests gen/tests"
    else
        skip static python 'install python3 and pytest for Python and documentation tests'
    fi
    if have_command node; then
        for test in "$root"/gen/tests/viewer-*-test.js "$root"/gen/tests/test-*.js "$root"/gen/tests/fullscreen-control-test.js "$root"/gen/tests/signal-meter-test.js; do
            [[ $(basename "$test") == *browser-test.js ]] && continue
            run static "$(basename "${test%.js}")" "cd '$root' && node '$test'"
        done
    else
        skip static node-units 'node is not installed'
    fi
}

run_webui() {
    local static
    have_command node || { skip webui node 'node is not installed'; return; }
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
    local static d3
    prepare_browser || { skip browser prerequisites 'install node/npm and Playwright/Chromium, or rerun with --install-browser-deps'; return; }
    for test in pane-divider-browser-test.js viewer-room-convergence-browser-test.js viewer-room-guide-browser-test.js viewer-sidebar-layout-test.js viewer-steering-resume-browser-test.js; do
        run browser "${test%.js}" "cd '$root' && node gen/tests/$test"
    done
    static=$(webui_static_dir)
    if [[ -n $static && -f $static/steering-cues.js ]]; then
        d3=$(find "$static" -name d3.min.js -type f -print -quit)
        if [[ -n $d3 ]]; then run browser steering-cues "cd '$root' && node gen/tests/steering-cues-browser-test.js '$static/steering-cues.js' '$d3'"; else skip browser steering-cues 'd3.min.js is absent from WEBUI_STATIC_DIR'; fi
        run browser room-follow "cd '$root' && node gen/tests/webui-room-follow-browser-test.js '$static'"
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
    prepare_lab || { skip live prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    run live vm-check "cd '$root' && EASYMESH_LXD_NAME='$vm' EASYMESH_WEBUI_PORT='$EASYMESH_WEBUI_PORT' WMEDIUMD_CONSOLE_PORT='$WMEDIUMD_CONSOLE_PORT' EASYMESH_ROOM_DEMO_PORT='$EASYMESH_ROOM_DEMO_PORT' gen/vm/lxd/build.sh check"
    run live health "$(guest_command 'bash gen/tests/health-audit.sh')"
    run live hwsim-profiles "$(guest_command 'bash gen/tests/verify-hwsim-profile-uniqueness.sh')"
    run live optimizer "$(guest_command 'python3 gen/tests/optimizer-live-smoke.py --cycles 5 --interval 1')"
    run live candidate-rcpi "$(guest_command 'python3 gen/tests/candidate-rcpi-test.py')"
    run live medium-idle "$(guest_command "python3 gen/tests/wmediumd-performance.py --mode idle --duration 30 --output '$guest_repo/test-results-wmediumd-idle.json'")"
    run live medium-ping "$(guest_command "python3 gen/tests/wmediumd-performance.py --mode ping --duration 30 --output '$guest_repo/test-results-wmediumd-ping.json'")"
}

run_rooms() {
    local worlds=$root/gen/wmediumd/configurator/worlds/golden
    prepare_lab || { skip rooms prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    prepare_browser || { skip rooms browser 'install Playwright/Chromium before running room acceptance'; return; }
    if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" true >/dev/null 2>&1; then
        skip rooms ssh "SSH host $ssh_host must execute 'lxc exec $vm' without a password"
        return
    fi
    run rooms default-readiness "cd '$root' && python3 gen/tests/room-final-readiness.py --room-url '$room_url' --require-absolute-best --output '$output_root/default-readiness'"
    run rooms catalog "cd '$root' && node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk --host '$ssh_host' --vm '$vm' --room-url '$room_url' --topology-url '$webui_url' --worlds '$worlds' --output '$output_root/catalog'"
    run rooms geometry "cd '$root' && node gen/tests/room-backhaul-features.js --yes-act true --flavor rdk --host '$ssh_host' --vm '$vm' --room-url '$room_url' --topology-url '$webui_url' --output '$output_root/geometry'"
    run rooms rf-hover "cd '$root' && node gen/tests/webui-rf-hover-browser-test.js '$webui_url' '$output_root/rf-hover'"
    run rooms world-switch "$(guest_command "python3 gen/tests/room-world-switch-smoke.py --yes-act --all-worlds --output '$guest_repo/test-results-world-switch-$stamp'")"
    run rooms steering-matrix "$(guest_command 'bash gen/tests/steering-matrix.sh 1 --ssid private_ssid && bash gen/tests/steering-matrix.sh 1 --ssid iot_ssid')"
    run rooms restore-default "$(guest_command 'python3 gen/tests/room-world-switch-smoke.py --yes-act --world home-five-agent--private-client-room-walk --skip-presence --output /tmp/easymesh-default-restore')"
}

run_soak() {
    prepare_lab || { skip soak prerequisites "LXD VM $vm or guest repository $guest_repo is unavailable"; return; }
    run soak p0-churn "$(guest_command "python3 gen/tests/p0-churn-soak.py --duration '$soak_duration' --output-root '$guest_repo/test-results-p0-soak-$stamp'")"
}

for section in "${sections[@]}"; do
    printf '\n===== EasyMesh %s section =====\n' "$section"
    case "$section" in
        static) run_static ;;
        webui) run_webui ;;
        browser) run_browser ;;
        live) run_live ;;
        rooms) run_rooms ;;
        soak) run_soak ;;
    esac
done

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
