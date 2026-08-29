#!/usr/bin/env python3
"""Prove the candidate-link RCPI transaction against controlled hwsim truth."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATOR = ROOT / "wmediumd" / "configurator"
if not CONFIGURATOR.is_dir():
    CONFIGURATOR = Path(
        os.environ.get("EASYMESH_REPO", "/home/vagrant/git/meta-cmf-bananapi-vcpe")
    ) / "gen" / "wmediumd" / "configurator"
sys.path.insert(0, str(CONFIGURATOR))

from wmdcfg.actuator import ControlClient  # noqa: E402
from wmdcfg.inventory import discover  # noqa: E402
from wmdcfg.kernel_actuator import KernelMediumClient  # noqa: E402


def lxc(container: str, command: str, attempts: int = 3) -> str:
    """Run a bounded, read-only container identity probe."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(
                ("lxc", "exec", container, "--", "sh", "-c", command),
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip().lower()
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            time.sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            document = json.load(error)
        except json.JSONDecodeError:
            document = {"message": error.read().decode(errors="replace")}
        return error.code, document


def select_pair(client: str, requested_target: str | None) -> tuple[dict, dict]:
    # Candidate RCPI needs one station and the mesh radios, not every other
    # client. Keeping this probe O(mesh) prevents the health gate from growing
    # linearly with the 20/50/100-client profiles.
    inventory = discover({client})["radios"]
    by_name = {item["container"]: item for item in inventory}
    station = by_name.get(client)
    if station is None or station["kind"] != "station":
        raise RuntimeError(f"{client}: WLAN client radio not found")
    owner = station.get("associated_bssid")
    candidates = []
    for item in inventory:
        if item["kind"] != "mesh" or item["container"] == "bpibroadband":
            continue
        bssids = {interface.get("mac") for interface in item.get("interfaces", [])}
        if owner not in bssids:
            candidates.append(item)
    if requested_target:
        candidates = [item for item in candidates if item["container"] == requested_target]
    if not candidates:
        raise RuntimeError("no unassociated target extender is available")
    return station, candidates[0]


def restore_frequency(
    control: ControlClient,
    source: str,
    destination: str,
    frequency: int,
    value: int,
    override: bool,
) -> None:
    generation = control.status().generation + 1
    control.apply_frequency(generation, [{
        "source": source,
        "destination": destination,
        "frequency_mhz": frequency,
        "value": value,
        "override": override,
    }])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set one exact wmediumd SNR and verify returned candidate RCPI"
    )
    parser.add_argument("--client", default="wlan-client")
    parser.add_argument("--target", help="target extender container")
    parser.add_argument("--socket", default="/run/wmediumd-control.sock")
    parser.add_argument(
        "--backend", choices=("userspace", "kernel"),
        default=os.environ.get("EASYMESH_MEDIUM_BACKEND", "userspace"),
    )
    parser.add_argument("--api", default="http://127.0.0.1:8888/api/v1")
    parser.add_argument("--opclass", type=int, default=115)
    parser.add_argument("--channel", type=int, default=36)
    parser.add_argument("--frequency", type=int, default=5180)
    parser.add_argument("--snr", type=int, default=25)
    args = parser.parse_args()

    station, target = select_pair(args.client, args.target)
    sta_mac = lxc(args.client, "cat /sys/class/net/wlan0/address")
    target_al = lxc(target["container"], "cat /sys/class/net/eth1_virt_peer/address")
    source = station["tx_mac"]
    destination = target["tx_mac"]
    expected_rcpi = max(0, min(220, 2 * (args.snr + 19)))
    query = {
        "AlMac": target_al,
        "UnassocStaQueryList": [{
            "opclass": args.opclass,
            "channels": [{"channel": args.channel, "sta_macs": [sta_mac]}],
        }],
    }

    result: dict = {
        "client": args.client,
        "target": target["container"],
        "agent_al": target_al,
        "sta": sta_mac,
        "source_radio": source,
        "target_radio": destination,
        "frequency_mhz": args.frequency,
        "snr_db": args.snr,
        "expected_rcpi": expected_rcpi,
        "medium_backend": args.backend,
    }
    control_client = (
        ControlClient(args.socket)
        if args.backend == "userspace"
        else KernelMediumClient()
    )
    with control_client as control:
        _, before_frequency = control.dump_frequency_links()
        _, original_value, original_override = control.get_frequency_link(
            source, destination, args.frequency
        )
        try:
            generation = control.status().generation + 1
            control.apply_frequency(generation, [{
                "source": source,
                "destination": destination,
                "frequency_mhz": args.frequency,
                "value": args.snr,
                "override": True,
            }])
            status, response = request_json(f"{args.api}/unassoc_sta_query", query)
            result["http_status"] = status
            result["response"] = response
            metrics = response.get("metrics", [])
            if status != 200 or not response.get("success") or len(metrics) != 1:
                raise RuntimeError(f"candidate query failed: HTTP {status}: {response}")
            metric = metrics[0]
            if (
                metric.get("agent_al", "").lower() != target_al
                or metric.get("sta", "").lower() != sta_mac
                or metric.get("opclass") != args.opclass
                or metric.get("channel") != args.channel
                or metric.get("rcpi") != expected_rcpi
                or response.get("provider") != "hwsim-wmediumd-read-only"
                or response.get("simulated") is not True
            ):
                raise RuntimeError(f"candidate result mismatch: {metric}")
        finally:
            restore_frequency(
                control, source, destination, args.frequency,
                original_value, original_override,
            )
            _, after_frequency = control.dump_frequency_links()
            if after_frequency != before_frequency:
                raise RuntimeError("frequency override state was not restored exactly")

    result["outcome"] = "passed"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
