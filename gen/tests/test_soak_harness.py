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


def test_soak_traffic_check_is_bounded_and_result_ordered():
    soak = load_script("p0-churn-soak.py")
    observed = []

    def traffic(client):
        observed.append(client)
        return {"client": client, "returncode": 0, "packet_loss_percent": 0}

    with patch.object(soak, "traffic_one", side_effect=traffic):
        results = soak.traffic_check()

    assert sorted(observed) == sorted(soak.CLIENTS)
    assert [result["client"] for result in results] == list(soak.CLIENTS)


def test_soak_accepts_an_explicit_mixed_client_set():
    soak = load_script("p0-churn-soak.py")
    clients = ("wlan-client", "wlan-client-010")

    with patch.object(
        soak, "traffic_one",
        side_effect=lambda client: {"client": client, "returncode": 0},
    ):
        results = soak.traffic_check(clients)

    assert [result["client"] for result in results] == list(clients)


def test_soak_counts_unique_clients_by_ssid():
    soak = load_script("p0-churn-soak.py")
    topology = {
        "nodes": [
            {"STAList": [
                {"staMAC": "02:00:00:00:09:00", "ssid": "private_ssid"},
                {"staMAC": "02:00:00:00:13:00", "ssid": "iot_ssid"},
            ]},
            {"STAList": [
                {"staMAC": "02:00:00:00:13:00", "ssid": "iot_ssid"},
            ]},
        ]
    }

    assert soak.topology_ssid_counts(topology) == {
        "iot_ssid": 1,
        "private_ssid": 1,
    }


def test_soak_carousel_command_selects_the_requested_cohort(tmp_path):
    soak = load_script("p0-churn-soak.py")

    command, cursor = soak.workload_command(
        "carousel", tmp_path, 3, "iot_ssid"
    )

    assert cursor == 3
    assert command[command.index("--ssid") + 1] == "iot_ssid"


def test_carousel_selects_only_matching_cohort_bssids():
    carousel = load_script("wmediumd-client-carousel.py")
    radio = {
        "interfaces": [
            {"ssid": "private_ssid", "mac": "02:00:00:00:01:00"},
            {"ssid": "iot_ssid", "mac": "02:00:00:00:02:00"},
        ]
    }

    assert carousel.cohort_bssids(radio, "iot_ssid") == {
        "02:00:00:00:02:00"
    }


def test_carousel_client_label_uses_the_selected_cohort_prefix():
    carousel = load_script("wmediumd-client-carousel.py")

    assert carousel.sta_label("02:00:00:00:13:00") == "STA-13"
    assert carousel.sta_label("02:00:00:00:13:00", "IOT") == "IOT-13"


@pytest.mark.parametrize("transport_status", [-15, 143])
def test_carousel_retries_idempotent_link_state_after_transport_signal(
    transport_status,
):
    carousel = load_script("wmediumd-client-carousel.py")
    terminated = subprocess.CompletedProcess(
        ["lxc", "exec"], transport_status, "", "lost"
    )
    completed = subprocess.CompletedProcess(["lxc", "exec"], 0, "", "")

    with patch.object(
        carousel.subprocess, "run", side_effect=[terminated, completed]
    ) as command, patch.object(carousel.time, "sleep") as sleep:
        carousel.set_client_link([{"container": "wlan-client"}], "up")

    assert command.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_carousel_does_not_retry_real_link_state_failure():
    carousel = load_script("wmediumd-client-carousel.py")
    failed = subprocess.CompletedProcess(["lxc", "exec"], 1, "", "denied")

    with patch.object(carousel.subprocess, "run", return_value=failed) as command:
        with pytest.raises(subprocess.CalledProcessError):
            carousel.set_client_link([{"container": "wlan-client"}], "up")

    command.assert_called_once()


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
