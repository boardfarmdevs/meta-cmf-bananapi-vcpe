from __future__ import annotations

import json
import unittest
from pathlib import Path

from wmdcfg.compiler import compile_scenario
from wmdcfg.model import ScenarioError
from wmdcfg.parser import parse


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = json.loads((ROOT / "tests/fixtures/inventory.json").read_text())
BINDINGS = {"client": "wlan-client", "ap_a": "bpibroadband", "ap_b": "bpiap"}


class CompilerTests(unittest.TestCase):
    def compile(self, name: str = "two-ap-crossover.wmd"):
        source = (ROOT / "scenarios" / name).read_text()
        return compile_scenario(parse(source), source, INVENTORY, BINDINGS)

    def test_crossover_is_deterministic_and_complete(self):
        first = self.compile()
        second = self.compile()
        self.assertEqual(first, second)
        self.assertEqual(first["duration_ms"], 60_000)
        self.assertEqual(first["events"][0]["time_ms"], 0)
        self.assertEqual(len(first["events"][0]["updates"]), 4)
        final = next(event for event in first["events"] if event["time_ms"] == 40_000)
        values = {
            (item["source_role"], item["destination_role"]): item["value"]
            for item in final["updates"]
        }
        self.assertEqual(values[("client", "ap_a")], 10)
        self.assertEqual(values[("client", "ap_b")], 42)

    def test_direction_expands_symmetrically(self):
        plan = self.compile("all-strong.wmd")
        pairs = {
            (item["source_role"], item["destination_role"])
            for item in plan["events"][0]["updates"]
        }
        self.assertEqual(
            pairs,
            {("client", "ap_a"), ("ap_a", "client"),
             ("client", "ap_b"), ("ap_b", "client")},
        )

    def test_rcpi_monitor_oscillates_one_live_link(self):
        source = (ROOT / "scenarios/client-rcpi-monitor.wmd").read_text()
        plan = compile_scenario(
            parse(source), source, INVENTORY,
            {"client": "wlan-client", "ap": "bpibroadband"},
        )
        self.assertEqual(plan["duration_ms"], 130_000)
        values = [
            update["value"]
            for event in plan["events"]
            for update in event["updates"]
            if update["source_role"] == "client"
        ]
        self.assertEqual(min(values), 25)
        self.assertEqual(max(values), 45)
        self.assertGreaterEqual(values.count(25), 6)
        self.assertGreaterEqual(values.count(45), 7)

    def test_missing_baseline_pair_is_rejected(self):
        source = """
scenario bad {
  protect backhaul
  restore captured
  role client : station
  role ap_a : fronthaul_ap
  role ap_b : fronthaul_ap
  phase baseline for 1s { link client <-> ap_a snr = 30dB }
}
"""
        with self.assertRaisesRegex(ScenarioError, "first phase"):
            compile_scenario(parse(source), source, INVENTORY, BINDINGS)

    def test_backhaul_protection_is_required(self):
        source = """
scenario bad {
  restore captured
  role client : station
  role ap_a : fronthaul_ap
  phase baseline for 1s { link client <-> ap_a snr = 30dB }
}
"""
        with self.assertRaisesRegex(ScenarioError, "protect backhaul"):
            compile_scenario(
                parse(source), source, INVENTORY,
                {"client": "wlan-client", "ap_a": "bpibroadband"},
            )

    def test_snr_range_and_units_are_strict(self):
        with self.assertRaisesRegex(ScenarioError, "outside"):
            parse("scenario bad { phase x for 1s { link a -> b snr = 80dB } }")
        with self.assertRaisesRegex(ScenarioError, "requires an integer dB"):
            parse("scenario bad { phase x for 1s { link a -> b snr = 10 } }")

    def test_binding_type_is_checked(self):
        source = (ROOT / "scenarios/two-ap-crossover.wmd").read_text()
        bindings = dict(BINDINGS, client="bpibroadband", ap_a="wlan-client")
        with self.assertRaisesRegex(ScenarioError, "expected"):
            compile_scenario(parse(source), source, INVENTORY, bindings)


if __name__ == "__main__":
    unittest.main()
