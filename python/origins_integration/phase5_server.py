from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .oracle_live import OracleLiveError, OracleRemoteNodeMount
from .phase5_runtime import LumiMount, OracleBrowserMount, Phase5Error

MAX_BODY_BYTES = 512 * 1024
DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 48720


def _require_loopback(host: str) -> str:
    value = str(host or "").strip()
    if value not in {"127.0.0.1", "localhost", "::1"}:
        raise Phase5Error("Phase 5 service refuses non-loopback bind addresses")
    return value


def _local_token() -> str:
    token = str(os.environ.get("ORIGINS_LOCAL_TOKEN") or "").strip()
    if not token:
        raise Phase5Error("ORIGINS_LOCAL_TOKEN is required")
    return token


class Phase5Service:
    def __init__(
        self,
        *,
        oracle: OracleBrowserMount,
        lumi: LumiMount,
        oracle_remote: OracleRemoteNodeMount | None = None,
    ):
        self.oracle = oracle
        self.lumi = lumi
        self.oracle_remote = oracle_remote

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": True,
            "service": "origins-phase5",
            "api_version": "v1",
            "oracle_remote": {"configured": self.oracle_remote is not None},
        }
        for name, operation in (("oracle", self.oracle.snapshot), ("lumi", self.lumi.snapshot)):
            try:
                value = operation()
                result[name] = {"available": bool(value.get("available"))}
            except Phase5Error:
                result[name] = {"available": False}
        return result

    def remote_node(self) -> dict[str, Any]:
        if self.oracle_remote is None:
            return {
                "owner": "oracle",
                "available": False,
                "reason": "ORACLE_REMOTE_NODE_NOT_CONFIGURED",
                "remote_application_attachment": {
                    "available": False,
                    "reason": "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE",
                },
            }
        return self.oracle_remote.snapshot()

    def retrieve_remote_file(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.oracle_remote is None:
            raise OracleLiveError("Oracle remote Node is not configured")
        forbidden = {
            "node_id",
            "nodeId",
            "destination",
            "destination_path",
            "local_path",
            "token",
            "headers",
            "authorization",
            "upload",
            "overwrite",
        }
        if forbidden.intersection(body):
            raise OracleLiveError("caller cannot override Oracle Node, destination, credentials, or write authority")
        remote_path = str(body.get("remote_path") or body.get("path") or "")
        return self.oracle_remote.retrieve_file(remote_path, approved=bool(body.get("approved")))


class Phase5Handler(BaseHTTPRequestHandler):
    server_version = "OriginsPhase5/1"

    @property
    def phase5(self) -> Phase5Service:
        return self.server.phase5  # type: ignore[attr-defined]

    @property
    def local_token(self) -> str:
        return self.server.local_token  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/health":
            return self._send(200, self.phase5.health())
        if not self._authorized():
            return self._send(401, {"error": "UNAUTHORIZED"})
        try:
            if parsed.path == "/v1/browser":
                return self._send(200, self.phase5.oracle.snapshot())
            if parsed.path == "/v1/lumi":
                return self._send(200, self.phase5.lumi.snapshot())
            if parsed.path == "/v1/oracle/node":
                return self._send(200, self.phase5.remote_node())
            if parsed.path.startswith("/v1/lumi/tasks/"):
                task_id = parsed.path.removeprefix("/v1/lumi/tasks/")
                return self._send(200, self.phase5.lumi.task(task_id))
            return self._send(404, {"error": "NOT_FOUND"})
        except (Phase5Error, OracleLiveError) as exc:
            return self._send(409, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized():
            return self._send(401, {"error": "UNAUTHORIZED"})
        try:
            body = self._json_body()
            if parsed.path == "/v1/browser/handoff":
                authority = str(body.get("authority") or "")
                approved = bool(body.get("approved"))
                return self._send(200, self.phase5.oracle.set_authority(authority, approved=approved))
            if parsed.path == "/v1/browser/human-takeover":
                return self._send(200, self.phase5.oracle.human_takeover())
            if parsed.path == "/v1/browser/command":
                command = body.get("command")
                if not isinstance(command, dict):
                    raise Phase5Error("command object is required")
                return self._send(
                    200,
                    self.phase5.oracle.command(command, approved=bool(body.get("approved"))),
                )
            if parsed.path == "/v1/lumi/downloads":
                forbidden = {"target_dir", "temp_dir", "request_envelope", "cookies", "headers"}
                if forbidden.intersection(body):
                    raise Phase5Error("Origins does not accept Lumi destination or request-secret overrides")
                task = self.phase5.lumi.queue_download(
                    str(body.get("url") or ""),
                    filename=str(body.get("filename") or ""),
                    queue_id=str(body.get("queue_id") or "default"),
                    priority=int(body.get("priority") or 0),
                    start_paused=bool(body.get("start_paused")),
                )
                return self._send(201, task)
            if parsed.path.startswith("/v1/lumi/artifact-candidates/"):
                task_id = parsed.path.removeprefix("/v1/lumi/artifact-candidates/")
                return self._send(200, self.phase5.lumi.artifact_candidate(task_id))
            if parsed.path == "/v1/oracle/files/retrieve":
                return self._send(201, self.phase5.retrieve_remote_file(body))
            return self._send(404, {"error": "NOT_FOUND"})
        except (Phase5Error, OracleLiveError, TypeError, ValueError) as exc:
            return self._send(400, {"error": str(exc)})

    def _authorized(self) -> bool:
        header = str(self.headers.get("Authorization") or "")
        expected = f"Bearer {self.local_token}"
        return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))

    def _json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise Phase5Error("invalid content length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise Phase5Error("request body exceeds Phase 5 limit")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise Phase5Error("request body must be a JSON object")
        return value

    def _send(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def serve(*, host: str = DEFAULT_BIND, port: int = DEFAULT_PORT) -> None:
    host = _require_loopback(host)
    token = _local_token()
    phase5 = Phase5Service(
        oracle=OracleBrowserMount.from_env(),
        lumi=LumiMount.from_env(),
        oracle_remote=OracleRemoteNodeMount.from_env(),
    )
    server = ThreadingHTTPServer((host, int(port)), Phase5Handler)
    server.phase5 = phase5  # type: ignore[attr-defined]
    server.local_token = token  # type: ignore[attr-defined]
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Origins Phase 5 Oracle/Lumi owner mount")
    parser.add_argument("--host", default=os.environ.get("ORIGINS_PHASE5_BIND", DEFAULT_BIND))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ORIGINS_PHASE5_PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
