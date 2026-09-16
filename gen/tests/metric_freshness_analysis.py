#!/usr/bin/env python3
"""Analyze saved collection evidence; never contact or change a controller."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import runpy
from statistics import median


def distribution(values):
    values = list(values)
    return {"count": len(values), "minimum": min(values), "median": median(values),
            "maximum": max(values)} if values else {"count": 0, "minimum": None,
                                                   "median": None, "maximum": None}


def seconds_after(mark, boundary):
    return (mark["monotonic_ns"] - boundary["monotonic_ns"]) / 1e9


def client_read_window(cycle):
    timing = cycle.get("raw", {}).get("api_timings", {}).get("clients")
    if timing is not None:
        if "error" in timing or "finished" not in timing:
            return None
        return {"started": timing["started"], "finished": timing["finished"],
                "scope": "clients-http-request-and-decode"}
    if cycle.get("error") or "clients" not in cycle.get("raw", {}):
        return None
    timings = cycle["timings"]
    return {"started": timings["observer"]["started"],
            "finished": timings.get("candidates", timings["observer"])[
                "started" if "candidates" in timings else "finished"],
            "scope": "legacy-passive-stage-bound-only"}


def cycle_transactions(cycle):
    if "candidates" not in cycle.get("timings", {}):
        return []
    return cycle.get("candidate_transactions", [])


def summarize_action(action, cycles):
    boundary = action["timings"]["verification"]["finished"]
    target = action["freshness_requirements"]["target"]
    station = action["decision"]["sta_mac"]
    rows = []
    for cycle in cycles:
        timing = cycle["timings"]["cycle"]
        if timing["started"]["monotonic_ns"] <= boundary["monotonic_ns"]:
            continue
        clients = [client for client in cycle.get("snapshot", {}).get("clients", [])
                   if client["sta_mac"] == station]
        client = clients[0] if len(clients) == 1 else None
        same_owner = client is not None and all(
            client.get(field) == target[target_field] for field, target_field in (
                ("connected_bssid", "bssid"), ("connected_device_id", "device_id"), ("band", "band")))
        window = client_read_window(cycle)
        timestamp = client.get("metric_observed_at") if same_owner else None
        rcpi = client.get("rcpi") if same_owner else None
        required = action["freshness_requirements"].get("candidates", [])
        candidates = [candidate for candidate in cycle.get("snapshot", {}).get("candidates", [])
                      if candidate["sta_mac"] == station and candidate.get("rcpi") is not None]
        rows.append({
            "cycle_index": cycle["cycle_index"], "error": cycle.get("error"),
            "cycle_started_after_verification_seconds": seconds_after(timing["started"], boundary),
            "cycle_finished_after_verification_seconds": seconds_after(timing["finished"], boundary),
            "client_read_scope": window["scope"] if window else None,
            "client_read_after_verification_seconds": {
                edge: seconds_after(window[edge], boundary) for edge in ("started", "finished")
            } if window else None,
            "same_target_owner": same_owner, "rcpi": rcpi,
            "metric_observed_at": timestamp,
            "reported_sample_after_verification_seconds": (
                datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() - boundary["at"]
            ) if timestamp else None,
            "client_read_to_cycle_finish_seconds": seconds_after(timing["finished"], window["finished"])
            if window else None,
            "candidate_elapsed_ms": cycle["timings"].get("candidates", {}).get("elapsed_ms"),
            "required_candidates_without_metrics": [identity for identity in required
                if not any(all(candidate.get(field) == value for field, value in identity.items())
                           for candidate in candidates)],
            "candidate_rejections": [rejected for transaction in cycle_transactions(cycle)
                for rejected in transaction.get("response", {}).get("rejected") or []
                if rejected["sta"] == station],
            "load_collection": cycle.get("raw", {}).get("load_collection"),
            "target_activity": [activity for activity in cycle.get("snapshot", {}).get("client_activity", [])
                if activity["sta_mac"] == station and activity["bssid"] == target["bssid"]],
        })
    milestones = action.get("post_verify_freshness", {})
    return {"sta_mac": station, "target_bssid": target["bssid"],
            "milestones_after_verification_seconds": {
                name: value["after_verification_seconds"] if value else None
                for name, value in milestones.items()},
            "native_arrival_after_verification_seconds": None,
            "sample_timestamp_scope": "reported sample time; may be age-adjusted, never native arrival",
            "post_verification_cycles": rows}


def summarize_run(report, cycles):
    transactions = [transaction for cycle in cycles for transaction in cycle_transactions(cycle)]
    coordination = [transaction["response"]["coordination"] for transaction in transactions
                    if isinstance(transaction.get("response", {}).get("coordination"), dict)]
    candidate_totals = [sum(transaction["elapsed_ms"] for transaction in cycle_transactions(cycle))
                        for cycle in cycles if cycle_transactions(cycle)]
    return {
        "scope": "saved collector observations; no native-arrival inference",
        "cycles": len(cycles), "failed_cycles": sum("error" in cycle for cycle in cycles),
        "stage_elapsed_ms": {stage: distribution(
            cycle["timings"][stage]["elapsed_ms"] for cycle in cycles
            if "elapsed_ms" in cycle.get("timings", {}).get(stage, {})
        ) for stage in ("observer", "candidates", "load", "evaluate", "cycle")},
        "observer_excluding_candidates_ms": distribution(
            cycle["observer_excluding_candidates_ms"] for cycle in cycles
            if "observer_excluding_candidates_ms" in cycle),
        "candidate_transactions_per_cycle": distribution(
            len(cycle_transactions(cycle)) for cycle in cycles),
        "unattributed_candidate_transactions": sum(len(cycle.get("candidate_transactions", []))
            for cycle in cycles if "candidates" not in cycle.get("timings", {})),
        "sum_transaction_elapsed_ms_per_cycle": distribution(candidate_totals),
        "candidate_request_elapsed_ms": distribution(
            transaction["request_timing"]["elapsed_ms"] for transaction in transactions
            if "elapsed_ms" in transaction.get("request_timing", {})),
        "candidate_transaction_errors": sum("error" in transaction for transaction in transactions),
        "candidate_native_queue_ms": distribution(row["native_queue_ms"] for row in coordination),
        "candidate_native_service_ms": distribution(row["native_service_ms"] for row in coordination),
        "candidate_handler_other_ms": distribution(
            row["elapsed_ms"] - row["native_service_ms"] - row["native_queue_ms"] for row in coordination),
        "candidate_handler_other_scope": "includes polling/protocol wait and handler work; not all avoidable",
        "actions": [summarize_action(action, cycles) for action in report.get("actions", [])],
    }


def summarize_native(events, profiles):
    identities = [event for event in events if event.get("kind") == "identity"]
    endings = [event for event in events if event.get("kind") == "end"]
    if len(identities) != 1 or len(endings) != 1 or events[-1] != endings[0]:
        raise ValueError("trace requires one identity and a complete terminal record")
    identity, ending = identities[0], endings[0]
    profile = profiles.get(identity.get("stack"), {}).get(identity.get("sha256"))
    if (not profile or not profile.get("instructions")
            or identity.get("profile") != json.loads(json.dumps(profile))
            or identity.get("clock") != "guest-monotonic"
            or identity.get("boundary") != "native-model-association-commit"
            or identity.get("metric_boundary") != "native-model-rcpi-store"):
        raise ValueError("trace requires a qualified binary SHA/profile and native metric boundary")
    records = [event for event in events if event.get("kind") in ("metric", "commit")]
    if (ending.get("lost") != 0 or ending.get("records") != len(records)
            or ending.get("emitted") != len(records)
            or sum(event.get("kind") == "ready" for event in events) != 1):
        raise ValueError("trace is incomplete or lost native events")
    previous = {}
    owners = {}
    pending = {}
    transitions = []
    gaps = []
    metrics = 0
    for event in sorted(records, key=lambda row: row["monotonic_ns"]):
        station, bssid = event["sta"], event["bssid"]
        if event["kind"] == "commit":
            if not event["associated"] or owners.get(station) != bssid:
                previous = {key: value for key, value in previous.items() if key[0] != station}
                pending.pop(station, None)
                if event["associated"]:
                    transition = {"sta": station, "bssid": bssid, "previous_bssid": owners.get(station),
                                  "commit_monotonic_ns": event["monotonic_ns"],
                                  "first_target_rcpi_store_after_commit_ms": None}
                    transitions.append(transition)
                    pending[station] = transition
            owners[station] = bssid if event["associated"] else None
            continue
        if (not event["associated"] or type(event.get("rcpi")) is not int
                or not 0 <= event["rcpi"] <= 220):
            continue
        if station in owners and owners[station] != bssid:
            continue
        owners.setdefault(station, bssid)
        transition = pending.pop(station, None)
        if transition is not None:
            transition["first_target_rcpi_store_after_commit_ms"] = (
                event["monotonic_ns"] - transition["commit_monotonic_ns"]
            ) / 1e6
        key = (station, bssid)
        metrics += 1
        if key in previous:
            gaps.append((event["monotonic_ns"] - previous[key]) / 1e9)
        previous[key] = event["monotonic_ns"]
    return {"scope": "within-trace native RCPI stores; not correlated to other runs",
            "sha256": identity["sha256"], "binary": identity.get("binary"),
            "metric_records": metrics, "metric_gap_seconds": distribution(gaps),
            "association_to_first_store": transitions,
            "first_store_scope": "same trace and owner; does not establish the reported sample age",
            "native_arrival_after_verification_seconds": None}


def read_jsonl(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="*")
    parser.add_argument("--trace", type=Path, action="append", default=[])
    args = parser.parse_args()
    if not args.runs and not args.trace:
        parser.error("provide saved run directories or --trace JSONL")
    profiles = runpy.run_path(str(Path(__file__).with_name("native-controller-trace.py")))["PROFILES"]
    output = {"schema": "easymesh.metric-freshness-analysis.v1", "runs": {}, "native_traces": {}}
    for directory in args.runs:
        output["runs"][str(directory)] = summarize_run(
            json.loads((directory / "report.json").read_text()), read_jsonl(directory / "cycles.jsonl"))
    for path in args.trace:
        output["native_traces"][str(path)] = summarize_native(read_jsonl(path), profiles)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
