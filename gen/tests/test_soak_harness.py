"""Unit coverage for the long-running soak harness invariants."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch


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
