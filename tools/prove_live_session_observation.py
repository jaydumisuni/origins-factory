from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
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

TOKEN = "origins-live-observation-proof-token"
TERMINAL_STATES = {"completed", "failed", "interrupted", "timed_out"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-live-proof-") as temp_dir:
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

        daemon = start(args.binary, env)
        try:
            wait_for_health(base_url, daemon)
            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Live observation proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]
            initial_events = request_json(
                f"{base_url}/v1/events?after_sequence=0&limit=100", token=TOKEN
            )
            journal_cursor = initial_events["next_sequence"]

            assert_http_status(
                f"{base_url}/v1/events/live?after_sequence={journal_cursor}", 401
            )

            command = command_envelope(
                workspace_id,
                workspace_root,
                args=[
                    "-c",
                    (
                        "import sys,time; "
                        "print('FIRST', flush=True); "
                        "time.sleep(1.0); "
                        "print('SECOND', flush=True); "
                        "time.sleep(0.5); "
                        "print('ERRTAIL', file=sys.stderr, flush=True)"
                    ),
                ],
            )
            accepted = submit_command(base_url, command)
            session_id = accepted["session"]["session_id"]

            first_delta = wait_for_output_delta(base_url, session_id)
            assert "FIRST" in (first_delta["stdout"]["text"] or "")
            assert first_delta["state"] in {"starting", "running"}
            stdout_cursor = first_delta["stdout"]["next"]
            stderr_cursor = first_delta["stderr"]["next"]

            empty_repeat = output_delta(
                base_url,
                session_id,
                stdout_after=stdout_cursor,
                stderr_after=stderr_cursor,
            )
            assert empty_repeat["stdout"]["bytes"] == 0
            assert empty_repeat["stderr"]["bytes"] == 0

            journal_live = open_sse(
                f"{base_url}/v1/events/live?after_sequence={journal_cursor}", TOKEN
            )
            try:
                journal_frame = read_sse_event(journal_live, timeout_seconds=5)
                assert journal_frame["event"] == "journal"
                sequence = int(journal_frame["id"])
                assert sequence == journal_cursor + 1
                journal_event = json.loads(journal_frame["data"])
                assert journal_event["sequence"] == sequence
                assert journal_event["kind"] == "process.session.starting"
            finally:
                journal_live.close()

            journal_reconnect = open_sse(
                f"{base_url}/v1/events/live?after_sequence={sequence}", TOKEN
            )
            try:
                next_journal_frame = read_sse_event(journal_reconnect, timeout_seconds=5)
                assert next_journal_frame["event"] == "journal"
                assert int(next_journal_frame["id"]) > sequence
            finally:
                journal_reconnect.close()

            output_live = open_sse(
                output_live_url(base_url, session_id, stdout_cursor, stderr_cursor), TOKEN
            )
            try:
                second_frame = read_sse_event(output_live, timeout_seconds=5)
                assert second_frame["event"] == "output"
                second_delta = json.loads(second_frame["data"])
                assert "SECOND" in (second_delta["stdout"]["text"] or "")
                stdout_cursor, stderr_cursor = parse_output_cursor(second_frame["id"])
            finally:
                output_live.close()

            resumed = output_delta(
                base_url,
                session_id,
                stdout_after=stdout_cursor,
                stderr_after=stderr_cursor,
            )
            if resumed["stderr"]["bytes"] == 0:
                resumed = wait_for_output_delta(
                    base_url,
                    session_id,
                    stdout_after=stdout_cursor,
                    stderr_after=stderr_cursor,
                    require_stderr=True,
                )
            assert "ERRTAIL" in (resumed["stderr"]["text"] or "")
            stdout_cursor = resumed["stdout"]["next"]
            stderr_cursor = resumed["stderr"]["next"]

            terminal = wait_for_session(base_url, session_id, timeout=8)
            assert terminal["state"] == "completed"

            terminal_stream = open_sse(
                output_live_url(base_url, session_id, stdout_cursor, stderr_cursor), TOKEN
            )
            try:
                terminal_frame = read_sse_event(terminal_stream, timeout_seconds=5)
                assert terminal_frame["event"] == "terminal"
                terminal_data = json.loads(terminal_frame["data"])
                assert terminal_data["state"] == "completed"
            finally:
                terminal_stream.close()

            assert_http_status(
                output_live_url(base_url, session_id, 0, 0),
                401,
            )

            final_output = request_json(
                f"{base_url}/v1/sessions/{session_id}/output", token=TOKEN
            )
            assert final_output["stdout"] == "FIRST\nSECOND\n"
            assert final_output["stderr"] == "ERRTAIL\n"

            database = data_dir / "origins.sqlite3"
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT stdout, stderr FROM session_outputs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                assert row == (b"FIRST\nSECOND\n", b"ERRTAIL\n")
                raw_output_tables = [
                    item[0]
                    for item in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'session_output%'"
                    )
                ]
                assert raw_output_tables == ["session_outputs"]
                journal_text = "\n".join(
                    item[0]
                    for item in connection.execute("SELECT event_json FROM journal_entries")
                )
                assert "FIRST" not in journal_text
                assert "SECOND" not in journal_text
                assert "ERRTAIL" not in journal_text
        finally:
            stdout, stderr = stop(daemon)

        combined = f"{stdout}\n{stderr}"
        assert TOKEN not in combined

    print(
        "PASS: one-copy incremental output, byte-cursor reconnect, authenticated SSE, "
        "journal cursor reconnect and terminal drain"
    )
    return 0


def command_envelope(workspace_id: str, workspace_root: Path, *, args: list[str]) -> dict:
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
            "timeout_seconds": 10,
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


def output_delta(
    base_url: str,
    session_id: str,
    *,
    stdout_after: int,
    stderr_after: int,
) -> dict:
    query = urllib.parse.urlencode(
        {
            "stdout_after": stdout_after,
            "stderr_after": stderr_after,
            "limit": 65536,
        }
    )
    return request_json(
        f"{base_url}/v1/sessions/{session_id}/output/delta?{query}", token=TOKEN
    )


def output_live_url(
    base_url: str, session_id: str, stdout_after: int, stderr_after: int
) -> str:
    query = urllib.parse.urlencode(
        {"stdout_after": stdout_after, "stderr_after": stderr_after}
    )
    return f"{base_url}/v1/sessions/{session_id}/output/live?{query}"


def wait_for_output_delta(
    base_url: str,
    session_id: str,
    *,
    stdout_after: int = 0,
    stderr_after: int = 0,
    require_stderr: bool = False,
) -> dict:
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = output_delta(
            base_url,
            session_id,
            stdout_after=stdout_after,
            stderr_after=stderr_after,
        )
        has_data = last["stderr"]["bytes"] > 0 if require_stderr else (
            last["stdout"]["bytes"] > 0 or last["stderr"]["bytes"] > 0
        )
        if has_data:
            return last
        time.sleep(0.05)
    raise AssertionError(f"incremental output did not appear: {last}")


def open_sse(url: str, token: str):
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
    )
    return urllib.request.urlopen(request, timeout=10)


def read_sse_event(response, *, timeout_seconds: int) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    frame: dict[str, str] = {}
    while time.monotonic() < deadline:
        raw = response.readline()
        if not raw:
            raise AssertionError("SSE stream ended before expected frame")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if frame.get("data"):
                return frame
            frame = {}
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.lstrip()
        if field in {"event", "id", "data"}:
            if field == "data" and field in frame:
                frame[field] += "\n" + value
            else:
                frame[field] = value
    raise AssertionError(f"SSE frame timeout: {frame}")


def parse_output_cursor(value: str) -> tuple[int, int]:
    stdout, stderr = value.split(":", 1)
    return int(stdout), int(stderr)


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
