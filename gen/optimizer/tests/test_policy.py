from __future__ import annotations

from optimizer.policy import PolicyConfig, ThresholdPolicy
from optimizer.state import PolicyState
from .helpers import TARGET, snapshot


def policy(**changes):
    values = {
        "expected_clients": 10,
        "condition_hold_seconds": 5,
        "minimum_dwell_seconds": 20,
        "reject_stale_metrics_after_seconds": 7,
    }
    values.update(changes)
    return ThresholdPolicy(PolicyConfig(**values))


def decision(result):
    return result.decisions[0]


def test_missing_metric_freshness_is_a_safe_no_action():
    result = policy().evaluate(snapshot(0, metric_age=None))
    assert decision(result).action == "none"
    assert decision(result).reason == "current_metric_freshness_unknown"


def test_stale_candidate_is_a_safe_no_action():
    result = policy().evaluate(snapshot(0, target_age=8))
    assert decision(result).reason == "fresh_candidate_metric_missing"


def test_threshold_margin_and_hold_produce_exactly_one_pending_recommendation():
    first = policy().evaluate(snapshot(0))
    assert decision(first).reason == "condition_hold_not_met"
    second = policy().evaluate(snapshot(5), first.state)
    assert decision(second).action == "steer"
    assert decision(second).target_bssid == TARGET
    third = policy().evaluate(snapshot(6), second.state)
    assert decision(third).action == "none"
    assert decision(third).reason == "steer_pending"


def test_dwell_and_health_are_gates():
    assert decision(policy().evaluate(snapshot(0, association_uptime=19))).reason == "minimum_dwell_not_met"
    assert decision(policy().evaluate(snapshot(0, devices=4))).reason == "mesh_device_count_mismatch"


def test_observed_target_association_enters_cooldown():
    first = policy().evaluate(snapshot(0))
    pending = policy().evaluate(snapshot(5), first.state)
    moved = policy().evaluate(snapshot(6, source=TARGET), pending.state)
    assert decision(moved).reason == "target_association_observed"
    assert moved.state.for_sta(snapshot(0).clients[0].sta_mac).phase == "cooldown"
