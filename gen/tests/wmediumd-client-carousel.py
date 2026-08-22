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
        if result.returncode >= 0:
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


def sta_label(mac: str) -> str:
    octets = mac.upper().split(":")
    if (
        len(octets) == 6
        and octets[:4] == ["02", "00", "00", "00"]
        and octets[5] == "00"
    ):
        return f"STA-{octets[4]}"
    return f"STA-{'-'.join(octets[-3:])}" if len(octets) == 6 else "STA"


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


def topology_owner(document: dict, mac: str) -> str | None:
    for node in document.get("nodes", []):
        if any(
            item.get("staMAC", "").lower() == mac
            for item in (node.get("STAList") or [])
        ):
            return str(node.get("id", "")).lower() or None
    return None


def private_bssids(radio: dict) -> set[str]:
    return {
        item["mac"].lower()
        for item in radio.get("interfaces", [])
        if item.get("ssid") == "private_ssid" and item.get("mac")
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
        owner = topology_owner(document, client["mac"]) if document else None
        stations.append(
            {
                "client": client["container"],
                "label": client["label"],
                "bssid": bssid,
                "actual_ap": bssid_to_ap.get(bssid) if bssid else None,
                "topology_owner": owner,
                "topology_ap": node_to_ap.get(owner) if owner else None,
            }
        )
    return {"valid_topology": document is not None, "stations": stations}


def assignment_reached(observation: dict, targets: dict[str, str]) -> bool:
    return bool(observation["valid_topology"]) and all(
        item["actual_ap"] == targets[item["client"]]
        and item["topology_ap"] == targets[item["client"]]
        for item in observation["stations"]
    )


def radio_disconnected(observation: dict) -> bool:
    return all(item["bssid"] is None for item in observation["stations"])


def set_client_link(clients: list[dict], state: str) -> None:
    for client in clients:
        run("lxc", "exec", client["container"], "--",
            "ip", "link", "set", "wlan0", state)


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
        # Agent does not advertise the lab's private_ssid.  It is a topology
        # identity, not a client-placement target for this scenario.
        mesh = [
            item for item in inventory["radios"]
            if item["kind"] == "mesh" and private_bssids(item)
        ]
        stations = [item for item in inventory["radios"] if item["kind"] == "station"]
        if len(mesh) < 2 or not stations:
            raise RuntimeError(f"need at least two APs and one client; found {len(mesh)}/{len(stations)}")

        aps = []
        for item in mesh:
            bssids = private_bssids(item)
            identity = topology_ap_identity(document, bssids)
            if not bssids or not identity:
                raise RuntimeError(f"{item['container']}: no live private BSS topology identity")
            node_id, node_name = identity
            aps.append(
                {**item, "bssids": bssids, "node_id": node_id, "node_name": node_name}
            )
        aps.sort(key=ap_order)

        clients = []
        for item in sorted(stations, key=lambda entry: natural_key(entry["container"])):
            mac = client_mac(item["container"])
            clients.append({**item, "mac": mac, "label": sta_label(mac)})

        bssid_to_ap = {
            bssid: ap["container"] for ap in aps for bssid in ap["bssids"]
        }
        node_to_ap = {ap["node_id"]: ap["container"] for ap in aps}
        original_targets = {}
        for client in clients:
            bssid = client_bssid(client["container"])
            target = bssid_to_ap.get(bssid) if bssid else None
            if not target:
                raise RuntimeError(
                    f"{client['container']}: not associated to a known private BSS ({bssid})"
                )
            original_targets[client["container"]] = target

        preflight = observe(clients, bssid_to_ap, node_to_ap, args.topology_url)
        if not preflight["valid_topology"] or any(
            item["topology_ap"] is None for item in preflight["stations"]
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
        print("\nOpen the Network Topology tab and watch the printed STA labels.", flush=True)
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
                        assignment_reached(
                            (value := observe(clients, bssid_to_ap, node_to_ap,
                                              args.topology_url)), formation_targets
                        ), value
                    ),
                    "complete carousel formation",
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
                        elapsed, returned = self.wait_for(
                            args.return_timeout,
                            lambda group=group, targets=targets: (
                                assignment_reached(
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
                    elapsed, returned = self.wait_for(
                        args.return_timeout,
                        lambda: (
                            assignment_reached(
                                (value := observe(clients, bssid_to_ap, node_to_ap,
                                                  args.topology_url)), original_targets
                            ), value
                        ),
                        "preflight client placement", allow_stop=False,
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
