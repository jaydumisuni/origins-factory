from __future__ import annotations

import argparse
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
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = "origins-repository-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-repository-proof-") as temp_dir:
        base = Path(temp_dir)
        data_dir = base / "data"
        workspace_root = base / "workspaces"
        workspace_root.mkdir()
        outside = base / "outside"
        outside.mkdir()
        repo = workspace_root / "repo"
        linked = workspace_root / "linked"
        init_repository(repo)

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
            assert health["repository_schema_version"] == 1
            assert health["repositories"] == 0

            workspace = request_json(
                f"{base_url}/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Repository proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            workspace_id = workspace["workspace_id"]

            assert_http_status(
                f"{base_url}/v1/repositories/inspect",
                401,
                method="POST",
                payload={"workspace_id": workspace_id, "path": str(repo)},
            )
            assert_http_status(
                f"{base_url}/v1/repositories/inspect",
                400,
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace_id, "path": str(outside)},
            )
            nongit = workspace_root / "not-a-repo"
            nongit.mkdir()
            assert_http_status(
                f"{base_url}/v1/repositories/inspect",
                400,
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace_id, "path": str(nongit)},
            )

            baseline_head = git(repo, "rev-parse", "HEAD").decode().strip()
            baseline_status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
            repository = inspect(base_url, workspace_id, repo)
            repository_id = repository["repository_id"]
            assert repository["workspace_id"] == workspace_id
            assert repository["worktree_root"] == str(repo.resolve())
            assert repository["branch"] == "main"
            assert repository["head_ref"] == "refs/heads/main"
            assert repository["head_oid"] == baseline_head
            assert repository["detached"] is False
            assert repository["unborn"] is False
            assert repository["staged_count"] == 0
            assert repository["unstaged_count"] == 0
            assert repository["untracked_count"] == 0
            assert repository["status_sha256"] == hashlib.sha256(baseline_status).hexdigest()
            assert git(repo, "rev-parse", "HEAD").decode().strip() == baseline_head
            assert git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all") == baseline_status

            fetched = request_json(
                f"{base_url}/v1/repositories/{repository_id}", token=TOKEN
            )
            assert fetched == repository
            listed = request_json(
                f"{base_url}/v1/repositories?{urllib.parse.urlencode({'workspace_id': workspace_id})}",
                token=TOKEN,
            )
            assert [item["repository_id"] for item in listed["repositories"]] == [repository_id]

            generic_git = command_envelope(workspace_id, workspace_root, "git", ["status"])
            error = request_error_json(
                f"{base_url}/v1/commands",
                token=TOKEN,
                method="POST",
                payload=generic_git,
                expected_status=400,
            )
            assert error["error_code"] == "DEDICATED_CAPABILITY_REQUIRED"

            tracked = repo / "tracked.txt"
            tracked.write_text("staged-version\n" + "A" * 256 + "\n", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            tracked.write_text("unstaged-version\n" + "B" * 256 + "\n", encoding="utf-8")
            (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

            dirty = inspect(base_url, workspace_id, repo)
            assert dirty["repository_id"] == repository_id
            assert dirty["revision"] > repository["revision"]
            assert dirty["staged_count"] >= 1
            assert dirty["unstaged_count"] >= 1
            assert dirty["untracked_count"] >= 1
            expected_status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
            assert dirty["status_sha256"] == hashlib.sha256(expected_status).hexdigest()

            staged_expected = git(
                repo,
                "diff",
                "--cached",
                "--no-ext-diff",
                "--binary",
                "--no-color",
                "--full-index",
                "--",
            )
            staged = request_json(
                f"{base_url}/v1/repositories/{repository_id}/diff?kind=staged&limit=32",
                token=TOKEN,
            )
            assert staged["sha256"] == hashlib.sha256(staged_expected).hexdigest()
            assert staged["complete_bytes"] == len(staged_expected)
            assert staged["retained_bytes"] == min(32, len(staged_expected))
            assert bytes.fromhex(staged["retained_hex"]) == staged_expected[:32]
            assert staged["truncated"] is (len(staged_expected) > 32)

            unstaged_expected = git(
                repo,
                "diff",
                "--no-ext-diff",
                "--binary",
                "--no-color",
                "--full-index",
                "--",
            )
            unstaged = request_json(
                f"{base_url}/v1/repositories/{repository_id}/diff?kind=unstaged&limit=47",
                token=TOKEN,
            )
            assert unstaged["sha256"] == hashlib.sha256(unstaged_expected).hexdigest()
            assert unstaged["complete_bytes"] == len(unstaged_expected)
            assert bytes.fromhex(unstaged["retained_hex"]) == unstaged_expected[:47]

            events = request_json(f"{base_url}/v1/events?after_sequence=0&limit=200", token=TOKEN)
            journal_text = json.dumps(events, sort_keys=True)
            if "staged-version" in journal_text or "unstaged-version" in journal_text:
                raise AssertionError("raw repository diff leaked into permanent journal")
            assert "repository.diff_observed" in journal_text

            git(repo, "checkout", "--detach", "HEAD")
            detached = inspect(base_url, workspace_id, repo)
            assert detached["repository_id"] == repository_id
            assert detached["detached"] is True
            assert detached["unborn"] is False
            assert detached["head_ref"] == ""
            assert detached["branch"] == ""
            assert detached["head_oid"]

            git(repo, "worktree", "add", "-b", "linked-proof", str(linked), "HEAD")
            linked_projection = inspect(base_url, workspace_id, linked)
            assert linked_projection["repository_id"] != repository_id
            assert linked_projection["branch"] == "linked-proof"
            assert linked_projection["detached"] is False
            assert linked_projection["common_dir"] == detached["common_dir"]
            assert linked_projection["git_dir"] != detached["git_dir"]

            health = request_json(f"{base_url}/v1/health")
            assert health["repositories"] == 2
        finally:
            first_stdout, first_stderr = stop(first)

        second = start(args.binary, env)
        try:
            wait_for_health(base_url, second)
            recovered = request_json(
                f"{base_url}/v1/repositories/{repository_id}", token=TOKEN
            )
            assert recovered["repository_id"] == repository_id
            assert recovered["detached"] is True
            linked_recovered = request_json(
                f"{base_url}/v1/repositories/{linked_projection['repository_id']}", token=TOKEN
            )
            assert linked_recovered["branch"] == "linked-proof"
        finally:
            second_stdout, second_stderr = stop(second)

        database = data_dir / "origins.sqlite3"
        tamper_repository(database, repository_id)
        third = start(args.binary, env)
        try:
            wait_for_health(base_url, third)
            error = request_error_json(
                f"{base_url}/v1/repositories/{repository_id}",
                token=TOKEN,
                expected_status=503,
            )
            assert error["error_code"] == "CORRUPT_STATE"
        finally:
            third_stdout, third_stderr = stop(third)

        combined = "\n".join(
            (
                first_stdout,
                first_stderr,
                second_stdout,
                second_stderr,
                third_stdout,
                third_stderr,
            )
        )
        if TOKEN in combined:
            raise AssertionError("repository proof token leaked into daemon output")

    print("PASS: repository Git identity, status, bounded diff, worktree, restart and tamper proof")
    return 0


def init_repository(repo: Path) -> None:
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Origins Proof")
    git(repo, "config", "user.email", "origins-proof@example.invalid")
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "initial")


def inspect(base_url: str, workspace_id: str, path: Path) -> dict:
    return request_json(
        f"{base_url}/v1/repositories/inspect",
        token=TOKEN,
        method="POST",
        payload={"workspace_id": workspace_id, "path": str(path)},
    )


def command_envelope(workspace_id: str, workspace_root: Path, executable: str, args: list[str]) -> dict:
    import uuid
    from datetime import datetime, timezone

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
            "cwd": ".",
            "timeout_seconds": 5,
            "max_output_bytes": 4096,
        },
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, "LC_ALL": "C", "GIT_PAGER": "cat", "GIT_OPTIONAL_LOCKS": "0"},
    )
    return completed.stdout


def tamper_repository(database: Path, repository_id: str) -> None:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT projection_json FROM repositories WHERE repository_id = ?", (repository_id,)
        ).fetchone()
        if row is None:
            raise AssertionError("repository missing before tamper proof")
        projection = json.loads(row[0])
        projection["branch"] = "tampered-branch"
        connection.execute(
            "UPDATE repositories SET projection_json = ? WHERE repository_id = ?",
            (json.dumps(projection, separators=(",", ":"), sort_keys=True), repository_id),
        )
        connection.commit()
    finally:
        connection.close()


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
                f"originsd exited before health: {process.returncode}\nstdout={stdout}\nstderr={stderr}"
            )
        try:
            return request_json(f"{base_url}/v1/health")
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
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


def request_error_json(
    url: str,
    *,
    expected_status: int,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> dict:
    try:
        request_json(url, token=token, method=method, payload=payload)
    except urllib.error.HTTPError as error:
        if error.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {error.code}") from error
        return json.loads(error.read().decode("utf-8"))
    raise AssertionError(f"expected HTTP {expected_status}, request succeeded")


def assert_http_status(
    url: str,
    expected_status: int,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> None:
    request_error_json(
        url,
        expected_status=expected_status,
        token=token,
        method=method,
        payload=payload,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
