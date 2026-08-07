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
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

TOKEN = "origins-active-control-proof-token"
TERMINAL_STATES = {"completed", "failed", "interrupted", "timed_out"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-active-control-") as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "state"
        workspace_root = root / "repo"
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
            wait_for_health(base_url, first)
            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Active control proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]
            assert_http_status(f"{base_url}/v1/events", 401)

            initial_page = events(base_url, after_sequence=0)
            assert [event["sequence"] for event in initial_page["events"]] == [1]
            assert initial_page["events"][0]["kind"] == "workspace.created"
            cursor_before_process = initial_page["next_sequence"]

            slow_command = command_envelope(
                workspace_id,
                workspace_root,
                args=["-c", "import time; time.sleep(2); print('ASYNC_DONE')"],
            )
            started = time.monotonic()
            accepted = submit_command(base_url, slow_command)
            elapsed = time.monotonic() - started
            assert elapsed < 1.0, f"command acceptance blocked for {elapsed:.3f}s"
            slow_session_id = accepted["session"]["session_id"]
            assert accepted["replayed"] is False
            assert accepted["session"]["state"] == "starting"

            immediate = request_json(
                f"{base_url}/v1/sessions/{slow_session_id}", token=TOKEN
            )
            assert immediate["session_id"] == slow_session_id
            assert immediate["state"] in {"starting", "running"}

            replay = submit_command(base_url, slow_command)
            assert replay["replayed"] is True
            assert replay["session"]["session_id"] == slow_session_id

            running_events = wait_for_event_kind(
                base_url,
                cursor_before_process,
                "process.session.running",
            )
            assert running_events["next_sequence"] > cursor_before_process

            slow_terminal = wait_for_session(base_url, slow_session_id, timeout=8)
            assert slow_terminal["state"] == "completed"
            slow_output = request_json(
                f"{base_url}/v1/sessions/{slow_session_id}/output", token=TOKEN
            )
            assert "ASYNC_DONE" in slow_output["stdout"]

            cursor_before_cancel = events(base_url, after_sequence=0)["next_sequence"]
            cancel_command = command_envelope(
                workspace_id,
                workspace_root,
                args=["-c", "import time; time.sleep(10); print('SHOULD_NOT_COMPLETE')"],
                timeout_seconds=20,
            )
            cancel_accept = submit_command(base_url, cancel_command)
            cancel_session_id = cancel_accept["session"]["session_id"]
            wait_for_state(base_url, cancel_session_id, {"running"}, timeout=5)

            cancel_response = request_json(
                f"{base_url}/v1/sessions/{cancel_session_id}/cancel",
                token=TOKEN,
                method="POST",
                payload={},
                expected_status=202,
            )
            assert cancel_response["accepted"] is True
            assert cancel_response["session_id"] == cancel_session_id

            cancelled = wait_for_session(base_url, cancel_session_id, timeout=5)
            assert cancelled["state"] == "interrupted"
            assert cancelled["exit_code"] is None
            assert cancelled["timed_out"] is False
            assert_http_status(
                f"{base_url}/v1/sessions/{cancel_session_id}/cancel",
                409,
                token=TOKEN,
                method="POST",
                payload={},
            )

            cancel_events = events(base_url, after_sequence=cursor_before_cancel)
            kinds = [event["kind"] for event in cancel_events["events"]]
            assert "process.session.cancel_requested" in kinds
            assert "process.session.interrupted" in kinds
            assert kinds.index("process.session.cancel_requested") < kinds.index(
                "process.session.interrupted"
            )
            reconnect_cursor = cursor_before_cancel
            expected_replay = cancel_events["events"]

            first_page = events(base_url, after_sequence=0, limit=1)
            second_page = events(base_url, after_sequence=first_page["next_sequence"], limit=1)
            assert len(first_page["events"]) == 1
            assert len(second_page["events"]) == 1
            assert second_page["events"][0]["sequence"] == first_page["next_sequence"] + 1
        finally:
            first_stdout, first_stderr = stop(first)

        second = start(args.binary, env)
        try:
            wait_for_health(base_url, second)
            replay_after_restart = events(base_url, after_sequence=reconnect_cursor)
            assert replay_after_restart["events"] == expected_replay
            assert replay_after_restart["next_sequence"] >= reconnect_cursor
        finally:
            second_stdout, second_stderr = stop(second)

        combined = "\n".join((first_stdout, first_stderr, second_stdout, second_stderr))
        assert TOKEN not in combined

    print("PASS: async acceptance, active replay, cancellation and reconnectable event cursor")
    return 0


def command_envelope(
    workspace_id: str,
    workspace_root: Path,
    *,
    args: list[str],
    timeout_seconds: int = 15,
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
            "executable": "python3",
            "args": args,
            "cwd": ".",
            "timeout_seconds": timeout_seconds,
            "max_output_bytes": 1024 * 1024,
        },
        "created_at": now(),
    }


def submit_command(base_url: str, command: dict) -> dict:
    return request_json(
        f"{base_url}/v1/commands",
        token=TOKEN,
        method="POST",
        payload=command,
        expected_status=202,
    )


def events(base_url: str, *, after_sequence: int, limit: int = 100) -> dict:
    query = urllib.parse.urlencode(
        {"after_sequence": after_sequence, "limit": limit}
    )
    return request_json(f"{base_url}/v1/events?{query}", token=TOKEN)


def wait_for_event_kind(base_url: str, after_sequence: int, kind: str) -> dict:
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = events(base_url, after_sequence=after_sequence)
        if any(event["kind"] == kind for event in last["events"]):
            return last
        time.sleep(0.05)
    raise AssertionError(f"event {kind} did not appear: {last}")


def wait_for_state(
    base_url: str, session_id: str, states: set[str], *, timeout: int
) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = request_json(f"{base_url}/v1/sessions/{session_id}", token=TOKEN)
        if last["state"] in states:
            return last
        if last["state"] in TERMINAL_STATES:
            raise AssertionError(f"session terminated before target state {states}: {last}")
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} did not reach {states}: {last}")


def wait_for_session(base_url: str, session_id: str, *, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = request_json(f"{base_url}/v1/sessions/{session_id}", token=TOKEN)
        if last["state"] in TERMINAL_STATES:
            return last
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} did not become terminal: {last}")


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
