from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest

from origins_integration.oracle_live import OracleLiveError
from origins_integration.phase5_runtime import (
    LumiMount,
    OracleBrowserMount,
    Phase5Error,
    _loopback_url,
)
from origins_integration.phase5_server import Phase5Handler, Phase5Service, _require_loopback


class OwnerHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []
    responses: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw.decode("utf-8")) if raw else None
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        path = self.path.split("?", 1)[0]
        status, value = self.__class__.responses.get(
            (self.command, path),
            (404, {"error": "NOT_FOUND"}),
        )
        encoded = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _handle
    do_POST = _handle


@contextmanager
def owner_server(
    responses: dict[tuple[str, str], tuple[int, dict[str, Any]]],
) -> Iterator[tuple[str, type[OwnerHandler]]]:
    class Handler(OwnerHandler):
        pass

    Handler.requests = []
    Handler.responses = responses
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_owner_origins_fail_closed_to_loopback_only() -> None:
    assert _loopback_url("http://127.0.0.1:7000", default="") == "http://127.0.0.1:7000"
    assert _require_loopback("127.0.0.1") == "127.0.0.1"
    with pytest.raises(Phase5Error, match="loopback-local"):
        _loopback_url("https://example.com", default="")
    with pytest.raises(Phase5Error, match="embed credentials"):
        _loopback_url("http://user:secret@127.0.0.1:7000", default="")
    with pytest.raises(Phase5Error, match="origin"):
        _loopback_url("http://127.0.0.1:7000/api", default="")
    with pytest.raises(Phase5Error, match="non-loopback"):
        _require_loopback("0.0.0.0")


def test_oracle_authority_uses_real_observe_assist_act_contract() -> None:
    mount = OracleBrowserMount("http://127.0.0.1:8765")
    with pytest.raises(Phase5Error, match="unsupported"):
        mount.set_authority("control", approved=True)
    with pytest.raises(Phase5Error, match="explicit approved"):
        mount.set_authority("act", approved=False)


def test_oracle_pairing_token_is_bearer_and_disconnected_bridge_is_not_ready() -> None:
    responses = {
        ("GET", "/health"): (200, {"ok": True, "browserConnected": False}),
        ("GET", "/capabilities"): (200, {"browserConnected": False}),
        ("GET", "/latest"): (404, {"error": "NO_OBSERVATION"}),
        ("POST", "/command"): (200, {"ok": True}),
    }
    with owner_server(responses) as (base_url, handler):
        mount = OracleBrowserMount(base_url, pairing_token="pairing-secret")
        snapshot = mount.snapshot()
        assert snapshot["service_available"] is True
        assert snapshot["browser_connected"] is False
        assert snapshot["available"] is False
        mount.set_authority("act", approved=True)
        command = handler.requests[-1]
        assert command["authorization"] == "Bearer pairing-secret"
        assert command["body"] == {
            "command": {"type": "setAuthority", "authority": "act"},
            "approved": True,
        }


def test_human_takeover_cannot_be_smuggled_through_generic_command() -> None:
    mount = OracleBrowserMount("http://127.0.0.1:8765")
    with pytest.raises(Phase5Error, match="dedicated"):
        mount.command({"type": "humanTakeover"}, approved=True)
    with pytest.raises(Phase5Error, match="dedicated"):
        mount.command({"type": "setAuthority", "authority": "act"}, approved=True)


def test_lumi_handoff_leaves_destination_and_secret_state_with_lumi() -> None:
    responses = {
        ("POST", "/api/downloads/start"): (200, {"id": "task-1", "status": "queued"}),
    }
    with owner_server(responses) as (base_url, handler):
        task = LumiMount(base_url).queue_download(
            "https://example.test/file.bin",
            filename="file.bin",
            queue_id="downloads",
            priority=4,
            start_paused=True,
        )
        assert task["id"] == "task-1"
        payload = handler.requests[-1]["body"]
        assert payload == {
            "url": "https://example.test/file.bin",
            "filename": "file.bin",
            "queue_id": "downloads",
            "priority": 4,
            "start_paused": True,
        }
        assert "target_dir" not in payload
        assert "temp_dir" not in payload
        assert "request_envelope" not in payload
        assert "headers" not in payload
        assert "cookies" not in payload

    with pytest.raises(Phase5Error, match="credentials"):
        LumiMount("http://127.0.0.1:7000").queue_download(
            "https://user:secret@example.test/file.bin"
        )


def test_lumi_artifact_candidate_requires_completed_owner_task() -> None:
    responses = {
        ("GET", "/api/downloads/task-running"): (
            200,
            {"id": "task-running", "status": "running", "path": "/tmp/file.bin"},
        ),
        ("GET", "/api/downloads/task-done"): (
            200,
            {
                "id": "task-done",
                "status": "completed",
                "path": "/tmp/file.bin",
                "filename": "file.bin",
                "total_bytes": 9,
                "content_type": "application/octet-stream",
            },
        ),
    }
    with owner_server(responses) as (base_url, _handler):
        mount = LumiMount(base_url)
        with pytest.raises(Phase5Error, match="completed"):
            mount.artifact_candidate("task-running")
        candidate = mount.artifact_candidate("task-done")
        assert candidate["owner"] == "lumi"
        assert candidate["owner_task_id"] == "task-done"
        assert candidate["path"] == "/tmp/file.bin"
        assert candidate["total_bytes"] == 9


class FakeOracle:
    def snapshot(self) -> dict[str, Any]:
        return {"available": False}

    def set_authority(self, authority: str, *, approved: bool = False) -> dict[str, Any]:
        return {"ok": True, "authority": authority, "approved": approved}

    def human_takeover(self) -> dict[str, Any]:
        return {"ok": True, "authority": "observe"}

    def command(self, command: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
        return {"ok": True, "command": command, "approved": approved}


class FakeLumi:
    def snapshot(self) -> dict[str, Any]:
        return {"available": True}

    def task(self, task_id: str) -> dict[str, Any]:
        return {"id": task_id, "status": "queued"}

    def queue_download(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": "queued"}

    def artifact_candidate(self, task_id: str) -> dict[str, Any]:
        return {"owner": "lumi", "owner_task_id": task_id, "path": "/tmp/file.bin"}


class FakeRemoteOracle:
    def snapshot(self) -> dict[str, Any]:
        return {
            "owner": "oracle",
            "available": True,
            "node_id": "node-fixed",
            "file_retrieval": True,
            "remote_application_attachment": {
                "available": False,
                "reason": "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE",
            },
        }

    def retrieve_file(self, remote_path: str, *, approved: bool) -> dict[str, Any]:
        if not approved:
            raise OracleLiveError("remote file retrieval requires explicit approval")
        return {
            "schema_version": "origins.oracle-remote-file-receipt.v1",
            "owner": "oracle",
            "node_id": "node-fixed",
            "remote_path": remote_path,
            "sha256": "a" * 64,
            "bytes_transferred": 4,
            "artifact_candidate": {"owner": "oracle", "path": "/safe/transfer/file.bin"},
        }


@contextmanager
def phase5_server(*, remote: bool = False) -> Iterator[str]:
    service = Phase5Service(
        oracle=FakeOracle(),  # type: ignore[arg-type]
        lumi=FakeLumi(),  # type: ignore[arg-type]
        oracle_remote=FakeRemoteOracle() if remote else None,  # type: ignore[arg-type]
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Phase5Handler)
    server.phase5 = service  # type: ignore[attr-defined]
    server.local_token = "local-secret"  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def read_json(url: str, *, token: str = "") -> tuple[int, dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def post_json(url: str, value: dict[str, Any], *, token: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(value).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def test_phase5_public_health_is_sanitized_and_state_routes_require_bearer() -> None:
    with phase5_server() as base_url:
        status, health = read_json(f"{base_url}/v1/health")
        assert status == 200
        assert health == {
            "api_version": "v1",
            "lumi": {"available": True},
            "ok": True,
            "oracle": {"available": False},
            "oracle_remote": {"configured": False},
            "service": "origins-phase5",
        }
        status, body = read_json(f"{base_url}/v1/lumi")
        assert status == 401
        assert body == {"error": "UNAUTHORIZED"}
        status, body = read_json(f"{base_url}/v1/lumi", token="local-secret")
        assert status == 200
        assert body["available"] is True


def test_phase5_service_rejects_lumi_destination_and_secret_overrides() -> None:
    with phase5_server() as base_url:
        for forbidden in ("target_dir", "temp_dir", "request_envelope", "cookies", "headers"):
            status, body = post_json(
                f"{base_url}/v1/lumi/downloads",
                {"url": "https://example.test/file.bin", forbidden: "forbidden"},
                token="local-secret",
            )
            assert status == 400
            assert "does not accept" in body["error"]


def test_remote_node_route_is_protected_and_application_attachment_is_truthful() -> None:
    with phase5_server(remote=True) as base_url:
        status, body = read_json(f"{base_url}/v1/oracle/node")
        assert status == 401
        assert body == {"error": "UNAUTHORIZED"}

        status, node = read_json(f"{base_url}/v1/oracle/node", token="local-secret")
        assert status == 200
        assert node["node_id"] == "node-fixed"
        assert node["remote_application_attachment"] == {
            "available": False,
            "reason": "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE",
        }


def test_remote_file_route_requires_approval_and_blocks_authority_overrides() -> None:
    with phase5_server(remote=True) as base_url:
        status, body = post_json(
            f"{base_url}/v1/oracle/files/retrieve",
            {"remote_path": "/home/node/file.bin", "approved": False},
            token="local-secret",
        )
        assert status == 400
        assert "explicit approval" in body["error"]

        for forbidden in ("node_id", "destination", "local_path", "token", "headers", "upload", "overwrite"):
            status, body = post_json(
                f"{base_url}/v1/oracle/files/retrieve",
                {
                    "remote_path": "/home/node/file.bin",
                    "approved": True,
                    forbidden: "override",
                },
                token="local-secret",
            )
            assert status == 400
            assert "cannot override" in body["error"]

        status, receipt = post_json(
            f"{base_url}/v1/oracle/files/retrieve",
            {"remote_path": "/home/node/file.bin", "approved": True},
            token="local-secret",
        )
        assert status == 201
        assert receipt["node_id"] == "node-fixed"
        assert receipt["remote_path"] == "/home/node/file.bin"
        assert "secret" not in json.dumps(receipt).lower()
