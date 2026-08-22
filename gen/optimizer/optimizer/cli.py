from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from .actuator import SteerActuator
from .candidates import ControllerCandidateProvider
from .config import load_policy
from .experiments import ExperimentError, build_matrix
from .traffic import compile_traffic_plan, load_json
from .simulator import SimulationConfig, WorldSimulator
from .model import Snapshot
from .observer import ControllerObserver
from .policy import ThresholdPolicy
from .planners import (
    BackhaulEdgeObservation,
    BackhaulPlannerConfig,
    RadioEnvironmentObservation,
    plan_backhaul,
    recommend_channel_width,
)
from .recorder import Journal, read_records
from .state import PolicyState
from .verifier import OutcomeVerifier


def _record_cycle(journal: Journal, snapshot: Snapshot, evaluation) -> None:
    journal.append("snapshot", snapshot.to_dict(), recorded_at=snapshot.observed_at)
    journal.append("evaluation", evaluation.to_dict(), recorded_at=snapshot.observed_at)


def _live(args, mode: str) -> int:
    candidate_provider = None
    if args.candidate_provider == "controller":
        candidate_provider = ControllerCandidateProvider(
            args.base_url,
            allow_simulated=args.allow_simulated_candidates,
        )
    observer = ControllerObserver(
        args.base_url,
        candidate_provider=candidate_provider,
        trust_api_metric_timestamp=args.trust_api_metric_timestamp,
    )
    journal = Journal(args.journal)
    policy = ThresholdPolicy(load_policy(args.policy)) if mode != "observe" else None
    state = PolicyState()
    actuator = SteerActuator(args.steer_script) if mode == "act" else None
    # Verification only needs the resulting association. Re-running the active
    # candidate measurement transaction on every verification poll needlessly
    # serializes behind the controller state machine and can consume the whole
    # steer timeout.
    verifier = (
        OutcomeVerifier(
            ControllerObserver(
                args.base_url,
                trust_api_metric_timestamp=args.trust_api_metric_timestamp,
            )
        )
        if mode == "act"
        else None
    )
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
        command.add_argument(
            "--candidate-provider",
            choices=("off", "controller"),
            default="off",
        )
        command.add_argument("--allow-simulated-candidates", action="store_true")
        command.add_argument(
            "--trust-api-metric-timestamp",
            action=argparse.BooleanOptionalAction,
            default=True,
            help=(
                "consume the controller's associated-report receipt timestamp "
                "(default: enabled; use --no-trust-api-metric-timestamp for an "
                "older controller image)"
            ),
        )
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
    matrix = sub.add_parser("matrix")
    matrix.add_argument("--spec", required=True)
    matrix.add_argument("--output", required=True)
    traffic = sub.add_parser("traffic-plan")
    traffic.add_argument("--matrix", required=True)
    traffic.add_argument("--case", required=True)
    traffic.add_argument("--bindings", required=True)
    traffic.add_argument("--output", required=True)
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--world", required=True)
    simulate.add_argument("--policy", required=True)
    simulate.add_argument("--output", required=True)
    simulate.add_argument("--initial-band", choices=("2.4", "5", "6"), default="5")
    simulate.add_argument("--metric-delay-ms", type=int, default=0)
    simulate.add_argument(
        "--client-behavior",
        action="append",
        default=[],
        metavar="ROLE=accept|reject|ignore",
    )
    backhaul = sub.add_parser("backhaul-plan")
    backhaul.add_argument("--input", required=True)
    backhaul.add_argument("--output", required=True)
    width = sub.add_parser("width-plan")
    width.add_argument("--input", required=True)
    width.add_argument("--output", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "matrix":
        try:
            value = build_matrix(args.spec)
        except ExperimentError as error:
            raise SystemExit(f"em-optimizer: {error}") from error
        Path(args.output).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.mode == "traffic-plan":
        try:
            value = compile_traffic_plan(
                load_json(args.matrix), args.case, load_json(args.bindings)
            )
        except ExperimentError as error:
            raise SystemExit(f"em-optimizer: {error}") from error
        Path(args.output).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.mode == "simulate":
        behavior = {}
        for item in args.client_behavior:
            if "=" not in item:
                raise SystemExit("--client-behavior requires ROLE=accept|reject|ignore")
            role, value = item.split("=", 1)
            if role in behavior:
                raise SystemExit(f"duplicate client behavior for {role}")
            behavior[role] = value
        try:
            value = WorldSimulator(
                load_json(args.world),
                ThresholdPolicy(load_policy(args.policy)),
                config=SimulationConfig(
                    initial_band=args.initial_band,
                    metric_delay_ms=args.metric_delay_ms,
                ),
                client_behavior=behavior,
            ).run()
        except (ExperimentError, ValueError) as error:
            raise SystemExit(f"em-optimizer: {error}") from error
        Path(args.output).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.mode == "backhaul-plan":
        value = load_json(args.input)
        if value.get("schema") != "optimizer.backhaul-observations.v1":
            raise SystemExit("em-optimizer: expected optimizer.backhaul-observations.v1")
        try:
            plan = plan_backhaul(
                root=value["root"],
                nodes=value["nodes"],
                observed_at=value["observed_at"],
                edges=[BackhaulEdgeObservation(**item) for item in value["edges"]],
                config=BackhaulPlannerConfig(**value.get("planner", {})),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit(f"em-optimizer: invalid backhaul input: {error}") from error
        output = {"schema": "optimizer.backhaul-plan.v1", **plan.to_dict()}
        Path(args.output).write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.mode == "width-plan":
        value = load_json(args.input)
        if value.get("schema") != "optimizer.radio-environment.v1":
            raise SystemExit("em-optimizer: expected optimizer.radio-environment.v1")
        try:
            recommendations = [
                recommend_channel_width(
                    RadioEnvironmentObservation(**item),
                    now=value["observed_at"],
                    maximum_metric_age_seconds=float(value.get("maximum_metric_age_seconds", 30)),
                ).to_dict()
                for item in value["radios"]
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit(f"em-optimizer: invalid radio environment: {error}") from error
        output = {
            "schema": "optimizer.channel-width-plan.v1",
            "observed_at": value["observed_at"],
            "recommendations": recommendations,
        }
        Path(args.output).write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.mode == "replay":
        return _replay(args)
    return _live(args, args.mode)


if __name__ == "__main__":
    sys.exit(main())
