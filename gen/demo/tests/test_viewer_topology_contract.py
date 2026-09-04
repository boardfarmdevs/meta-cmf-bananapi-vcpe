from __future__ import annotations

import unittest
from pathlib import Path


VIEWER = (
    Path(__file__).resolve().parents[2]
    / "wmediumd/configurator/worlds/viewer/index.html"
)


class ViewerTopologyContractTests(unittest.TestCase):
    def test_live_backhaul_uses_controller_graph_not_rf_possibilities(self):
        source = VIEWER.read_text(encoding="utf-8")

        self.assertIn("mesh.backhaul_edges || []", source)
        self.assertIn("edge.parent_role", source)
        self.assertIn("edge.child_role", source)
        self.assertIn("else if (!liveMode && !replayMode)", source)
        self.assertIn("Actual mesh backhaul", source)

    def test_live_ap_labels_use_the_same_controller_identity(self):
        source = VIEWER.read_text(encoding="utf-8")

        self.assertIn("const meshNode = observedMeshNode(role);", source)
        self.assertIn("meshNode && meshNode.name", source)
        self.assertIn("actualBackhaulFor(selected)", source)


if __name__ == "__main__":
    unittest.main()
