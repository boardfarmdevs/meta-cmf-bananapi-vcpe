"""room-settled.py: the default room settled, and the pods' known metric gap said, not waited for."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "room-settled.py"
SPEC = importlib.util.spec_from_file_location("room_settled", SCRIPT)
room = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(room)

SCENARIO = "home-five-agent-pods--private-client-room-walk"


def current(checked=20, *, decisions=(), healthy=True, **fleet):
    """The room service's /api/demo/current as the bring-up reads it (rdk-1010, 20 October)."""
    complete = checked == 20
    return {
        "scenario": SCENARIO,
        "health": {"healthy": healthy, "api_total": 20, "expected_online_clients": 20},
        "optimizer": {
            "client_decisions": [
                {"role": f"sta_static_{n:02d}", "sta_mac": f"02:00:00:00:{n:02x}:00",
                 "reason": "candidate_gain_too_small", "source_role": "extender_1"}
                for n in range(1, 21 - len(decisions))
            ] + list(decisions),
            "fleet": {
                "roster_complete": True, "clients_evaluated": 20, "clients_checked": checked,
                "measurement_complete": complete, "converged": complete,
                "clients_outside_policy_margin": 0, **fleet,
            },
        },
    }


def missing(role, on):
    return {"role": role, "sta_mac": "02:00:00:00:06:00", "reason": "current_metric_missing",
            "source_role": on, "current_rcpi": None}


ON_POD = missing("sta_static_04", "pod_2")


def test_a_converged_room_is_settled():
    assert room.verdict(current()) == (True, f"settled {SCENARIO} 20 20 True")


def test_a_client_on_a_pod_with_no_metric_is_the_known_gap_said_by_name():
    ok, line = room.verdict(current(19, decisions=[ON_POD]))
    assert ok
    assert line == f"settled {SCENARIO} 20 19 False with the pods' known metric gap: sta_static_04 on pod_2"


def test_the_same_reason_on_the_gateway_or_an_extender_still_waits():
    for on in ("gateway", "extender_3"):
        assert room.verdict(current(19, decisions=[missing("sta_static_04", on)])) == (
            False, f"waiting {SCENARIO} 20 19 False")


def test_a_pod_client_not_checked_for_another_reason_still_waits():
    other = dict(ON_POD, reason="candidate_measurement_missing")
    assert not room.verdict(current(19, decisions=[other]))[0]


def test_the_gap_does_not_cover_another_client_not_checked():
    assert not room.verdict(current(18, decisions=[ON_POD]))[0]


def test_the_gap_does_not_cover_a_client_outside_the_policy_margin():
    assert not room.verdict(current(19, decisions=[ON_POD], clients_outside_policy_margin=1))[0]


def test_the_gap_does_not_cover_another_clients_missing_load_measurement():
    unavailable = ["02:00:00:00:06:00", "02:00:00:00:03:00"]
    assert not room.verdict(current(19, decisions=[ON_POD], load_measurements_unavailable=unavailable))[0]
    assert room.verdict(current(19, decisions=[ON_POD], load_measurements_unavailable=unavailable[:1]))[0]


def test_the_gap_does_not_cover_an_unhealthy_lab_or_an_incomplete_roster():
    assert not room.verdict(current(19, decisions=[ON_POD], healthy=False))[0]
    assert not room.verdict(current(19, decisions=[ON_POD], roster_complete=False))[0]
    lacking = copy.deepcopy(current(19, decisions=[ON_POD]))
    lacking["health"]["expected_online_clients"] = 19
    assert not room.verdict(lacking)[0]


def run(stdin):
    return subprocess.run([sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True)


def test_the_script_answers_with_its_line_and_exit_status():
    settled = run(json.dumps(current(19, decisions=[ON_POD])))
    assert settled.returncode == 0 and "known metric gap" in settled.stdout
    waiting = run(json.dumps(current(19, decisions=[missing("sta_static_04", "gateway")])))
    assert waiting.returncode == 1 and waiting.stdout.startswith("waiting ")
    nothing = run("")
    assert nothing.returncode == 1 and nothing.stdout.strip() == "waiting no answer"
