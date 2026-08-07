from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from origins_integration.doctor import EngineeringMountDoctor  # noqa: E402
from origins_integration.engineering import OriginsClient  # noqa: E402

TOKEN = "origins-mount-doctor-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-mount-doctor-") as temp_dir:
        base = Path(temp_dir)
        state = base / "state"
        workspaces = base / "workspaces"
        repo = workspaces / "repo"
        fake_python = base / "python-fixtures"
        full_bin = base / "full-bin"
        codeops_only_bin = base / "codeops-only-bin"
        repo.mkdir(parents=True)
        fake_python.mkdir()
        full_bin.mkdir()
        codeops_only_bin.mkdir()
        install_python_owner_fixtures(fake_python)
        install_cli_fixture(full_bin / "hunter-codeops-switcher", "Hunter CodeOps fixture help")
        install_cli_fixture(full_bin / "sergeant", "Sergeant fixture help")
        install_cli_fixture(codeops_only_bin / "hunter-codeops-switcher", "Hunter CodeOps fixture help")
        sys.path.insert(0, str(fake_python))
        init_repository(repo)

        port = reserve_port()
        base_url = f"http://127.0.0.1:{port}"
        common_env = os.environ.copy()
        common_env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(state),
                "ORIGINS_LOCAL_TOKEN": TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspaces),
            }
        )
        first_env = {**common_env, "PATH": os.pathsep.join([str(full_bin), common_env.get("PATH", "")])}

        first = start(args.binary, first_env)
        try:
            wait_for_health(base_url, first)
            workspace = request_json(
                base_url + "/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={"name": "Mount doctor proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            repository = request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            repository_id = repository["repository_id"]
            doctor = EngineeringMountDoctor(OriginsClient(base_url, TOKEN))
            result = doctor.run(repository_id)
            assert result.overall_status == "compatible"
            assert result.live_engineering_proven is False
            assert result.blockers == ()
            surfaces = {surface.surface: surface for surface in result.surfaces}
            assert surfaces["agentops_python"].status == "compatible"
            assert surfaces["agentops_python"].version == "0.3.0"
            assert surfaces["codeops_python"].status == "compatible"
            assert surfaces["codeops_python"].version == "0.3.0"
            assert surfaces["codeops_cli"].status == "compatible"
            assert surfaces["sergeant_cli"].status == "compatible"
            assert surfaces["sergeant_cli"].version == "0.4.1"
            assert surfaces["codeops_cli"].session_id
            assert surfaces["sergeant_cli"].session_id
            assert surfaces["codeops_cli"].evidence_sha256
            assert surfaces["sergeant_cli"].evidence_sha256

            sessions = request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"]
            assert len(sessions) == 2
            assert all(session["capability_id"] == "origins.process.run" for session in sessions)
        finally:
            first_stdout, first_stderr = stop(first)

        # Restart against the same durable Origins state with Sergeant intentionally absent from PATH.
        # Git must remain available because the doctor now refreshes Repository truth before probing owners.
        system_git = shutil.which("git")
        if not system_git:
            raise AssertionError("system Git is required for the Repository refresh proof")
        second_path = os.pathsep.join([str(codeops_only_bin), str(Path(system_git).parent)])
        if shutil.which("sergeant", path=second_path) is not None:
            raise AssertionError("Sergeant unexpectedly exists in the missing-owner proof PATH")
        second_env = {**common_env, "PATH": second_path}
        second = start(args.binary, second_env)
        try:
            wait_for_health(base_url, second)
            before = list(codeops_only_bin.iterdir())
            result = EngineeringMountDoctor(OriginsClient(base_url, TOKEN)).run(repository_id)
            surfaces = {surface.surface: surface for surface in result.surfaces}
            assert surfaces["agentops_python"].status == "compatible"
            assert surfaces["codeops_python"].status == "compatible"
            assert surfaces["codeops_cli"].status == "compatible"
            assert surfaces["sergeant_cli"].status == "missing"
            assert result.overall_status == "missing"
            assert result.live_engineering_proven is False
            assert any("sergeant_cli" in blocker for blocker in result.blockers)
            after = list(codeops_only_bin.iterdir())
            assert before == after
            assert not (codeops_only_bin / "sergeant").exists()
        finally:
            second_stdout, second_stderr = stop(second)

        combined = "\n".join((first_stdout, first_stderr, second_stdout, second_stderr))
        if TOKEN in combined:
            raise AssertionError("mount-doctor token leaked into daemon output")

    print(
        "PASS: production engineering doctor classified compatible owner fixtures through real originsd, "
        "then kept overall status missing when Sergeant disappeared without self-repair"
    )
    return 0


def install_python_owner_fixtures(root: Path) -> None:
    agentops = root / "hunter_agentops"
    codeops = root / "hunter_codeops"
    agentops.mkdir()
    codeops.mkdir()
    (agentops / "__init__.py").write_text("", encoding="utf-8")
    (codeops / "__init__.py").write_text("", encoding="utf-8")
    (agentops / "code_ops_switcher_runner.py").write_text(
        '''from dataclasses import dataclass, field\nfrom enum import Enum\n\nclass ApprovalState(str, Enum):\n    NOT_REQUIRED = "not_required"\n    REQUIRED = "required"\n    APPROVED = "approved"\n    DENIED = "denied"\n\n@dataclass(frozen=True)\nclass CodeOpsOperationPacket:\n    operation_id: str\n    task: str\n    client_kind: str = "terminal"\n    mode: str = "quick_edit"\n    config: str = "config/code_ops_switcher.example.json"\n    provider_id: str = ""\n    required_capability: str = ""\n    review: str = "auto"\n    workspace: str = "."\n    files: tuple[str, ...] = field(default_factory=tuple)\n    plan: str = ""\n    apply_plan: bool = False\n    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED\n''',
        encoding="utf-8",
    )
    (codeops / "code_ops_sergeant_ingest.py").write_text(
        '''import json\nfrom dataclasses import dataclass\nfrom enum import Enum\n\nclass SergeantVerdict(str, Enum):\n    PASS_ = "PASS"\n    NEEDS_WORK = "NEEDS WORK"\n    BLOCK = "BLOCK"\n\n@dataclass(frozen=True)\nclass Result:\n    verdict: SergeantVerdict\n    needs_loop: bool\n    blocked: bool\n\ndef ingest_sergeant_result_text(text: str):\n    verdict = json.loads(text)["verdict"]\n    if verdict == "PASS":\n        return Result(SergeantVerdict.PASS_, False, False)\n    if verdict == "NEEDS WORK":\n        return Result(SergeantVerdict.NEEDS_WORK, True, False)\n    if verdict == "BLOCK":\n        return Result(SergeantVerdict.BLOCK, True, True)\n    raise ValueError(verdict)\n''',
        encoding="utf-8",
    )
    install_metadata(root, "hunter_agentops-0.3.0.dist-info", "hunter-agentops", "0.3.0")
    install_metadata(root, "hunter_codeops-0.3.0.dist-info", "hunter-codeops", "0.3.0")
    install_metadata(root, "sergeant_reviewer-0.4.1.dist-info", "sergeant-reviewer", "0.4.1")


def install_metadata(root: Path, directory: str, name: str, version: str) -> None:
    dist = root / directory
    dist.mkdir()
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        encoding="utf-8",
    )


def install_cli_fixture(path: Path, text: str) -> None:
    path.write_text(
        f'''#!/bin/sh\nif [ "$1" = "--help" ]; then\n  printf '%s\\n' '{text}'\n  exit 0\nfi\nprintf '%s\\n' 'unsupported fixture command' >&2\nexit 2\n''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def init_repository(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Origins Proof"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "origins-proof@example.invalid"], check=True
    )
    (repo / "tracked.txt").write_text("doctor\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial"], check=True, capture_output=True)


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
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
