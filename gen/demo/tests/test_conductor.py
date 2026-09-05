from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

if sys.version_info < (3, 9):
    raise unittest.SkipTest("optimizer runtime requires Python 3.9 or newer")

from optimizer.model import ClientObservation, MeshHealth, Snapshot
from optimizer.policy import Decision, Evaluation
from optimizer.state import ClientPolicyState, PolicyState
from room_demo.conductor import (
    LiveConductor,
    _deferred_state,
    _fleet_status,
    _simulated_bss_channels,
    _single_action_state,
)
from room_demo.events import EventStore


class ConductorProjectionTests(unittest.TestCase):
    def test_live_simulated_channels_are_mapped_per_bssid(self):
        plan = {"bindings": {
            "extender_1": {
                "role_type": "fronthaul_ap",
                "band_radios": {"6": {
                    "frequency_mhz": 5955,
                    "interfaces": [{
                        "mac": "02:00:00:00:01:60",
                        "frequency_mhz": 5955,
                    }],
                }},
            },
            "extender_2": {
                "role_type": "fronthaul_ap",
                "band_radios": {"6": {
                    "frequency_mhz": 6135,
                    "interfaces": [{
                        "mac": "02:00:00:00:02:60",
                        "frequency_mhz": 6135,
                    }],
                }},
            },
        }}

        self.assertEqual(_simulated_bss_channels(plan), {
            "02:00:00:00:01:60": 1,
            "02:00:00:00:02:60": 37,
        })

    def test_unexpected_worker_failure_is_retained_as_fatal(self):
        conductor, store = self._conductor()

        def broken():
            raise AttributeError("synthetic worker fault")

        conductor._run_worker("optimizer", broken)
        self.assertEqual(len(conductor.errors), 1)
        self.assertIn("synthetic worker fault", conductor.errors[0])
        event = store.current()["latest"]["worker.error"]
        self.assertTrue(event["payload"]["fatal"])

    def _conductor(self):
        world = {"name": "world", "duration_ms": 1000, "tick_ms": 100}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = EventStore("run", world, Path(temp.name) / "live-events.jsonl")
        plan = {
            "bindings": {
                "sta_mobile_01": {
                    "role_type": "station",
                    "radio_permanent_mac": "02:00:00:00:0c:00",
                    "container": "wlan-client-007",
                },
                "sta_static_01": {
                    "role_type": "station",
                    "radio_permanent_mac": "02:00:00:00:03:00",
                    "container": "wlan-client",
                },
                "extender_1": {
                    "role_type": "fronthaul_ap",
                    "container": "bpiap",
                    "radio_permanent_mac": "02:00:00:00:01:00",
                    "band_radios": {
                        "5": {"interfaces": [{
                            "mac": "02:00:00:00:04:01",
                            "ssid": "private_ssid",
                        }]}
                    },
                },
                "gateway": {
                    "role_type": "fronthaul_ap",
                    "container": "bpibroadband",
                    "radio_permanent_mac": "02:00:00:00:00:00",
                    "band_radios": {
                        "5": {"interfaces": [{
                            "mac": "02:00:00:00:01:01",
                            "ssid": "private_ssid",
                        }]}
                    },
                }
            }
        }
        manifest = {
            "hero": {"role": "sta_mobile_01"},
            "traffic": {"target": "10.0.0.1", "timeout_seconds": 1},
        }
        return LiveConductor(
            store, plan, manifest, mode="recommend", repo_root=Path(temp.name)
        ), store

    def test_closed_action_window_preserves_holding_without_false_pending(self):
        sta = "02:00:00:00:0c:00"
        pending = ClientPolicyState(
            sta_mac=sta,
            phase="pending",
            source_bssid="02:00:00:00:01:01",
            target_bssid="02:00:00:00:04:01",
            condition_since="2026-09-03T00:00:00Z",
            pending_since="2026-09-03T00:00:10Z",
            last_action_at="2026-09-03T00:00:10Z",
        )
        evaluation = Evaluation(
            "hash",
            (Decision(
                sta_mac=sta,
                action="steer",
                reason="threshold_margin_hold_satisfied",
                source_bssid="02:00:00:00:01:01",
                target_bssid="02:00:00:00:04:01",
            ),),
            PolicyState((pending,)),
        )
        state = _deferred_state(PolicyState(), evaluation).for_sta(sta)
        self.assertEqual(state.phase, "holding")
        self.assertIsNone(state.pending_since)
        self.assertIsNone(state.last_action_at)

    def test_single_fleet_action_leaves_other_client_eligible(self):
        first = "02:00:00:00:03:00"
        second = "02:00:00:00:0c:00"
        pending = tuple(
            ClientPolicyState(
                sta_mac=sta,
                phase="pending",
                source_bssid="02:00:00:00:01:01",
                target_bssid="02:00:00:00:04:01",
                condition_since="2026-09-03T00:00:00Z",
                pending_since="2026-09-03T00:00:10Z",
                last_action_at="2026-09-03T00:00:10Z",
            )
            for sta in (first, second)
        )
        evaluation = Evaluation(
            "hash",
            tuple(Decision(
                sta_mac=sta,
                action="steer",
                reason="threshold_margin_hold_satisfied",
                source_bssid="02:00:00:00:01:01",
                target_bssid="02:00:00:00:04:01",
            ) for sta in (first, second)),
            PolicyState(pending),
        )

        state = _single_action_state(PolicyState(), evaluation, first)

        self.assertEqual(state.for_sta(first).phase, "pending")
        self.assertEqual(state.for_sta(second).phase, "holding")
        self.assertIsNone(state.for_sta(second).pending_since)

    def test_fleet_convergence_uses_measured_best_ap_not_hold_phase(self):
        clients = (
            ClientObservation(
                sta_mac="02:00:00:00:03:00",
                connected_device_id="02:00:00:00:00:01",
                connected_device_name="Agent-1",
                connected_bssid="02:00:00:00:01:01",
                rcpi=80,
                association_uptime_seconds=90,
                metric_observed_at="2026-09-03T00:00:00Z",
                measurement_source="associated_sta_link_metrics",
                band="5", ssid="private_ssid", cohort="private",
            ),
        )
        from optimizer.model import CandidateObservation
        snapshot = Snapshot(
            schema_version=1, sequence=0,
            observed_at="2026-09-03T00:00:00Z",
            controller_url="http://controller",
            health=MeshHealth(devices=5, clients=1, bsses=50),
            clients=clients,
            candidates=(CandidateObservation(
                sta_mac=clients[0].sta_mac,
                bssid="02:00:00:00:04:01",
                device_id="02:00:00:00:00:04",
                device_name="Extender-1",
                rcpi=138,
                metric_observed_at="2026-09-03T00:00:00Z",
                measurement_source="candidate",
                band="5",
            ),),
        )

        status = _fleet_status(snapshot, {clients[0].sta_mac})

        self.assertFalse(status["converged"])
        self.assertEqual(status["clients_with_stronger_ap"], 1)
        self.assertEqual(status["stronger_candidates"][0]["gain_rcpi"], 58)

    def test_interactive_action_window_is_not_bound_to_scenario_time(self):
        conductor, _store = self._conductor()
        conductor.interactive = True

        self.assertEqual(
            conductor._action_window(999_999, [150_000, 220_000]),
            (True, "stable_interactive_environment"),
        )

    def test_interactive_subject_is_the_last_present_moved_client(self):
        conductor, _store = self._conductor()
        conductor.interactive = True
        room = {
            "last_rf_role": "sta_static_01",
            "roles": {"sta_static_01": {"present": True}},
        }

        self.assertEqual(
            conductor._optimization_subject(room),
            ("sta_static_01", "02:00:00:00:03:00", "wlan-client"),
        )
        room["roles"]["sta_static_01"]["present"] = False
        self.assertIsNone(conductor._optimization_subject(room))

    def test_controller_observation_is_projected_to_world_role(self):
        conductor, _store = self._conductor()
        snapshot = Snapshot(
            schema_version=1,
            sequence=0,
            observed_at="2026-09-03T00:00:00Z",
            controller_url="http://controller",
            health=MeshHealth(devices=5, clients=1, bsses=50),
            clients=(ClientObservation(
                sta_mac="02:00:00:00:0c:00",
                connected_device_id="02:00:00:00:00:01",
                connected_device_name="Extender-4",
                connected_bssid="02:00:00:00:04:01",
                rcpi=138,
                association_uptime_seconds=90,
                metric_observed_at="2026-09-03T00:00:00Z",
                measurement_source="associated_sta_link_metrics",
                band="5",
                ssid="private_ssid",
                cohort="private",
            ),),
            candidates=(),
        )
        payload = conductor._network_payload(snapshot)
        self.assertEqual(payload["hero"]["role"], "sta_mobile_01")
        self.assertEqual(payload["hero"]["connected_role"], "extender_1")
        self.assertEqual(payload["hero"]["connected_world_name"], "Extender-1")
        self.assertEqual(payload["hero"]["rssi_dbm"], -41)
        self.assertEqual(payload["cohorts"], {"private": 1, "iot": 0, "other": 0})

    def test_controller_backhaul_is_projected_by_bssid_not_display_ordinal(self):
        conductor, _store = self._conductor()
        topology = {
            "nodes": [
                {
                    "id": "02:00:00:00:10:20",
                    "name": "Agent-1",
                    "backhaulMedia": "Ethernet",
                    "haulTypes": [{"BSSList": [{
                        "BSSID": "02:00:00:00:01:01",
                    }]}],
                },
                {
                    "id": "02:00:00:00:44:20",
                    # Deliberately differs from the world role's ordinal.
                    "name": "Extender-4",
                    "backhaulMedia": "Wireless LAN",
                    "upstreamBSSID": "02:00:00:00:02:01",
                    "haulTypes": [{"BSSList": [
                        {
                            # Parent BSSID must not steal the child's role.
                            "BSSID": "02:00:00:00:01:01",
                            "vapMode": 1,
                        },
                        {
                            "BSSID": "02:00:00:00:04:01",
                            "vapMode": 0,
                        },
                    ]}],
                },
            ],
            "edges": [{
                "from": "02:00:00:00:10:20",
                "to": "02:00:00:00:44:20",
                "mediaType": "Wireless LAN",
                "band": 1,
                "channel": 36,
                "upstreamBSSID": "02:00:00:00:02:01",
                "backhaulSTA": "02:00:00:00:03:01",
                "signal": {"status": "fresh", "rcpi": 138, "rssi_dbm": -41},
            }],
        }

        mesh = conductor._topology_payload(topology)

        self.assertTrue(mesh["available"])
        self.assertEqual(mesh["unresolved_edges"], 0)
        self.assertEqual(
            {item["role"]: item["name"] for item in mesh["nodes"]},
            {"gateway": "Agent-1", "extender_1": "Extender-4"},
        )
        self.assertEqual(mesh["backhaul_edges"], [{
            "parent_role": "gateway",
            "child_role": "extender_1",
            "media_type": "Wireless LAN",
            "band": "5",
            "channel": 36,
            "upstream_bssid": "02:00:00:00:02:01",
            "backhaul_sta": "02:00:00:00:03:01",
            "signal": {"status": "fresh", "rcpi": 138, "rssi_dbm": -41},
        }])


if __name__ == "__main__":
    unittest.main()
