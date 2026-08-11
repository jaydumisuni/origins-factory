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
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ORIGINS_TOKEN = "origins-hunter-failure-proof-token"
HUNTER_TOKEN = "hunter-failure-token-must-not-persist"
INVALID_BODY_MARKER = b"HUNTER_INVALID_BODY_MUST_NOT_PERSIST"
OVERSIZE_MARKER = b"HUNTER_OVERSIZE_BODY_MUST_NOT_PERSIST"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class FixtureState:
    mode = "invalid_json"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path != "/api/system/version":
            self.send_response(404)
            self.end_headers()
            return

        authorization = self.headers.get("Authorization", "")
        if authorization:
            raise AssertionError("version operation must not send Hunter credential")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Deliberately omit Content-Length so the bounded body reader, not the
        # header preflight, must enforce the retained response limit.
        self.end_headers()
        if FixtureState.mode == "invalid_json":
            self.wfile.write(INVALID_BODY_MARKER + b" not-json")
            return
        if FixtureState.mode == "oversize":
            block = OVERSIZE_MARKER + b"X" * (64 * 1024)
            remaining = MAX_RESPONSE_BYTES + 4096
            while remaining > 0:
                chunk = block[: min(len(block), remaining)]
                self.wfile.write(chunk)
                self.wfile.flush()
                remaining -= len(chunk)
            return
        raise AssertionError(FixtureState.mode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-hunter-failure-proof-") as temp:
        root = Path(temp)
        data_dir = root / "state"
        workspace_root = root / "workspace"
        workspace_root.mkdir()

        hunter_port = reserve_port()
        server = ThreadingHTTPServer(("127.0.0.1", hunter_port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        origins_port = reserve_port()
        base_url = f"http://127.0.0.1:{origins_port}"
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{origins_port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_LOCAL_TOKEN": ORIGINS_TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
                "ORIGINS_HUNTER_URL": f"http://127.0.0.1:{hunter_port}",
                "ORIGINS_HUNTER_TOKEN": HUNTER_TOKEN,
            }
        )

        daemon = start(args.binary, env)
        try:
            health = wait_for_health(base_url, daemon)
            assert health["capabilities"] == 6
            capabilities = request_json(f"{base_url}/v1/capabilities", token=ORIGINS_TOKEN)
            capability_ids = {item["capability_id"] for item in capabilities["capabilities"]}
            assert "origins.hunter.transport" in capability_ids

            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=ORIGINS_TOKEN,
                method="POST",
                payload={"name": "Hunter failure evidence", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]

            FixtureState.mode = "invalid_json"
            assert_hunter_failure(base_url, workspace_id, "HUNTER_INVALID_RESPONSE")
            invalid_event = latest_hunter_failure(base_url)
            assert invalid_event["payload"]["failure_class"] == "invalid_json"
            assert invalid_event["payload"]["http_status"] == 200
            assert invalid_event["payload"]["response_bytes"] == len(INVALID_BODY_MARKER + b" not-json")
            assert len(invalid_event["payload"]["response_sha256"]) == 64

            FixtureState.mode = "oversize"
            assert_hunter_failure(base_url, workspace_id, "HUNTER_INVALID_RESPONSE")
            oversize_event = latest_hunter_failure(base_url)
            assert oversize_event["payload"]["failure_class"] == "response_too_large"
            assert oversize_event["payload"]["http_status"] == 200
            assert "response_bytes" not in oversize_event["payload"]
            assert "response_sha256" not in oversize_event["payload"]

            events = request_json(f"{base_url}/v1/events?after_sequence=0&limit=100", token=ORIGINS_TOKEN)
            event_text = json.dumps(events, sort_keys=True)
            assert HUNTER_TOKEN not in event_text
            assert INVALID_BODY_MARKER.decode() not in event_text
            assert OVERSIZE_MARKER.decode() not in event_text
        finally:
            daemon_stdout, daemon_stderr = stop(daemon)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        combined = f"{daemon_stdout}\n{daemon_stderr}"
        assert HUNTER_TOKEN not in combined
        assert INVALID_BODY_MARKER.decode() not in combined
        assert OVERSIZE_MARKER.decode() not in combined
        assert_no_persisted_marker(data_dir, HUNTER_TOKEN.encode())
        assert_no_persisted_marker(data_dir, INVALID_BODY_MARKER)
        assert_no_persisted_marker(data_dir, OVERSIZE_MARKER)

    print(
        "PASS: Hunter invalid/oversized responses fail closed, retain metadata-only evidence, "
        "and persist no Hunter credential or response body"
    )
    return 0


def assert_hunter_failure(base_url: str, workspace_id: str, error_code: str) -> None:
    try:
        request_json(
            f"{base_url}/v1/hunter/request",
            token=ORIGINS_TOKEN,
            method="POST",
            payload={"workspace_id": workspace_id, "operation": "version", "payload": {}},
        )
    except urllib.error.HTTPError as error:
        assert error.code == 502
        body = json.loads(error.read().decode("utf-8"))
        assert body["error_code"] == error_code
        return
    raise AssertionError("Hunter failure request unexpectedly succeeded")


def latest_hunter_failure(base_url: str) -> dict:
    page = request_json(f"{base_url}/v1/events?after_sequence=0&limit=100", token=ORIGINS_TOKEN)
    failures = [event for event in page["events"] if event.get("kind") == "hunter.transport.failed"]
    if not failures:
        raise AssertionError("Hunter transport failure was not journaled")
    return failures[-1]


def assert_no_persisted_marker(root: Path, marker: bytes) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if marker in data:
            raise AssertionError(f"sensitive Hunter marker persisted in Origins state: {path}")


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
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"originsd exited before health check: {process.returncode}\nstdout={stdout}\nstderr={stderr}"
            )
        try:
            return request_json(f"{base_url}/v1/health")
        except Exception as error:  # noqa: BLE001 - bounded startup retry
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
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
