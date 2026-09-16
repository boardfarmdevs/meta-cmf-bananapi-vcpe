#!/usr/bin/env python3
"""Audit RDK native AP-metrics periodic and restart behavior without changing policy."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from optimizer.load_observer import NativeLoadProvider


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*arguments, timeout=30):
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=timeout)


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def service_state(container, service):
    values = command("lxc", "exec", container, "--", "systemctl", "show", service,
                     "-p", "ActiveState", "-p", "MainPID", "-p", "NRestarts").stdout
    return dict(line.split("=", 1) for line in values.splitlines() if "=" in line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=16)
    parser.add_argument("--restart-container", default="bpiap")
    args = parser.parse_args()
    if os.geteuid() or not 12 <= args.seconds <= 30:
        parser.error("requires root in the RDK lab VM and 12..30 seconds")
    args.output.mkdir(parents=True, exist_ok=False)
    reports = []
    provider = None
    report = {
        "stack": "rdk",
        "state": "failed",
        "read_only_policy": True,
        "explicit_query": {
            "state": "not_exercised",
            "reason": "run rdk-reporting-policy-acceptance.py --extended for isolated native query qualification",
        },
        "threshold_crossing": {
            "state": "not_isolated",
            "reason": "this audit leaves periodic reporting enabled; run rdk-reporting-policy-acceptance.py for isolated threshold/query qualification",
        },
    }
    try:
        interactions = fetch("http://127.0.0.1:8891/api/demo/interactions")
        require(interactions["selected_world"] == "home-five-agent--private-client-room-walk"
                and interactions["playback"]["status"] == "paused"
                and interactions["playback"]["time_ms"] == 0
                and not interactions["lease"]["held"], "requires the idle default room")
        policy = fetch("http://127.0.0.1:8888/api/v1/wifipolicy")
        configs = policy.get("policyConfig", [])
        require(len(configs) == 5, "expected five native policy records")
        intervals = {row["id"].lower(): row["apMetricReportingPolicy"]["interval"] for row in configs}
        require(set(intervals.values()) == {5}, "expected the deployed five-second reporting interval")
        report["policy"] = {"records": len(configs), "intervals_seconds": intervals}
        controller_before = service_state("bpibroadband", "em_ctrl.service")
        require(controller_before.get("ActiveState") == "active", "native controller is not active")
        provider = NativeLoadProvider("bpibroadband", report_observer=lambda value: reports.append(
            {**value, "audit_monotonic": time.monotonic()}))
        started = time.monotonic()
        while time.monotonic() - started < args.seconds:
            time.sleep(.1)
        counts = Counter(row["source"] for row in reports)
        require(len(counts) == 5 and min(counts.values()) >= 2,
                "periodic reports did not advance twice for all five mesh devices")
        report["periodic"] = {
            "passed": True,
            "observed_seconds": time.monotonic() - started,
            "reports_per_source": dict(sorted(counts.items())),
        }
        bssid = command("lxc", "exec", args.restart_container, "--", "cat",
                        "/sys/class/net/wifi1/address").stdout.strip().lower()
        sources = {row["source"] for row in reports
                   if any(load["bssid"].lower() == bssid for load in row["loads"])}
        require(len(sources) == 1, "could not identify the restart agent's report source")
        source = sources.pop()
        agent_before = service_state(args.restart_container, "em_agent.service")
        restart_started = time.monotonic()
        command("lxc", "exec", args.restart_container, "--", "systemctl", "restart", "em_agent.service",
                timeout=60)
        restart_completed = time.monotonic()
        deadline = restart_started + 45
        first_report = None
        while time.monotonic() < deadline:
            current = [row for row in reports
                       if row["source"] == source and row["audit_monotonic"] >= restart_completed]
            if current:
                first_report = current[0]
                break
            time.sleep(.1)
        require(first_report is not None, "restarted agent did not resume native AP-metrics reporting")
        agent_after = service_state(args.restart_container, "em_agent.service")
        controller_after = service_state("bpibroadband", "em_ctrl.service")
        require(agent_after.get("ActiveState") == "active"
                and agent_after.get("MainPID") not in ("0", agent_before.get("MainPID")),
                "native agent did not restart successfully")
        require(controller_after.get("ActiveState") == "active"
                and controller_after.get("MainPID") == controller_before.get("MainPID")
                and controller_after.get("NRestarts") == controller_before.get("NRestarts"),
                "native controller restarted during the agent reporting audit")
        report["restart"] = {
            "passed": True,
            "container": args.restart_container,
            "source": source,
            "bssid": bssid,
            "first_report_seconds": first_report["audit_monotonic"] - restart_started,
            "restart_command_seconds": restart_completed - restart_started,
            "first_report_after_restart_seconds": first_report["audit_monotonic"] - restart_completed,
            "agent": agent_after,
            "controller_unchanged": True,
        }
        report["state"] = "passed"
        report["audit_completed"] = True
        report["overall_policy_contract"] = "periodic-and-agent-restart-only"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if provider is not None:
            provider.close()
        (args.output / "reports.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in reports))
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report.get("audit_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
