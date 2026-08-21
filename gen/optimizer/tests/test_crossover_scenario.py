from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimizer.model import Snapshot
from optimizer.policy import PolicyConfig, ThresholdPolicy
from optimizer.state import PolicyState
from wmdcfg.parser import parse


@pytest.mark.scenario
def test_existing_two_ap_crossover_yields_one_report_based_recommendation():
    root = Path(__file__).resolve().parents[2]
    scenario_path = root / "wmediumd" / "configurator" / "scenarios" / "two-ap-crossover.wmd"
    scenario = parse(scenario_path.read_text(encoding="utf-8"))
    assert [phase.name for phase in scenario.phases] == [
        "baseline",
        "crossover",
        "destination_hold",
    ]
    assert sum(phase.duration_ms for phase in scenario.phases) == 60_000

    fixture = Path(__file__).parent / "fixtures" / "two-ap-crossover-observations.jsonl"
    snapshots = [
        Snapshot.from_dict(json.loads(line))
        for line in fixture.read_text(encoding="utf-8").splitlines()
        if line
    ]
    # These are recorded controller/EasyMesh observations. The optimizer test
    # intentionally never derives RCPI or a target from the scenario's SNR.
    assert {
        item.measurement_source
        for snapshot in snapshots
        for item in (*snapshot.clients, *snapshot.candidates)
    } == {"associated_sta_link_metrics", "beacon_metrics_response"}

    engine = ThresholdPolicy(PolicyConfig())
    state = PolicyState()
    decisions = []
    for snapshot in snapshots:
        evaluated = engine.evaluate(snapshot, state)
        state = evaluated.state
        decisions.extend(evaluated.decisions)
    actionable = [item for item in decisions if item.action == "steer"]
    assert len(actionable) == 1
    assert actionable[0].reason == "threshold_margin_hold_satisfied"
