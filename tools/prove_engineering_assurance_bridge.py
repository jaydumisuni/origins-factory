from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from origins_integration.engineering import (  # noqa: E402
    BridgeError,
    EngineeringAttemptRequest,
    EngineeringBridge,
    OriginsClient,
)

TOKEN = "origins-engineering-proof-token"


class FixtureContracts:
    """Protocol fixture only; production uses the owning AgentOps/CodeOps packages."""

    def __init__(self) -> None:
        self.packet_calls = 0
        self.ingest_calls = 0

    def build_agentops_packet(self, request: EngineeringAttemptRequest, *, workspace: str):
        self.packet_calls += 1
        for item in request.files:
            posix = PurePosixPath(item.replace("\\", "/"))
            windows = PureWindowsPath(item)
            if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts:
                raise BridgeError("fixture AgentOps rejected unsafe file path")
        if request.apply_plan and request.approval_state != "approved":
            raise BridgeError("fixture AgentOps rejected unapproved apply")
        return SimpleNamespace(
            operation_id=request.operation_id,
            task=request.task,
            workspace=workspace,
            files=request.files,
            plan=request.plan,
            apply_plan=request.apply_plan,
        )

    def ingest_sergeant_result_text(self, text: str):
        self.ingest_calls += 1
        data = json.loads(text)
        raw = data.get("verdict")
        verdict = raw if raw in {"PASS", "NEEDS WORK", "BLOCK"} else "UNKNOWN"
        return SimpleNamespace(
            verdict=verdict,
            needs_loop=verdict != "PASS",
            blocked=verdict == "BLOCK",
            summary=str(data.get("summary", f"fixture {verdict}")),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-engineering-proof-") as temp_dir:
        base = Path(temp_dir)
        state = base / "state"
        workspaces = base / "workspaces"
        repo = workspaces / "repo"
        fake_bin = base / "bin"
        repo.mkdir(parents=True)
        fake_bin.mkdir()
        install_fixture_tools(fake_bin)
        init_repository(repo)
        (repo / "config").mkdir()
        (repo / "config" / "code_ops_switcher.example.json").write_text("{}\n", encoding="utf-8")
        (repo / "plans").mkdir()
        (repo / "plans" / "fix.json").write_text(
            json.dumps({"path": "tracked.txt", "content": "fixed\n"}), encoding="utf-8"
        )

        port = reserve_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(state),
                "ORIGINS_LOCAL_TOKEN": TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspaces),
                "PATH": os.pathsep.join([str(fake_bin), env.get("PATH", "")]),
            }
        )
        daemon = start(args.binary, env)
        try:
            wait_for_health(base_url, daemon)
            workspace = request_json(
                base_url + "/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Engineering proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            repository = request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            repository_id = repository["repository_id"]

            contracts = FixtureContracts()
            bridge = EngineeringBridge(OriginsClient(base_url, TOKEN), contracts)
            operation_id = "agentops-op-proof-001"

            first = bridge.run_attempt(
                EngineeringAttemptRequest(
                    operation_id=operation_id,
                    repository_id=repository_id,
                    task="Correct tracked.txt and prove it independently",
                    files=("tracked.txt",),
                    approval_state="not_required",
                )
            )
            assert first.operation_id == operation_id
            assert first.verdict == "NEEDS WORK"
            assert first.needs_loop is True
            assert first.blocked is False
            assert first.recommended_agentops_action == "correct"
            assert first.plan_preview is None
            assert first.plan_apply is None
            assert first.route.session_id != first.sergeant_command.session_id
            assert first.sergeant_review.session_id not in {
                first.route.session_id,
                first.sergeant_command.session_id,
            }
            first_review_bytes = bytes.fromhex(first.sergeant_review.output["stdout_hex"])
            assert hashlib.sha256(first_review_bytes).hexdigest() == first.review_sha256
            assert "NEEDS WORK" not in json.dumps(first.evidence_record())
            assert first.evidence_record()["verdict"] == "NEEDS WORK"

            before_unapproved = session_count(base_url)
            try:
                bridge.run_attempt(
                    EngineeringAttemptRequest(
                        operation_id=operation_id,
                        repository_id=repository_id,
                        task="Attempt unapproved correction",
                        files=("tracked.txt",),
                        plan="plans/fix.json",
                        apply_plan=True,
                        approval_state="required",
                    )
                )
            except BridgeError as error:
                assert "unapproved" in str(error).lower()
            else:
                raise AssertionError("unapproved apply did not fail")
            assert session_count(base_url) == before_unapproved

            try:
                EngineeringAttemptRequest(
                    operation_id=operation_id,
                    repository_id=repository_id,
                    task="Unsafe plan",
                    plan="../escape.json",
                )
            except BridgeError:
                pass
            else:
                raise AssertionError("unsafe plan path was accepted")
            assert session_count(base_url) == before_unapproved

            second = bridge.run_attempt(
                EngineeringAttemptRequest(
                    operation_id=operation_id,
                    repository_id=repository_id,
                    task="Apply approved correction and re-review",
                    files=("tracked.txt",),
                    plan="plans/fix.json",
                    apply_plan=True,
                    approval_state="approved",
                )
            )
            assert second.operation_id == operation_id
            assert second.verdict == "PASS"
            assert second.needs_loop is False
            assert second.blocked is False
            assert second.recommended_agentops_action == "complete_candidate"
            assert second.plan_preview is not None
            assert second.plan_apply is not None
            assert (repo / "tracked.txt").read_text(encoding="utf-8") == "fixed\n"
            first_ids = {
                first.route.session_id,
                first.sergeant_command.session_id,
                first.sergeant_review.session_id,
            }
            second_ids = {
                second.route.session_id,
                second.plan_preview.session_id,
                second.plan_apply.session_id,
                second.sergeant_command.session_id,
                second.sergeant_review.session_id,
            }
            assert first_ids.isdisjoint(second_ids)

            (repo / "tracked.txt").write_text("block\n", encoding="utf-8")
            request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            blocked = bridge.run_attempt(
                EngineeringAttemptRequest(
                    operation_id="agentops-op-proof-block",
                    repository_id=repository_id,
                    task="Review blocked state",
                    files=("tracked.txt",),
                )
            )
            assert blocked.verdict == "BLOCK"
            assert blocked.blocked is True
            assert blocked.recommended_agentops_action == "block"

            (repo / "tracked.txt").write_text("unknown PASS somewhere\n", encoding="utf-8")
            request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            unresolved = bridge.run_attempt(
                EngineeringAttemptRequest(
                    operation_id="agentops-op-proof-unknown",
                    repository_id=repository_id,
                    task="Review ambiguous state",
                    files=("tracked.txt",),
                )
            )
            assert unresolved.verdict == "UNKNOWN"
            assert unresolved.recommended_agentops_action == "unresolved"
            assert unresolved.needs_loop is True

            assert contracts.packet_calls == 5  # includes rejected unapproved packet
            assert contracts.ingest_calls == 4

            sessions = request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"]
            assert all(session["capability_id"] == "origins.process.run" for session in sessions)
            journal = request_json(base_url + "/v1/events?after_sequence=0&limit=500", token=TOKEN)
            journal_text = json.dumps(journal, sort_keys=True)
            assert "fixed\\n" not in journal_text
            assert TOKEN not in journal_text
        finally:
            stdout, stderr = stop(daemon)

        combined = stdout + "\n" + stderr
        if TOKEN in combined:
            raise AssertionError("Origins token leaked into hosted engineering proof output")

    print(
        "PASS: Origins protocol fixture proved AgentOps-gated CodeOps Sessions, independent Sergeant "
        "review, NEEDS WORK correction attempt, fresh PASS, BLOCK and UNKNOWN routing"
    )
    return 0


def install_fixture_tools(fake_bin: Path) -> None:
    switcher = fake_bin / "hunter-codeops-switcher"
    switcher.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
command = next((item for item in ("route", "apply-plan", "sergeant-command") if item in args), "")
if command == "route":
    print(json.dumps({"ok": True, "decision": {"event": "fixture.route", "model": "none"}}))
    raise SystemExit(0)
if command == "apply-plan":
    root = pathlib.Path(args[args.index("--root") + 1])
    plan_path = pathlib.Path(args[args.index("--plan") + 1])
    if not plan_path.is_absolute():
        plan_path = pathlib.Path.cwd() / plan_path
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    applied = "--apply" in args
    if applied:
        target = root / plan["path"]
        target.write_text(plan["content"], encoding="utf-8")
    print(json.dumps({"ok": True, "file_edit": {"applied": applied, "path": plan["path"]}}))
    raise SystemExit(0)
if command == "sergeant-command":
    workspace = args[args.index("--workspace") + 1]
    mode = args[args.index("--review-mode") + 1]
    result = ["sergeant", "app-review", workspace, "--mode", mode]
    if "--files" in args:
        result.extend(["--files", args[args.index("--files") + 1]])
    result.append("--pretty")
    print(json.dumps({"ok": True, "command": result, "audit_event": {"event": "fixture.sergeant"}}))
    raise SystemExit(0)
print(json.dumps({"ok": False, "error": "unsupported fixture command"}))
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    sergeant = fake_bin / "sergeant"
    sergeant.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
if len(args) < 2 or args[0] != "app-review":
    print(json.dumps({"verdict": "BLOCK", "summary": "invalid fixture review command"}))
    raise SystemExit(0)
workspace = pathlib.Path(args[1])
content = (workspace / "tracked.txt").read_text(encoding="utf-8")
if content == "fixed\\n":
    result = {"verdict": "PASS", "summary": "fixture correction verified"}
elif content == "block\\n":
    result = {"verdict": "BLOCK", "summary": "fixture blocker"}
elif content.startswith("unknown"):
    result = {"message": "PASS appears in prose but no canonical verdict"}
else:
    result = {"verdict": "NEEDS WORK", "summary": "fixture correction required"}
print(json.dumps(result))
""",
        encoding="utf-8",
    )
    switcher.chmod(0o755)
    sergeant.chmod(0o755)


def init_repository(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Origins Proof"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "origins-proof@example.invalid"], check=True
    )
    (repo / "tracked.txt").write_text("bad\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True)


def session_count(base_url: str) -> int:
    return len(request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"])


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
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {response.status}")
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, BridgeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
