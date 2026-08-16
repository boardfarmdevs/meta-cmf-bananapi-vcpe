from __future__ import annotations

import datetime as dt
import json
import os
import signal
import time
from pathlib import Path

from .actuator import ActuatorError, ControlClient
from .observers import mesh_health, snapshot


REQUIRED_CAPABILITIES = {"radio_pair_snr", "atomic_generations", "readback", "dump_links"}


def _append(path: Path, value: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


class Runner:
    def __init__(self, plan: dict, socket_path: str, output_root: Path):
        self.plan = plan
        self.socket_path = socket_path
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = output_root / f"{timestamp}-{plan['scenario']}-{os.getpid()}"
        self.stop_requested = False

    def _signal(self, signum, frame) -> None:
        self.stop_requested = True

    @staticmethod
    def _require_healthy(health: dict, stage: str) -> None:
        if health["api_active"] != health["api_total"]:
            raise ActuatorError(f"mesh {stage} has inactive clients")
        if health["complete_nodes"] != health["topology_nodes"]:
            raise ActuatorError(f"mesh {stage} has incomplete topology nodes")

    def execute(self) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        (self.run_dir / "event-plan.json").write_text(
            json.dumps(self.plan, indent=2, sort_keys=True) + "\n"
        )
        event_log = self.run_dir / "medium-events.jsonl"
        health_log = self.run_dir / "health-events.jsonl"
        old_handlers = {
            signum: signal.signal(signum, self._signal)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        outcome = "failed"
        error_text = None
        restored = False
        overall_started = time.monotonic()
        execution_started = None
        try:
            with ControlClient(self.socket_path) as client:
                status = client.status()
                missing = REQUIRED_CAPABILITIES - status.capabilities
                if missing:
                    raise ActuatorError(f"daemon lacks capabilities {sorted(missing)}")
                _, dumped = client.dump_links()
                baseline = {
                    (item["source"], item["destination"]): item["value"]
                    for item in dumped
                }
                touched = {
                    (update["source"], update["destination"])
                    for event in self.plan["events"] for update in event["updates"]
                }
                unknown = sorted(touched - set(baseline))
                if unknown:
                    raise ActuatorError(f"plan identities are absent from daemon: {unknown}")
                restore_updates = [
                    {"source": source, "destination": destination,
                     "value": baseline[(source, destination)]}
                    for source, destination in sorted(touched)
                ]
                initial_health = mesh_health()
                _append(health_log, {"event": "preflight", **initial_health})
                self._require_healthy(initial_health, "preflight")
                execution_started = time.monotonic()
                generation = status.generation
                try:
                    for event in self.plan["events"]:
                        deadline = execution_started + event["time_ms"] / 1000
                        while True:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                break
                            if self.stop_requested:
                                raise InterruptedError("run interrupted")
                            time.sleep(min(remaining, 0.1))
                        if not event["updates"]:
                            _append(event_log, {"event": "mark", **event})
                            continue
                        generation += 1
                        desired_at = execution_started + event["time_ms"] / 1000
                        applied = client.apply(generation, event["updates"])
                        readback = [
                            {
                                "source": item["source"],
                                "destination": item["destination"],
                                "value": client.get_link(
                                    item["source"], item["destination"]
                                )[1],
                            }
                            for item in applied
                        ]
                        if readback != applied:
                            raise ActuatorError("generation readback mismatch")
                        _append(
                            event_log,
                            {
                                "event": "generation",
                                "plan_generation": event["generation"],
                                "daemon_generation": generation,
                                "time_ms": event["time_ms"],
                                "deadline_lateness_ms": round(
                                    (time.monotonic() - desired_at) * 1000, 3
                                ),
                                "updates": applied,
                                "observation": snapshot(self.plan),
                            },
                        )
                    end_deadline = execution_started + self.plan["duration_ms"] / 1000
                    while time.monotonic() < end_deadline:
                        if self.stop_requested:
                            raise InterruptedError("run interrupted")
                        time.sleep(min(end_deadline - time.monotonic(), 0.1))
                finally:
                    if restore_updates:
                        generation += 1
                        client.apply(generation, restore_updates)
                        restored = all(
                            client.get_link(item["source"], item["destination"])[1]
                            == item["value"]
                            for item in restore_updates
                        )
                        _append(
                            event_log,
                            {"event": "restore", "daemon_generation": generation,
                             "verified": restored, "updates": restore_updates},
                        )
                        if not restored:
                            raise ActuatorError("baseline restoration readback failed")
                final_health = mesh_health()
                _append(health_log, {"event": "postflight", **final_health})
                self._require_healthy(final_health, "postflight")
                outcome = "passed"
        except Exception as error:
            outcome = "failed"
            error_text = str(error)
            raise
        finally:
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)
            summary = {
                "scenario": self.plan["scenario"],
                "outcome": outcome,
                "restored": restored,
                "error": error_text,
                "elapsed_ms": round((time.monotonic() - overall_started) * 1000, 3),
                "execution_elapsed_ms": (
                    round((time.monotonic() - execution_started) * 1000, 3)
                    if execution_started is not None else None
                ),
            }
            (self.run_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
        return self.run_dir
