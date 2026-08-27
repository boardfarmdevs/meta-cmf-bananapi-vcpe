import subprocess
from unittest.mock import patch

from wmdcfg.inventory import _run, discover


def test_inventory_probe_retries_a_lost_lxc_exec_transport():
    failed = subprocess.CalledProcessError(-15, ["lxc", "exec"])
    completed = subprocess.CompletedProcess(["lxc", "exec"], 0, "ready\n", "")
    with patch("wmdcfg.inventory.subprocess.run", side_effect=[failed, completed]) as run, patch(
        "wmdcfg.inventory.time.sleep"
    ) as sleep:
        assert _run("lxc", "exec", "mesh", attempts=2) == "ready"

    assert run.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_inventory_probe_retries_a_bounded_timeout():
    failed = subprocess.TimeoutExpired(["lxc", "exec"], 0.25)
    completed = subprocess.CompletedProcess(["lxc", "exec"], 0, "ready\n", "")
    with patch("wmdcfg.inventory.subprocess.run", side_effect=[failed, completed]) as run, patch(
        "wmdcfg.inventory.time.sleep"
    ) as sleep:
        assert _run(
            "lxc", "exec", "mesh", attempts=2, timeout_seconds=0.25
        ) == "ready"

    assert run.call_count == 2
    assert all(call.kwargs["timeout"] == 0.25 for call in run.call_args_list)
    sleep.assert_called_once_with(0.5)


def test_discover_ignores_stopped_matching_containers():
    listing = "\n".join(
        (
            "bpibroadband,RUNNING",
            "bpiap,RUNNING",
            "bpiap-001,STOPPED",
            "wlan-client,RUNNING",
            "wlan-client-001,STOPPED",
        )
    )

    def inspect(container: str, command: str) -> str:
        assert container not in {"bpiap-001", "wlan-client-001"}
        if "macaddress" in command:
            return {
                "bpibroadband": "02:00:00:00:00:01",
                "bpiap": "02:00:00:00:00:02",
                "wlan-client": "02:00:00:00:00:03",
            }[container]
        if command.startswith("iw dev wlan0 link"):
            return "Connected to 02:00:00:10:00:01\n\tSSID: iot_ssid\n\tfreq: 5180"
        return ""

    with patch("wmdcfg.inventory._run", return_value=listing), patch(
        "wmdcfg.inventory._exec", side_effect=inspect
    ):
        inventory = discover()

    assert [radio["container"] for radio in inventory["radios"]] == [
        "bpiap",
        "bpibroadband",
        "wlan-client",
    ]
    station = next(item for item in inventory["radios"] if item["kind"] == "station")
    assert station["associated_bssid"] == "02:00:00:10:00:01"
    assert station["ssid"] == "iot_ssid"
    assert station["cohort"] == "iot"


def test_discover_can_limit_station_probes_without_omitting_mesh_radios():
    listing = "\n".join(
        (
            "bpibroadband,RUNNING",
            "bpiap,RUNNING",
            "wlan-client,RUNNING",
            "wlan-client-001,RUNNING",
        )
    )
    inspected: set[str] = set()

    def inspect(container: str, command: str) -> str:
        inspected.add(container)
        if "macaddress" in command:
            return {
                "bpibroadband": "02:00:00:00:00:01",
                "bpiap": "02:00:00:00:00:02",
                "wlan-client-001": "02:00:00:00:00:04",
            }[container]
        if command.startswith("iw dev wlan0 link"):
            return "Connected to 02:00:00:10:00:01\n\tSSID: private_ssid"
        return ""

    with patch("wmdcfg.inventory._run", return_value=listing), patch(
        "wmdcfg.inventory._exec", side_effect=inspect
    ):
        inventory = discover({"wlan-client-001"})

    assert [radio["container"] for radio in inventory["radios"]] == [
        "bpiap",
        "bpibroadband",
        "wlan-client-001",
    ]
    assert inspected == {"bpiap", "bpibroadband", "wlan-client-001"}
