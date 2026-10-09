"""The lab's mesh counted from the lab: the five Wi-Fi nodes, the wired extenders and the pods,
and what the tests that compare the controller with it expect (lab_composition.py)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lab_composition import Composition, composition  # noqa: E402


def fake_lxc(instances: dict[str, dict[str, str]], stopped: tuple[str, ...] = ()):
    """LXD with ``instances`` (name -> its user.* settings) running, ``stopped`` stopped."""
    def lxc(*arguments: str) -> str:
        if arguments[:1] == ("list",):
            rows = [f"{name},RUNNING" for name in instances] + [f"{name},STOPPED" for name in stopped]
            return "\n".join(rows) + "\n"
        if arguments[:2] == ("config", "get"):
            return instances.get(arguments[2], {}).get(arguments[3], "") + "\n"
        raise AssertionError(arguments)
    return lxc


WIFI = {name: {} for name in ("bpibroadband", "bpiap", "bpiap-001", "bpiap-002", "bpiap-003")}
CLIENTS = {f"wlan-client-{i:03d}": {} for i in range(3)}


class CompositionTests(unittest.TestCase):
    def test_the_five_wifi_nodes(self):
        lab = composition(fake_lxc({**WIFI, **CLIENTS}))
        self.assertEqual((lab.native, lab.devices, lab.wired, lab.pods), (5, 5, (), ()))
        self.assertEqual(lab.native_model(20), {"devices": 5, "radios": 15, "bss": 50, "associated": 24})
        self.assertEqual(lab.topology(20), {"nodes": 6, "clients": 20, "edges": 5})

    def test_a_wired_extender_is_one_more_agent_with_no_backhaul_station(self):
        lab = composition(fake_lxc({**WIFI, "bpiap-004": {"user.easymesh.backhaul": "wired"}, **CLIENTS}))
        self.assertEqual((lab.native, lab.devices, lab.wired), (6, 6, ("bpiap-004",)))
        # rdk-1009 (9 October): the controller's 6 devices, the topology's 7 nodes and 6 edges
        self.assertEqual(lab.native_model(20), {"devices": 6, "radios": 18, "bss": 60, "associated": 24})
        self.assertEqual(lab.topology(20), {"nodes": 7, "clients": 20, "edges": 6})

    def test_the_pods_are_devices_of_the_controller_not_agents_of_the_lab(self):
        lab = composition(fake_lxc({
            **WIFI, "bpiap-004": {"user.easymesh.backhaul": "wired"},
            "pod-2": {"user.emosa.role": "pod"}, "pod-1": {"user.emosa.role": "pod"},
            "em-gtp": {"user.emosa.role": "gtp"}, **CLIENTS}))
        self.assertEqual((lab.native, lab.devices, lab.pods), (6, 8, ("pod-1", "pod-2")))
        # the lab's own model leaves the pods out (health-audit.sh); the topology has them
        self.assertEqual(lab.native_model(20)["devices"], 6)
        self.assertEqual(lab.topology(20), {"nodes": 9, "clients": 20, "edges": 8})
        self.assertEqual(lab.as_dict(), {"wifi": 5, "wired": ["bpiap-004"], "pods": ["pod-1", "pod-2"],
                                         "native": 6, "devices": 8})

    def test_stopped_instances_and_other_settings_do_not_count(self):
        lab = composition(fake_lxc(
            {**WIFI, "bpiap-005": {"user.easymesh.backhaul": "wifi"}, "bpiap-010": {"user.easymesh.backhaul": "wired"},
             "bpiap-004": {"user.easymesh.backhaul": "wired"}},
            stopped=("bpiap-006", "pod-3")))
        self.assertEqual(lab.wired, ("bpiap-004", "bpiap-010"))
        self.assertEqual(lab.devices, 7)

    def test_a_fixed_composition(self):
        self.assertEqual(Composition().devices, 5)


class ConsumerTests(unittest.TestCase):
    """The tests that compare the controller with the lab take its counts, not a constant."""

    def test_the_live_optimizer_smoke_takes_the_labs_devices(self):
        source = (HERE / "optimizer-live-smoke.py").read_text()
        self.assertIn("--expected-devices", source)
        self.assertIn("composition().devices", source)

    def test_the_steering_matrix_takes_the_labs_agents(self):
        source = (HERE / "steering-matrix.sh").read_text()
        self.assertIn('lab_composition.py" --native', source)
        self.assertNotIn("-ne 5 ]", source)

    def test_the_churn_soak_takes_the_labs_topology_and_model(self):
        source = (HERE / "p0-churn-soak.py").read_text()
        self.assertIn("self.lab.topology(expected_clients)", source)
        self.assertIn("self.lab.native_model(expected_clients)", source)
        self.assertNotIn('"devices": 5, "radios": 15', source)


if __name__ == "__main__":
    unittest.main()
