#!/usr/bin/env python3
"""Unit tests for the deterministic steering RF snapshot."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
