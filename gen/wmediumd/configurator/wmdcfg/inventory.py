from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .model import ScenarioError


MESH_NAME = re.compile(r"^(bpibroadband|bpiap(?:-\d{3})?)$")
CLIENT_NAME = re.compile(r"^wlan-client(?:-\d{3})?$")


def _run(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def _exec(container: str, command: str) -> str:
    return _run("lxc", "exec", container, "--", "sh", "-c", command)


def _tx_mac(permanent: str) -> str:
    raw = bytearray.fromhex(permanent.replace(":", ""))
    if len(raw) != 6:
        raise ScenarioError(f"invalid radio MAC {permanent!r}")
    raw[0] |= 0x40
    return ":".join(f"{value:02x}" for value in raw)


def _parse_iw(text: str) -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        value = line.strip()
        if value.startswith("Interface "):
            current = {"name": value.split(None, 1)[1]}
            interfaces.append(current)
        elif current is not None and value.startswith("addr "):
            current["mac"] = value.split()[1].lower()
        elif current is not None and value.startswith("ssid "):
            current["ssid"] = value.split(None, 1)[1]
        elif current is not None and value.startswith("channel "):
            match = re.search(r"\((\d+) MHz\)", value)
            if match:
                current["frequency_mhz"] = int(match.group(1))
    return interfaces


def discover() -> dict[str, Any]:
    # A scaled lab intentionally retains stopped containers across cold-start
    # reconstruction and extender-outage tests.  ``lxc exec`` cannot inspect a
    # stopped instance, so inventory must describe the active RF world rather
    # than every matching name in LXD's persistent database.
    names = sorted(
        [
            name
            for line in _run("lxc", "list", "-c", "ns", "--format", "csv").splitlines()
            for name, _, state in [line.partition(",")]
            if state.strip().upper() == "RUNNING"
            and (MESH_NAME.fullmatch(name) or CLIENT_NAME.fullmatch(name))
        ],
        key=lambda name: [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)],
    )
    if not names:
        raise ScenarioError("no active EasyMesh or WLAN client containers found")
    radios = []
    for name in names:
        permanent = _exec(
            name, "cat /sys/class/ieee80211/*/macaddress 2>/dev/null | head -1"
        ).lower()
        if not permanent:
            raise ScenarioError(f"{name}: no hwsim radio found")
        interfaces = _parse_iw(_exec(name, "iw dev 2>/dev/null"))
        item: dict[str, Any] = {
            "container": name,
            "kind": "station" if CLIENT_NAME.fullmatch(name) else "mesh",
            "permanent_mac": permanent,
            "tx_mac": _tx_mac(permanent),
            "interfaces": interfaces,
        }
        if item["kind"] == "station":
            link = _exec(name, "iw dev wlan0 link 2>/dev/null || true")
            match = re.search(r"Connected to ([0-9a-f:]{17})", link, re.I)
            item["associated_bssid"] = match.group(1).lower() if match else None
        radios.append(item)
    return {
        "schema": "wmdcfg.inventory.v1",
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "radios": radios,
    }


def save(inventory: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
