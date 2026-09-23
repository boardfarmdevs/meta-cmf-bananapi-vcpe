#!/usr/bin/env python3
"""Unit tests for the deterministic steering RF snapshot."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


MODULE_PATH = Path(__file__).with_name("steering-rf-bias.py")
SPEC = importlib.util.spec_from_file_location("steering_rf_bias", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Status:
    def __init__(self, generation: int):
        self.generation = generation


class FakeControl:
    def __init__(self, final_generation: int = 7):
        self.statuses = iter((Status(7), Status(final_generation)))

    def status(self):
        return next(self.statuses)

    def dump_links(self):
        return 7, [
            {"source": "station", "destination": "radio-a", "value": 40},
            {"source": "radio-a", "destination": "station", "value": 41},
            {"source": "station", "destination": "radio-b", "value": 42},
        ]

    def dump_frequency_links(self):
        return 7, [{
            "source": "station",
            "destination": "radio-a",
            "frequency_mhz": 5180,
            "value": 55,
            "override": True,
        }]


class SnapshotTests(unittest.TestCase):
    def test_cross_band_bias_snapshots_both_actual_frequencies(self):
        source = "02:00:00:00:00:01"
        target = "02:00:00:00:00:02"
        station = "02:00:00:00:00:03"
        args = SimpleNamespace(source_bssid=source, target_bssid=target, client="wlan-client-052",
                               frequency=5180, station_radio=None, source_radio=None,
                               target_radio=None, mesh_radio=None, target_snr=60,
                               source_snr=20, other_snr=-20, state=Path("unused"), backend="control")
        inventory = {"radios": [
            {"kind": "station", "container": args.client, "tx_mac": station},
            {"kind": "mesh", "tx_mac": source, "interfaces": [{"mac": source, "frequency_mhz": 2437}]},
            {"kind": "mesh", "tx_mac": target, "interfaces": [{"mac": target, "frequency_mhz": 5180}]},
        ]}
        control = MagicMock()
        status = SimpleNamespace(generation=7, instance_id="medium")
        with patch.object(MODULE, "discover", return_value=inventory), \
                patch.object(MODULE, "medium_client") as context, \
                patch.object(MODULE, "snapshot_link_keys", return_value=(status, [])) as snapshot, \
                patch.object(MODULE, "write_state"):
            context.return_value.__enter__.return_value = control
            self.assertEqual(MODULE.apply(args), 0)
        self.assertEqual({key[2] for key in snapshot.call_args.args[1]}, {2437, 5180})
        generation, updates = control.apply_frequency.call_args.args
        self.assertEqual(generation, 8)
        values = {(row["destination"], row["frequency_mhz"]): row["value"]
                  for row in updates if row["source"] == station}
        self.assertEqual(values, {(source, 2437): 20, (source, 5180): -20,
                                  (target, 2437): -20, (target, 5180): 60})

    def test_combines_frequency_overrides_with_base_links(self):
        status, prior = MODULE.snapshot_frequency_links(
            FakeControl(),
            [("station", "radio-a"), ("radio-a", "station")],
            5180,
        )
        self.assertEqual(status.generation, 7)
        self.assertEqual(prior, [
            {
                "source": "station",
                "destination": "radio-a",
                "frequency_mhz": 5180,
                "value": 55,
                "override": True,
            },
            {
                "source": "radio-a",
                "destination": "station",
                "frequency_mhz": 5180,
                "value": 41,
                "override": False,
            },
        ])

    def test_rejects_a_generation_change(self):
        with self.assertRaisesRegex(RuntimeError, "generation changed"):
            MODULE.snapshot_frequency_links(
                FakeControl(final_generation=8),
                [("station", "radio-a")],
                5180,
            )

    def test_rejects_a_missing_base_link(self):
        with self.assertRaisesRegex(RuntimeError, "snapshot has no link"):
            MODULE.snapshot_frequency_links(
                FakeControl(),
                [("radio-b", "station")],
                5180,
            )

    def test_snapshots_multiple_frequencies_in_one_generation(self):
        _, prior = MODULE.snapshot_link_keys(
            FakeControl(),
            [
                ("station", "radio-a", 5180),
                ("station", "radio-b", 5955),
            ],
        )
        self.assertEqual(prior, [
            {
                "source": "station",
                "destination": "radio-a",
                "frequency_mhz": 5180,
                "value": 55,
                "override": True,
            },
            {
                "source": "station",
                "destination": "radio-b",
                "frequency_mhz": 5955,
                "value": 42,
                "override": False,
            },
        ])


if __name__ == "__main__":
    unittest.main()
