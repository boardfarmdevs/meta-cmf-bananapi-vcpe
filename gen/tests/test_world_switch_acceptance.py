import importlib.util
from pathlib import Path
from unittest.mock import Mock


SCRIPT = Path(__file__).with_name("room-world-switch-smoke.py")
SPEC = importlib.util.spec_from_file_location("world_switch_acceptance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def current_snapshot(gain=0):
    return {
        "network": {"clients": [{"sta_mac": "client", "connected_bssid": "source"}]},
        "optimizer": {
            "fleet": {"converged": True, "absolute_best_converged": gain <= 0},
            "client_decisions": [{"sta_mac": "client", "source_bssid": "source",
                                  "current_rcpi": 100, "current_band": "5",
                                  "scores": [{"band": "5", "gain_rcpi": gain}]}],
        },
    }


def test_policy_margin_is_reported_separately_from_absolute_best():
    assert MODULE.client_convergence(current_snapshot(2), 1) == (True, False)
    assert MODULE.client_convergence(current_snapshot(), 1) == (True, True)


def test_missing_clients_and_stale_owners_do_not_converge():
    current = current_snapshot()
    assert MODULE.client_convergence(current, 2) == (False, False)
    current["optimizer"]["client_decisions"][0]["source_bssid"] = "old-owner"
    assert MODULE.client_convergence(current, 1) == (False, False)


def test_policy_failure_remains_a_failure():
    current = current_snapshot(20)
    current["optimizer"]["fleet"]["converged"] = False
    assert MODULE.client_convergence(current, 1) == (False, False)


def test_release_uses_only_owned_token():
    request = Mock()
    MODULE.release_control(request, "owned-token")
    request.assert_called_once_with("/api/demo/interactions/lease", {"token": "owned-token"}, method="DELETE")


def test_lease_release_is_in_unconditional_cleanup():
    source = SCRIPT.read_text()
    assert 'finally:\n            if lease is not None:' in source
    assert source.index('release_control(request, lease)') > source.index('report["restore_error"]')
    assert source.index('if report.get("lease_release_error")') > source.rindex('args.output.write_text')
