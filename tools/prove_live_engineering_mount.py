from __future__ import annotations

import argparse
import json
import os
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
from origins_integration.engineering import ExternalContracts, OriginsClient  # noqa: E402
from origins_integration.live_mount import (  # noqa: E402
    LiveEngineeringMount,
    MountSmokeError,
)

TOKEN = "origins-live-mount-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="origins-live-mount-") as temp_dir:
        base = Path(temp_dir)
        state = base / "state"
        workspaces = base / "workspaces"
        repo = workspaces / "repo"
        integration = base / "integration"
        fake_python = base / "python-fixtures"
        full_bin = base / "full-bin"
        codeops_only_bin = base / "codeops-only-bin"
        repo.mkdir(parents=True)
        integration.mkdir()
        fake_python.mkdir()
        full_bin.mkdir()
        codeops_only_bin.mkdir()
        config = integration / "codeops.json"
        config.write_text("{}\n", encoding="utf-8")
        install_python_owner_fixtures(fake_python)
        install_codeops_fixture(full_bin / "hunter-codeops-switcher")
        install_sergeant_fixture(full_bin / "sergeant")
        install_codeops_fixture(codeops_only_bin / "hunter-codeops-switcher")
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
                payload={"name": "Live mount proof", "authority_refs": [], "session_refs": []},
                expected_status=201,
            )
            repository = request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            repository_id = repository["repository_id"]
            client = OriginsClient(base_url, TOKEN)
            contracts = ExternalContracts.load()
            mount = LiveEngineeringMount._for_fixture(
                client,
                doctor=EngineeringMountDoctor(client),
                contracts=contracts,
            )
            receipt = mount.run(repository_id, config=str(config), files=("tracked.txt",))

            assert receipt.proof_scope == "fixture"
            assert receipt.mount_status == "compatible"
            assert receipt.live_engineering_proven is False
            assert receipt.project_verdict == "NEEDS WORK"
            assert receipt.recommended_agentops_action == "correct"
            assert receipt.route_session_id
            assert receipt.sergeant_command_session_id
            assert receipt.sergeant_review_session_id
            assert receipt.review_sha256
            assert str(config).startswith(str(integration))
            assert not str(config).startswith(str(repo))
            payload = receipt.as_dict()
            assert "config" not in payload
            assert "summary" not in payload
            assert "stdout" not in json.dumps(payload)
            assert all(surface["status"] == "compatible" for surface in payload["doctor_surfaces"])

            sessions = request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"]
            # 2 doctor CLI probes + CodeOps route + CodeOps sergeant-command + Sergeant review.
            assert len(sessions) == 5
            assert all(session["capability_id"] == "origins.process.run" for session in sessions)
            journal_text = json.dumps(
                request_json(base_url + "/v1/events?after_sequence=0&limit=500", token=TOKEN),
                sort_keys=True,
            )
            assert str(config) not in journal_text
            assert TOKEN not in journal_text
        finally:
            first_stdout, first_stderr = stop(first)

        second_env = {**common_env, "PATH": str(codeops_only_bin)}
        second = start(args.binary, second_env)
        try:
            wait_for_health(base_url, second)
            client = OriginsClient(base_url, TOKEN)
            mount = LiveEngineeringMount._for_fixture(
                client,
                doctor=EngineeringMountDoctor(client),
                contracts=ExternalContracts.load(),
            )
            before = len(request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"])
            try:
                mount.run(repository_id, config=str(config), files=("tracked.txt",))
            except MountSmokeError as error:
                assert "doctor is not compatible" in str(error)
            else:
                raise AssertionError("missing Sergeant owner did not block smoke")
            after = len(request_json(base_url + "/v1/sessions", token=TOKEN)["sessions"])
            # Only the two doctor CLI probes may be added. No CodeOps route/review bridge Sessions follow.
            assert after == before + 2
            assert not (codeops_only_bin / "sergeant").exists()
        finally:
            second_stdout, second_stderr = stop(second)

        combined = "\n".join((first_stdout, first_stderr, second_stdout, second_stderr))
        if TOKEN in combined:
            raise AssertionError("live-mount proof token leaked into daemon output")

    print(
        "PASS: doctor-gated fixture smoke used absolute external CodeOps config, real originsd Sessions, "
        "canonical review, fixture non-promotion, and missing-owner block before bridge work"
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
        '''import json\nfrom dataclasses import dataclass\nfrom enum import Enum\n\nclass SergeantVerdict(str, Enum):\n    PASS_ = "PASS"\n    NEEDS_WORK = "NEEDS WORK"\n    BLOCK = "BLOCK"\n\n@dataclass(frozen=True)\nclass Result:\n    verdict: object\n    needs_loop: bool\n    blocked: bool\n    summary: str\n\ndef ingest_sergeant_result_text(text: str):\n    data = json.loads(text)\n    verdict = data.get("verdict")\n    if verdict == "PASS":\n        return Result(SergeantVerdict.PASS_, False, False, "fixture PASS")\n    if verdict == "NEEDS WORK":\n        return Result(SergeantVerdict.NEEDS_WORK, True, False, "fixture NEEDS WORK")\n    if verdict == "BLOCK":\n        return Result(SergeantVerdict.BLOCK, True, True, "fixture BLOCK")\n    return Result("UNKNOWN", True, False, "fixture UNKNOWN")\n''',
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


def install_codeops_fixture(path: Path) -> None:
    path.write_text(
        '''#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
if args == ["--help"]:
    print("Hunter CodeOps fixture help")
    raise SystemExit(0)
if "--config" not in args:
    print(json.dumps({"ok": False, "error": "config missing"}))
    raise SystemExit(2)
config = pathlib.Path(args[args.index("--config") + 1])
if not config.is_file():
    print(json.dumps({"ok": False, "error": "config unavailable"}))
    raise SystemExit(2)
command = next((item for item in ("route", "sergeant-command") if item in args), "")
if command == "route":
    print(json.dumps({"ok": True, "decision": {"event": "fixture.route", "model": "none"}}))
    raise SystemExit(0)
if command == "sergeant-command":
    workspace = args[args.index("--workspace") + 1]
    mode = args[args.index("--review-mode") + 1]
    result = ["sergeant", "app-review", workspace, "--mode", mode]
    if "--files" in args:
        result.extend(["--files", args[args.index("--files") + 1]])
    result.append("--pretty")
    print(json.dumps({"ok": True, "command": result}))
    raise SystemExit(0)
print(json.dumps({"ok": False, "error": "mutation/provider command forbidden in smoke fixture"}))
raise SystemExit(2)
''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def install_sergeant_fixture(path: Path) -> None:
    path.write_text(
        '''#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
if args == ["--help"]:
    print("Sergeant fixture help")
    raise SystemExit(0)
if len(args) < 2 or args[0] != "app-review":
    print(json.dumps({"verdict": "BLOCK", "summary": "invalid command"}))
    raise SystemExit(0)
workspace = pathlib.Path(args[1])
content = (workspace / "tracked.txt").read_text(encoding="utf-8")
if content == "bad\\n":
    print(json.dumps({"verdict": "NEEDS WORK", "summary": "fixture review found work"}))
else:
    print(json.dumps({"verdict": "PASS", "summary": "fixture review passed"}))
''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def init_repository(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Origins Proof"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "origins-proof@example.invalid"], check=True
    )
    (repo / "tracked.txt").write_text("bad\n", encoding="utf-8")
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
    except (AssertionError, MountSmokeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
