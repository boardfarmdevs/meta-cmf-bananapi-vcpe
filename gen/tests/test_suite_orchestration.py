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
    result = subprocess.run(["bash", str(ROOT / "gen/tests/run-easymesh-suite.sh"), "live"],
                            capture_output=True, text=True)
    assert result.returncode == 2 and "--yes-act" in result.stderr


def test_native_audit_replaces_old_operator_owned_tmp_file():
    expected = "install -m 0644 /dev/stdin /tmp/room-feature-guest-audit.py"
    for name in ("room-backhaul-features.js", "room-feature-acceptance.js", "run-easymesh-suite.sh"):
        source = (ROOT / "gen/tests" / name).read_text()
        assert expected in source
        assert "--mode non-interactive" in source
        assert not re.search(r"lxc file push[^\n]+room-feature-guest-audit", source)
