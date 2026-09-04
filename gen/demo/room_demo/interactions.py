from __future__ import annotations

import copy
import datetime as dt
import math
import secrets
import threading
import time
from typing import Any, Callable

from wmdcfg.actuator import ActuatorError, ControlClient
from wmdcfg.runner import FREQUENCY_CAPABILITIES, Runner
from wmdcfg.world import _link

from .events import EventStore


class InteractionError(RuntimeError):
    """A validated interactive-control failure suitable for an HTTP response."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


class InteractiveMediumSession:
    """Revisioned room state and the sole interactive wmediumd writer.

    The session deliberately works in stable world roles.  The existing
    configurator plan is the only component allowed to translate those roles
    into live radio identities and per-band frequencies.
    """

    def __init__(
        self,
        store: EventStore,
        world: dict[str, Any],
        layout: dict[str, Any],
        plan: dict[str, Any],
        socket_path: str,
        *,
        client_factory: Callable[[str], ControlClient] = ControlClient,
        lease_seconds: int = 30,
        minimum_update_interval: float = 0.15,
    ) -> None:
        self.store = store
        self.world = world
        self.layout = layout
        self.plan = plan
        self.socket_path = socket_path
        self.client_factory = client_factory
        self.lease_seconds = max(10, min(120, int(lease_seconds)))
        self.minimum_update_interval = max(0.0, float(minimum_update_interval))
        self._lock = threading.RLock()
        self._client: ControlClient | None = None
        self._instance_id: str | None = None
        self._generation = 0
        self._revision = 0
        self._started_at = time.monotonic()
        self._lease: dict[str, Any] | None = None
        self._last_update_at = 0.0
        self._baseline: dict[tuple[str, str, int], tuple[int, bool]] = {}
        self._restored = False
        self._faulted: str | None = None
        self._closing = False
        self._movements: dict[str, dict[str, Any]] = {}
        self._movement_threads: dict[str, threading.Thread] = {}
        first = world["generations"][0]
        self._roles = {
            role: {
                "position": [float(value) for value in first["positions"][role]],
                "present": bool(first["present"][role]),
            }
            for role in sorted(world["roles"])
        }
        self._initial_roles = copy.deepcopy(self._roles)
        self._allowed_roles = tuple(
            role for role in sorted(world["roles"])
            if world["roles"][role] == "station"
        )
        layout_nodes = {item["role"]: dict(item) for item in layout.get("nodes", [])}
        self._nodes = {
            role: {"role": role, **layout_nodes.get(role, {})}
            for role in world["roles"]
        }

    def _world_time(self) -> int:
        return max(0, round((time.monotonic() - self._started_at) * 1000))

    @staticmethod
    def runtime_world(world: dict[str, Any], layout: dict[str, Any]) -> dict[str, Any]:
        """Add the source geometry needed by a live viewer without resigning a Golden World."""
        result = copy.deepcopy(world)
        result["space"] = copy.deepcopy(layout["space"])
        result["propagation"] = copy.deepcopy(layout["propagation"])
        result["interaction"] = {
            "authoritative": True,
            "position_url": "/api/demo/roles/{role}/position",
            "presence_url": "/api/demo/roles/{role}/presence",
            "move_url": "/api/demo/roles/{role}/move",
            "movement_url": "/api/demo/movements/{movement}",
        }
        return result

    def start(self) -> None:
        with self._lock:
            if self._client is not None:
                raise InteractionError(409, "already_started", "interactive session is already started")
            client = self.client_factory(self.socket_path)
            try:
                status = client.connect()
                missing = FREQUENCY_CAPABILITIES - status.capabilities
                if missing:
                    raise ActuatorError(
                        f"daemon lacks interactive capabilities {sorted(missing)}"
                    )
                self._client = client
                self._instance_id = status.instance_id
                self._generation = status.generation
                self._started_at = time.monotonic()
                initial_updates = []
                for role in self._allowed_roles:
                    updates, _ = self._links_for_role(role)
                    initial_updates.extend(updates)
                if len(initial_updates) > status.max_updates:
                    raise ActuatorError(
                        f"initial room requires {len(initial_updates)} updates, "
                        f"daemon limit is {status.max_updates}"
                    )
                self._capture_baseline(initial_updates)
                generation, applied = Runner._apply_generation(
                    client, self._generation, initial_updates, True
                )
                self._generation = generation
                for item in applied:
                    _, value, overridden = client.get_frequency_link(
                        item["source"], item["destination"], item["frequency_mhz"]
                    )
                    if value != item["value"] or overridden != item["override"]:
                        raise ActuatorError("initial interactive generation readback mismatch")
                self.store.emit(
                    "rf.generation.applied", 0,
                    {
                        "revision": 0,
                        "role": None,
                        "cause": "interactive-initial-state",
                        "daemon_generation": self._generation,
                        "changed_link_count": len(applied),
                    },
                    producer="interaction",
                )
                self.store.emit(
                    "interaction.session.ready", 0,
                    {
                        "revision": self._revision,
                        "allowed_roles": list(self._allowed_roles),
                        "daemon_instance_id": status.instance_id,
                        "daemon_generation": status.generation,
                    },
                    producer="interaction",
                )
            except Exception:
                if self._client is not None and self._baseline:
                    try:
                        self.restore()
                    except Exception:
                        pass
                client.close()
                self._client = None
                raise

    def _expire_lease(self) -> None:
        if self._lease is None or self._lease["expires_monotonic"] > time.monotonic():
            return
        owner = self._lease["owner"]
        token = self._lease["token"]
        self._lease = None
        self._cancel_owned_movements(token, "lease_expired")
        self.store.emit(
            "interaction.lease.expired", self._world_time(), {"owner": owner},
            producer="interaction",
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._expire_lease()
            lease = None if self._lease is None else {
                "held": True,
                "owner": self._lease["owner"],
                "expires_at": self._lease["expires_at"],
            }
            return {
                "schema": "easymesh.room-demo.interactions.v1",
                "enabled": self._client is not None,
                "revision": self._revision,
                "allowed_roles": list(self._allowed_roles),
                "roles": copy.deepcopy(self._roles),
                "lease": lease or {"held": False},
                "daemon": {
                    "instance_id": self._instance_id,
                    "generation": self._generation,
                },
                "movements": [
                    self._public_movement(value)
                    for value in sorted(
                        self._movements.values(), key=lambda item: item["created_monotonic"]
                    )
                ],
                "restored": self._restored,
                "fault": self._faulted,
            }

    def acquire(self, owner: str) -> dict[str, Any]:
        owner = str(owner or "").strip()[:80]
        if not owner:
            raise InteractionError(400, "invalid_owner", "lease owner is required")
        with self._lock:
            self._expire_lease()
            if self._lease is not None:
                raise InteractionError(
                    409, "lease_held",
                    f"interactive control is held by {self._lease['owner']}",
                )
            token = secrets.token_urlsafe(24)
            expires = time.monotonic() + self.lease_seconds
            expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                seconds=self.lease_seconds
            )
            self._lease = {
                "token": token,
                "owner": owner,
                "expires_monotonic": expires,
                "expires_at": expires_at.isoformat(),
            }
            self.store.emit(
                "interaction.lease.acquired", self._world_time(),
                {"owner": owner, "expires_at": expires_at.isoformat()},
                producer="interaction",
            )
            return {
                "token": token,
                "owner": owner,
                "expires_at": expires_at.isoformat(),
                "lease_seconds": self.lease_seconds,
                "revision": self._revision,
            }

    def renew(self, token: str) -> dict[str, Any]:
        with self._lock:
            lease = self._require_lease(token)
            expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                seconds=self.lease_seconds
            )
            lease["expires_monotonic"] = time.monotonic() + self.lease_seconds
            lease["expires_at"] = expires_at.isoformat()
            return {
                "owner": lease["owner"],
                "expires_at": expires_at.isoformat(),
                "lease_seconds": self.lease_seconds,
                "revision": self._revision,
            }

    def release(self, token: str) -> dict[str, Any]:
        with self._lock:
            lease = self._require_lease(token)
            owner = lease["owner"]
            self._lease = None
            self._cancel_owned_movements(token, "lease_released")
            self.store.emit(
                "interaction.lease.released", self._world_time(), {"owner": owner},
                producer="interaction",
            )
            return {"released": True, "revision": self._revision}

    def _require_lease(self, token: str) -> dict[str, Any]:
        self._expire_lease()
        if self._lease is None:
            raise InteractionError(409, "lease_required", "interactive control lease is required")
        if not secrets.compare_digest(str(token or ""), self._lease["token"]):
            raise InteractionError(403, "lease_mismatch", "interactive control lease does not match")
        return self._lease

    def _validate_mutation(self, role: str, token: str, expected_revision: Any) -> None:
        if self._client is None:
            raise InteractionError(503, "not_started", "interactive medium is unavailable")
        if self._faulted is not None:
            raise InteractionError(
                503, "session_faulted",
                f"interactive medium was restored after an actuator failure: {self._faulted}",
            )
        self._require_lease(token)
        if role not in self._allowed_roles:
            raise InteractionError(400, "role_not_interactive", f"role {role!r} is not interactive")
        try:
            revision = int(expected_revision)
        except (TypeError, ValueError) as error:
            raise InteractionError(400, "invalid_revision", "expected_revision is required") from error
        if revision != self._revision:
            raise InteractionError(
                409, "stale_revision",
                f"expected revision {revision}, current revision is {self._revision}",
            )

    def _clamp_position(self, value: Any) -> list[float]:
        if not isinstance(value, list) or len(value) != 2:
            raise InteractionError(400, "invalid_position", "position must be [x, y]")
        try:
            point = [float(value[0]), float(value[1])]
        except (TypeError, ValueError) as error:
            raise InteractionError(400, "invalid_position", "position must contain numbers") from error
        if not all(math.isfinite(item) for item in point):
            raise InteractionError(400, "invalid_position", "position must contain finite numbers")
        width = float(self.layout["space"]["width_m"])
        height = float(self.layout["space"]["height_m"])
        if not 0 <= point[0] <= width or not 0 <= point[1] <= height:
            raise InteractionError(
                400, "outside_room",
                f"position must be inside 0..{width:g} by 0..{height:g} metres",
            )
        return [round(point[0], 3), round(point[1], 3)]

    def position(
        self,
        role: str,
        *,
        token: str,
        expected_revision: Any,
        position: Any,
        final: bool = False,
        client_sequence: Any = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._validate_mutation(role, token, expected_revision)
            self._cancel_role_movement(role, "direct_position")
            now = time.monotonic()
            if not final and now - self._last_update_at < self.minimum_update_interval:
                raise InteractionError(429, "rate_limited", "position updates are limited to five per second")
            point = self._clamp_position(position)
            previous = copy.deepcopy(self._roles[role])
            self._roles[role]["position"] = point
            try:
                result = self._apply_role(role, "position", client_sequence=client_sequence)
            except Exception:
                if self._faulted is None:
                    self._roles[role] = previous
                raise
            self._last_update_at = now
            return result

    def presence(
        self,
        role: str,
        *,
        token: str,
        expected_revision: Any,
        present: Any,
        client_sequence: Any = None,
    ) -> dict[str, Any]:
        if not isinstance(present, bool):
            raise InteractionError(400, "invalid_presence", "present must be true or false")
        with self._lock:
            self._validate_mutation(role, token, expected_revision)
            if not present:
                self._cancel_role_movement(role, "role_absent")
            previous = copy.deepcopy(self._roles[role])
            self._roles[role]["present"] = present
            try:
                return self._apply_role(role, "presence", client_sequence=client_sequence)
            except Exception:
                if self._faulted is None:
                    self._roles[role] = previous
                raise

    @staticmethod
    def _public_movement(movement: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in movement.items()
            if key not in {"lease_token", "wake", "created_monotonic", "started_monotonic",
                           "paused_monotonic", "paused_seconds"}
        }

    def _cancel_movement(self, movement: dict[str, Any], reason: str) -> None:
        if movement["status"] not in {"running", "paused"}:
            return
        movement["status"] = "cancelled"
        movement["reason"] = reason
        movement["position"] = list(self._roles[movement["role"]]["position"])
        movement["wake"].set()
        self.store.emit(
            "interaction.movement.cancelled", self._world_time(),
            {"revision": self._revision, "reason": reason,
             "movement": self._public_movement(movement)},
            producer="interaction",
        )

    def _cancel_role_movement(self, role: str, reason: str) -> None:
        for movement in self._movements.values():
            if movement["role"] == role:
                self._cancel_movement(movement, reason)

    def _cancel_owned_movements(self, token: str, reason: str) -> None:
        for movement in self._movements.values():
            if movement.get("lease_token") == token:
                self._cancel_movement(movement, reason)

    def move(
        self,
        role: str,
        *,
        token: str,
        expected_revision: Any,
        destination: Any,
        speed_mps: Any,
        client_sequence: Any = None,
    ) -> dict[str, Any]:
        """Start a server-owned constant-speed path for one station role."""
        with self._lock:
            self._validate_mutation(role, token, expected_revision)
            target = self._clamp_position(destination)
            try:
                speed = float(speed_mps)
            except (TypeError, ValueError) as error:
                raise InteractionError(400, "invalid_speed", "speed_mps must be a number") from error
            if not math.isfinite(speed) or not 0.1 <= speed <= 10.0:
                raise InteractionError(
                    400, "invalid_speed", "speed_mps must be between 0.1 and 10.0",
                )
            self._cancel_role_movement(role, "superseded")
            start = list(self._roles[role]["position"])
            distance = math.dist(start, target)
            movement_id = secrets.token_hex(8)
            now = time.monotonic()
            movement = {
                "id": movement_id,
                "role": role,
                "status": "running",
                "start": start,
                "destination": target,
                "position": start,
                "speed_mps": round(speed, 3),
                "distance_m": round(distance, 3),
                "remaining_m": round(distance, 3),
                "duration_ms": round(distance / speed * 1000),
                "progress": 0.0,
                "client_sequence": client_sequence,
                "lease_token": token,
                "created_monotonic": now,
                "started_monotonic": now,
                "paused_monotonic": None,
                "paused_seconds": 0.0,
                "wake": threading.Event(),
            }
            self._movements[movement_id] = movement
            self._revision += 1
            payload = {
                "revision": self._revision,
                "movement": self._public_movement(movement),
            }
            self.store.emit(
                "interaction.movement.started", self._world_time(), payload,
                producer="interaction",
            )
            thread = threading.Thread(
                target=self._movement_worker,
                args=(movement_id,),
                name=f"room-demo-move-{role}",
                daemon=True,
            )
            self._movement_threads[movement_id] = thread
            thread.start()
            return payload

    def _movement_worker(self, movement_id: str) -> None:
        while True:
            with self._lock:
                movement = self._movements[movement_id]
                self._expire_lease()
                if self._closing or movement["status"] in {"cancelled", "completed", "failed"}:
                    return
                if movement["status"] == "paused":
                    wake = movement["wake"]
                    delay = 0.5
                elif (
                    self._lease is None
                    or not secrets.compare_digest(
                        movement["lease_token"], self._lease["token"]
                    )
                ):
                    self._cancel_movement(movement, "lease_lost")
                    return
                else:
                    now = time.monotonic()
                    elapsed = max(
                        0.0,
                        now - movement["started_monotonic"] - movement["paused_seconds"],
                    )
                    duration = max(0.001, movement["duration_ms"] / 1000)
                    fraction = min(1.0, elapsed / duration)
                    point = [
                        round(
                            movement["start"][axis]
                            + (movement["destination"][axis] - movement["start"][axis])
                            * fraction,
                            3,
                        )
                        for axis in (0, 1)
                    ]
                    previous = copy.deepcopy(self._roles[movement["role"]])
                    self._roles[movement["role"]]["position"] = point
                    try:
                        applied = self._apply_role(
                            movement["role"], "position",
                            client_sequence=movement["client_sequence"],
                        )
                    except Exception as error:
                        if self._faulted is None:
                            self._roles[movement["role"]] = previous
                        movement["status"] = "failed"
                        movement["reason"] = str(error)
                        self.store.emit(
                            "interaction.movement.failed", self._world_time(),
                            {"revision": self._revision, "reason": str(error),
                             "movement": self._public_movement(movement)},
                            producer="interaction",
                        )
                        return
                    movement["position"] = point
                    movement["progress"] = round(fraction, 4)
                    movement["remaining_m"] = round(
                        math.dist(point, movement["destination"]), 3
                    )
                    movement["daemon_generation"] = applied["daemon_generation"]
                    movement["revision"] = self._revision
                    if fraction >= 1:
                        movement["status"] = "completed"
                        movement["remaining_m"] = 0.0
                        kind = "interaction.movement.completed"
                    else:
                        kind = "interaction.movement.progress"
                    self.store.emit(
                        kind, self._world_time(),
                        {"revision": self._revision,
                         "movement": self._public_movement(movement)},
                        producer="interaction",
                    )
                    if fraction >= 1:
                        return
                    wake = movement["wake"]
                    delay = max(0.2, self.minimum_update_interval)
            wake.wait(delay)
            wake.clear()

    def movement_control(
        self,
        movement_id: str,
        action: str,
        *,
        token: str,
        expected_revision: Any,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_lease(token)
            try:
                revision = int(expected_revision)
            except (TypeError, ValueError) as error:
                raise InteractionError(
                    400, "invalid_revision", "expected_revision is required"
                ) from error
            # Progress advances the global room revision up to five times per
            # second. A movement-specific control remains unambiguous because
            # both its opaque ID and originating lease must match, so accept a
            # revision that was current when the operator clicked. A future
            # revision is never valid.
            if revision > self._revision:
                raise InteractionError(
                    409, "stale_revision",
                    f"expected revision {revision} is ahead of current revision "
                    f"{self._revision}",
                )
            movement = self._movements.get(movement_id)
            if movement is None:
                raise InteractionError(404, "movement_not_found", "movement does not exist")
            if not secrets.compare_digest(movement["lease_token"], token):
                raise InteractionError(403, "lease_mismatch", "movement belongs to another lease")
            now = time.monotonic()
            if action == "pause":
                if movement["status"] != "running":
                    raise InteractionError(409, "movement_not_running", "movement is not running")
                movement["status"] = "paused"
                movement["paused_monotonic"] = now
            elif action == "resume":
                if movement["status"] != "paused":
                    raise InteractionError(409, "movement_not_paused", "movement is not paused")
                movement["paused_seconds"] += now - movement["paused_monotonic"]
                movement["paused_monotonic"] = None
                movement["status"] = "running"
                movement["wake"].set()
            elif action == "cancel":
                if movement["status"] not in {"running", "paused"}:
                    raise InteractionError(409, "movement_not_active", "movement is not active")
                self._revision += 1
                movement["revision"] = self._revision
                self._cancel_movement(movement, "operator_cancelled")
                return {
                    "revision": self._revision,
                    "movement": self._public_movement(movement),
                }
            else:
                raise InteractionError(400, "invalid_action", "unknown movement action")
            self._revision += 1
            movement["revision"] = self._revision
            payload = {
                "revision": self._revision,
                "movement": self._public_movement(movement),
            }
            if action != "cancel":
                self.store.emit(
                    f"interaction.movement.{action}d", self._world_time(), payload,
                    producer="interaction",
                )
            return payload

    def _links_for_role(self, role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positions = {
            name: tuple(value["position"]) for name, value in self._roles.items()
        }
        present = {name: bool(value["present"]) for name, value in self._roles.items()}
        station = self._nodes[role]
        station_binding = self.plan["bindings"][role]
        updates: list[dict[str, Any]] = []
        summary: list[dict[str, Any]] = []
        for ap_role in sorted(
            name for name, kind in self.world["roles"].items()
            if kind == "fronthaul_ap"
        ):
            ap = self._nodes[ap_role]
            ap_binding = self.plan["bindings"][ap_role]
            down = _link(
                ap, station, positions, present, self.layout, {"seed": 0},
                self._revision + 1, "fronthaul",
            )
            up = _link(
                station, ap, positions, present, self.layout, {"seed": 0},
                self._revision + 1, "fronthaul",
            )
            for band in ("2.4", "5", "6"):
                frequency = ap_binding.get("fronthaul_frequencies_mhz", {}).get(band)
                if frequency is None:
                    continue
                radio = ap_binding.get("band_radios", {}).get(band)
                ap_mac = str((radio or {}).get("tx_mac") or ap_binding["radio_tx_mac"])
                station_mac = str(station_binding["radio_tx_mac"])
                for source, destination, value in (
                    (ap_mac, station_mac, down["snr_db_by_band"][band]),
                    (station_mac, ap_mac, up["snr_db_by_band"][band]),
                ):
                    updates.append({
                        "source": source,
                        "destination": destination,
                        "frequency_mhz": int(frequency),
                        "value": int(value),
                        "override": True,
                    })
                summary.append({
                    "ap_role": ap_role,
                    "band": band,
                    "frequency_mhz": int(frequency),
                    "distance_m": down["distance_m"],
                    "wall_loss_db": down["wall_loss_db"],
                    "snr_db": int(down["snr_db_by_band"][band]),
                })
        if not updates:
            raise InteractionError(500, "no_links", f"role {role!r} resolved no live RF links")
        return updates, summary

    def _capture_baseline(self, updates: list[dict[str, Any]]) -> None:
        assert self._client is not None
        for item in updates:
            key = (item["source"], item["destination"], item["frequency_mhz"])
            if key in self._baseline:
                continue
            _, value, overridden = self._client.get_frequency_link(*key)
            self._baseline[key] = (value, overridden)

    def _apply_role(
        self, role: str, change: str, *, client_sequence: Any
    ) -> dict[str, Any]:
        assert self._client is not None
        updates, links = self._links_for_role(role)
        applied_started = False
        try:
            self._capture_baseline(updates)
            generation, applied = Runner._apply_generation(
                self._client, self._generation, updates, True
            )
            applied_started = True
            self._generation = generation
            readback = []
            for item in applied:
                _, value, overridden = self._client.get_frequency_link(
                    item["source"], item["destination"], item["frequency_mhz"]
                )
                readback.append({**item, "value": value, "override": overridden})
            if readback != applied:
                raise ActuatorError("interactive generation readback mismatch")
            self._revision += 1
        except Exception as error:
            if applied_started:
                self._faulted = str(error)
                self._roles = copy.deepcopy(self._initial_roles)
                self.restore()
            raise
        payload = {
            "revision": self._revision,
            "role": role,
            "position": list(self._roles[role]["position"]),
            "present": self._roles[role]["present"],
            "change": change,
            "client_sequence": client_sequence,
            "daemon_generation": self._generation,
            "changed_link_count": len(applied),
            "links": links,
        }
        self.store.emit(
            f"interaction.{change}.accepted", self._world_time(), payload,
            producer="interaction",
        )
        self.store.emit(
            "rf.generation.applied", self._world_time(),
            {
                "revision": self._revision,
                "role": role,
                "cause": change,
                "daemon_generation": self._generation,
                "changed_link_count": len(applied),
            },
            producer="interaction",
        )
        return payload

    def restore(self) -> bool:
        with self._lock:
            if self._client is None:
                return self._restored
            self.store.emit(
                "rf.restore.started", self._world_time(),
                {"touched_links": len(self._baseline)}, producer="interaction",
            )
            restored = True
            if self._baseline:
                updates = [
                    {
                        "source": source,
                        "destination": destination,
                        "frequency_mhz": frequency,
                        "value": value if overridden else 0,
                        "override": overridden,
                    }
                    for (source, destination, frequency), (value, overridden)
                    in sorted(self._baseline.items())
                ]
                self._generation, _ = Runner._apply_generation(
                    self._client, self._generation, updates, True
                )
                for item in updates:
                    key = (item["source"], item["destination"], item["frequency_mhz"])
                    _, value, overridden = self._client.get_frequency_link(*key)
                    expected_value, expected_override = self._baseline[key]
                    if value != expected_value or overridden != expected_override:
                        restored = False
            self._restored = restored
            self.store.emit(
                "rf.restore.completed", self._world_time(),
                {
                    "verified": restored,
                    "daemon_generation": self._generation,
                    "restored_links": len(self._baseline),
                },
                producer="interaction",
            )
            return restored

    def close(self) -> bool:
        with self._lock:
            self._closing = True
            for movement in self._movements.values():
                self._cancel_movement(movement, "session_stopped")
            threads = list(self._movement_threads.values())
        for thread in threads:
            thread.join(timeout=2)
        with self._lock:
            if self._client is None:
                return self._restored
            try:
                return self.restore()
            finally:
                self._client.close()
                self._client = None
