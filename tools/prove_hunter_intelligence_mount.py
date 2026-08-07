from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from origins_integration.engineering import OriginsClient  # noqa: E402
from origins_integration.hunter import (  # noqa: E402
    HunterConversationConflict,
    HunterIntelligenceMount,
    HunterMountError,
    hunter_session_id,
)

ORIGINS_TOKEN = "origins-hunter-proof-local-token"
HUNTER_TOKEN = "hunter-proof-owner-token-do-not-leak"
USER_MARKER = "HUNTER_USER_BODY_MUST_NOT_ENTER_ORIGINS_JOURNAL"
ASSISTANT_MARKER = "HUNTER_ASSISTANT_BODY_MUST_NOT_ENTER_ORIGINS_JOURNAL"


class HunterFixtureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.identity = {
            "authenticated": True,
            "role": "owner_admin",
            "status": "approved",
            "userId": "owner-proof",
            "emailVerified": True,
        }
        self.sessions: dict[str, dict] = {}
        self.last_core_messages: list[dict] = []
        self.authenticated_paths: list[str] = []
        self.save_conflict = False


FIXTURE = HunterFixtureState()


class HunterFixtureHandler(BaseHTTPRequestHandler):
    server_version = "HunterFixture/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        expected = f"Bearer {HUNTER_TOKEN}"
        supplied = self.headers.get("authorization", "")
        if supplied != expected:
            self._json(401, {"ok": False, "error": "OWNER_AUTH_REQUIRED"})
            return False
        with FIXTURE.lock:
            FIXTURE.authenticated_paths.append(self.path)
        return True

    def do_GET(self) -> None:  # noqa: N802 - HTTP handler contract
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/system/version":
            if self.headers.get("authorization"):
                self._json(400, {"ok": False, "error": "VERSION_MUST_NOT_NEED_OWNER_TOKEN"})
                return
            self._json(
                200,
                {
                    "ok": True,
                    "service": "hunter-api-worker",
                    "environment": "production",
                    "deployment": {"gitCommit": "d" * 40, "buildId": "hunter-fixture"},
                },
            )
            return

        if not self._authorized():
            return

        if url.path == "/api/auth/v2/session":
            with FIXTURE.lock:
                identity = deepcopy(FIXTURE.identity)
            self._json(200, {"ok": True, "identity": identity})
            return
        if url.path == "/core/status":
            self._json(
                200,
                {
                    "ok": True,
                    "service": "hunter-core",
                    "context": "hunter_core_chat",
                    "identity": deepcopy(FIXTURE.identity),
                    "publicSafe": False,
                },
            )
            return
        if url.path == "/core/providers/status":
            self._json(
                200,
                {
                    "ok": True,
                    "providers": [
                        {"id": "cloudflare-workers-ai", "status": "ready", "model": "fixture"}
                    ],
                    "secretsExposed": False,
                },
            )
            return
        if url.path == "/chat/list":
            with FIXTURE.lock:
                sessions = [
                    {
                        "id": value["id"],
                        "title": value.get("title", ""),
                        "updatedAt": value.get("updatedAt", 0),
                    }
                    for value in FIXTURE.sessions.values()
                ]
            self._json(200, {"ok": True, "sessions": sessions})
            return
        if url.path == "/chat/load":
            query = urllib.parse.parse_qs(url.query)
            session_id = (query.get("id") or [""])[0]
            with FIXTURE.lock:
                session = deepcopy(FIXTURE.sessions.get(session_id))
            if session is None:
                self._json(404, {"ok": False, "error": "CHAT_NOT_FOUND"})
            else:
                self._json(200, {"ok": True, "session": session})
            return

        self._json(404, {"ok": False, "error": "ROUTE_NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802 - HTTP handler contract
        if not self._authorized():
            return
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "INVALID_JSON"})
            return

        if self.path == "/core/chat":
            messages = body.get("messages")
            if not isinstance(messages, list):
                self._json(400, {"ok": False, "error": "MESSAGES_REQUIRED"})
                return
            with FIXTURE.lock:
                FIXTURE.last_core_messages = deepcopy(messages)
            self._json(
                200,
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion",
                    "model": "hunter-cloudflare",
                    "provider": "cloudflare-workers-ai",
                    "context": "hunter_core_chat",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": ASSISTANT_MARKER},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
            return

        if self.path == "/chat/save":
            session = body.get("session")
            if not isinstance(session, dict) or not session.get("id"):
                self._json(400, {"ok": False, "error": "CHAT_SESSION_REQUIRED"})
                return
            session_id = str(session["id"])
            with FIXTURE.lock:
                if FIXTURE.save_conflict:
                    existing = deepcopy(FIXTURE.sessions.get(session_id) or session)
                    existing["updatedAt"] = max(
                        int(existing.get("updatedAt") or 0),
                        int(session.get("updatedAt") or 0) + 1000,
                    )
                    FIXTURE.sessions[session_id] = deepcopy(existing)
                    self._json(200, {"ok": True, "skipped": "server_newer", "session": existing})
                    return
                FIXTURE.sessions[session_id] = deepcopy(session)
                saved = deepcopy(session)
            self._json(200, {"ok": True, "session": saved})
            return

        self._json(404, {"ok": False, "error": "ROUTE_NOT_FOUND"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-hunter-mount-") as temp_dir:
        base = Path(temp_dir)
        data_dir = base / "state"
        workspace_root = base / "workspaces"
        workspace_root.mkdir(parents=True)

        hunter_server = ThreadingHTTPServer(("127.0.0.1", 0), HunterFixtureHandler)
        hunter_thread = threading.Thread(target=hunter_server.serve_forever, daemon=True)
        hunter_thread.start()
        hunter_port = int(hunter_server.server_address[1])

        origins_port = reserve_port()
        origins_url = f"http://127.0.0.1:{origins_port}"
        hunter_url = f"http://127.0.0.1:{hunter_port}"
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{origins_port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_LOCAL_TOKEN": ORIGINS_TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
                "ORIGINS_HUNTER_URL": hunter_url,
                "ORIGINS_HUNTER_TOKEN": HUNTER_TOKEN,
            }
        )

        daemon = start(args.binary, env)
        try:
            wait_for_health(origins_url, daemon)
            workspace = request_json(
                origins_url + "/v1/workspaces",
                token=ORIGINS_TOKEN,
                method="POST",
                payload={"name": "Hunter intelligence proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]
            assert request_json(origins_url + "/v1/health")["repositories"] == 0

            status = request_json(origins_url + "/v1/hunter/status", token=ORIGINS_TOKEN)
            assert status["configured"] is True
            assert status["token_exposed"] is False
            assert status["base_origin"] == hunter_url

            origins = OriginsClient(origins_url, ORIGINS_TOKEN)
            mount = HunterIntelligenceMount._for_fixture(origins)
            doctor = mount.doctor(workspace_id)
            assert doctor.compatible is True
            assert doctor.live_hunter_proven is False
            assert doctor.identity_authenticated is True
            assert doctor.identity_role == "owner_admin"
            assert doctor.identity_status == "approved"
            assert doctor.core_context == "hunter_core_chat"
            assert doctor.provider_count == 1
            assert doctor.proof_scope == "fixture"
            assert len(doctor.receipt_sha256) == 64

            session_id = hunter_session_id(workspace_id)
            previous = [
                {"role": "user" if index % 2 == 0 else "assistant", "content": f"history-{index}"}
                for index in range(20)
            ]
            with FIXTURE.lock:
                FIXTURE.sessions[session_id] = {
                    "id": session_id,
                    "title": "Existing Hunter conversation",
                    "messages": deepcopy(previous),
                    "createdAt": 1,
                    "updatedAt": 2,
                    "archived": False,
                    "pinned": False,
                }

            turn = mount.send_turn(workspace_id, USER_MARKER)
            assert turn.proof_scope == "fixture"
            assert turn.live_hunter_proven is False
            assert turn.saved is True
            assert turn.provider == "cloudflare-workers-ai"
            assert turn.model == "hunter-cloudflare"
            assert turn.context == "hunter_core_chat"
            assert turn.assistant_text == ASSISTANT_MARKER
            assert len(turn.receipt_sha256) == 64
            assert len(turn.response_sha256) == 64

            with FIXTURE.lock:
                core_messages = deepcopy(FIXTURE.last_core_messages)
                saved = deepcopy(FIXTURE.sessions[session_id])
                authenticated_paths = list(FIXTURE.authenticated_paths)
            assert len(core_messages) == 12
            assert core_messages[-1] == {"role": "user", "content": USER_MARKER}
            assert core_messages[0] == previous[9]
            assert len(saved["messages"]) == 22
            assert saved["messages"][-2] == {"role": "user", "content": USER_MARKER}
            assert saved["messages"][-1] == {"role": "assistant", "content": ASSISTANT_MARKER}
            assert authenticated_paths
            assert all(not path.startswith("/api/system/version") for path in authenticated_paths)

            rejected_status, rejected = request_json_status(
                origins_url + "/v1/hunter/request",
                token=ORIGINS_TOKEN,
                method="POST",
                payload={
                    "workspace_id": workspace_id,
                    "operation": "github_write",
                    "payload": {"path": "should-never-route"},
                },
            )
            assert rejected_status == 400
            assert rejected["error_code"] == "HUNTER_INVALID_REQUEST"

            events = request_json(
                origins_url + "/v1/events?after_sequence=0&limit=500",
                token=ORIGINS_TOKEN,
            )
            journal_text = json.dumps(events, sort_keys=True)
            assert HUNTER_TOKEN not in journal_text
            assert USER_MARKER not in journal_text
            assert ASSISTANT_MARKER not in journal_text
            assert "hunter.transport.completed" in journal_text
            assert "response_sha256" in journal_text

            with FIXTURE.lock:
                FIXTURE.identity = {
                    "authenticated": True,
                    "role": "tester",
                    "status": "approved",
                }
            try:
                mount.doctor(workspace_id)
            except HunterMountError as error:
                assert "owner_admin" in str(error)
            else:
                raise AssertionError("non-owner Hunter identity was accepted")
            finally:
                with FIXTURE.lock:
                    FIXTURE.identity = {
                        "authenticated": True,
                        "role": "owner_admin",
                        "status": "approved",
                    }

            with FIXTURE.lock:
                FIXTURE.save_conflict = True
            try:
                mount.send_turn(workspace_id, "conflict proof")
            except HunterConversationConflict:
                pass
            else:
                raise AssertionError("server_newer Hunter session did not block overwrite")
            finally:
                with FIXTURE.lock:
                    FIXTURE.save_conflict = False
        finally:
            daemon_stdout, daemon_stderr = stop(daemon)

        # Optionality theorem: Hunter may disappear while the mechanical Origins foundation remains healthy.
        disabled_port = reserve_port()
        disabled_url = f"http://127.0.0.1:{disabled_port}"
        disabled_env = os.environ.copy()
        disabled_env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{disabled_port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_LOCAL_TOKEN": ORIGINS_TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
            }
        )
        disabled_env.pop("ORIGINS_HUNTER_URL", None)
        disabled_env.pop("ORIGINS_HUNTER_TOKEN", None)
        disabled = start(args.binary, disabled_env)
        try:
            health = wait_for_health(disabled_url, disabled)
            assert health["ok"] is True
            status = request_json(disabled_url + "/v1/hunter/status", token=ORIGINS_TOKEN)
            assert status["configured"] is False
            blocked_status, blocked = request_json_status(
                disabled_url + "/v1/hunter/request",
                token=ORIGINS_TOKEN,
                method="POST",
                payload={"workspace_id": workspace_id, "operation": "session", "payload": {}},
            )
            assert blocked_status == 503
            assert blocked["error_code"] == "HUNTER_NOT_CONFIGURED"
        finally:
            disabled_stdout, disabled_stderr = stop(disabled)
            hunter_server.shutdown()
            hunter_server.server_close()
            hunter_thread.join(timeout=5)

        combined_output = "\n".join(
            (daemon_stdout, daemon_stderr, disabled_stdout, disabled_stderr)
        )
        assert HUNTER_TOKEN not in combined_output
        assert USER_MARKER not in combined_output
        assert ASSISTANT_MARKER not in combined_output

    print(
        "PASS: Hunter fixture owner auth, Workspace continuity, last-12 inference, save conflict, "
        "bounded Rust relay, journal sanitation, route allowlist, and optional Hunter failure were proven"
    )
    return 0


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start(binary: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def stop(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            return process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.communicate(timeout=10)


def wait_for_health(base_url: str, process: subprocess.Popen[str]) -> dict:
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"originsd exited before health: {process.returncode}\nstdout={stdout}\nstderr={stderr}"
            )
        try:
            return request_json(base_url + "/v1/health")
        except Exception as error:  # noqa: BLE001
            last_error = error
            time.sleep(0.2)
    raise AssertionError(f"originsd health did not become ready: {last_error}")


def request_json(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
    expected_status: int = 200,
) -> dict:
    status, data = request_json_status(
        url,
        token=token,
        method=method,
        payload=payload,
    )
    if status != expected_status:
        raise AssertionError(f"expected HTTP {expected_status}, got {status}: {data}")
    return data


def request_json_status(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return error.code, json.loads(raw or "{}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, HunterMountError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
