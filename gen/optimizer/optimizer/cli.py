from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from .actuator import SteerActuator
from .config import load_policy
from .model import Snapshot
from .observer import ControllerObserver
from .policy import ThresholdPolicy
from .recorder import Journal, read_records
from .state import PolicyState
from .verifier import OutcomeVerifier


def _record_cycle(journal: Journal, snapshot: Snapshot, evaluation) -> None:
    journal.append("snapshot", snapshot.to_dict(), recorded_at=snapshot.observed_at)
    journal.append("evaluation", evaluation.to_dict(), recorded_at=snapshot.observed_at)


def _live(args, mode: str) -> int:
    observer = ControllerObserver(args.base_url)
    journal = Journal(args.journal)
    policy = ThresholdPolicy(load_policy(args.policy)) if mode != "observe" else None
    state = PolicyState()
    actuator = SteerActuator(args.steer_script) if mode == "act" else None
    verifier = OutcomeVerifier(observer) if mode == "act" else None
    for index in range(args.count):
        snapshot = observer.observe()
        journal.append("raw_observation", observer.last_raw, recorded_at=snapshot.observed_at)
        journal.append("snapshot", snapshot.to_dict(), recorded_at=snapshot.observed_at)
        if policy:
            evaluation = policy.evaluate(snapshot, state)
            state = evaluation.state
            journal.append("evaluation", evaluation.to_dict(), recorded_at=snapshot.observed_at)
            for decision in evaluation.decisions:
                print(json.dumps(decision.to_dict(), sort_keys=True))
            actionable = [item for item in evaluation.decisions if item.action == "steer"]
            for decision in actionable:
                if mode == "act":
                    if not args.yes_act:
                        raise SystemExit("act mode requires --yes-act")
                    result = actuator.execute(decision, snapshot)
                    journal.append("action", result.to_dict())
                    if result.success:
                        verified = verifier.verify(
                            decision.sta_mac,
                            decision.target_bssid,
                            timeout_seconds=policy.config.steer_timeout_seconds,
                        )
                        journal.append("verification", verified.to_dict())
        if index + 1 < args.count:
            time.sleep(args.interval)
    return 0


def _replay(args) -> int:
    policy = ThresholdPolicy(load_policy(args.policy))
    journal = Journal(args.journal)
    state = PolicyState()
    count = 0
    for record in read_records(args.input):
        if record.get("kind") != "snapshot":
            continue
        snapshot = Snapshot.from_dict(record["payload"])
        evaluation = policy.evaluate(snapshot, state)
        state = evaluation.state
        _record_cycle(journal, snapshot, evaluation)
        count += 1
    if count == 0:
        raise SystemExit("input journal contains no snapshot records")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="em-optimizer")
    sub = result.add_subparsers(dest="mode", required=True)
    for mode in ("observe", "recommend", "act"):
        command = sub.add_parser(mode)
        command.add_argument("--base-url", default="http://127.0.0.1:8888")
        command.add_argument("--journal", required=True)
        command.add_argument("--count", type=int, default=1)
        command.add_argument("--interval", type=float, default=1)
        if mode != "observe":
            command.add_argument("--policy", required=True)
        if mode == "act":
            command.add_argument(
                "--steer-script",
                default=str(Path(__file__).resolve().parents[2] / "steer.sh"),
            )
            command.add_argument("--yes-act", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("--input", required=True)
    replay.add_argument("--journal", required=True)
    replay.add_argument("--policy", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "replay":
        return _replay(args)
    return _live(args, args.mode)


if __name__ == "__main__":
    sys.exit(main())
