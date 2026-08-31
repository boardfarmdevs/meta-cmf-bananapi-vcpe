#!/usr/bin/env python3
"""Reject unbounded OneWifi PSS growth across the provisioned mesh nodes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROBE = r'''
set -eu
pid=$(pidof OneWifi)
pss=$(awk '/^Pss:/ {print $2; exit}' /proc/$pid/smaps_rollup)
rss=$(awk '/^Rss:/ {print $2; exit}' /proc/$pid/smaps_rollup)
private_dirty=$(awk '/^Private_Dirty:/ {print $2; exit}' /proc/$pid/smaps_rollup)
vmsize=$(awk '/^VmSize:/ {print $2; exit}' /proc/$pid/status)
threads=$(awk '/^Threads:/ {print $2; exit}' /proc/$pid/status)
printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$pid" "$pss" "$rss" "$private_dirty" "$vmsize" "$threads"
'''


def run(*args: str, timeout: float = 30) -> str:
    result = subprocess.run(
        args, check=True, text=True, capture_output=True, timeout=timeout
    )
    return result.stdout.strip()


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def discover_containers() -> list[str]:
    instances = json.loads(run("lxc", "list", "--format=json"))
    names = [
        str(item["name"])
        for item in instances
        if str(item.get("status", "")).upper() == "RUNNING"
        and (
            item.get("name") == "bpibroadband"
            or str(item.get("name", "")).startswith("bpiap")
        )
    ]
    return sorted(names, key=lambda name: (name != "bpibroadband", name))


def probe(container: str) -> dict[str, int]:
    fields = run("lxc", "exec", container, "--", "sh", "-c", PROBE).split("\t")
    if len(fields) != 6:
        raise RuntimeError(f"unexpected OneWifi probe from {container}: {fields!r}")
    values = [int(value) for value in fields]
    return dict(
        zip(
            ("pid", "pss_kib", "rss_kib", "private_dirty_kib", "vmsize_kib", "threads"),
            values,
        )
    )


def linear_slope(values: list[tuple[float, float]]) -> float:
    """Return the least-squares slope in value units per second."""
    if len(values) < 2:
        raise ValueError("at least two points are required")
    x_mean = sum(value[0] for value in values) / len(values)
    y_mean = sum(value[1] for value in values) / len(values)
    denominator = sum((value[0] - x_mean) ** 2 for value in values)
    if denominator == 0:
        return 0.0
    return sum(
        (value[0] - x_mean) * (value[1] - y_mean) for value in values
    ) / denominator


def summarize(
    samples: list[dict[str, Any]],
    containers: list[str],
    warmup: float,
    max_slope: float,
) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {}
    failures: list[str] = []
    for container in containers:
        points = [
            (float(sample["elapsed_seconds"]), float(sample["nodes"][container]["pss_kib"]))
            for sample in samples
            if float(sample["elapsed_seconds"]) >= warmup
            and container in sample.get("nodes", {})
        ]
        pids = {
            int(sample["nodes"][container]["pid"])
            for sample in samples
            if container in sample.get("nodes", {})
        }
        if len(points) < 3:
            failures.append(f"{container}: fewer than three post-warmup samples")
            continue
        slope = linear_slope(points) * 3600.0
        growth = points[-1][1] - points[0][1]
        result[container] = {
            "pid": min(pids) if len(pids) == 1 else sorted(pids),
            "samples": len(points),
            "pss_kib_start": round(points[0][1]),
            "pss_kib_end": round(points[-1][1]),
            "pss_growth_kib": round(growth),
            "pss_slope_kib_per_hour": round(slope, 2),
        }
        if len(pids) != 1:
            failures.append(f"{container}: OneWifi restarted, PIDs={sorted(pids)}")
        if slope > max_slope:
            failures.append(
                f"{container}: PSS slope {slope:.2f} KiB/hour exceeds {max_slope:.2f}"
            )
    return result, failures


def self_test() -> int:
    assert linear_slope([(0, 10), (10, 20), (20, 30)]) == 1
    assert linear_slope([(0, 30), (10, 20), (20, 10)]) == -1
    assert linear_slope([(0, 10), (10, 10), (20, 10)]) == 0
    print("PASS: OneWifi memory-slope arithmetic")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "sample OneWifi on every running BPI container and fail when its "
            "post-warmup PSS slope is unbounded"
        )
    )
    parser.add_argument("--duration", type=float, default=900)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--warmup", type=float, default=120)
    parser.add_argument("--max-slope-kib-per-hour", type=float, default=2048)
    parser.add_argument("--containers", help="comma-separated explicit container names")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.interval <= 0 or args.warmup < 0 or args.duration <= args.warmup + 2 * args.interval:
        parser.error("duration must leave at least three samples after warmup")
    if args.max_slope_kib_per_hour < 0:
        parser.error("maximum slope must be non-negative")

    containers = (
        [name for name in args.containers.split(",") if name]
        if args.containers
        else discover_containers()
    )
    if not containers:
        raise SystemExit("no running BPI mesh containers were found")

    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        current: dict[str, Any] = {
            "at": iso_now(),
            "elapsed_seconds": round(elapsed, 3),
            "nodes": {},
        }
        for container in containers:
            try:
                current["nodes"][container] = probe(container)
            except (subprocess.SubprocessError, RuntimeError, ValueError) as error:
                message = f"{container} at {elapsed:.1f}s: {error}"
                current.setdefault("errors", []).append(message)
                errors.append(message)
        samples.append(current)
        values = " ".join(
            f"{name}={data['pss_kib']}KiB" for name, data in current["nodes"].items()
        )
        print(f"elapsed={elapsed:.1f}s {values}", flush=True)
        if elapsed >= args.duration:
            break
        time.sleep(max(0.0, min(args.interval, args.duration - elapsed)))

    nodes, failures = summarize(
        samples, containers, args.warmup, args.max_slope_kib_per_hour
    )
    failures = errors + failures
    report = {
        "schema_version": 1,
        "completed_at": iso_now(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "interval_seconds": args.interval,
        "warmup_seconds": args.warmup,
        "max_slope_kib_per_hour": args.max_slope_kib_per_hour,
        "containers": nodes,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
        "samples": samples,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(json.dumps({key: report[key] for key in ("status", "containers", "failures")}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
