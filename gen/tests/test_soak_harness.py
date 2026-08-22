"""Unit coverage for the long-running soak harness invariants."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


HERE = Path(__file__).resolve().parent


def load_script(name: str):
    path = HERE / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(*, pid: int = 100, restarts: int = 0, processes: object = 100):
    return {
        "mesh": {
            "onewifi.service": {
                "ActiveState": "active",
                "MainPID": pid,
                "NRestarts": restarts,
                "ProcessPIDs": processes,
            }
        }
    }


def test_service_validation_ignores_transient_cgroup_children():
    soak = load_script("p0-churn-soak.py")

    assert soak.validate_services(
        state(processes=100), state(processes="100,201,202")
    ) == []


def test_service_validation_retains_restart_and_main_pid_gates():
    soak = load_script("p0-churn-soak.py")

    assert soak.validate_services(state(), state(pid=101)) == [
        "mesh/onewifi.service: pid 100->101"
    ]
    assert soak.validate_services(state(), state(restarts=1)) == [
        "mesh/onewifi.service: restarts 0->1"
    ]


def test_read_only_lxc_probe_retries_a_lost_exec_transport(monkeypatch):
    soak = load_script("p0-churn-soak.py")
    calls = []

    def probe(container, command, check=True):
        calls.append((container, command, check))
        if len(calls) == 1:
            raise subprocess.CalledProcessError(-15, ["lxc", "exec"])
        return "healthy"

    monkeypatch.setattr(soak, "lxc", probe)
    monkeypatch.setattr(soak.time, "sleep", lambda _seconds: None)

    assert soak.lxc_read("mesh", "systemctl show", attempts=2) == "healthy"
    assert len(calls) == 2


def test_candidate_identity_probe_retries_a_lost_exec_transport():
    candidate = load_script("candidate-rcpi-test.py")
    failed = subprocess.CalledProcessError(-15, ["lxc", "exec"])
    completed = subprocess.CompletedProcess(
        ["lxc", "exec"], 0, "02:00:00:00:03:00\n", ""
    )
    with patch.object(
        candidate.subprocess, "run", side_effect=[failed, completed]
    ) as probe, patch.object(candidate.time, "sleep") as sleep:
        assert candidate.lxc("wlan-client", "cat address", attempts=2) == (
            "02:00:00:00:03:00"
        )

    assert probe.call_count == 2
    sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize(
    "script", ["wmediumd-client-carousel.py", "wmediumd-extender-outage.py"]
)
@pytest.mark.parametrize("transport_status", [-15, 143])
def test_scenario_read_retries_only_signal_terminated_lxc_transport(
    script, transport_status
):
    scenario = load_script(script)
    terminated = subprocess.CompletedProcess(
        ["lxc", "exec"], transport_status, "", "lost"
    )
    completed = subprocess.CompletedProcess(["lxc", "exec"], 0, "pass\n", "")

    with patch.object(
        scenario.subprocess, "run", side_effect=[terminated, completed]
    ) as probe, patch.object(scenario.time, "sleep") as sleep:
        assert scenario.lxc("wlan-client", "ping") == "pass"

    assert probe.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_outage_read_preserves_a_real_command_failure_without_retry():
    outage = load_script("wmediumd-extender-outage.py")
    failed = subprocess.CompletedProcess(["lxc", "exec"], 1, "fail\n", "")

    with patch.object(outage.subprocess, "run", return_value=failed) as probe:
        assert outage.lxc("wlan-client", "ping") == "fail"

    probe.assert_called_once()


@pytest.mark.parametrize("transport_status", [-15, 143])
def test_soak_traffic_retries_transport_signal_but_not_ping_failure(
    transport_status,
):
    soak = load_script("p0-churn-soak.py")
    terminated = subprocess.CompletedProcess(
        ["lxc", "exec"], transport_status, "", "lost"
    )
    ping_failed = subprocess.CompletedProcess(
        ["lxc", "exec"], 1, "3 packets transmitted, 0 received, 100% packet loss\n", ""
    )

    with patch.object(
        soak.subprocess, "run", side_effect=[terminated, ping_failed]
    ) as probe, patch.object(soak.time, "sleep") as sleep:
        result = soak.traffic_one("wlan-client")

    assert probe.call_count == 2
    sleep.assert_called_once_with(0.5)
    assert result["returncode"] == 1
    assert result["packet_loss_percent"] == 100


def test_soak_traffic_check_is_sequential_and_ordered():
    soak = load_script("p0-churn-soak.py")
    observed = []

    def traffic(client):
        observed.append(client)
        return {"client": client, "returncode": 0, "packet_loss_percent": 0}

    with patch.object(soak, "traffic_one", side_effect=traffic):
        results = soak.traffic_check()

    assert observed == list(soak.CLIENTS)
    assert [result["client"] for result in results] == list(soak.CLIENTS)


def test_stability_window_can_follow_a_separate_recovery_interval(monkeypatch):
    outage = load_script("wmediumd-extender-outage.py")

    clock = {"now": 0.0}
    monkeypatch.setattr(outage.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        outage.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds)
    )

    elapsed_ms, observation = outage.wait_stable(
        timeout=9,
        interval=1,
        stable_for=3,
        predicate=lambda: {"agreed": True} if clock["now"] >= 4 else None,
    )

    assert elapsed_ms == 7000
    assert observation == {"agreed": True}
