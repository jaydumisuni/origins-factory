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
EXPECTED_CAPABILITY_IDS = {
    "origins.hunter.transport",
    "origins.journal.verify",
    "origins.process.run",
    "origins.repository.diff",
    "origins.repository.inspect",
    "origins.workspace.persistence",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    prove_non_loopback_refusal(args.binary)

    with tempfile.TemporaryDirectory(prefix="originsd-proof-") as temp_dir:
        data_dir = Path(temp_dir)
        workspace_root = data_dir / "workspaces"
        workspace_root.mkdir()
        port = reserve_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_LOCAL_TOKEN": TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
            }
        )

        first = start(args.binary, env)
        try:
            health = wait_for_health(base_url, first)
            assert health["ok"] is True
            assert health["database_schema_version"] == 2
            assert health["repository_schema_version"] == 1
            assert health["workspaces"] == 0
            assert health["repositories"] == 0
            assert health["sessions"] == 0
            assert health["capabilities"] == len(EXPECTED_CAPABILITY_IDS)
            assert health["journal"]["entries"] == 0

            assert_http_status(f"{base_url}/v1/capabilities", 401)
            assert_http_status(
                f"{base_url}/v1/workspaces",
                401,
                method="POST",
                payload={"name": "Unauthorized", "authority_refs": [], "session_refs": []},
            )
            capabilities = request_json(f"{base_url}/v1/capabilities", token=TOKEN)
            capability_ids = {
                descriptor["capability_id"] for descriptor in capabilities["capabilities"]
            }
            assert capability_ids == EXPECTED_CAPABILITY_IDS

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
            first_stdout, first_stderr = stop(first)

        second = start(args.binary, env)
        try:
            health = wait_for_health(base_url, second)
            assert health["workspaces"] == 1
            assert health["repositories"] == 0
            assert health["sessions"] == 0
            assert health["journal"]["entries"] == 1
            assert health["journal"]["head_hash"]
            recovered_after_restart = request_json(
                f"{base_url}/v1/workspaces/{workspace_id}", token=TOKEN
            )
            assert recovered_after_restart == workspace
        finally:
            second_stdout, second_stderr = stop(second)

        combined = "\n".join((first_stdout, first_stderr, second_stdout, second_stderr))
        if TOKEN in combined:
            raise AssertionError("local token leaked into daemon output")

        database = data_dir / "origins.sqlite3"
        if not database.exists() or database.stat().st_size == 0:
            raise AssertionError("durable SQLite database was not created")

    print("PASS: originsd bind, auth, persistence, journal, repository schema and restart recovery")
    return 0


def prove_non_loopback_refusal(binary: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="originsd-bind-proof-") as temp_dir:
        workspace_root = Path(temp_dir) / "workspaces"
        workspace_root.mkdir()
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": "0.0.0.0:48700",
                "ORIGINS_DATA_DIR": temp_dir,
                "ORIGINS_LOCAL_TOKEN": TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
            }
        )
        completed = subprocess.run(
            [str(binary)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if completed.returncode == 0:
            raise AssertionError("originsd accepted a non-loopback bind")
        output = f"{completed.stdout}\n{completed.stderr}"
        if "refuses non-loopback bind addresses" not in output:
            raise AssertionError(f"non-loopback refusal was not explicit: {output[-1000:]}")
        if TOKEN in output:
            raise AssertionError("local token leaked during rejected startup")


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


def assert_http_status(
    url: str,
    expected_status: int,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> None:
    try:
        request_json(url, method=method, payload=payload)
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
