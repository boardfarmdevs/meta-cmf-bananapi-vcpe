from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .events import EventStore
from .interactions import InteractionError, InteractiveMediumSession


class RoomDemoServer:
    def __init__(
        self,
        address: tuple[str, int],
        store: EventStore,
        viewer_root: Path,
        interactions: InteractiveMediumSession | None = None,
    ):
        self.store = store
        self.viewer_root = viewer_root.resolve()
        self.interactions = interactions
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(address, handler)
        self.httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.httpd.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="room-demo-http",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _handler(self):
        store = self.store
        viewer_root = self.viewer_root
        interactions = self.interactions

        class Handler(BaseHTTPRequestHandler):
            server_version = "EasyMeshRoomDemo/0.1"

            def log_message(self, format, *args):
                return

            def _headers(self, status: int, content_type: str, length: int | None = None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if length is not None:
                    self.send_header("Content-Length", str(length))
                self.end_headers()

            def _json(self, value, status: int = HTTPStatus.OK):
                body = (json.dumps(value, sort_keys=True) + "\n").encode()
                self._headers(status, "application/json; charset=utf-8", len(body))
                self.wfile.write(body)

            def _body(self) -> dict:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as error:
                    raise InteractionError(400, "invalid_length", "invalid Content-Length") from error
                if length <= 0 or length > 64 * 1024:
                    raise InteractionError(400, "invalid_body", "a JSON body is required")
                try:
                    value = json.loads(self.rfile.read(length))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise InteractionError(400, "invalid_json", "request body is not valid JSON") from error
                if not isinstance(value, dict):
                    raise InteractionError(400, "invalid_body", "request body must be an object")
                return value

            def _interaction_error(self, error: Exception):
                if isinstance(error, InteractionError):
                    status, code, message = error.status, error.code, str(error)
                else:
                    status, code, message = 502, "medium_error", str(error)
                self._json({"error": code, "message": message}, status)

            @staticmethod
            def _role_path(path: str) -> tuple[str, str] | None:
                parts = path.strip("/").split("/")
                if len(parts) != 5 or parts[:3] != ["api", "demo", "roles"]:
                    return None
                return unquote(parts[3]), parts[4]

            @staticmethod
            def _movement_path(path: str, *, action: bool) -> tuple[str, str | None] | None:
                parts = path.strip("/").split("/")
                expected = 5 if action else 4
                if len(parts) != expected or parts[:3] != ["api", "demo", "movements"]:
                    return None
                return unquote(parts[3]), (parts[4] if action else None)

            def _static(self, relative: str):
                target = (viewer_root / relative).resolve()
                if viewer_root not in target.parents and target != viewer_root:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = target.read_bytes()
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self._headers(HTTPStatus.OK, content_type, len(body))
                self.wfile.write(body)

            def _events(self, parsed):
                query = parse_qs(parsed.query)
                raw = self.headers.get("Last-Event-ID") or query.get("after", ["0"])[0]
                try:
                    sequence = max(0, int(raw))
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid event sequence")
                    return
                self._headers(HTTPStatus.OK, "text/event-stream; charset=utf-8")
                try:
                    while True:
                        events = store.wait_after(sequence, 10)
                        if not events:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        for event in events:
                            encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
                            self.wfile.write(f"id: {event['sequence']}\ndata: {encoded}\n\n".encode())
                            sequence = event["sequence"]
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", "/viewer/?mode=live")
                    self.end_headers()
                elif parsed.path == "/healthz":
                    current = store.current()
                    self._json({"status": "ok", "run_id": store.run_id,
                                "state": current["state"]})
                elif parsed.path == "/api/demo/current":
                    self._json(store.current())
                elif parsed.path == "/api/demo/world":
                    self._json(store.world)
                elif parsed.path == "/api/demo/events":
                    self._events(parsed)
                elif parsed.path == "/api/demo/events.json":
                    self._json({
                        "schema": "easymesh.room-demo.events.v1",
                        "run_id": store.run_id,
                        "events": store.all(),
                    })
                elif parsed.path == "/api/demo/interactions" and interactions is not None:
                    self._json(interactions.snapshot())
                elif parsed.path in {"/viewer", "/viewer/", "/viewer/index.html"}:
                    self._static("index.html")
                elif parsed.path.startswith("/viewer/"):
                    self._static(parsed.path[len("/viewer/"):])
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self):
                parsed = urlparse(self.path)
                if interactions is None:
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only milestone")
                    return
                try:
                    body = self._body()
                    if parsed.path == "/api/demo/interactions/lease":
                        if body.get("token"):
                            self._json(interactions.renew(str(body["token"])))
                        else:
                            self._json(interactions.acquire(str(body.get("owner") or "")), 201)
                        return
                    matched = self._role_path(parsed.path)
                    if matched is not None and matched[1] == "move":
                        role, _ = matched
                        self._json(interactions.move(
                            role,
                            token=str(body.get("token") or ""),
                            expected_revision=body.get("expected_revision"),
                            destination=body.get("destination"),
                            speed_mps=body.get("speed_mps"),
                            client_sequence=body.get("client_sequence"),
                        ), 201)
                        return
                    movement = self._movement_path(parsed.path, action=True)
                    if movement is not None and movement[1] in {"pause", "resume"}:
                        self._json(interactions.movement_control(
                            movement[0], movement[1],
                            token=str(body.get("token") or ""),
                            expected_revision=body.get("expected_revision"),
                        ))
                        return
                    raise InteractionError(404, "unknown_operation", "unknown interaction operation")
                except Exception as error:
                    self._interaction_error(error)

            def do_PUT(self):
                parsed = urlparse(self.path)
                matched = self._role_path(parsed.path)
                if matched is None or interactions is None:
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only milestone")
                    return
                role, operation = matched
                try:
                    body = self._body()
                    common = {
                        "token": str(body.get("token") or ""),
                        "expected_revision": body.get("expected_revision"),
                        "client_sequence": body.get("client_sequence"),
                    }
                    if operation == "position":
                        result = interactions.position(
                            role, position=body.get("position"),
                            final=bool(body.get("final")), **common,
                        )
                    elif operation == "presence":
                        result = interactions.presence(
                            role, present=body.get("present"), **common,
                        )
                    else:
                        raise InteractionError(404, "unknown_operation", "unknown role operation")
                    self._json(result)
                except Exception as error:
                    self._interaction_error(error)

            def do_DELETE(self):
                parsed = urlparse(self.path)
                if interactions is None:
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only milestone")
                    return
                try:
                    body = self._body()
                    if parsed.path == "/api/demo/interactions/lease":
                        self._json(interactions.release(str(body.get("token") or "")))
                        return
                    movement = self._movement_path(parsed.path, action=False)
                    if movement is not None:
                        self._json(interactions.movement_control(
                            movement[0], "cancel",
                            token=str(body.get("token") or ""),
                            expected_revision=body.get("expected_revision"),
                        ))
                        return
                    raise InteractionError(404, "unknown_operation", "unknown interaction operation")
                except Exception as error:
                    self._interaction_error(error)

        return Handler
