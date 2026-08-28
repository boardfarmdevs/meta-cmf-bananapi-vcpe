#!/usr/bin/env python3
"""Move WLAN clients around every mesh AP through wmediumd RF generations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATOR = ROOT / "wmediumd" / "configurator"
if not CONFIGURATOR.is_dir():
    CONFIGURATOR = Path(
        os.environ.get("EASYMESH_REPO", "/home/vagrant/git/meta-cmf-bananapi-vcpe")
    ) / "gen" / "wmediumd" / "configurator"
sys.path.insert(0, str(CONFIGURATOR))

from wmdcfg.actuator import ActuatorError, ControlClient  # noqa: E402
from wmdcfg.inventory import discover  # noqa: E402


REQUIRED_CAPABILITIES = {
    "radio_pair_snr", "atomic_generations", "readback", "dump_links"
}
LOG_MARKERS = (
    "topology notification", "topo notification", "send_topology_notification",
    "analyze_sta_list", "orch_execute", "client cap", "sta not found",
    "failed to send cmdu", "no destination_mac", "sap", "error", "warn",
)


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, check=check, text=True, capture_output=True)
    return result.stdout.strip()


def lxc(container: str, command: str) -> str:
    for attempt in range(1, 4):
        result = subprocess.run(
            ("lxc", "exec", container, "--", "sh", "-c", command),
            check=False,
            text=True,
            capture_output=True,
        )
        if 0 <= result.returncode < 128:
            return result.stdout.strip()
        if attempt < 3:
            time.sleep(0.5 * attempt)
    raise subprocess.CalledProcessError(
        result.returncode, result.args, output=result.stdout, stderr=result.stderr
    )


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def sta_label(mac: str, prefix: str = "STA") -> str:
    octets = mac.upper().split(":")
    if (
        len(octets) == 6
        and octets[:4] == ["02", "00", "00", "00"]
        and octets[5] == "00"
    ):
        return f"{prefix}-{octets[4]}"
    return f"{prefix}-{'-'.join(octets[-3:])}" if len(octets) == 6 else prefix


def client_mac(container: str) -> str:
    value = lxc(container, "cat /sys/class/net/wlan0/address").lower()
    if not re.fullmatch(r"[0-9a-f:]{17}", value):
        raise RuntimeError(f"{container}: invalid wlan0 MAC {value!r}")
    return value


def client_bssid(container: str) -> str | None:
    for line in lxc(container, "iw dev wlan0 link 2>/dev/null").splitlines():
        value = line.strip()
        if value.startswith("Connected to "):
            return value.split()[2].lower()
    return None


def client_frequency(container: str) -> int:
    """Return the client's configured band frequency for directed scans."""
    config = lxc(container, "cat /etc/wpa.conf 2>/dev/null")
    match = re.search(
        r"^\s*(?:scan_freq|freq_list)\s*=\s*(\d+)", config, re.MULTILINE
    )
    if match:
        return int(match.group(1))
    link = lxc(container, "iw dev wlan0 link 2>/dev/null")
    match = re.search(r"^\s*freq:\s*(\d+)", link, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{container}: cannot determine WLAN frequency")
    return int(match.group(1))


def frequency_band(frequency: int) -> str:
    if 2400 <= frequency < 2500:
        return "2.4"
    if 5000 <= frequency < 5955:
        return "5"
    if 5955 <= frequency <= 7115:
        return "6"
    raise ValueError(f"unsupported Wi-Fi frequency {frequency} MHz")


def fetch_topology(url: str) -> dict | None:
    try:
        document = json.loads(run("curl", "-fsS", url))
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return None
    # The controller must always be present. Treat a zero-node response as the
    # known transient raw-frame/provider miss, never as topology truth.
    if not document.get("nodes"):
        return None
    return document


def topology_station(document: dict, mac: str) -> tuple[str, str | None] | None:
    for node in document.get("nodes", []):
        for item in node.get("STAList") or []:
            if item.get("staMAC", "").lower() != mac:
                continue
            owner = str(node.get("id", "")).lower()
            bssid = str(item.get("bssid") or item.get("BSSID") or "").lower()
            return owner, bssid or None
    return None


def topology_owner(document: dict, mac: str) -> str | None:
    station = topology_station(document, mac)
    return station[0] if station else None


def cohort_bssids(radio: dict, ssid: str) -> set[str]:
    return {
        item["mac"].lower()
        for item in radio.get("interfaces", [])
        if item.get("ssid") == ssid and item.get("mac")
    }


def cohort_bsses(radio: dict, ssid: str) -> dict[str, int]:
    return {
        item["mac"].lower(): int(item["frequency_mhz"])
        for item in radio.get("interfaces", [])
        if item.get("ssid") == ssid
        and item.get("mac")
        and item.get("frequency_mhz")
    }


def topology_ap_identity(document: dict, bssids: set[str]) -> tuple[str, str] | None:
    for node in document.get("nodes", []):
        node_bssids = {
            str(bss.get("BSSID", "")).lower()
            for haul in (node.get("haulTypes") or [])
            for bss in (haul.get("BSSList") or [])
        }
        if bssids & node_bssids:
            return str(node.get("id", "")).lower(), str(node.get("name", node.get("id")))
    return None


def ap_order(ap: dict) -> tuple[int, int, str]:
    name = ap["node_name"]
    if name.lower().startswith("agent"):
        return (0, 0, name)
    match = re.search(r"(\d+)$", name)
    return (1, int(match.group(1)) if match else 999, name)


def split_groups(clients: list[dict], count: int) -> list[list[dict]]:
    base, extra = divmod(len(clients), count)
    groups = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        groups.append(clients[cursor:cursor + size])
        cursor += size
    return [group for group in groups if group]


def matrix_updates(
    clients: list[dict], aps: list[dict], targets: dict[str, str | None],
    strong_snr: int, outage_snr: int,
) -> list[dict]:
    updates = []
    for client in clients:
        target = targets[client["container"]]
        for ap in aps:
            value = strong_snr if ap["container"] == target else outage_snr
            updates.extend(
                [
                    {"source": client["tx_mac"], "destination": ap["tx_mac"],
                     "value": value},
                    {"source": ap["tx_mac"], "destination": client["tx_mac"],
                     "value": value},
                ]
            )
    return updates


def observe(
    clients: list[dict], bssid_to_ap: dict[str, str], node_to_ap: dict[str, str],
    topology_url: str,
) -> dict:
    document = fetch_topology(topology_url)
    stations = []
    for client in clients:
        bssid = client_bssid(client["container"])
        station = topology_station(document, client["mac"]) if document else None
        owner = station[0] if station else None
        topology_bssid = station[1] if station else None
        stations.append(
            {
                "client": client["container"],
                "label": client["label"],
                "bssid": bssid,
                "actual_ap": bssid_to_ap.get(bssid) if bssid else None,
                "topology_owner": owner,
                "topology_ap": node_to_ap.get(owner) if owner else None,
                "topology_bssid": topology_bssid,
            }
        )
    return {"valid_topology": document is not None, "stations": stations}


def assignment_reached(observation: dict, targets: dict[str, str]) -> bool:
    return bool(observation["valid_topology"]) and all(
        item["actual_ap"] == targets[item["client"]]
        and item["topology_ap"] == targets[item["client"]]
        and item["bssid"] == item["topology_bssid"]
        for item in observation["stations"]
    )


def radio_assignment_reached(observation: dict, targets: dict[str, str]) -> bool:
    return all(
        item["actual_ap"] == targets[item["client"]]
        for item in observation["stations"]
    )


def assignment_mismatches(observation: dict, targets: dict[str, str]) -> set[str]:
    return {
        item["client"]
        for item in observation["stations"]
        if item["actual_ap"] != targets[item["client"]]
        or item["topology_ap"] != targets[item["client"]]
        or item["bssid"] != item["topology_bssid"]
    }


def radio_disconnected(observation: dict) -> bool:
    return all(item["bssid"] is None for item in observation["stations"])


def set_client_link(clients: list[dict], state: str) -> None:
    for client in clients:
        for attempt in range(1, 4):
            result = subprocess.run(
                (
                    "lxc", "exec", client["container"], "--", "ip", "link",
                    "set", "wlan0", state,
                ),
                check=False,
                text=True,
                capture_output=True,
            )
            if result.returncode == 0:
                break
            signal_status = result.returncode < 0 or result.returncode >= 128
            if not signal_status or attempt == 3:
                raise subprocess.CalledProcessError(
                    result.returncode, result.args,
                    output=result.stdout, stderr=result.stderr,
                )
            time.sleep(0.5 * attempt)


def prime_candidate_scans(
    clients: list[dict], aps_by_container: dict[str, dict],
    targets: dict[str, str], attempts: int = 3,
) -> None:
    """Put each selected target BSS into the pinned-band client's scan cache."""
    for client in clients:
        target_name = targets[client["container"]]
        target = aps_by_container[target_name]
        candidates = {
            bssid: frequency
            for bssid, frequency in target["bsses"].items()
            if frequency_band(frequency) == client["band"]
        }
        if not candidates:
            raise RuntimeError(
                f"{client['container']}: {target_name} has no {client['band']} GHz "
                "BSS for the selected SSID"
            )
        frequencies = sorted(set(candidates.values()))
        last_error = "target BSS absent"
        for attempt in range(1, attempts + 1):
            outputs = []
            errors = []
            for frequency in frequencies:
                request = subprocess.run(
                    (
                        "lxc", "exec", client["container"], "--", "wpa_cli",
                        "-i", "wlan0", "scan", f"freq={frequency}",
                    ),
                    check=False,
                    text=True,
                    capture_output=True,
                )
                if request.returncode or request.stdout.strip() != "OK":
                    errors.append(
                        request.stderr.strip() or request.stdout.strip()
                        or f"wpa_cli scan failed for {frequency}MHz"
                    )
                    continue
                time.sleep(0.5)
                result = subprocess.run(
                    (
                        "lxc", "exec", client["container"], "--", "wpa_cli",
                        "-i", "wlan0", "scan_results",
                    ),
                    check=False,
                    text=True,
                    capture_output=True,
                )
                outputs.append(result.stdout.lower())
                if result.returncode:
                    errors.append(result.stderr.strip())
            output = "\n".join(outputs)
            if any(bssid in output for bssid in candidates):
                break
            last_error = (
                "; ".join(error for error in errors if error)
                or "target BSS absent at "
                + ",".join(str(value) for value in frequencies)
                + "MHz via wpa_supplicant"
            )
            if attempt < attempts:
                time.sleep(float(attempt))
        else:
            raise RuntimeError(
                f"{client['container']}: cannot prime {target_name} candidate: "
                f"{last_error}"
            )


def relevant_log_lines(text: str, identities: set[str]) -> str:
    """Retain association-path records without copying multi-megabyte subdocs."""
    selected = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(value in lowered for value in identities) or any(
            marker in lowered for marker in LOG_MARKERS
        ):
            selected.append(line)
    return "\n".join(selected) + ("\n" if selected else "")


class Recorder:
    def __init__(self, path: Path):
        self.path = path

    def write(self, event: str, **fields) -> None:
        value = {"at": now(), "event": event, **fields}
        with self.path.open("a") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
        print(json.dumps(value, sort_keys=True), flush=True)


class Carousel:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.stop_requested = False
        self.recorder: Recorder | None = None
        self.last_wait_description = ""
        self.last_observation: dict = {}

    def request_stop(self, signum, frame) -> None:
        self.stop_requested = True

    def wait_for(
        self, timeout: float, predicate: Callable[[], tuple[bool, dict]],
        description: str, allow_stop: bool = True,
    ) -> tuple[int, dict]:
        started = time.monotonic()
        last: dict = {}
        while time.monotonic() - started < timeout:
            if allow_stop and self.stop_requested:
                raise InterruptedError("carousel interrupted")
            complete, last = predicate()
            self.last_wait_description = description
            self.last_observation = last
            if complete:
                return round((time.monotonic() - started) * 1000), last
            time.sleep(0.5)
        raise RuntimeError(f"timed out waiting for {description}; last={last}")

    def wait_for_stable(
        self, timeout: float, stable_for: float,
        predicate: Callable[[], tuple[bool, dict]], description: str,
    ) -> tuple[int, dict]:
        started = time.monotonic()
        stable_since: float | None = None
        last: dict = {}
        while time.monotonic() - started < timeout:
            complete, last = predicate()
            self.last_wait_description = description
            self.last_observation = last
            if complete:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= stable_for:
                    return round((time.monotonic() - started) * 1000), last
            else:
                stable_since = None
            time.sleep(0.5)
        raise RuntimeError(f"timed out waiting for {description}; last={last}")

    def collect_failure_evidence(
        self, output: Path, clients: list[dict], aps: list[dict],
        bssid_to_ap: dict[str, str], node_to_ap: dict[str, str], topology_url: str,
    ) -> None:
        """Capture the event path at failure before cleanup changes the state."""
        evidence = output / "failure-evidence"
        evidence.mkdir(exist_ok=True)
        failed_names = {
            item.get("client") for item in self.last_observation.get("stations", [])
        }
        failed_clients = [
            item for item in clients if not failed_names or item["container"] in failed_names
        ]
        identities = {
            str(value).lower()
            for item in failed_clients
            for value in (
                item.get("mac"), item.get("tx_mac"),
            )
            if value
        }
        identities.update(
            str(item.get("bssid")).lower()
            for observation in (
                self.last_observation,
                observe(clients, bssid_to_ap, node_to_ap, topology_url),
            )
            for item in observation.get("stations", [])
            if item.get("client") in failed_names and item.get("bssid")
        )
        snapshot = {
            "at": now(),
            "wait_description": self.last_wait_description,
            "last_observation": self.last_observation,
            "current_observation": observe(
                clients, bssid_to_ap, node_to_ap, topology_url
            ),
        }
        (evidence / "association-state.json").write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        )
        document = fetch_topology(topology_url)
        if document:
            (evidence / "topology.json").write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n"
            )

        containers = sorted({"bpibroadband", *(item["container"] for item in aps)})
        log_files = (
            "/tmp/em_agent.log",
            "/tmp/ieee1905_agent_log.txt", "/tmp/ieee1905_ctrl_log.txt",
            "/rdklogs/logs/wifiEM.txt",
        )
        expression = "|".join(
            re.escape(value) for value in sorted(identities | set(LOG_MARKERS))
        )
        for container in containers:
            if container == "bpibroadband":
                content = lxc(
                    container,
                    "journalctl -u em_ctrl.service --since '-30 minutes' "
                    "--no-pager 2>/dev/null | "
                    f"grep -i -E {shlex.quote(expression)} || true",
                )
                filtered = relevant_log_lines(content, identities)
                if filtered:
                    (evidence / f"{container}-em_ctrl-journal.txt").write_text(
                        filtered
                    )
            status = lxc(
                container,
                "systemctl --no-pager --full status "
                "em_agent.service em_ctrl.service ieee1905_em_agent.service "
                "ieee1905_em_ctrl.service 2>&1",
            )
            (evidence / f"{container}-services.txt").write_text(status + "\n")
            for log_file in log_files:
                content = lxc(
                    container,
                    f"test -r {shlex.quote(log_file)} && "
                    f"grep -i -E {shlex.quote(expression)} {shlex.quote(log_file)} "
                    "2>/dev/null || true",
                )
                filtered = relevant_log_lines(content, identities)
                if filtered:
                    name = log_file.strip("/").replace("/", "-")
                    (evidence / f"{container}-{name}").write_text(filtered)
        if self.recorder:
            self.recorder.write(
                "failure_evidence_collected", directory=str(evidence),
                wait_description=self.last_wait_description,
            )

    def hold(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stop_requested:
                raise InterruptedError("carousel interrupted")
            time.sleep(min(0.2, deadline - time.monotonic()))

    def execute(self) -> Path:
        args = self.args
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = args.output_root / f"{stamp}-client-carousel"
        output.mkdir(parents=True, exist_ok=False)
        self.recorder = Recorder(output / "events.jsonl")

        inventory = discover()
        (output / "inventory.json").write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n"
        )
        document = fetch_topology(args.topology_url)
        if not document:
            raise RuntimeError("live topology is empty at preflight")
        (output / "topology-before.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n"
        )

        # The controller container also owns an hwsim radio, but its colocated
        # Agent does not advertise the selected fronthaul SSID. It is a topology
        # identity, not a client-placement target for this scenario.
        mesh = [
            item for item in inventory["radios"]
            if item["kind"] == "mesh" and cohort_bssids(item, args.ssid)
        ]
        stations = [
            item for item in inventory["radios"]
            if item["kind"] == "station" and item.get("ssid") == args.ssid
        ]
        if len(mesh) < 2 or not stations:
            raise RuntimeError(f"need at least two APs and one client; found {len(mesh)}/{len(stations)}")

        aps = []
        for item in mesh:
            bssids = cohort_bssids(item, args.ssid)
            bsses = cohort_bsses(item, args.ssid)
            identity = topology_ap_identity(document, bssids)
            if not bssids or bssids != set(bsses) or not identity:
                raise RuntimeError(
                    f"{item['container']}: incomplete live {args.ssid} BSS inventory"
                )
            node_id, node_name = identity
            aps.append(
                {**item, "bssids": bssids, "bsses": bsses,
                 "node_id": node_id, "node_name": node_name}
            )
        aps.sort(key=ap_order)

        clients = []
        for item in sorted(stations, key=lambda entry: natural_key(entry["container"])):
            mac = client_mac(item["container"])
            prefix = "IOT" if args.ssid == "iot_ssid" else "STA"
            clients.append(
                {
                    **item,
                    "mac": mac,
                    "label": sta_label(mac, prefix),
                    "frequency": (frequency := client_frequency(item["container"])),
                    "band": frequency_band(frequency),
                }
            )

        bssid_to_ap = {
            bssid: ap["container"] for ap in aps for bssid in ap["bssids"]
        }
        node_to_ap = {ap["node_id"]: ap["container"] for ap in aps}
        aps_by_container = {ap["container"]: ap for ap in aps}
        original_targets = {}
        for client in clients:
            bssid = client_bssid(client["container"])
            target = bssid_to_ap.get(bssid) if bssid else None
            if not target:
                raise RuntimeError(
                    f"{client['container']}: not associated to a known {args.ssid} BSS ({bssid})"
                )
            original_targets[client["container"]] = target

        preflight = observe(clients, bssid_to_ap, node_to_ap, args.topology_url)
        if not preflight["valid_topology"] or any(
            item["topology_ap"] is None
            or item["topology_bssid"] != item["bssid"]
            for item in preflight["stations"]
        ):
            raise RuntimeError(f"client/API association is incomplete at preflight: {preflight}")

        groups = split_groups(clients, min(len(aps), len(clients)))
        positions = list(range(len(groups)))
        formation_targets = {
            client["container"]: aps[group_index]["container"]
            for group_index, group in enumerate(groups)
            for client in group
        }
        scenario = {
            "name": "five_ap_client_carousel",
            "ap_ring": [
                {"position": index, "container": ap["container"],
                 "topology_name": ap["node_name"], "node_id": ap["node_id"]}
                for index, ap in enumerate(aps)
            ],
            "groups": [
                {"group": index + 1, "clients": [client["label"] for client in group],
                 "initial_ap": aps[index]["node_name"]}
                for index, group in enumerate(groups)
            ],
            "rounds": args.rounds,
            "strong_snr": args.strong_snr,
            "outage_snr": args.outage_snr,
            "blackout_hold_seconds": args.blackout_hold,
            "arrival_hold_seconds": args.arrival_hold,
        }
        (output / "scenario.json").write_text(
            json.dumps(scenario, indent=2, sort_keys=True) + "\n"
        )
        self.recorder.write(
            "preflight", aps=[ap["node_name"] for ap in aps],
            clients=[client["label"] for client in clients], groups=scenario["groups"],
        )
        print("\nOpen the Network Topology tab and watch the printed client labels.", flush=True)
        print("Each BLACKOUT disconnects one group; ARRIVAL moves it to the next AP.\n", flush=True)

        touched = {
            (client["tx_mac"], ap["tx_mac"])
            for client in clients for ap in aps
        } | {
            (ap["tx_mac"], client["tx_mac"])
            for client in clients for ap in aps
        }
        outcome = "failed"
        error_text = None
        restored = False
        placement_restored = False
        interrupted = False
        failure: Exception | None = None
        rounds_completed = 0
        with ControlClient(args.socket) as control:
            status = control.status()
            missing = REQUIRED_CAPABILITIES - status.capabilities
            if missing:
                raise RuntimeError(f"wmediumd lacks capabilities {sorted(missing)}")
            if len(touched) > status.max_updates:
                raise RuntimeError(
                    f"carousel requires {len(touched)} atomic updates; "
                    f"wmediumd supports {status.max_updates}"
                )
            generation, dumped = control.dump_links()
            baseline = {
                (item["source"], item["destination"]): item["value"] for item in dumped
            }
            absent = sorted(touched - set(baseline))
            if absent:
                raise RuntimeError(f"wmediumd matrix lacks {len(absent)} required pairs")
            restore_updates = [
                {"source": source, "destination": destination,
                 "value": baseline[(source, destination)]}
                for source, destination in sorted(touched)
            ]
            try:
                # Establish the visual formation in the same two-client
                # phases used by the carousel. Releasing all ten clients at
                # once is a separate association-burst stress case and can
                # obscure this scenario with controller event-path overload.
                for group_index, group in enumerate(groups):
                    targets = {
                        client["container"]: formation_targets[client["container"]]
                        for client in group
                    }
                    generation += 1
                    control.apply(
                        generation,
                        matrix_updates(group, aps, targets,
                                       args.strong_snr, args.outage_snr),
                    )
                    prime_candidate_scans(group, aps_by_container, targets)
                    self.recorder.write(
                        "formation_group_applied", generation=generation,
                        group=group_index + 1, targets=targets,
                    )
                    elapsed, formed = self.wait_for(
                        args.connect_timeout,
                        lambda group=group, targets=targets: (
                            assignment_reached(
                                (value := observe(group, bssid_to_ap, node_to_ap,
                                                  args.topology_url)), targets
                            ), value
                        ),
                        f"carousel formation for group {group_index + 1}",
                    )
                    self.recorder.write(
                        "formation_group_converged", elapsed_ms=elapsed,
                        group=group_index + 1, observation=formed,
                    )

                elapsed, formed = self.wait_for(
                    args.connect_timeout,
                    lambda: (
                        radio_assignment_reached(
                            (value := observe(clients, bssid_to_ap, node_to_ap,
                                              args.topology_url)), formation_targets
                        ), value
                    ),
                    "complete radio carousel formation",
                )
                self.recorder.write("formation_converged", elapsed_ms=elapsed,
                                    observation=formed)
                self.hold(args.formation_hold)

                round_index = 0
                while args.rounds == 0 or round_index < args.rounds:
                    round_index += 1
                    for group_index, group in enumerate(groups):
                        if self.stop_requested:
                            raise InterruptedError("carousel interrupted")
                        source_index = positions[group_index]
                        target_index = (source_index + 1) % len(aps)
                        source_ap = aps[source_index]
                        target_ap = aps[target_index]
                        labels = [client["label"] for client in group]
                        print(
                            f"BLACKOUT round={round_index} group={group_index + 1} "
                            f"{','.join(labels)} {source_ap['node_name']} -> DISCONNECTED",
                            flush=True,
                        )
                        blackout_targets = {client["container"]: None for client in group}
                        generation += 1
                        control.apply(
                            generation,
                            matrix_updates(group, aps, blackout_targets,
                                           args.strong_snr, args.outage_snr),
                        )
                        # -20 dB alone still permits the supplicant to attempt
                        # another candidate. Hold the station link down so the
                        # disconnect interval is real and repeatable.
                        set_client_link(group, "down")
                        self.recorder.write(
                            "blackout_applied", generation=generation, round=round_index,
                            group=group_index + 1, clients=labels,
                            source=source_ap["node_name"], target=target_ap["node_name"],
                        )
                        elapsed, absent_state = self.wait_for(
                            args.disconnect_timeout,
                            lambda: (
                                radio_disconnected(
                                    (value := observe(group, bssid_to_ap, node_to_ap,
                                                      args.topology_url))
                                ), value
                            ),
                            f"{','.join(labels)} radio disconnect",
                        )
                        self.recorder.write(
                            "group_disconnected", elapsed_ms=elapsed, round=round_index,
                            group=group_index + 1, clients=labels,
                            observation=absent_state,
                        )
                        self.hold(args.blackout_hold)

                        print(
                            f"ARRIVAL  round={round_index} group={group_index + 1} "
                            f"{','.join(labels)} DISCONNECTED -> {target_ap['node_name']}",
                            flush=True,
                        )
                        targets = {
                            client["container"]: target_ap["container"] for client in group
                        }
                        generation += 1
                        control.apply(
                            generation,
                            matrix_updates(group, aps, targets,
                                           args.strong_snr, args.outage_snr),
                        )
                        set_client_link(group, "up")
                        prime_candidate_scans(group, aps_by_container, targets)
                        self.recorder.write(
                            "arrival_applied", generation=generation, round=round_index,
                            group=group_index + 1, clients=labels,
                            target=target_ap["node_name"],
                        )
                        elapsed, arrived = self.wait_for(
                            args.connect_timeout,
                            lambda: (
                                assignment_reached(
                                    (value := observe(group, bssid_to_ap, node_to_ap,
                                                      args.topology_url)), targets
                                ), value
                            ),
                            f"{','.join(labels)} at {target_ap['node_name']}",
                        )
                        self.recorder.write(
                            "group_arrived", elapsed_ms=elapsed, round=round_index,
                            group=group_index + 1, clients=labels,
                            target=target_ap["node_name"], observation=arrived,
                        )
                        positions[group_index] = target_index
                        self.hold(args.arrival_hold)
                    rounds_completed = round_index
                outcome = "passed"
            except InterruptedError as error:
                interrupted = True
                outcome = "interrupted"
                error_text = str(error)
            except Exception as error:
                error_text = str(error)
                failure = error
                try:
                    self.collect_failure_evidence(
                        output, clients, aps, bssid_to_ap, node_to_ap,
                        args.topology_url,
                    )
                except Exception as evidence_error:
                    self.recorder.write(
                        "failure_evidence_error", error=str(evidence_error)
                    )
            finally:
                # Return one group at a time.  Releasing all ten stations in
                # one atomic generation creates a synthetic association burst
                # that can overrun the controller's event path even though the
                # actual links recover.  Phased restoration also makes a
                # failed group explicit in the evidence.
                try:
                    set_client_link(clients, "up")
                    for group_index, group in enumerate(groups):
                        targets = {
                            client["container"]: original_targets[client["container"]]
                            for client in group
                        }
                        generation += 1
                        control.apply(
                            generation,
                            matrix_updates(group, aps, targets,
                                           args.strong_snr, args.outage_snr),
                        )
                        prime_candidate_scans(group, aps_by_container, targets)
                        elapsed, returned = self.wait_for(
                            args.return_timeout,
                            lambda group=group, targets=targets: (
                                radio_assignment_reached(
                                    (value := observe(group, bssid_to_ap, node_to_ap,
                                                      args.topology_url)), targets
                                ), value
                            ),
                            f"preflight placement for group {group_index + 1}",
                            allow_stop=False,
                        )
                        self.recorder.write(
                            "placement_group_restored", group=group_index + 1,
                            elapsed_ms=elapsed, observation=returned,
                        )

                    # A delayed association notification can overwrite a
                    # newer controller parent after an individual group has
                    # already converged. Require the complete placement to be
                    # stable, and repair only mismatched stations by bouncing
                    # them through a different RF-reachable AP and back. A
                    # simple wlan0 down/up on the same BSSID is insufficient
                    # because it need not produce a new parent transition.
                    repair_timeout = min(args.return_timeout, 30)
                    for repair_attempt in range(1, 4):
                        try:
                            elapsed, returned = self.wait_for_stable(
                                repair_timeout, args.restore_settle,
                                lambda: (
                                    assignment_reached(
                                        (value := observe(
                                            clients, bssid_to_ap, node_to_ap,
                                            args.topology_url,
                                        )), original_targets
                                    ), value
                                ),
                                "stable preflight client placement",
                            )
                            break
                        except RuntimeError:
                            current = observe(
                                clients, bssid_to_ap, node_to_ap, args.topology_url
                            )
                            names = assignment_mismatches(current, original_targets)
                            repair = [
                                client for client in clients
                                if client["container"] in names
                            ]
                            if not repair or repair_attempt == 3:
                                raise
                            alternate_targets = {}
                            for client in repair:
                                original_index = next(
                                    index for index, ap in enumerate(aps)
                                    if ap["container"]
                                    == original_targets[client["container"]]
                                )
                                alternate_targets[client["container"]] = aps[
                                    (original_index + 1) % len(aps)
                                ]["container"]
                            self.recorder.write(
                                "placement_repair_started", attempt=repair_attempt,
                                clients=[client["label"] for client in repair],
                                observation=current,
                            )
                            set_client_link(repair, "down")
                            generation += 1
                            control.apply(
                                generation,
                                matrix_updates(
                                    repair, aps, alternate_targets,
                                    args.strong_snr, args.outage_snr,
                                ),
                            )
                            set_client_link(repair, "up")
                            prime_candidate_scans(
                                repair, aps_by_container, alternate_targets
                            )
                            self.wait_for(
                                repair_timeout,
                                lambda: (
                                    assignment_reached(
                                        (value := observe(
                                            repair, bssid_to_ap, node_to_ap,
                                            args.topology_url,
                                        )), alternate_targets
                                    ), value
                                ),
                                "placement repair alternate AP", allow_stop=False,
                            )
                            repair_targets = {
                                client["container"]:
                                original_targets[client["container"]]
                                for client in repair
                            }
                            set_client_link(repair, "down")
                            generation += 1
                            control.apply(
                                generation,
                                matrix_updates(
                                    repair, aps, repair_targets,
                                    args.strong_snr, args.outage_snr,
                                ),
                            )
                            set_client_link(repair, "up")
                            prime_candidate_scans(
                                repair, aps_by_container, repair_targets
                            )
                            self.wait_for(
                                repair_timeout,
                                lambda: (
                                    assignment_reached(
                                        (value := observe(
                                            repair, bssid_to_ap, node_to_ap,
                                            args.topology_url,
                                        )), repair_targets
                                    ), value
                                ),
                                "placement repair original AP", allow_stop=False,
                            )
                            self.recorder.write(
                                "placement_repair_completed", attempt=repair_attempt,
                                clients=[client["label"] for client in repair],
                            )
                    placement_restored = True
                    self.recorder.write("placement_restored", elapsed_ms=elapsed,
                                        observation=returned)
                except Exception as cleanup_error:
                    self.recorder.write("placement_restore_failed", error=str(cleanup_error))
                    if failure is None and not interrupted:
                        failure = cleanup_error
                        error_text = str(cleanup_error)
                        outcome = "failed"
                finally:
                    generation += 1
                    control.apply(generation, restore_updates)
                    restored = all(
                        control.get_link(item["source"], item["destination"])[1]
                        == item["value"]
                        for item in restore_updates
                    )
                    self.recorder.write("medium_restored", generation=generation,
                                        verified=restored)
                    if not restored:
                        raise RuntimeError("wmediumd baseline restoration failed")

        final_document = fetch_topology(args.topology_url)
        if final_document:
            (output / "topology-after.json").write_text(
                json.dumps(final_document, indent=2, sort_keys=True) + "\n"
            )
        summary = {
            "scenario": "five_ap_client_carousel",
            "outcome": outcome,
            "error": error_text,
            "interrupted": interrupted,
            "medium_restored": restored,
            "placement_restored": placement_restored,
            "rounds_completed": rounds_completed,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        print(f"{outcome.upper()} artifacts={output}", flush=True)
        if interrupted:
            raise InterruptedError(error_text)
        if failure:
            raise failure
        return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visually rotate WLAN client groups through every EasyMesh AP"
    )
    parser.add_argument(
        "--ssid", choices=("private_ssid", "iot_ssid"), default="private_ssid",
        help="client cohort and matching fronthaul BSS set to move",
    )
    parser.add_argument("--rounds", type=int, default=2,
                        help="full one-hop rotations; 0 runs until Ctrl-C (default: 2)")
    parser.add_argument("--strong-snr", type=int, default=45)
    parser.add_argument("--outage-snr", type=int, default=-20)
    parser.add_argument("--formation-hold", type=float, default=5)
    parser.add_argument("--blackout-hold", type=float, default=4)
    parser.add_argument("--arrival-hold", type=float, default=4)
    parser.add_argument("--disconnect-timeout", type=float, default=30)
    parser.add_argument("--connect-timeout", type=float, default=60)
    parser.add_argument("--return-timeout", type=float, default=90)
    parser.add_argument(
        "--restore-settle", type=float, default=6,
        help="seconds the final client/API placement must remain stable",
    )
    parser.add_argument("--socket", default="/run/wmediumd-control.sock")
    parser.add_argument(
        "--topology-url", default="http://127.0.0.1:8888/api/v1/topology"
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("/tmp/wmediumd-client-carousel")
    )
    args = parser.parse_args()
    if args.rounds < 0:
        parser.error("--rounds must be zero or greater")
    if not -20 <= args.outage_snr <= 60 or not -20 <= args.strong_snr <= 60:
        parser.error("SNR values must be within [-20, 60]")
    if args.strong_snr <= args.outage_snr:
        parser.error("--strong-snr must exceed --outage-snr")
    if any(
        value < 0 for value in (
            args.formation_hold, args.blackout_hold, args.arrival_hold,
            args.disconnect_timeout, args.connect_timeout, args.return_timeout,
            args.restore_settle,
        )
    ):
        parser.error("holds and timeouts cannot be negative")

    carousel = Carousel(args)
    old_handlers = {
        signum: signal.signal(signum, carousel.request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        carousel.execute()
        return 0
    except InterruptedError:
        return 130
    except (OSError, RuntimeError, ActuatorError, subprocess.SubprocessError) as error:
        print(f"client-carousel: {error}", file=sys.stderr)
        return 2
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
