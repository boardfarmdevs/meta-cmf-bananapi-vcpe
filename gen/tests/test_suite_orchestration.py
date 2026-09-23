from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SUITE = (ROOT / "gen/tests/run-easymesh-suite.sh").read_text()


def function(name):
    return re.search(rf"^{name}\(\) \{{.*?^\}}", SUITE, re.MULTILINE | re.DOTALL).group() + "\n"


def test_native_matrix_is_not_run_under_live_room_ownership():
    assert "steering-matrix.sh" not in function("run_rooms")
    assert "steering-matrix.sh" in function("run_live")
    assert function("run_live").index("qualify_client_profile") < function("run_live").index("steering-matrix.sh")
    assert function("run_rooms").index("guest-audit") < function("run_rooms").index("run rooms catalog")


def test_shared_profile_guard_is_acquired_only_once_and_not_released_between_steps():
    script = '''
room_service_was_active=false
room_service_stopped=false
room_service_guarded=false
full_profile_reset=false
vm=fixture
root=$1
lxc() { printf '%s\\n' "$*" >> "$CALLS"; if [[ "$*" == *ActiveState* ]]; then echo active; fi; }
wait_for_live_clients() { return 0; }
archive_rebuilt_room_recovery() { return 0; }
''' + function("prepare_full_client_profile") + function("restore_room_service") + '''
prepare_full_client_profile 100 || exit 1
prepare_full_client_profile 100 || exit 1
test "$(grep -c 'acquire' "$CALLS")" = 1 || exit 2
test "$(grep -c 'restart easymesh-lab.service' "$CALLS")" = 1 || exit 3
! grep -q 'start easymesh-room-demo.service' "$CALLS" || exit 4
restore_room_service || exit 5
test "$(grep -c 'release' "$CALLS")" = 1 || exit 6
'''
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["bash", "-c", script, "test", str(ROOT)], check=True,
                       env={**os.environ, "CALLS": directory + "/calls"}, capture_output=True)


def test_failed_dependency_and_cleanup_are_not_reported_as_passes():
    assert '[[ $status == passed ]]' in function("run")
    assert "skip live dependents" in function("run_live")
    assert 'else outcome=failed' in function("qualify_client_profile")
    assert 'record cleanup room-service' in SUITE
    guard = (ROOT / "gen/tests/lib/suite-room-guard.sh").read_text()
    assert "ConditionPathExists=!%s" in guard
    assert "systemctl mask" not in function("prepare_full_client_profile")


def test_live_section_requires_explicit_mutation_consent():
    for section in ("live", "rf-actions"):
        result = subprocess.run(["bash", str(ROOT / "gen/tests/run-easymesh-suite.sh"), section],
                                capture_output=True, text=True)
        assert result.returncode == 2 and "--yes-act" in result.stderr


def test_rf_actions_stop_on_failure_and_precede_shared_full_pool_guard():
    source = function("run_rf_actions")
    assert "for scenario in clear pressure rescue" in source
    assert "--counter-case" in source and "load-counter-guard-policy.yaml" in source
    assert "--payload-bytes 1400" in source
    assert "--yes-change-lab" in source and "|| return" in source
    assert "qualify_client_profile" not in source
    assert "'static webui browser rooms rf rf-actions' 'live soak'" in SUITE


def test_native_audit_replaces_old_operator_owned_tmp_file():
    expected = "install -m 0644 /dev/stdin /tmp/room-feature-guest-audit.py"
    for name in ("room-backhaul-features.js", "room-feature-acceptance.js", "run-easymesh-suite.sh"):
        source = (ROOT / "gen/tests" / name).read_text()
        assert expected in source
        assert "--mode non-interactive" in source
        assert not re.search(r"lxc file push[^\n]+room-feature-guest-audit", source)


def test_generated_test_output_does_not_dirty_source_checkout():
    for path in ("test-results/fixture/results.tsv", ".cache/easymesh-browser-tools/package-lock.json"):
        subprocess.run(["git", "check-ignore", "--no-index", "--quiet", path], cwd=ROOT, check=True)


def test_room_and_rf_tiers_preserve_independent_evidence():
    assert "'$output_root/rf-properties.json'" in function("run_rooms")
    assert "'$output_root/rf-tier-properties.json'" in function("run_rf")


def test_both_steering_cohorts_run_after_a_private_failure():
    script = '''
root=/fixture
vm=fixture
guest_repo=/guest
stamp=run
EASYMESH_WEBUI_PORT=1
WMEDIUMD_CONSOLE_PORT=2
EASYMESH_ROOM_DEMO_PORT=3
prepare_lab() { return 0; }
lab_client_count() { echo 100; }
qualify_client_profile() { return 0; }
guest_command() { printf '%s' "$1"; }
run() { printf '%s\\n' "$*"; [[ "$2" != steering-private ]]; }
skip() { return 1; }
''' + function("run_live") + '\nrun_live\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "live steering-private" in result.stdout
    assert "live steering-iot" in result.stdout
    assert "/guest/test-results/run/steering-private.csv" in result.stdout
    assert "/guest/test-results/run/steering-iot.csv" in result.stdout
