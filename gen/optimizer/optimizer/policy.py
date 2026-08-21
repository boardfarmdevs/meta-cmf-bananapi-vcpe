from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
import hashlib
import json
from typing import Any

from .model import CandidateObservation, ClientObservation, Snapshot, parse_time
from .state import ClientPolicyState, PolicyState


@dataclass(frozen=True)
class PolicyConfig:
    policy_version: int = 1
    decision_interval_seconds: float = 1
    current_rcpi_below: int = 100
    minimum_target_gain_rcpi: int = 16
    condition_hold_seconds: float = 5
    minimum_dwell_seconds: int = 20
    steer_timeout_seconds: float = 10
    post_steer_cooldown_seconds: float = 30
    reject_stale_metrics_after_seconds: float = 7
    expected_devices: int = 5
    expected_clients: int = 10

    def __post_init__(self) -> None:
        if self.policy_version != 1:
            raise ValueError("only policy_version 1 is supported")
        for name, value in asdict(self).items():
            if name == "policy_version":
                continue
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if not 0 <= self.current_rcpi_below <= 220:
            raise ValueError("current_rcpi_below must be a valid RCPI")

    def digest(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class CandidateScore:
    bssid: str
    rcpi: int
    gain_rcpi: int


@dataclass(frozen=True)
class Decision:
    sta_mac: str
    action: str
    reason: str
    source_bssid: str
    target_bssid: str | None = None
    current_rcpi: int | None = None
    target_rcpi: int | None = None
    hold_seconds: float = 0
    scores: tuple[CandidateScore, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Evaluation:
    policy_hash: str
    decisions: tuple[Decision, ...]
    state: PolicyState

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_hash": self.policy_hash,
            "decisions": [item.to_dict() for item in self.decisions],
            "state": self.state.to_dict(),
        }


def _fresh(timestamp: str | None, now, maximum_age: float) -> bool:
    if timestamp is None:
        return False
    observed = parse_time(timestamp)
    age = (now - observed).total_seconds()
    return 0 <= age <= maximum_age


class ThresholdPolicy:
    def __init__(self, config: PolicyConfig) -> None:
        self.config = config

    def evaluate(self, snapshot: Snapshot, prior: PolicyState | None = None) -> Evaluation:
        state = prior or PolicyState()
        decisions: list[Decision] = []
        now = parse_time(snapshot.observed_at)

        health_reason = None
        if snapshot.health.devices != self.config.expected_devices:
            health_reason = "mesh_device_count_mismatch"
        elif snapshot.health.clients != self.config.expected_clients:
            health_reason = "client_count_mismatch"

        for client in snapshot.clients:
            old = state.for_sta(client.sta_mac)
            decision, new = self._evaluate_client(
                snapshot, client, old, now, health_reason
            )
            decisions.append(decision)
            state = state.replace(new)
        return Evaluation(self.config.digest(), tuple(decisions), state)

    def _evaluate_client(
        self,
        snapshot: Snapshot,
        client: ClientObservation,
        old: ClientPolicyState,
        now,
        health_reason: str | None,
    ) -> tuple[Decision, ClientPolicyState]:
        base = dict(
            sta_mac=client.sta_mac,
            source_bssid=client.connected_bssid,
            current_rcpi=client.rcpi,
        )
        stable = ClientPolicyState(
            sta_mac=client.sta_mac,
            phase="stable",
            source_bssid=client.connected_bssid,
            last_action_at=old.last_action_at,
        )

        if old.phase == "pending" and old.target_bssid:
            if client.connected_bssid == old.target_bssid:
                until = now + timedelta(seconds=self.config.post_steer_cooldown_seconds)
                new = ClientPolicyState(
                    sta_mac=client.sta_mac,
                    phase="cooldown",
                    source_bssid=client.connected_bssid,
                    cooldown_until=until.isoformat(),
                    last_action_at=old.pending_since,
                )
                return Decision(action="none", reason="target_association_observed", **base), new
            if old.pending_since and (
                now - parse_time(old.pending_since)
            ).total_seconds() <= self.config.steer_timeout_seconds:
                return Decision(action="none", reason="steer_pending", **base), old
            stable = ClientPolicyState(
                sta_mac=client.sta_mac,
                phase="stable",
                source_bssid=client.connected_bssid,
                last_action_at=old.last_action_at,
            )

        if old.phase == "cooldown" and old.cooldown_until:
            if now < parse_time(old.cooldown_until):
                return Decision(action="none", reason="post_steer_cooldown", **base), old

        if health_reason:
            return Decision(action="none", reason=health_reason, **base), stable
        if client.rcpi is None:
            return Decision(action="none", reason="current_metric_missing", **base), stable
        if not _fresh(
            client.metric_observed_at,
            now,
            self.config.reject_stale_metrics_after_seconds,
        ):
            reason = (
                "current_metric_freshness_unknown"
                if client.metric_observed_at is None
                else "current_metric_stale"
            )
            return Decision(action="none", reason=reason, **base), stable
        if client.association_uptime_seconds < self.config.minimum_dwell_seconds:
            return Decision(action="none", reason="minimum_dwell_not_met", **base), stable
        if client.rcpi >= self.config.current_rcpi_below:
            return Decision(action="none", reason="current_link_acceptable", **base), stable

        observed_candidates = [
            item
            for item in snapshot.candidates_for(client.sta_mac)
            if item.eligible
            and item.bssid != client.connected_bssid
            and item.rcpi is not None
            and _fresh(
                item.metric_observed_at,
                now,
                self.config.reject_stale_metrics_after_seconds,
            )
        ]
        if not observed_candidates:
            return Decision(action="none", reason="fresh_candidate_metric_missing", **base), stable

        ranked = sorted(observed_candidates, key=lambda item: (-int(item.rcpi), item.bssid))
        scores = tuple(
            CandidateScore(item.bssid, int(item.rcpi), int(item.rcpi) - client.rcpi)
            for item in ranked
        )
        best: CandidateObservation = ranked[0]
        gain = int(best.rcpi) - client.rcpi
        if gain < self.config.minimum_target_gain_rcpi:
            return (
                Decision(action="none", reason="candidate_gain_too_small", scores=scores, **base),
                stable,
            )

        same_condition = (
            old.phase == "holding"
            and old.source_bssid == client.connected_bssid
            and old.target_bssid == best.bssid
            and old.condition_since is not None
        )
        condition_since = old.condition_since if same_condition else snapshot.observed_at
        held = (now - parse_time(condition_since)).total_seconds()
        if held < self.config.condition_hold_seconds:
            new = ClientPolicyState(
                sta_mac=client.sta_mac,
                phase="holding",
                source_bssid=client.connected_bssid,
                target_bssid=best.bssid,
                condition_since=condition_since,
                last_action_at=old.last_action_at,
            )
            return (
                Decision(
                    action="none",
                    reason="condition_hold_not_met",
                    target_bssid=best.bssid,
                    target_rcpi=best.rcpi,
                    hold_seconds=held,
                    scores=scores,
                    **base,
                ),
                new,
            )

        new = ClientPolicyState(
            sta_mac=client.sta_mac,
            phase="pending",
            source_bssid=client.connected_bssid,
            target_bssid=best.bssid,
            condition_since=condition_since,
            pending_since=snapshot.observed_at,
            last_action_at=old.last_action_at,
        )
        return (
            Decision(
                action="steer",
                reason="threshold_margin_hold_satisfied",
                target_bssid=best.bssid,
                target_rcpi=best.rcpi,
                hold_seconds=held,
                scores=scores,
                **base,
            ),
            new,
        )
