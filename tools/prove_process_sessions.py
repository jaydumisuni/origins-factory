from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

TOKEN = "origins-process-proof-token"
SECRET_ARG = "SECRET_PROCESS_ARG_91"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-process-proof-") as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "state"
        workspace_root = root / "repo"
        outside_root = root / "outside"
        workspace_root.mkdir()
        outside_root.mkdir()
        (workspace_root / "nested").mkdir()
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

        daemon = start(args.binary, env)
        try:
            health = wait_for_health(base_url, daemon)
            assert health["database_schema_version"] == 2
            assert health["sessions"] == 0
            assert health["capabilities"] == 3

            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Process proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]

            assert_http_status(f"{base_url}/v1/sessions", 401)
            unauthorized = command_envelope(
                workspace_id,
                workspace_root,
                executable="python3",
                args=["-c", "print('unauthorized')"],
            )
            assert_http_status(
                f"{base_url}/v1/commands", 401, method="POST", payload=unauthorized
            )

            success_command = command_envelope(
                workspace_id,
                workspace_root,
                executable="python3",
                args=[
                    "-c",
                    (
                        "import os,sys; "
                        "print('VISIBLE_OUT'); "
                        "print('TOKEN_PRESENT' if 'ORIGINS_LOCAL_TOKEN' in os.environ else 'TOKEN_ABSENT'); "
                        "print('VISIBLE_ERR', file=sys.stderr)"
                    ),
                    SECRET_ARG,
                ],
                cwd="nested",
            )
            success = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=success_command,
            )
            assert success["replayed"] is False
            assert success["session"]["state"] == "completed"
            assert success["session"]["exit_code"] == 0
            assert "VISIBLE_OUT" in success["output"]["stdout"]
            assert "TOKEN_ABSENT" in success["output"]["stdout"]
            assert "TOKEN_PRESENT" not in success["output"]["stdout"]
            assert "VISIBLE_ERR" in success["output"]["stderr"]
            success_session_id = success["session"]["session_id"]
            stdout_bytes = bytes.fromhex(success["output"]["stdout_hex"])
            stderr_bytes = bytes.fromhex(success["output"]["stderr_hex"])
            assert hashlib.sha256(stdout_bytes).hexdigest() == success["session"]["stdout_sha256"]
            assert hashlib.sha256(stderr_bytes).hexdigest() == success["session"]["stderr_sha256"]
            assert len(stdout_bytes) == success["session"]["stdout_bytes"]
            assert len(stderr_bytes) == success["session"]["stderr_bytes"]

            replay = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=success_command,
            )
            assert replay["replayed"] is True
            assert replay["session"]["session_id"] == success_session_id

            conflicting_replay = copy.deepcopy(success_command)
            conflicting_replay["payload"]["args"] = ["-c", "print('different command')"]
            assert_http_status(
                f"{base_url}/v1/commands",
                409,
                token=TOKEN,
                method="POST",
                payload=conflicting_replay,
            )

            failed = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=command_envelope(
                    workspace_id,
                    workspace_root,
                    executable="python3",
                    args=["-c", "import sys; sys.exit(7)"],
                ),
            )
            assert failed["session"]["state"] == "failed"
            assert failed["session"]["exit_code"] == 7

            interrupted = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=command_envelope(
                    workspace_id,
                    workspace_root,
                    executable="hunter-codeops-switcher",
                    args=[],
                ),
            )
            assert interrupted["session"]["state"] == "interrupted"
            assert interrupted["session"]["exit_code"] is None
            assert interrupted["session"]["timed_out"] is False

            timed_out = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=command_envelope(
                    workspace_id,
                    workspace_root,
                    executable="python3",
                    args=["-c", "import time; time.sleep(2)"],
                    timeout_seconds=1,
                ),
                timeout=8,
            )
            assert timed_out["session"]["state"] == "timed_out"
            assert timed_out["session"]["timed_out"] is True
            assert timed_out["session"]["exit_code"] is None

            truncated = request_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=command_envelope(
                    workspace_id,
                    workspace_root,
                    executable="python3",
                    args=["-c", "print('X' * 1024)"],
                    max_output_bytes=64,
                ),
            )
            assert truncated["session"]["state"] == "completed"
            assert truncated["output"]["output_truncated"] is True
            assert truncated["output"]["stdout_bytes"] > 64
            assert truncated["output"]["stdout_retained_bytes"] == 64
            assert len(bytes.fromhex(truncated["output"]["stdout_hex"])) == 64

            shell_command = command_envelope(
                workspace_id,
                workspace_root,
                executable="bash",
                args=["-c", "echo forbidden"],
            )
            assert_http_status(
                f"{base_url}/v1/commands",
                400,
                token=TOKEN,
                method="POST",
                payload=shell_command,
            )

            escape_command = command_envelope(
                workspace_id,
                workspace_root,
                executable="python3",
                args=["-c", "print('escape')"],
                cwd="../outside",
            )
            assert_http_status(
                f"{base_url}/v1/commands",
                400,
                token=TOKEN,
                method="POST",
                payload=escape_command,
            )

            unregistered_root = command_envelope(
                workspace_id,
                outside_root,
                executable="python3",
                args=["-c", "print('outside root')"],
            )
            assert_http_status(
                f"{base_url}/v1/commands",
                400,
                token=TOKEN,
                method="POST",
                payload=unregistered_root,
            )

            sessions = request_json(f"{base_url}/v1/sessions", token=TOKEN)["sessions"]
            assert len(sessions) == 5
            output = request_json(
                f"{base_url}/v1/sessions/{success_session_id}/output", token=TOKEN
            )
            assert "VISIBLE_OUT" in output["stdout"]
            assert output["stdout_hex"] == success["output"]["stdout_hex"]

            updated_workspace = request_json(
                f"{base_url}/v1/workspaces/{workspace_id}", token=TOKEN
            )
            assert updated_workspace["revision"] == 6
            assert len(updated_workspace["session_refs"]) == 5

            health = request_json(f"{base_url}/v1/health")
            assert health["database_schema_version"] == 2
            assert health["sessions"] == 5
            assert health["journal"]["entries"] == 15
        finally:
            first_stdout, first_stderr = stop(daemon)

        combined = f"{first_stdout}\n{first_stderr}"
        assert TOKEN not in combined
        assert SECRET_ARG not in combined

        database = data_dir / "origins.sqlite3"
        with sqlite3.connect(database) as connection:
            journal_text = "\n".join(
                row[0] for row in connection.execute("SELECT event_json FROM journal_entries")
            )
            assert SECRET_ARG not in journal_text
            assert "VISIBLE_OUT" not in journal_text
            assert "VISIBLE_ERR" not in journal_text
            assert "args_sha256" in journal_text
            assert "command_sha256" in journal_text
            assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 5
            connection.execute(
                "UPDATE session_outputs SET stdout = ?1 WHERE session_id = ?2",
                (b"TAMPERED", success_session_id),
            )
            connection.commit()

        second = start(args.binary, env)
        try:
            wait_for_health(base_url, second)
            assert_http_status(
                f"{base_url}/v1/sessions/{success_session_id}/output",
                503,
                token=TOKEN,
            )
        finally:
            second_stdout, second_stderr = stop(second)

        combined = f"{combined}\n{second_stdout}\n{second_stderr}"
        assert TOKEN not in combined
        assert SECRET_ARG not in combined

    print(
        "PASS: supervised process sessions, replay binding, environment hygiene, "
        "root policy, output integrity and journal hygiene"
    )
    return 0


def command_envelope(
    workspace_id: str,
    workspace_root: Path,
    *,
    executable: str,
    args: list[str],
    cwd: str = ".",
    timeout_seconds: int = 15,
    max_output_bytes: int = 1024 * 1024,
) -> dict:
    return {
        "contract_type": "command_envelope",
        "schema_version": "1.0.0",
        "command_id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "capability_id": "origins.process.run",
        "effect": "execute",
        "payload": {
            "workspace_root": str(workspace_root),
            "executable": executable,
            "args": args,
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
            "max_output_bytes": max_output_bytes,
        },
        "created_at": now(),
    }


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        except Exception as error:  # noqa: BLE001 - startup retry boundary
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
    timeout: int = 5,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        assert response.status == expected_status
        return json.loads(response.read().decode("utf-8"))


def assert_http_status(
    url: str,
    expected_status: int,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> None:
    try:
        request_json(url, token=token, method=method, payload=payload)
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
