#!/usr/bin/env python3
"""Apply and exactly restore one client's deterministic steering RF bias."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


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


def medium_client(args: argparse.Namespace):
    if args.backend == "userspace":
        return ControlClient(args.socket)
    if args.backend == "kernel":
        return KernelMediumClient(
            args.kernel_root, noise_floor_dbm=args.noise_floor_dbm
        )
    raise RuntimeError(f"unsupported medium backend {args.backend!r}")


def normalize_mac(value: str) -> str:
    return value.strip().lower()


def write_state(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def snapshot_frequency_links(
    control: ControlClient,
    pairs: list[tuple[str, str]],
    frequency_mhz: int,
):
    """Read effective frequency links with bounded bulk control requests.

    A frequency-qualified link inherits its value from the base radio-pair
    matrix unless an explicit frequency override exists.  Reading every pair
    with OP_GET_FREQUENCY serializes one control round trip per direction and
    can exceed steer.sh's safety deadline while wmediumd is handling traffic.
    The two dump operations provide the same information in fixed request
    cardinality.  Matching generations make the composed snapshot coherent;
    a concurrent writer is rejected rather than captured ambiguously.
    """
    status = control.status()
    base_generation, base_links = control.dump_links()
    frequency_generation, frequency_links = control.dump_frequency_links()
    final_status = control.status()
    generations = {
        status.generation,
        base_generation,
        frequency_generation,
        final_status.generation,
    }
    if len(generations) != 1:
        raise RuntimeError("wmediumd generation changed during RF-bias snapshot")

    base = {
        (item["source"], item["destination"]): int(item["value"])
        for item in base_links
    }
    overrides = {
        (
            item["source"],
            item["destination"],
            int(item["frequency_mhz"]),
        ): (int(item["value"]), bool(item["override"]))
        for item in frequency_links
    }
    prior = []
    for source, destination in pairs:
        frequency_key = (source, destination, frequency_mhz)
        if frequency_key in overrides:
            value, overridden = overrides[frequency_key]
        else:
            pair = (source, destination)
            if pair not in base:
                raise RuntimeError(
                    f"wmediumd snapshot has no link {source} -> {destination}"
                )
            value, overridden = base[pair], False
        prior.append({
            "source": source,
            "destination": destination,
            "frequency_mhz": frequency_mhz,
            "value": value,
            "override": overridden,
        })
    return final_status, prior


def apply(args: argparse.Namespace) -> int:
    source_bssid = normalize_mac(args.source_bssid)
    target_bssid = normalize_mac(args.target_bssid)
    if source_bssid == target_bssid:
        raise RuntimeError("source and target BSSIDs are identical")
    explicit = (
        args.station_radio,
        args.source_radio,
        args.target_radio,
        args.mesh_radio,
    )
    if any(explicit):
        if not all((args.station_radio, args.source_radio, args.target_radio)) \
                or not args.mesh_radio:
            raise RuntimeError(
                "explicit radio identities require station, source, target and mesh radios"
            )
        station = normalize_mac(args.station_radio)
        source_radio = normalize_mac(args.source_radio)
        target_radio = normalize_mac(args.target_radio)
        mesh_radios = sorted(set(normalize_mac(value) for value in args.mesh_radio))
        if source_radio not in mesh_radios or target_radio not in mesh_radios:
            raise RuntimeError("source and target must be members of the mesh radio roster")
    else:
        inventory = discover({args.client})["radios"]
        stations = [
            item for item in inventory
            if item["kind"] == "station" and item["container"] == args.client
        ]
        if len(stations) != 1:
            raise RuntimeError(
                f"{args.client}: expected one station radio, found {len(stations)}"
            )
        station = stations[0]["tx_mac"]
        mesh = [item for item in inventory if item["kind"] == "mesh"]
        sources = [
            item for item in mesh
            if any(
                normalize_mac(interface.get("mac", "")) == source_bssid
                and int(interface.get("frequency_mhz") or 0) == args.frequency
                for interface in item.get("interfaces", [])
            )
        ]
        targets = [
            item for item in mesh
            if any(
                normalize_mac(interface.get("mac", "")) == target_bssid
                and int(interface.get("frequency_mhz") or 0) == args.frequency
                for interface in item.get("interfaces", [])
            )
        ]
        if len(sources) != 1:
            raise RuntimeError(
                f"{source_bssid}: expected one {args.frequency} MHz source radio, "
                f"found {len(sources)}"
            )
        if len(targets) != 1:
            raise RuntimeError(
                f"{target_bssid}: expected one {args.frequency} MHz target radio, "
                f"found {len(targets)}"
            )
        source_radio = sources[0]["tx_mac"]
        target_radio = targets[0]["tx_mac"]
        mesh_radios = sorted(item["tx_mac"] for item in mesh)
    updates = []
    pairs = []
    values = {}
    for radio in mesh_radios:
        values[radio] = (
            args.target_snr if radio == target_radio
            else args.source_snr if radio == source_radio
            else args.other_snr
        )
        pairs.extend(((station, radio), (radio, station)))
    with medium_client(args) as control:
        status, prior = snapshot_frequency_links(control, pairs, args.frequency)
        for source, destination in pairs:
            radio = destination if source == station else source
            updates.append({
                "source": source,
                "destination": destination,
                "frequency_mhz": args.frequency,
                "value": values[radio],
                "override": True,
            })
        state = {
            "schema": "easymesh.steering-rf-bias.v1",
            "backend": args.backend,
            "instance_id": status.instance_id,
            "client": args.client,
            "target_bssid": target_bssid,
            "updates": prior,
        }
        write_state(args.state, state)
        control.apply_frequency(status.generation + 1, updates)
    print(
        f"RF bias applied: {args.client} source={source_bssid} "
        f"target={target_bssid} source_snr={args.source_snr} "
        f"target_snr={args.target_snr} other_snr={args.other_snr}"
    )
    return 0


def restore(args: argparse.Namespace) -> int:
    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("schema") != "easymesh.steering-rf-bias.v1":
        raise RuntimeError("unsupported steering RF-bias state")
    updates = state.get("updates") or []
    if not updates:
        raise RuntimeError("steering RF-bias state has no updates")
    state_backend = state.get("backend", "userspace")
    if state_backend != args.backend:
        raise RuntimeError(
            f"RF-bias state belongs to {state_backend}, not {args.backend}"
        )
    with medium_client(args) as control:
        status = control.status()
        if status.instance_id != state.get("instance_id"):
            raise RuntimeError("medium instance changed; exact RF restore is unsafe")
        control.apply_frequency(status.generation + 1, updates)
    args.state.unlink()
    print(f"RF bias restored: {state.get('client', 'unknown')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/wmediumd-control.sock")
    parser.add_argument(
        "--backend",
        choices=("userspace", "kernel"),
        default=os.environ.get("EASYMESH_MEDIUM_BACKEND", "userspace"),
    )
    parser.add_argument("--kernel-root", default="/sys/kernel/debug/ieee80211")
    parser.add_argument("--noise-floor-dbm", type=int, default=-91)
    commands = parser.add_subparsers(dest="command", required=True)

    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--client", required=True)
    apply_parser.add_argument("--source-bssid", required=True)
    apply_parser.add_argument("--target-bssid", required=True)
    apply_parser.add_argument("--state", required=True, type=Path)
    apply_parser.add_argument("--frequency", type=int, default=5180)
    apply_parser.add_argument("--source-snr", type=int, default=40)
    apply_parser.add_argument("--target-snr", type=int, default=60)
    apply_parser.add_argument("--other-snr", type=int, default=-20)
    apply_parser.add_argument("--station-radio")
    apply_parser.add_argument("--source-radio")
    apply_parser.add_argument("--target-radio")
    apply_parser.add_argument("--mesh-radio", action="append", default=[])
    apply_parser.set_defaults(handler=apply)

    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--state", required=True, type=Path)
    restore_parser.set_defaults(handler=restore)

    args = parser.parse_args()
    try:
        return args.handler(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
