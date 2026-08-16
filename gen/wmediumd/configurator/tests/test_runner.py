from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wmdcfg.actuator import ActuatorError
from wmdcfg.runner import REQUIRED_CAPABILITIES, Runner


SOURCE = "42:00:00:00:01:00"
DESTINATION = "42:00:00:00:02:00"


def _plan() -> dict:
    return {
        "scenario": "runner_test",
        "duration_ms": 0,
        "bindings": {},
        "events": [
            {
                "time_ms": 0,
                "generation": 1,
                "marks": [],
                "updates": [
                    {"source": SOURCE, "destination": DESTINATION, "value": 10}
                ],
            }
        ],
    }


class FakeControlClient:
    fail_restore = False
    last = None

    def __init__(self, socket_path: str):
        self.generation = 0
        self.matrix = {(SOURCE, DESTINATION): 40}
        type(self).last = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def status(self):
        return SimpleNamespace(
            capabilities=REQUIRED_CAPABILITIES,
            generation=self.generation,
        )

    def dump_links(self):
        return self.generation, [
            {"source": source, "destination": destination, "value": value}
            for (source, destination), value in self.matrix.items()
        ]

    def apply(self, generation: int, updates: list[dict]):
        self.generation = generation
        for update in updates:
            if not (self.fail_restore and update["value"] == 40):
                self.matrix[(update["source"], update["destination"])] = update["value"]
        return updates

    def get_link(self, source: str, destination: str):
        return self.generation, self.matrix[(source, destination)]


class RunnerTests(unittest.TestCase):
    def _execute(self, fail_restore: bool):
        FakeControlClient.fail_restore = fail_restore
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        healthy = {
            "api_active": 10,
            "api_total": 10,
            "complete_nodes": 6,
            "topology_nodes": 6,
        }
        patches = (
            patch("wmdcfg.runner.ControlClient", FakeControlClient),
            patch("wmdcfg.runner.mesh_health", return_value=healthy),
            patch("wmdcfg.runner.snapshot", return_value={"stations": []}),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        runner = Runner(_plan(), "/test/control.sock", root)
        return runner, root

    def test_success_restores_and_reports_passed(self):
        runner, _ = self._execute(False)
        run_dir = runner.execute()
        summary = json.loads((run_dir / "summary.json").read_text())
        self.assertEqual(summary["outcome"], "passed")
        self.assertTrue(summary["restored"])
        self.assertIsNone(summary["error"])
        self.assertIsNotNone(summary["execution_elapsed_ms"])
        self.assertEqual(FakeControlClient.last.matrix[(SOURCE, DESTINATION)], 40)

    def test_restore_readback_failure_reports_failed(self):
        runner, root = self._execute(True)
        with self.assertRaisesRegex(ActuatorError, "restoration readback"):
            runner.execute()
        run_dir = next(root.iterdir())
        summary = json.loads((run_dir / "summary.json").read_text())
        self.assertEqual(summary["outcome"], "failed")
        self.assertFalse(summary["restored"])
        self.assertIn("restoration readback", summary["error"])


if __name__ == "__main__":
    unittest.main()
