from unittest.mock import patch

from wmdcfg.inventory import discover


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
            return "Not connected."
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
