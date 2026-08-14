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
from pathlib import Path

TOKEN = "origins-workspace-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-workspace-proof-") as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data"
        workspace_root = root / "workspaces"
        repository_root = workspace_root / "sample-repo"
        data_dir.mkdir()
        repository_root.mkdir(parents=True)
        initialize_repository(repository_root)

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
                payload={"name": "Editor proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]
            repository = request_json(
                f"{base_url}/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace_id, "path": str(repository_root)},
            )
            repository_id = repository["repository_id"]

            files_url = f"{base_url}/v1/repositories/{repository_id}/files"
            assert_http_error(files_url, 401)
            listing = request_json(files_url, token=TOKEN)
            names = {entry["name"] for entry in listing["entries"]}
            assert {"README.md", "src"}.issubset(names), names
            assert ".git" not in names
            assert listing["truncated"] is False

            nested = request_json(
                f"{files_url}?{urllib.parse.urlencode({'path': 'src'})}", token=TOKEN
            )
            assert [entry["name"] for entry in nested["entries"]] == ["main.txt"]

            file_url = f"{base_url}/v1/repositories/{repository_id}/file"
            read = request_json(
                f"{file_url}?{urllib.parse.urlencode({'path': 'src/main.txt'})}", token=TOKEN
            )
            assert read["editable"] is True
            assert read["text"] == "before\n"
            original_sha = read["sha256"]

            write = request_json(
                file_url,
                token=TOKEN,
                method="POST",
                payload={
                    "path": "src/main.txt",
                    "text": "after\n",
                    "expected_sha256": original_sha,
                },
            )
            assert write["sha256"] != original_sha
            assert write["request_event"]["kind"] == "workspace.file_write_requested"
            assert write["event"]["kind"] == "workspace.file_written"
            assert repository_root.joinpath("src/main.txt").read_text(encoding="utf-8") == "after\n"

            changed = request_json(
                f"{file_url}?{urllib.parse.urlencode({'path': 'src/main.txt'})}", token=TOKEN
            )
            assert changed["text"] == "after\n"
            assert changed["sha256"] == write["sha256"]

            conflict = assert_http_error(
                file_url,
                409,
                token=TOKEN,
                method="POST",
                payload={
                    "path": "src/main.txt",
                    "text": "stale-overwrite\n",
                    "expected_sha256": original_sha,
                },
            )
            assert conflict["error_code"] == "FILE_CHANGED"
            assert repository_root.joinpath("src/main.txt").read_text(encoding="utf-8") == "after\n"

            traversal = assert_http_error(
                f"{file_url}?{urllib.parse.urlencode({'path': '../outside.txt'})}",
                400,
                token=TOKEN,
            )
            assert traversal["error_code"] == "INVALID_PATH"

            events = request_json(f"{base_url}/v1/events?after_sequence=0&limit=100", token=TOKEN)
            kinds = [event["kind"] for event in events["events"]]
            requested_index = kinds.index("workspace.file_write_requested")
            written_index = kinds.index("workspace.file_written")
            assert requested_index < written_index
        finally:
            first_stdout, first_stderr = stop(first)

        second = start(args.binary, env)
        try:
            health = wait_for_health(base_url, second)
            assert health["workspaces"] == 1
            assert health["repositories"] == 1
            recovered = request_json(
                f"{base_url}/v1/repositories/{repository_id}/file?{urllib.parse.urlencode({'path': 'src/main.txt'})}",
                token=TOKEN,
            )
            assert recovered["text"] == "after\n"
            assert recovered["sha256"] == write["sha256"]
        finally:
            second_stdout, second_stderr = stop(second)

        output = "\n".join((first_stdout, first_stderr, second_stdout, second_stderr))
        if TOKEN in output:
            raise AssertionError("local token leaked into daemon output")

    print("PASS: bounded repository editor auth, confinement, SHA conflict, evidence ordering and restart recovery")
    return 0


def initialize_repository(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], check=True, text=True, capture_output=True)
    path.joinpath("README.md").write_text("# editor proof\n", encoding="utf-8")
    path.joinpath("src").mkdir()
    path.joinpath("src/main.txt").write_text("before\n", encoding="utf-8")


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start(binary: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(binary)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
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


def assert_http_error(
    url: str,
    expected_status: int,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> dict:
    try:
        request_json(url, token=token, method=method, payload=payload)
    except urllib.error.HTTPError as error:
        if error.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {error.code}") from error
        body = error.read().decode("utf-8")
        return json.loads(body) if body else {}
    raise AssertionError(f"expected HTTP {expected_status}, request succeeded")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
