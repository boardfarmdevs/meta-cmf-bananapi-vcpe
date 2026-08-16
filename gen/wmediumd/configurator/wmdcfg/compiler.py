from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from .model import HoldAction, LinkAction, MarkAction, Scenario, ScenarioError


ROLE_TYPES = {"station", "fronthaul_ap"}
CAPABILITIES = {"radio_pair_snr", "atomic_generations", "readback"}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_scenario(scenario: Scenario) -> None:
    if not scenario.roles:
        raise ScenarioError("scenario defines no roles")
    unknown_types = set(scenario.roles.values()) - ROLE_TYPES
    if unknown_types:
        raise ScenarioError(f"unsupported role types: {sorted(unknown_types)}")
    if not scenario.phases:
        raise ScenarioError("scenario defines no phases")
    if scenario.restore != "captured":
        raise ScenarioError("v1 requires 'restore captured'")
    if "backhaul" not in scenario.protections:
        raise ScenarioError("v1 requires 'protect backhaul'")
    missing = scenario.requirements - CAPABILITIES
    if missing:
        raise ScenarioError(f"unsupported capabilities: {sorted(missing)}")
    if not 100 <= scenario.tick_ms <= 60_000:
        raise ScenarioError("tick must be between 100ms and 60s")
    for phase in scenario.phases:
        holds = [action for action in phase.actions if isinstance(action, HoldAction)]
        links = [action for action in phase.actions if isinstance(action, LinkAction)]
        if holds and links:
            raise ScenarioError(f"phase {phase.name}: hold cannot be combined with link actions")
        for link in links:
            for role in (link.source, link.destination):
                if role not in scenario.roles:
                    raise ScenarioError(f"line {link.line}: undefined role {role}")
            types = {scenario.roles[link.source], scenario.roles[link.destination]}
            if types != {"station", "fronthaul_ap"}:
                raise ScenarioError(
                    f"line {link.line}: v1 links require one station and one fronthaul_ap"
                )


def _bind(
    scenario: Scenario, inventory: dict[str, Any], requested: dict[str, str]
) -> dict[str, dict[str, Any]]:
    if set(requested) != set(scenario.roles):
        missing = sorted(set(scenario.roles) - set(requested))
        extra = sorted(set(requested) - set(scenario.roles))
        raise ScenarioError(f"bindings must cover every role; missing={missing} extra={extra}")
    by_name = {item["container"]: item for item in inventory.get("radios", [])}
    result: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for role, role_type in scenario.roles.items():
        container = requested[role]
        if container in used:
            raise ScenarioError(f"container {container} is bound more than once")
        item = by_name.get(container)
        if item is None:
            raise ScenarioError(f"role {role}: container {container} not in inventory")
        expected_kind = "station" if role_type == "station" else "mesh"
        if item.get("kind") != expected_kind:
            raise ScenarioError(
                f"role {role}: {container} is {item.get('kind')}, expected {expected_kind}"
            )
        if role_type == "fronthaul_ap":
            candidates = [
                iface for iface in item.get("interfaces", [])
                if iface.get("ssid") == "private_ssid" and iface.get("frequency_mhz")
            ]
            if not candidates:
                raise ScenarioError(f"role {role}: {container} has no live private fronthaul")
        result[role] = {
            "role_type": role_type,
            "container": container,
            "radio_tx_mac": item["tx_mac"],
            "radio_permanent_mac": item["permanent_mac"],
        }
        used.add(container)
    return result


def _directions(action: LinkAction) -> list[tuple[str, str]]:
    if action.direction == "->":
        return [(action.source, action.destination)]
    if action.direction == "<-":
        return [(action.destination, action.source)]
    return [(action.source, action.destination), (action.destination, action.source)]


def compile_scenario(
    scenario: Scenario,
    source: str,
    inventory: dict[str, Any],
    requested_bindings: dict[str, str],
) -> dict[str, Any]:
    validate_scenario(scenario)
    bindings = _bind(scenario, inventory, requested_bindings)

    station_roles = {name for name, kind in scenario.roles.items() if kind == "station"}
    ap_roles = {name for name, kind in scenario.roles.items() if kind == "fronthaul_ap"}
    baseline_pairs: set[frozenset[str]] = set()
    for action in scenario.phases[0].actions:
        if isinstance(action, LinkAction):
            baseline_pairs.add(frozenset((action.source, action.destination)))
    required_pairs = {frozenset((sta, ap)) for sta in station_roles for ap in ap_roles}
    if not required_pairs.issubset(baseline_pairs):
        missing = sorted("<->".join(sorted(pair)) for pair in required_pairs - baseline_pairs)
        raise ScenarioError(f"first phase must define every station/AP link: {missing}")

    events_by_time: dict[int, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    marks_by_time: dict[int, list[str]] = defaultdict(list)
    phase_records = []
    cursor_ms = 0
    for phase in scenario.phases:
        phase_start = cursor_ms
        for action in phase.actions:
            if isinstance(action, MarkAction):
                marks_by_time[phase_start].append(action.text)
                continue
            if not isinstance(action, LinkAction):
                continue
            sample_offsets = [0]
            if action.end_snr_db is not None:
                sample_offsets = list(range(0, phase.duration_ms, scenario.tick_ms))
                if not sample_offsets or sample_offsets[-1] != phase.duration_ms:
                    sample_offsets.append(phase.duration_ms)
            for offset in sample_offsets:
                if action.end_snr_db is None:
                    value = action.start_snr_db
                else:
                    fraction = offset / phase.duration_ms
                    value = round(
                        action.start_snr_db
                        + (action.end_snr_db - action.start_snr_db) * fraction
                    )
                for source_role, destination_role in _directions(action):
                    source_mac = bindings[source_role]["radio_tx_mac"]
                    destination_mac = bindings[destination_role]["radio_tx_mac"]
                    key = (source_mac, destination_mac)
                    update = {
                        "property": "snr_db",
                        "source": source_mac,
                        "destination": destination_mac,
                        "value": value,
                        "source_role": source_role,
                        "destination_role": destination_role,
                    }
                    existing = events_by_time[phase_start + offset].get(key)
                    if existing is not None and existing["value"] != value:
                        raise ScenarioError(
                            f"phase {phase.name}: conflicting values for {source_role}->{destination_role}"
                        )
                    events_by_time[phase_start + offset][key] = update
        cursor_ms += phase.duration_ms
        phase_records.append(
            {"name": phase.name, "start_ms": phase_start, "end_ms": cursor_ms}
        )

    events = []
    generation = 0
    all_times = sorted(set(events_by_time) | set(marks_by_time))
    for time_ms in all_times:
        updates = sorted(
            events_by_time[time_ms].values(),
            key=lambda item: (item["source"], item["destination"]),
        )
        if updates:
            generation += 1
        events.append(
            {
                "time_ms": time_ms,
                "generation": generation if updates else None,
                "updates": updates,
                "marks": marks_by_time[time_ms],
            }
        )

    return {
        "schema": "wmdcfg.event-plan.v1",
        "scenario": scenario.name,
        "language": scenario.language,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "inventory_sha256": _canonical_hash(inventory),
        "capabilities": sorted(CAPABILITIES),
        "tick_ms": scenario.tick_ms,
        "duration_ms": cursor_ms,
        "restore": scenario.restore,
        "protections": sorted(scenario.protections),
        "bindings": bindings,
        "phases": phase_records,
        "events": events,
    }
