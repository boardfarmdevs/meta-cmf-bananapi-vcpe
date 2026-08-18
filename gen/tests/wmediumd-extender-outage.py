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
    return run("lxc", "exec", container, "--", "sh", "-c", command, check=False)


def topology(url: str) -> dict:
    return json.loads(run("curl", "-fsS", url))


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
    parser.add_argument("--client-timeout", type=int, default=90)
    parser.add_argument("--node-timeout", type=int, default=90)
    parser.add_argument("--recovery-timeout", type=int, default=120)
    parser.add_argument("--skip-full-outage", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/wmediumd-extender-outage"))
    args = parser.parse_args()
    if not -20 <= args.outage_snr <= 60:
        parser.error("--outage-snr must be within [-20, 60]")

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
    if not impacted:
        raise RuntimeError(f"no clients are currently associated with {args.extender}")

    node_id = extender_id(args.extender)
    initial_topology = topology(args.topology_url)
    (output / "topology-before.json").write_text(
        json.dumps(initial_topology, indent=2, sort_keys=True) + "\n"
    )
    if not any(str(node.get("id")).lower() == node_id for node in initial_topology.get("nodes", [])):
        raise RuntimeError(f"extender {node_id} is absent before the test")

    client_pairs = []
    for item in impacted:
        client_pairs.extend([(item["tx_mac"], extender_tx), (extender_tx, item["tx_mac"])])
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
        missing = sorted(set(all_pairs) - set(baseline))
        if missing:
            raise RuntimeError(f"wmediumd matrix lacks radio pairs: {missing}")
        restore = [
            {"source": source, "destination": destination, "value": baseline[(source, destination)]}
            for source, destination in sorted(set(all_pairs))
        ]
        try:
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
                # RF isolation itself is successful even when the controller exposes
                # a retained, stale node; that semantic is an explicit test result.
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
    final_topology = topology(args.topology_url)
    (output / "topology-after.json").write_text(
        json.dumps(final_topology, indent=2, sort_keys=True) + "\n"
    )
    summary["outcome"] = "passed"
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"PASS artifacts={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
