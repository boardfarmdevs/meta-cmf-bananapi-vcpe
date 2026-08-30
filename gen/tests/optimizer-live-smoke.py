#!/usr/bin/env python3
"""Read-only five-Agent optimizer acceptance against a running hwsim lab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "gen" / "optimizer"))

from optimizer.candidates import CandidateMetricsError, ControllerCandidateProvider
from optimizer.config import load_policy
from optimizer.model import parse_time
from optimizer.observer import ControllerObserver
from optimizer.policy import ThresholdPolicy
from optimizer.state import PolicyState


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8888")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--maximum-age-seconds", type=float, default=60)
    parser.add_argument(
        "--candidate-attempts",
        type=int,
        default=1,
        help="bounded attempts for each idempotent candidate query (default: 1)",
    )
    parser.add_argument(
        "--policy",
        default=str(REPO / "gen" / "optimizer" / "configs" / "threshold-policy.yaml"),
    )
    args = parser.parse_args()
    if (
        args.cycles < 1
        or args.interval < 0
        or args.maximum_age_seconds <= 0
        or args.candidate_attempts < 1
    ):
        parser.error(
            "cycles, maximum age and candidate attempts must be positive; "
            "interval cannot be negative"
        )

    provider = ControllerCandidateProvider(
        args.base_url,
        allow_simulated=True,
        request_attempts=args.candidate_attempts,
    )
    observer = ControllerObserver(args.base_url, candidate_provider=provider)
    policy = ThresholdPolicy(load_policy(args.policy))
    state = PolicyState()

    for cycle in range(args.cycles):
        try:
            snapshot = observer.observe()
        except (CandidateMetricsError, OSError, ValueError) as error:
            print(f"FAIL cycle={cycle}: {error}", file=sys.stderr)
            if provider.last_raw:
                print(json.dumps({
                    "candidate_transactions": provider.last_raw,
                }, sort_keys=True), file=sys.stderr)
            return 1

        if snapshot.health.devices != policy.config.expected_devices:
            print(f"FAIL cycle={cycle}: devices={snapshot.health.devices}", file=sys.stderr)
            return 1
        if snapshot.health.clients != policy.config.expected_clients:
            print(f"FAIL cycle={cycle}: clients={snapshot.health.clients}", file=sys.stderr)
            return 1

        now = parse_time(snapshot.observed_at)
        missing_current = [
            item.sta_mac for item in snapshot.clients
            if item.rcpi is None or item.metric_observed_at is None
        ]
        same_band = [
            item for item in snapshot.candidates
            if item.band == snapshot.client(item.sta_mac).band
        ]
        missing_candidates = [
            f"{item.sta_mac}@{item.bssid}" for item in same_band
            if item.rcpi is None or item.metric_observed_at is None
        ]
        ages = [
            (now - parse_time(item.metric_observed_at)).total_seconds()
            for item in (*snapshot.clients, *same_band)
            if item.metric_observed_at is not None
        ]
        max_age = max(ages, default=float("inf"))
        if missing_current or missing_candidates:
            print(json.dumps({
                "cycle": cycle,
                "missing_current": missing_current,
                "missing_candidates": missing_candidates,
            }, sort_keys=True), file=sys.stderr)
            return 1
        if max_age < 0 or max_age > args.maximum_age_seconds:
            print(f"FAIL cycle={cycle}: maximum_metric_age={max_age:.3f}s", file=sys.stderr)
            return 1

        evaluation = policy.evaluate(snapshot, state)
        state = evaluation.state
        print(json.dumps({
            "cycle": cycle,
            "devices": snapshot.health.devices,
            "clients": snapshot.health.clients,
            "same_band_candidates": len(same_band),
            "candidate_transactions": len(provider.last_raw),
            "maximum_metric_age_seconds": round(max_age, 3),
            "actions": sum(item.action == "steer" for item in evaluation.decisions),
            "reasons": sorted({item.reason for item in evaluation.decisions}),
        }, sort_keys=True))
        if cycle + 1 < args.cycles:
            time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
