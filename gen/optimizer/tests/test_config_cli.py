from __future__ import annotations

from pathlib import Path

from optimizer.cli import main
from optimizer.config import load_policy
from optimizer.recorder import Journal
from .helpers import snapshot


def test_example_policy_loads_without_external_yaml_dependency():
    config = load_policy(Path(__file__).parents[1] / "configs" / "threshold-policy.yaml")
    assert config.policy_version == 1
    assert config.current_rcpi_below == 100
    assert config.expected_clients == 10


def test_replay_is_byte_deterministic(tmp_path):
    source = tmp_path / "capture.jsonl"
    journal = Journal(source)
    for item in (snapshot(0), snapshot(5), snapshot(6)):
        journal.append("snapshot", item.to_dict(), recorded_at=item.observed_at)

    policy = Path(__file__).parents[1] / "configs" / "threshold-policy.yaml"
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    assert main(
        ["replay", "--input", str(source), "--policy", str(policy), "--journal", str(first)]
    ) == 0
    assert main(
        ["replay", "--input", str(source), "--policy", str(policy), "--journal", str(second)]
    ) == 0
    assert first.read_bytes() == second.read_bytes()
