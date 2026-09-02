from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gen" / "optimizer"))

from optimizer.model import (
    CandidateObservation,
    ClientObservation,
    MeshHealth,
    Snapshot,
)


SCRIPT = Path(__file__).with_name("optimizer-live-smoke.py")
SPEC = importlib.util.spec_from_file_location("optimizer_live_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def client(sta: str, band: str = "5") -> ClientObservation:
    return ClientObservation(
        sta_mac=sta,
        connected_device_id="02:00:00:00:01:20",
        connected_device_name="Extender-1",
        connected_bssid="02:00:00:aa:aa:01",
        rcpi=120,
        association_uptime_seconds=120,
        metric_observed_at="2026-09-01T00:00:00Z",
        measurement_source="associated_sta_link_metrics",
        band=band,
    )


def candidate(sta: str, bssid: str, band: str) -> CandidateObservation:
    return CandidateObservation(
        sta_mac=sta,
        bssid=bssid,
        device_id="02:00:00:00:02:20",
        device_name="Extender-2",
        rcpi=None,
        metric_observed_at=None,
        measurement_source="controller_bss_inventory_only",
        band=band,
    )


def test_live_smoke_validates_candidates_only_for_selected_clients_and_band():
    first = "02:00:00:00:03:00"
    second = "02:00:00:00:04:00"
    snapshot = Snapshot(
        schema_version=1,
        sequence=0,
        observed_at="2026-09-01T00:00:01Z",
        controller_url="recorded://controller",
        health=MeshHealth(devices=5, clients=2, radios=15, bsses=50),
        clients=(client(first), client(second)),
        candidates=(
            candidate(first, "02:00:00:bb:bb:01", "5"),
            candidate(first, "02:00:00:bb:bb:02", "2.4"),
            candidate(second, "02:00:00:bb:bb:03", "5"),
        ),
    )

    scoped = MODULE.selected_same_band_candidates(snapshot, {first})

    assert [(item.sta_mac, item.bssid) for item in scoped] == [
        (first, "02:00:00:bb:bb:01")
    ]
