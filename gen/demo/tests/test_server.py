from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from room_demo.events import EventStore
from room_demo.server import RoomDemoServer


class FakeInteractions:
    def __init__(self):
        self.revision = 2

    def snapshot(self):
        return {"enabled": True, "revision": self.revision}

    def acquire(self, owner):
        return {"token": "lease-token", "owner": owner, "revision": self.revision}

    def renew(self, token):
        return {"token_seen": token, "revision": self.revision}

    def release(self, token):
        return {"released": token == "lease-token", "revision": self.revision}

    def position(self, role, **body):
        self.revision += 1
        return {"role": role, "revision": self.revision, **body}

    def presence(self, role, **body):
        self.revision += 1
        return {"role": role, "revision": self.revision, **body}

    def move(self, role, **body):
        self.revision += 1
        return {
            "revision": self.revision,
            "movement": {"id": "move-1", "role": role, "status": "running"},
            **body,
        }

    def movement_control(self, movement_id, action, **body):
        self.revision += 1
        return {
            "revision": self.revision,
            "movement": {"id": movement_id, "status": action},
            **body,
        }


class ServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "index.html").write_text("<html>viewer</html>")
        (root / "vendor").mkdir()
        (root / "vendor" / "three.min.js").write_text("window.THREE={};")
        (root / "interaction-model.js").write_text("window.RoomInteractionModel={};")
        world = {
            "schema": "wmdcfg.world-plan.v1",
            "name": "test-world",
            "duration_ms": 1000,
            "tick_ms": 100,
        }
        self.store = EventStore("run-1", world, root / "events.jsonl")
        self.server = RoomDemoServer(("127.0.0.1", 0), self.store, root)
        self.server.start()
        self.addCleanup(self.server.close)
        self.base = f"http://127.0.0.1:{self.server.address[1]}"

    def _json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=2) as response:
            return json.load(response)

    def _request(self, path, method, body):
        request = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.load(response)

    def test_health_current_world_and_viewer(self):
        self.assertEqual(self._json("/healthz")["status"], "ok")
        self.assertEqual(self._json("/api/demo/current")["state"], "preparing")
        self.assertEqual(self._json("/api/demo/world")["name"], "test-world")
        with urllib.request.urlopen(self.base + "/viewer/?mode=live", timeout=2) as response:
            self.assertIn(b"viewer", response.read())
        with urllib.request.urlopen(
            self.base + "/viewer/vendor/three.min.js", timeout=2
        ) as response:
            self.assertIn(b"THREE", response.read())
        with urllib.request.urlopen(
            self.base + "/viewer/interaction-model.js", timeout=2
        ) as response:
            self.assertIn(b"RoomInteractionModel", response.read())

    def test_post_is_not_a_control_surface(self):
        request = urllib.request.Request(self.base + "/api/demo/current", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 405)

    def test_sse_replays_an_ordered_event(self):
        self.store.publish({
            "schema": "easymesh.room-demo.event.v1",
            "run_id": "run-1",
            "sequence": 1,
            "recorded_at": "2026-09-03T00:00:00+00:00",
            "world_time_ms": 100,
            "kind": "scenario.clock",
            "payload": {},
        })
        with urllib.request.urlopen(self.base + "/api/demo/events?after=0", timeout=2) as response:
            self.assertEqual(response.readline().decode().strip(), "id: 1")
            data = response.readline().decode().strip()
        self.assertTrue(data.startswith("data: "))
        self.assertEqual(json.loads(data[6:])["kind"], "scenario.clock")

    def test_events_json_supports_browser_replay(self):
        self.store.emit("scenario.clock", 100, producer="wmdcfg")
        payload = self._json("/api/demo/events.json")
        self.assertEqual(payload["schema"], "easymesh.room-demo.events.v1")
        self.assertEqual(payload["events"][0]["kind"], "scenario.clock")


class InteractiveServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "index.html").write_text("<html>viewer</html>")
        world = {"name": "world", "duration_ms": 1000, "tick_ms": 100}
        store = EventStore("run", world, root / "events.jsonl")
        self.interactions = FakeInteractions()
        self.server = RoomDemoServer(
            ("127.0.0.1", 0), store, root, self.interactions
        )
        self.server.start()
        self.addCleanup(self.server.close)
        self.base = f"http://127.0.0.1:{self.server.address[1]}"

    def _request(self, path, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, method=method, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.load(response)

    def test_lease_position_presence_and_release_routes(self):
        _, state = self._request("/api/demo/interactions")
        self.assertEqual(state["revision"], 2)
        status, lease = self._request(
            "/api/demo/interactions/lease", "POST", {"owner": "browser"}
        )
        self.assertEqual(status, 201)
        _, moved = self._request(
            "/api/demo/roles/sta_01/position", "PUT",
            {"token": lease["token"], "expected_revision": 2,
             "position": [4, 2], "final": True},
        )
        self.assertEqual(moved["role"], "sta_01")
        self.assertEqual(moved["position"], [4, 2])
        _, presence = self._request(
            "/api/demo/roles/sta_01/presence", "PUT",
            {"token": lease["token"], "expected_revision": 3,
             "present": False},
        )
        self.assertFalse(presence["present"])
        _, released = self._request(
            "/api/demo/interactions/lease", "DELETE", {"token": lease["token"]}
        )
        self.assertTrue(released["released"])

    def test_server_owned_movement_routes(self):
        _, lease = self._request(
            "/api/demo/interactions/lease", "POST", {"owner": "browser"}
        )
        status, started = self._request(
            "/api/demo/roles/sta_01/move", "POST",
            {"token": lease["token"], "expected_revision": 2,
             "destination": [8, 2], "speed_mps": 1.4},
        )
        self.assertEqual(status, 201)
        self.assertEqual(started["movement"]["role"], "sta_01")
        _, paused = self._request(
            "/api/demo/movements/move-1/pause", "POST",
            {"token": lease["token"], "expected_revision": 3},
        )
        self.assertEqual(paused["movement"]["status"], "pause")
        _, cancelled = self._request(
            "/api/demo/movements/move-1", "DELETE",
            {"token": lease["token"], "expected_revision": 4},
        )
        self.assertEqual(cancelled["movement"]["status"], "cancel")


if __name__ == "__main__":
    unittest.main()
