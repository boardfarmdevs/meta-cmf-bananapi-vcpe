#!/usr/bin/env python3
"""Exercise client and complete-extender RF loss through wmediumd's socket."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
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
        # Statuses below 128 belong to the command inside the container;
        # callers intentionally interpret its output.  LXD may expose a lost
        # signal as either -N or 128+N, so both forms receive a read-only retry.
        if 0 <= result.returncode < 128:
            return result.stdout.strip()
        if attempt < 3:
            time.sleep(0.5 * attempt)
    raise subprocess.CalledProcessError(
        result.returncode, result.args, output=result.stdout, stderr=result.stderr
    )


def topology(url: str) -> dict:
    return json.loads(
        run("curl", "-fsS", "--connect-timeout", "3", "--max-time", "15", url)
    )


def client_bssid(container: str) -> str | None:
    for line in lxc(container, "iw dev wlan0 link 2>/dev/null").splitlines():
        value = line.strip()
        if value.startswith("Connected to "):
            return value.split()[2].lower()
    return None


def client_mac(container: str) -> str:
    return lxc(container, "cat /sys/class/net/wlan0/address").lower()


def topology_owner(document: dict, sta_mac: str) -> str | None:
    sta_mac = sta_mac.lower()
    for node in document.get("nodes", []):
        if any(item.get("staMAC", "").lower() == sta_mac for item in (node.get("STAList") or [])):
            return str(node.get("id"))
    return None


def topology_bssid_owner(document: dict, bssid: str) -> str | None:
    bssid = bssid.lower()
    for node in document.get("nodes", []):
        for haul in node.get("haulTypes") or []:
            for item in haul.get("BSSList") or []:
                if item.get("BSSID", "").lower() == bssid:
                    return str(node.get("id")).lower()
    return None


def client_consistency(document: dict, stations: list[dict]) -> list[dict]:
    observations = []
    for item in stations:
        name = item["container"]
        sta_mac = client_mac(name)
        bssid = client_bssid(name)
        api_owner = topology_owner(document, sta_mac)
        bssid_owner = topology_bssid_owner(document, bssid) if bssid else None
        observations.append(
            {
                "client": name,
                "sta_mac": sta_mac,
                "bssid": bssid,
                "api_owner": api_owner,
                "bssid_owner": bssid_owner,
                "agreed": bool(
                    bssid and api_owner and bssid_owner
                    and api_owner.lower() == bssid_owner
                ),
            }
        )
    return observations


def service_state(unit: str) -> dict:
    values = {}
    output = lxc(
        "bpibroadband",
        f"systemctl show {unit} --property=MainPID --property=NRestarts --property=ActiveState",
    )
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = int(value) if value.isdigit() else value
    return values


def extender_id(container: str) -> str:
    base = lxc(container, "cat /nvram/em_al_base_mac").lower()
    parts = base.split(":")
    if len(parts) != 6:
        raise RuntimeError(f"{container}: invalid EasyMesh base AL-MAC {base!r}")
    parts[-1] = f"{(int(parts[-1], 16) + 0x20) & 0xff:02x}"
    return ":".join(parts)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Recorder:
    def __init__(self, path: Path):
        self.path = path

    def write(self, event: str, **fields) -> None:
        value = {"at": now(), "event": event, **fields}
        with self.path.open("a") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
        print(json.dumps(value, sort_keys=True), flush=True)


def wait_until(timeout: float, interval: float, predicate):
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        last = predicate()
        if last:
            return round((time.monotonic() - started) * 1000), last
        time.sleep(interval)
    return -1, last


def wait_stable(timeout: float, interval: float, stable_for: float, predicate):
    """Require predicate to remain true continuously before accepting it."""
    started = time.monotonic()
    stable_started = None
    last = None
    while time.monotonic() - started < timeout:
        last = predicate()
        if last:
            if stable_started is None:
                stable_started = time.monotonic()
            if time.monotonic() - stable_started >= stable_for:
                return round((time.monotonic() - started) * 1000), last
        else:
            stable_started = None
        time.sleep(interval)
    return -1, last


def updates_for(pairs: list[tuple[str, str]], value: int) -> list[dict]:
    return [
        {"source": source, "destination": destination, "value": value}
        for source, destination in pairs
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate client-facing and complete extender RF outage"
    )
    parser.add_argument("--extender", default="bpiap-003")
    parser.add_argument("--socket", default="/run/wmediumd-control.sock")
    parser.add_argument("--topology-url", default="http://127.0.0.1:8888/api/v1/topology")
    parser.add_argument("--outage-snr", type=int, default=-20)
    parser.add_argument("--prepare-snr", type=int, default=55)
    parser.add_argument("--prepare-timeout", type=int, default=90)
    parser.add_argument("--client-timeout", type=int, default=90)
    parser.add_argument("--node-timeout", type=int, default=90)
    parser.add_argument(
        "--recovery-timeout", type=int, default=120,
        help=(
            "seconds allowed for client/controller convergence before the "
            "requested stability window begins"
        ),
    )
    parser.add_argument(
        "--stability-window", type=int, default=75,
        help="seconds all physical/API client ownership must remain consistent",
    )
    parser.add_argument("--skip-full-outage", action="store_true")
    parser.add_argument(
        "--allow-stale-node", action="store_true",
        help="diagnostic mode: do not fail when an isolated extender remains in the API",
    )
    parser.add_argument(
        "--allow-preflight-disagreement", action="store_true",
        help="diagnostic mode: permit unrelated physical/API client disagreement",
    )
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/wmediumd-extender-outage"))
    args = parser.parse_args()
    if not -20 <= args.outage_snr <= 60:
        parser.error("--outage-snr must be within [-20, 60]")
    if not -20 <= args.prepare_snr <= 60:
        parser.error("--prepare-snr must be within [-20, 60]")
    if args.prepare_snr <= args.outage_snr:
        parser.error("--prepare-snr must be greater than --outage-snr")
    if args.prepare_timeout <= 0:
        parser.error("--prepare-timeout must be greater than zero")
    if args.stability_window <= 0:
        parser.error("--stability-window must be greater than zero")
    if args.recovery_timeout <= 0:
        parser.error("--recovery-timeout must be greater than zero")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root / f"{stamp}-{args.extender}"
    output.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(output / "events.jsonl")
    inventory = discover()
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    radios = {item["container"]: item for item in inventory["radios"]}
    if args.extender not in radios or radios[args.extender]["kind"] != "mesh":
        raise RuntimeError(f"unknown extender {args.extender!r}")

    extender = radios[args.extender]
    extender_tx = extender["tx_mac"]
    extender_bssids = {
        item["mac"].lower()
        for item in extender["interfaces"]
        if item.get("ssid") == "private_ssid"
    }
    impacted = [
        item for item in radios.values()
        if item["kind"] == "station" and item.get("associated_bssid") in extender_bssids
    ]
    stations = [item for item in radios.values() if item["kind"] == "station"]
    if not stations:
        raise RuntimeError("no WLAN clients were discovered")

    node_id = extender_id(args.extender)
    initial_topology = topology(args.topology_url)
    (output / "topology-before.json").write_text(
        json.dumps(initial_topology, indent=2, sort_keys=True) + "\n"
    )
    if not any(str(node.get("id")).lower() == node_id for node in initial_topology.get("nodes", [])):
        raise RuntimeError(f"extender {node_id} is absent before the test")
    initial_consistency = client_consistency(initial_topology, stations)
    (output / "client-consistency-before.json").write_text(
        json.dumps(initial_consistency, indent=2, sort_keys=True) + "\n"
    )
    if (not args.allow_preflight_disagreement
            and any(not item["agreed"] for item in initial_consistency)):
        raise RuntimeError("physical links and controller topology disagree before the test")

    services_before = {
        unit: service_state(unit) for unit in ("ieee1905_em_ctrl.service", "em_ctrl.service")
    }

    all_pairs = [
        pair
        for item in radios.values()
        if item["tx_mac"] != extender_tx
        for pair in ((extender_tx, item["tx_mac"]), (item["tx_mac"], extender_tx))
    ]

    summary = {
        "extender": args.extender,
        "extender_node_id": node_id,
        "impacted_clients": [item["container"] for item in impacted],
        "client_preconditioned": False,
        "client_rf_loss": "failed",
        "full_extender_rf_loss": "skipped" if args.skip_full_outage else "failed",
        "backhaul_lost": None,
        "extender_disappeared_from_api": None,
        "restored": False,
    }
    recorder.write(
        "preflight",
        extender=args.extender,
        extender_tx=extender_tx,
        extender_node_id=node_id,
        impacted_clients=summary["impacted_clients"],
        topology_nodes=len(initial_topology.get("nodes", [])),
    )

    with ControlClient(args.socket) as control:
        status = control.status()
        required = {"radio_pair_snr", "atomic_generations", "readback", "dump_links"}
        if not required.issubset(status.capabilities):
            raise RuntimeError(f"wmediumd lacks {sorted(required - status.capabilities)}")
        generation, dumped = control.dump_links()
        baseline = {
            (item["source"], item["destination"]): item["value"] for item in dumped
        }
        restore_pairs = set(all_pairs)
        prepare_pairs = set()
        prepare_client = None
        if not impacted:
            prepare_client = sorted(stations, key=lambda item: item["container"])[0]
            prepare_pairs = {
                pair
                for item in radios.values()
                if item["kind"] == "mesh"
                for pair in (
                    (prepare_client["tx_mac"], item["tx_mac"]),
                    (item["tx_mac"], prepare_client["tx_mac"]),
                )
            }
            restore_pairs.update(prepare_pairs)

        missing = sorted(restore_pairs - set(baseline))
        if missing:
            raise RuntimeError(f"wmediumd matrix lacks radio pairs: {missing}")
        restore = [
            {"source": source, "destination": destination, "value": baseline[(source, destination)]}
            for source, destination in sorted(restore_pairs)
        ]
        try:
            if prepare_client is not None:
                prepare_updates = []
                for item in radios.values():
                    if item["kind"] != "mesh":
                        continue
                    value = (
                        args.prepare_snr
                        if item["container"] == args.extender
                        else args.outage_snr
                    )
                    prepare_updates.extend(
                        updates_for(
                            [
                                (prepare_client["tx_mac"], item["tx_mac"]),
                                (item["tx_mac"], prepare_client["tx_mac"]),
                            ],
                            value,
                        )
                    )

                generation += 1
                control.apply(generation, prepare_updates)
                recorder.write(
                    "client_precondition_applied",
                    generation=generation,
                    client=prepare_client["container"],
                    target_extender=args.extender,
                    target_snr=args.prepare_snr,
                    other_mesh_snr=args.outage_snr,
                )

                def client_prepared():
                    bssid = client_bssid(prepare_client["container"])
                    owner = topology_owner(
                        topology(args.topology_url),
                        client_mac(prepare_client["container"]),
                    )
                    ready = bool(
                        bssid in extender_bssids
                        and owner
                        and owner.lower() == node_id
                    )
                    return {"bssid": bssid, "topology_owner": owner} if ready else None

                prepared_ms, prepared = wait_until(
                    args.prepare_timeout, 0.5, client_prepared
                )
                recorder.write(
                    "client_precondition_reached",
                    elapsed_ms=prepared_ms,
                    observation=prepared,
                )
                if prepared_ms < 0:
                    raise RuntimeError(
                        f"could not place {prepare_client['container']} on {args.extender}"
                    )

                generation += 1
                prepare_restore = [
                    {
                        "source": source,
                        "destination": destination,
                        "value": baseline[(source, destination)],
                    }
                    for source, destination in sorted(prepare_pairs)
                ]
                control.apply(generation, prepare_restore)
                prepare_restored = all(
                    control.get_link(item["source"], item["destination"])[1]
                    == item["value"]
                    for item in prepare_restore
                )
                recorder.write(
                    "client_precondition_medium_restored",
                    generation=generation,
                    verified=prepare_restored,
                )
                if not prepare_restored:
                    raise RuntimeError("client precondition did not restore the RF baseline")

                stable_ms, stable = wait_stable(
                    min(args.prepare_timeout, 30),
                    0.5,
                    3,
                    client_prepared,
                )
                recorder.write(
                    "client_precondition_stable",
                    elapsed_ms=stable_ms,
                    observation=stable,
                )
                if stable_ms < 0:
                    raise RuntimeError(
                        "prepared client did not remain on the extender after RF restoration"
                    )
                impacted = [prepare_client]
                summary["impacted_clients"] = [prepare_client["container"]]
                summary["client_preconditioned"] = True

            client_pairs = []
            for item in impacted:
                client_pairs.extend(
                    [
                        (item["tx_mac"], extender_tx),
                        (extender_tx, item["tx_mac"]),
                    ]
                )

            generation += 1
            control.apply(generation, updates_for(client_pairs, args.outage_snr))
            recorder.write("client_rf_loss_applied", generation=generation, snr=args.outage_snr)

            def clients_moved():
                observations = []
                complete = True
                document = topology(args.topology_url)
                for item in impacted:
                    name = item["container"]
                    bssid = client_bssid(name)
                    owner = topology_owner(document, client_mac(name))
                    moved = bool(bssid and bssid not in extender_bssids)
                    converged = bool(moved and owner and owner.lower() != node_id)
                    observations.append(
                        {"client": name, "bssid": bssid, "topology_owner": owner,
                         "moved": moved, "converged": converged}
                    )
                    complete = complete and converged
                return observations if complete else None

            move_ms, moved = wait_until(args.client_timeout, 0.5, clients_moved)
            recorder.write("clients_moved", elapsed_ms=move_ms, observations=moved)
            if move_ms < 0:
                raise RuntimeError("affected clients did not move and converge in topology")
            summary["client_rf_loss"] = "passed"

            if not args.skip_full_outage:
                generation += 1
                control.apply(generation, updates_for(all_pairs, args.outage_snr))
                recorder.write("full_extender_rf_loss_applied", generation=generation,
                               snr=args.outage_snr)

                def backhaul_absent():
                    link = lxc(args.extender, "iw dev wifi1.3 link 2>/dev/null")
                    return {"link": link or "Not connected"} if "Connected to" not in link else None

                backhaul_ms, backhaul = wait_until(
                    min(args.node_timeout, 60), 1.0, backhaul_absent
                )
                summary["backhaul_lost"] = backhaul_ms >= 0
                recorder.write("extender_backhaul_loss", elapsed_ms=backhaul_ms,
                               disconnected=backhaul_ms >= 0, observation=backhaul)
                if backhaul_ms < 0:
                    raise RuntimeError("extender backhaul did not fail under full RF isolation")

                def node_absent():
                    document = topology(args.topology_url)
                    ids = [str(node.get("id")).lower() for node in document.get("nodes", [])]
                    return {"topology_nodes": len(ids)} if node_id not in ids else None

                absent_ms, absent = wait_until(args.node_timeout, 1.0, node_absent)
                summary["extender_disappeared_from_api"] = absent_ms >= 0
                recorder.write("extender_api_absence", elapsed_ms=absent_ms,
                               disappeared=absent_ms >= 0, observation=absent)
                if absent_ms < 0 and not args.allow_stale_node:
                    raise RuntimeError("isolated extender did not disappear from controller topology")
                summary["full_extender_rf_loss"] = "passed"
        finally:
            generation += 1
            control.apply(generation, restore)
            restored = all(
                control.get_link(item["source"], item["destination"])[1] == item["value"]
                for item in restore
            )
            summary["restored"] = restored
            recorder.write("medium_restored", generation=generation, verified=restored)
            if not restored:
                raise RuntimeError("wmediumd baseline restoration failed")

    def extender_recovered():
        document = topology(args.topology_url)
        present = any(
            str(node.get("id")).lower() == node_id for node in document.get("nodes", [])
        )
        backhaul = "Connected to" in lxc(args.extender, "iw dev wifi1.3 link 2>/dev/null")
        return {"present": present, "backhaul": backhaul} if present and backhaul else None

    recovered_ms, recovered = wait_until(args.recovery_timeout, 1.0, extender_recovered)
    recorder.write("extender_recovered", elapsed_ms=recovered_ms, observation=recovered)
    if recovered_ms < 0:
        raise RuntimeError("extender did not recover after medium restoration")

    def clients_converged():
        document = topology(args.topology_url)
        observations = client_consistency(document, stations)
        return observations if all(item["agreed"] for item in observations) else None

    # Recovery and stability are separate requirements.  The former timeout
    # bounds how long the stack may take to regain agreement; it must not also
    # consume the continuous stability window.  Allowing their sum means a
    # stable interval has to begin within recovery_timeout seconds.
    convergence_ms, final_consistency = wait_stable(
        args.recovery_timeout + args.stability_window,
        1.0,
        args.stability_window,
        clients_converged,
    )
    recorder.write(
        "all_clients_converged", elapsed_ms=convergence_ms,
        recovery_timeout_seconds=args.recovery_timeout,
        stability_window_seconds=args.stability_window,
        observations=final_consistency,
    )
    if convergence_ms < 0:
        raise RuntimeError(
            "physical links and controller topology did not remain converged"
        )
    (output / "client-consistency-after.json").write_text(
        json.dumps(final_consistency, indent=2, sort_keys=True) + "\n"
    )

    traffic = {
        item["container"]: lxc(
            item["container"],
            "ping -c 3 -W 1 10.0.0.1 >/dev/null 2>&1 && echo pass || echo fail",
        )
        for item in stations
    }
    recorder.write("client_traffic", results=traffic)
    if any(value != "pass" for value in traffic.values()):
        raise RuntimeError("one or more clients have no post-recovery traffic")

    services_after = {
        unit: service_state(unit) for unit in ("ieee1905_em_ctrl.service", "em_ctrl.service")
    }
    recorder.write("service_stability", before=services_before, after=services_after)
    if services_before != services_after:
        raise RuntimeError("controller service PID, restart count or state changed during test")

    final_topology = topology(args.topology_url)
    (output / "topology-after.json").write_text(
        json.dumps(final_topology, indent=2, sort_keys=True) + "\n"
    )
    summary["outcome"] = "passed"
    summary["services"] = services_after
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"PASS artifacts={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
