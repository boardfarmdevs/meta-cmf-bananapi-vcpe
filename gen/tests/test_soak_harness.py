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
    spec = importlib.util.spec_from_file_location(path.stem, path)
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


def test_carousel_keeps_frequency_with_each_matching_bssid():
    carousel = load_script("wmediumd-client-carousel.py")
    radio = {
        "interfaces": [
            {"ssid": "private_ssid", "mac": "02:00:00:00:01:00",
             "frequency_mhz": 5955},
            {"ssid": "iot_ssid", "mac": "02:00:00:00:02:00",
             "frequency_mhz": 6135},
        ]
    }

    assert carousel.cohort_bsses(radio, "iot_ssid") == {
        "02:00:00:00:02:00": 6135
    }


def test_carousel_client_label_uses_the_selected_cohort_prefix():
    carousel = load_script("wmediumd-client-carousel.py")

    assert carousel.sta_label("02:00:00:00:13:00") == "STA-13"
    assert carousel.sta_label("02:00:00:00:13:00", "IOT") == "IOT-13"


def test_carousel_bounds_repair_association_groups():
    carousel = load_script("wmediumd-client-carousel.py")
    clients = [{"container": f"wlan-client-{index:03d}"} for index in range(5)]

    assert carousel.bounded_groups(clients) == [
        clients[0:2], clients[2:4], clients[4:5]
    ]
    assert carousel.bounded_groups(clients, 1) == [
        clients[0:1], clients[1:2], clients[2:3], clients[3:4], clients[4:5]
    ]
    with pytest.raises(ValueError):
        carousel.bounded_groups(clients, 0)


def test_carousel_reads_pinned_or_current_client_frequency():
    carousel = load_script("wmediumd-client-carousel.py")

    with patch.object(
        carousel, "lxc", return_value="network={\n scan_freq=2437\n}"
    ) as probe:
        assert carousel.client_frequency("wlan-client-008") == 2437
        probe.assert_called_once()

    with patch.object(
        carousel, "lxc",
        side_effect=["network={\n ssid=private_ssid\n}", "freq: 5180\n"],
    ):
        assert carousel.client_frequency("wlan-client") == 5180


def test_carousel_primes_the_selected_ap_on_the_client_band():
    carousel = load_script("wmediumd-client-carousel.py")
    client = {
        "container": "wlan-client-008", "frequency": 2437,
        "band": "2.4", "ssid": "private_ssid",
    }
    aps = {
        "bpiap-002": {
            "bsses": {
                "02:00:00:e4:c3:c8": 2437,
                "02:00:00:7f:f9:ae": 5180,
            }
        }
    }
    requested = subprocess.CompletedProcess(
        ["lxc", "exec"], 0, "OK\n", "",
    )
    completed = subprocess.CompletedProcess(
        ["lxc", "exec"], 0,
        "bssid / frequency / signal level / flags / ssid\n"
        "02:00:00:e4:c3:c8\t2437\t-41\t[ESS]\tprivate_ssid\n", "",
    )

    with patch.object(
        carousel.subprocess, "run", side_effect=[requested, completed]
    ) as scan:
        carousel.prime_candidate_scans(
            [client], aps, {"wlan-client-008": "bpiap-002"}
        )

    assert scan.call_args_list[0].args[0][-3:] == (
        "freq=2437", "bssid=02:00:00:e4:c3:c8",
        "ssid 707269766174655f73736964",
    )
    assert scan.call_args_list[1].args[0][-1] == "scan_results"


def test_carousel_scans_the_target_aps_actual_same_band_frequency():
    carousel = load_script("wmediumd-client-carousel.py")
    client = {
        "container": "wlan-client-009", "frequency": 5955,
        "band": "6", "ssid": "private_ssid",
    }
    aps = {
        "bpiap": {
            "bsses": {
                "02:00:00:a5:b9:eb": 6135,
                "02:00:00:0f:e2:94": 5180,
            }
        }
    }
    requested = subprocess.CompletedProcess(
        ["lxc", "exec"], 0, "OK\n", "",
    )
    completed = subprocess.CompletedProcess(
        ["lxc", "exec"], 0,
        "bssid / frequency / signal level / flags / ssid\n"
        "02:00:00:a5:b9:eb\t6135\t-43\t[ESS]\tprivate_ssid\n", "",
    )

    with patch.object(
        carousel.subprocess, "run", side_effect=[requested, completed]
    ) as scan:
        carousel.prime_candidate_scans(
            [client], aps, {"wlan-client-009": "bpiap"}
        )

    assert scan.call_args_list[0].args[0][-3:] == (
        "freq=6135", "bssid=02:00:00:a5:b9:eb",
        "ssid 707269766174655f73736964",
    )
    assert scan.call_args_list[1].args[0][-1] == "scan_results"


def test_carousel_does_not_accept_an_empty_hidden_bss_cache_entry():
    carousel = load_script("wmediumd-client-carousel.py")
    client = {
        "container": "wlan-client-019", "frequency": 5180,
        "band": "5", "ssid": "iot_ssid",
    }
    aps = {"bpiap-002": {"bsses": {"02:00:00:3a:26:05": 5180}}}
    requested = subprocess.CompletedProcess(["lxc", "exec"], 0, "OK\n", "")
    empty = subprocess.CompletedProcess(
        ["lxc", "exec"], 0,
        "02:00:00:3a:26:05\t5180\t-31\t[ESS]\t\n", "",
    )
    resolved = subprocess.CompletedProcess(
        ["lxc", "exec"], 0,
        "02:00:00:3a:26:05\t5180\t-31\t[ESS]\tiot_ssid\n", "",
    )

    with patch.object(
        carousel.subprocess, "run", side_effect=[requested, empty, resolved]
    ) as scan, patch.object(carousel.time, "sleep"):
        carousel.prime_candidate_scans(
            [client], aps, {"wlan-client-019": "bpiap-002"}
        )

    assert scan.call_count == 3
    assert scan.call_args_list[0].args[0][-1] == "ssid 696f745f73736964"


def test_carousel_requires_exact_controller_bssid_agreement():
    carousel = load_script("wmediumd-client-carousel.py")
    observation = {
        "valid_topology": True,
        "stations": [{
            "client": "wlan-client-009",
            "actual_ap": "bpiap",
            "topology_ap": "bpiap",
            "bssid": "02:00:00:a5:b9:eb",
            "topology_bssid": "02:00:00:0f:e2:94",
        }],
    }

    assert not carousel.assignment_reached(
        observation, {"wlan-client-009": "bpiap"}
    )


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
