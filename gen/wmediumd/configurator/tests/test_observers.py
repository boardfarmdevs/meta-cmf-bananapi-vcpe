from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from wmdcfg.observers import mesh_health


class ObserverTests(unittest.TestCase):
    @patch("wmdcfg.observers._run")
    def test_mesh_health_accepts_null_optional_lists(self, run):
        run.return_value = json.dumps(
            {
                "nodes": [
                    {"name": "Controller", "STAList": None, "haulTypes": None},
                    {
                        "name": "Agent-1",
                        "STAList": [{"staMAC": "02:00:00:00:05:00"}],
                        "haulTypes": [
                            {"BSSList": [{} for _ in range(10)]},
                            {"BSSList": None},
                        ],
                    },
                ]
            }
        )

        self.assertEqual(
            mesh_health(),
            {
                "api_active": 1,
                "api_total": 1,
                "topology_nodes": 2,
                "complete_nodes": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
