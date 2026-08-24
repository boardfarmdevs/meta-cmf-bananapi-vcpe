from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


POOL = Path(__file__).resolve().parents[1] / "wlan-client-pool.sh"


def plan(profile: str) -> str:
    return subprocess.run(
        (str(POOL), "plan", "--profile", profile),
        check=True,
        text=True,
        capture_output=True,
    ).stdout


@pytest.mark.parametrize(
    ("profile", "cohorts", "hwsim"),
    (
        ("small", "private=10\tiot=10\ttotal=20", "required=25\tpool=32"),
        ("medium", "private=25\tiot=25\ttotal=50", "required=55\tpool=64"),
        ("stress", "private=50\tiot=50\ttotal=100", "required=105\tpool=dynamic-required"),
    ),
)
def test_named_client_profiles_have_stable_counts(profile, cohorts, hwsim):
    output = plan(profile)

    assert f"CLIENTS\t{cohorts}" in output
    assert f"HWSIM\t{hwsim}" in output


def test_small_profile_assigns_distinct_ssid_cohorts_and_security():
    rows = plan("small").splitlines()[4:]

    assert len(rows) == 20
    assert all("\tprivate\t" in row for row in rows[:10])
    assert all("\tiot\t" in row and row.endswith("\tiot_ssid\twpa2\tauto") for row in rows[10:])
    assert rows[8].endswith("\tprivate_ssid\twpa2\t2.4")
    assert rows[9].endswith("\tprivate_ssid\tsae\t6")
    assert rows[9].startswith("9\twlan-client-009\t")
    assert rows[10].startswith("10\twlan-client-010\t")
