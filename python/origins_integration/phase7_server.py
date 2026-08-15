from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .capability_evolution import CapabilityEvolutionError
from .engineering import BridgeError
from .intelligence_runtime import IntelligenceApprovalError, IntelligenceMountError, IntelligenceRequestError
from .phase7_runtime import Phase7Runtime, Phase7RuntimeError

MAX_BODY = 256 * 1024


class Phase7ServerError(RuntimeError):
    pass


def serve_from_env() -> None:
    host = os.environ.get("ORIGINS_PHASE7_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise Phase7ServerError("Phase 7 service is loopback-only")
    token = os.environ.get("ORIGINS_LOCAL_TOKEN", "")
    if not token:
        raise Phase7ServerError("ORIGINS_LOCAL_TOKEN is required")
    port = int(os.environ.get("ORIGINS_PHASE7_PORT", "49327"))
    runtime = Phase7Runtime.from_env()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _json(self, status: int, value: object) -> None:
            body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return hmac.compare_digest(supplied, expected)

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self._json(401, {"error": "UNAUTHORIZED"})
            return False

        def _body(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise Phase7ServerError("Content-Length is required")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise Phase7ServerError("invalid Content-Length") from exc
            if length < 0 or length > MAX_BODY:
                raise Phase7ServerError("request body exceeds Phase 7 limit")
            raw = self.rfile.read(length)
            try:
                value = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise Phase7ServerError("request body must be JSON") from exc
            if not isinstance(value, dict):
                raise Phase7ServerError("request JSON root must be an object")
            forbidden = {"owner_approved", "approval_state", "self_approve", "runtime_authority_activated"} & set(value)
            if forbidden:
                raise Phase7ServerError(f"client cannot assert authority fields: {', '.join(sorted(forbidden))}")
            return value

        def _conflict(self, exc: Exception) -> None:
            self._json(409, {"error": type(exc).__name__, "detail": str(exc)})

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/v1/health":
                health = runtime.health()
                self._json(
                    200,
                    {
                        "ok": True,
                        "service": "origins-phase7",
                        "phase": 7,
                        "runtime_authority_expansion": health["runtime_authority_expansion"],
                        "model_self_approval": health["model_self_approval"],
                    },
                )
                return
            if not self._require_auth():
                return
            try:
                if path == "/v1/evolutions":
                    return self._json(200, runtime.list())
                if path.startswith("/v1/evolutions/"):
                    evolution_id = path.removeprefix("/v1/evolutions/")
                    return self._json(200, runtime.get(evolution_id))
                self._json(404, {"error": "NOT_FOUND"})
            except (
                CapabilityEvolutionError,
                Phase7RuntimeError,
                IntelligenceMountError,
                IntelligenceRequestError,
                IntelligenceApprovalError,
                BridgeError,
            ) as exc:
                self._conflict(exc)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == "/v1/evolutions/gap":
                    return self._json(201, runtime.confirm_gap(body))
                if not path.startswith("/v1/evolutions/"):
                    return self._json(404, {"error": "NOT_FOUND"})
                parts = path.strip("/").split("/")
                if len(parts) < 4:
                    return self._json(404, {"error": "NOT_FOUND"})
                evolution_id, action = parts[2], "/".join(parts[3:])
                if action == "approval":
                    return self._json(201, runtime.create_approval(evolution_id))
                if action == "approval/decision":
                    return self._json(
                        200,
                        runtime.decide_approval(
                            evolution_id,
                            approval_id=_required(body, "approval_id"),
                            decision=_required(body, "decision"),
                            decided_by=_required(body, "decided_by"),
                        ),
                    )
                if action == "child-operation":
                    return self._json(201, runtime.create_child_upgrade_operation(evolution_id, _required(body, "approval_id")))
                if action == "candidate":
                    return self._json(200, runtime.implement_candidate(evolution_id, body))
                if action == "canary":
                    return self._json(200, runtime.record_canary_from_session(evolution_id, _required(body, "session_id")))
                if action == "decision":
                    return self._json(
                        200,
                        runtime.decide(
                            evolution_id,
                            decision=_required(body, "decision"),
                            decided_by=_required(body, "decided_by"),
                        ),
                    )
                if action == "resume":
                    if body:
                        raise Phase7ServerError("resume accepts no client state")
                    return self._json(200, runtime.resume(evolution_id))
                self._json(404, {"error": "NOT_FOUND"})
            except (
                CapabilityEvolutionError,
                Phase7RuntimeError,
                Phase7ServerError,
                IntelligenceMountError,
                IntelligenceRequestError,
                IntelligenceApprovalError,
                BridgeError,
                KeyError,
                ValueError,
            ) as exc:
                self._conflict(exc)

        def do_PUT(self) -> None:  # noqa: N802
            self._json(405, {"error": "PHASE7_CONTROLLED_TRANSITIONS_ONLY"})

        do_PATCH = do_PUT
        do_DELETE = do_PUT

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _required(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise Phase7ServerError(f"{field} is required")
    return value.strip()


if __name__ == "__main__":
    serve_from_env()
