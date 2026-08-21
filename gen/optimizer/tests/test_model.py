from __future__ import annotations

import pytest

from optimizer.model import Snapshot, normalize_mac
from .helpers import snapshot


def test_snapshot_round_trip_is_lossless():
    original = snapshot(5)
    assert Snapshot.from_dict(original.to_dict()) == original


def test_mac_normalization_rejects_non_mac_input():
    assert normalize_mac("02:00:00:AA:BB:01") == "02:00:00:aa:bb:01"
    with pytest.raises(ValueError, match="invalid MAC"):
        normalize_mac("extender-1")
