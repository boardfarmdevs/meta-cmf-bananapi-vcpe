from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from wmdcfg.actuator import ActuatorError, DaemonStatus
from room_demo.events import EventStore
from room_demo.interactions import InteractionError, InteractiveMediumSession


WORLD = {
    "schema": "wmdcfg.world-plan.v1",
    "name": "interactive-test",
    "duration_ms": 60_000,
    "tick_ms": 1000,
    "roles": {
        "gateway": "fronthaul_ap",
        "extender_1": "fronthaul_ap",
        "sta_01": "station",
    },
    "generations": [{
        "time_ms": 0,
        "positions": {"gateway": [1, 2], "extender_1": [9, 2], "sta_01": [2, 2]},
        "present": {"gateway": True, "extender_1": True, "sta_01": True},
        "links": [],
    }],
}

LAYOUT = {
    "schema": "wmdcfg.world-layout.v1",
    "name": "interactive-test",
    "space": {"width_m": 10, "height_m": 6},
    "propagation": {
        "reference_distance_m": 1,
        "reference_snr_db_by_band": {"2.4": 54, "5": 50, "6": 47},
        "path_loss_exponent": 2,
        "shadowing_stddev_db": 0,
        "minimum_snr_db": -20,
        "maximum_snr_db": 60,
    },
    "nodes": [
        {"role": "gateway", "kind": "fronthaul_ap", "position": [1, 2]},
        {"role": "extender_1", "kind": "fronthaul_ap", "position": [9, 2]},
    ],
    "walls": [{"name": "partition", "start": [5, 0], "end": [5, 6], "loss_db": 5}],
}

PLAN = {
    "bindings": {
        "gateway": {
            "role_type": "fronthaul_ap", "radio_tx_mac": "02:00:00:00:01:00",
            "fronthaul_frequencies_mhz": {"5": 5180},
            "band_radios": {"5": {"tx_mac": "02:00:00:00:01:20"}},
        },
        "extender_1": {
            "role_type": "fronthaul_ap", "radio_tx_mac": "02:00:00:00:02:00",
            "fronthaul_frequencies_mhz": {"5": 5180},
            "band_radios": {"5": {"tx_mac": "02:00:00:00:02:20"}},
        },
        "sta_01": {
            "role_type": "station", "radio_tx_mac": "02:00:00:00:03:00",
            "radio_permanent_mac": "02:00:00:00:03:00", "container": "client",
        },
    },
}


class FakeClient:
    def __init__(self, _path):
        self.generation = 4
        self.closed = False
        self.values = {}
        self.applied = []

    def _status(self):
        return DaemonStatus(
            "instance", self.generation,
            frozenset({
                "atomic_generations", "readback", "dump_links",
                "frequency_qualified_snr",
            }),
            1024, 3,
        )

    def connect(self):
        return self._status()

    def status(self):
        return self._status()

    def close(self):
        self.closed = True

    def get_frequency_link(self, source, destination, frequency):
        value, overridden = self.values.get((source, destination, frequency), (31, False))
        return self.generation, value, overridden

    def apply_frequency(self, generation, updates):
        if generation != self.generation + 1:
            raise ActuatorError("generation conflict")
        self.generation = generation
        normalized = []
        for item in updates:
            row = {
                "source": item["source"], "destination": item["destination"],
                "frequency_mhz": int(item["frequency_mhz"]),
                "value": int(item.get("value", 0)),
                "override": bool(item.get("override", True)),
            }
            key = (row["source"], row["destination"], row["frequency_mhz"])
            if row["override"]:
                self.values[key] = (row["value"], True)
            else:
                self.values.pop(key, None)
            normalized.append(row)
        self.applied.append(normalized)
        return normalized


class InteractiveMediumSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = EventStore(
            "interactive-1", WORLD, Path(temp.name) / "events.jsonl"
        )
        self.client = FakeClient("fake")
        self.session = InteractiveMediumSession(
            self.store, WORLD, LAYOUT, PLAN, "fake",
            client_factory=lambda _path: self.client,
            minimum_update_interval=0,
        )
        self.session.start()
        self.addCleanup(self.session.close)
        self.lease = self.session.acquire("browser-test")

    def test_position_is_atomic_revisioned_and_frequency_qualified(self):
        result = self.session.position(
            "sta_01", token=self.lease["token"], expected_revision=0,
            position=[8, 2], final=True, client_sequence=7,
        )
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["position"], [8.0, 2.0])
        self.assertEqual(result["changed_link_count"], 4)
        self.assertEqual({item["frequency_mhz"] for item in self.client.applied[-1]}, {5180})
        self.assertEqual(self.client.applied[0][0]["override"], True)
        by_ap = {item["ap_role"]: item for item in result["links"]}
        self.assertEqual(by_ap["extender_1"]["snr_db"], 50)
        self.assertLess(by_ap["gateway"]["snr_db"], 50)
        with self.assertRaisesRegex(InteractionError, "current revision is 1"):
            self.session.position(
                "sta_01", token=self.lease["token"], expected_revision=0,
                position=[7, 2], final=True,
            )

    def test_presence_uses_the_minimum_snr_and_release_freezes_state(self):
        result = self.session.presence(
            "sta_01", token=self.lease["token"], expected_revision=0,
            present=False,
        )
        self.assertFalse(result["present"])
        self.assertTrue(all(item["snr_db"] == -20 for item in result["links"]))
        self.assertTrue(all(item["value"] == -20 for item in self.client.applied[-1]))
        self.session.release(self.lease["token"])
        self.assertFalse(self.session.snapshot()["lease"]["held"])
        self.assertFalse(self.session.snapshot()["roles"]["sta_01"]["present"])

    def test_wrong_lease_and_non_station_are_rejected(self):
        with self.assertRaisesRegex(InteractionError, "does not match"):
            self.session.position(
                "sta_01", token="wrong", expected_revision=0,
                position=[4, 2], final=True,
            )
        with self.assertRaisesRegex(InteractionError, "not interactive"):
            self.session.position(
                "gateway", token=self.lease["token"], expected_revision=0,
                position=[4, 2], final=True,
            )

    def test_close_restores_exact_override_state(self):
        self.session.position(
            "sta_01", token=self.lease["token"], expected_revision=0,
            position=[8, 2], final=True,
        )
        self.assertTrue(any(value[1] for value in self.client.values.values()))
        self.assertTrue(self.session.close())
        self.assertEqual(self.client.values, {})
        self.assertTrue(self.client.closed)
        self.assertTrue(self.store.current()["restored"])

    def test_runtime_world_carries_source_geometry(self):
        runtime = InteractiveMediumSession.runtime_world(WORLD, LAYOUT)
        self.assertEqual(runtime["space"], LAYOUT["space"])
        self.assertEqual(runtime["propagation"], LAYOUT["propagation"])
        self.assertTrue(runtime["interaction"]["authoritative"])

    def test_server_owned_movement_completes_at_the_destination(self):
        started = self.session.move(
            "sta_01", token=self.lease["token"], expected_revision=0,
            destination=[2.2, 2], speed_mps=10, client_sequence=11,
        )
        self.assertEqual(started["revision"], 1)
        self.assertEqual(started["movement"]["status"], "running")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            movement = self.session.snapshot()["movements"][-1]
            if movement["status"] == "completed":
                break
            time.sleep(0.02)
        self.assertEqual(movement["status"], "completed")
        self.assertEqual(movement["position"], [2.2, 2.0])
        self.assertEqual(self.session.snapshot()["roles"]["sta_01"]["position"], [2.2, 2.0])
        kinds = [item["kind"] for item in self.store.all()]
        self.assertIn("interaction.movement.started", kinds)
        self.assertIn("interaction.movement.completed", kinds)

    def test_releasing_lease_cancels_a_server_owned_movement(self):
        started = self.session.move(
            "sta_01", token=self.lease["token"], expected_revision=0,
            destination=[8, 2], speed_mps=0.1,
        )
        self.session.release(self.lease["token"])
        movement = next(
            item for item in self.session.snapshot()["movements"]
            if item["id"] == started["movement"]["id"]
        )
        self.assertEqual(movement["status"], "cancelled")
        self.assertEqual(movement["reason"], "lease_released")

    def test_server_owned_movement_can_pause_resume_and_cancel(self):
        started = self.session.move(
            "sta_01", token=self.lease["token"], expected_revision=0,
            destination=[8, 2], speed_mps=0.1,
        )
        movement_id = started["movement"]["id"]
        paused = self.session.movement_control(
            movement_id, "pause", token=self.lease["token"],
            expected_revision=started["revision"],
        )
        self.assertEqual(paused["movement"]["status"], "paused")
        position = self.session.snapshot()["roles"]["sta_01"]["position"]
        time.sleep(0.25)
        self.assertEqual(
            self.session.snapshot()["roles"]["sta_01"]["position"], position
        )
        resumed = self.session.movement_control(
            movement_id, "resume", token=self.lease["token"],
            expected_revision=paused["revision"],
        )
        self.assertEqual(resumed["movement"]["status"], "running")
        cancelled = self.session.movement_control(
            movement_id, "cancel", token=self.lease["token"],
            expected_revision=resumed["revision"],
        )
        self.assertEqual(cancelled["movement"]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
