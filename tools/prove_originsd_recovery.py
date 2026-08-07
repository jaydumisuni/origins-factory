from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN = "origins-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="originsd-proof-") as temp_dir:
        data_dir = Path(temp_dir)
        port = reserve_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_LOCAL_TOKEN": TOKEN,
            }
        )

        first = start(args.binary, env)
        try:
            health = wait_for_health(base_url, first)
            assert health["ok"] is True
            assert health["database_schema_version"] == 1
            assert health["workspaces"] == 0
            assert health["capabilities"] == 2
            assert health["journal"]["entries"] == 0

            assert_http_status(f"{base_url}/v1/capabilities", 401)
            capabilities = request_json(f"{base_url}/v1/capabilities", token=TOKEN)
            assert len(capabilities["capabilities"]) == 2

            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Restart proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]
            recovered = request_json(f"{base_url}/v1/workspaces/{workspace_id}", token=TOKEN)
            assert recovered == workspace
        finally:
            stop(first)

        second = start(args.binary, env)
        try:
            health = wait_for_health(base_url, second)
            assert health["workspaces"] == 1
            assert health["journal"]["entries"] == 1
            assert health["journal"]["head_hash"]
            recovered_after_restart = request_json(
                f"{base_url}/v1/workspaces/{workspace_id}", token=TOKEN
            )
            assert recovered_after_restart == workspace
        finally:
            stdout, stderr = stop(second)

        combined = f"{stdout}\n{stderr}"
        if TOKEN in combined:
            raise AssertionError("local token leaked into daemon output")

        database = data_dir / "origins.sqlite3"
        if not database.exists() or database.stat().st_size == 0:
            raise AssertionError("durable SQLite database was not created")

    print("PASS: originsd auth, persistence, journal and restart recovery")
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
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"originsd exited before health check: {process.returncode}\nstdout={stdout}\nstderr={stderr}"
            )
        try:
            return request_json(f"{base_url}/v1/health")
        except Exception as error:  # noqa: BLE001 - proof retries transient startup errors
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
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def assert_http_status(url: str, expected_status: int) -> None:
    try:
        request_json(url)
    except urllib.error.HTTPError as error:
        if error.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {error.code}") from error
        return
    raise AssertionError(f"expected HTTP {expected_status}, request succeeded")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
