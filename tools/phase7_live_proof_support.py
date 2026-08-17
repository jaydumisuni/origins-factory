from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origins_integration.engineering import OriginsClient

DEFAULT_DAEMON = Path("/home/kratos/origins-factory/rust/target/debug/originsd")
PROOF_BIND = "127.0.0.1:48777"
PROOF_URL = f"http://{PROOF_BIND}"


class ProofError(RuntimeError):
    pass


@dataclass
class Daemon:
    process: subprocess.Popen[bytes]

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: float = 30) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ProofError(
            f"command failed ({result.returncode}): {args!r}: "
            f"stdout={result.stdout[-1200:]!r} stderr={result.stderr[-1200:]!r}"
        )
    return result.stdout.strip()


def git_head(path: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=path)


def assert_tracked_clean(name: str, path: Path) -> None:
    for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        result = subprocess.run(args, cwd=path, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise ProofError(f"{name} checkout has tracked changes and cannot be used as exact proof")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _ensure_proof_port_free() -> None:
    host, raw_port = PROOF_BIND.rsplit(":", 1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, int(raw_port)))
    except OSError as exc:
        raise ProofError(f"Phase 7 proof port is already in use: {PROOF_BIND}") from exc


def _wait_health(process: subprocess.Popen[bytes], token: str, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise ProofError(f"originsd exited before becoming healthy: {exit_code}")
        try:
            with urllib.request.urlopen(f"{PROOF_URL}/v1/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("ok") is True:
                    auth_request = urllib.request.Request(
                        f"{PROOF_URL}/v1/capabilities",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    with urllib.request.urlopen(auth_request, timeout=0.5) as authenticated:
                        auth_payload = json.loads(authenticated.read().decode("utf-8"))
                    if authenticated.status == 200 and isinstance(auth_payload.get("capabilities"), list):
                        if process.poll() is not None:
                            raise ProofError("originsd exited after health while a foreign listener remained")
                        return
        except ProofError:
            raise
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(0.05)
    raise ProofError(f"originsd did not become healthy and authenticated: {last}")


def start_daemon(*, data_dir: Path, workspace_root: Path, token: str) -> Daemon:
    daemon_path = Path(os.environ.get("ORIGINS_PHASE7_DAEMON", str(DEFAULT_DAEMON))).resolve()
    if not daemon_path.is_file():
        raise ProofError(f"originsd binary unavailable: {daemon_path}")
    _ensure_proof_port_free()
    env = os.environ.copy()
    env.update(
        {
            "ORIGINS_BIND": PROOF_BIND,
            "ORIGINS_DATA_DIR": str(data_dir),
            "ORIGINS_LOCAL_TOKEN": token,
            "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
            "ORIGINS_ARTIFACT_ROOTS": str(workspace_root),
            "PATH": os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")]),
        }
    )
    process = subprocess.Popen(
        [str(daemon_path)],
        cwd=workspace_root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    daemon = Daemon(process)
    try:
        _wait_health(process, token)
    except Exception:
        daemon.stop()
        raise
    return daemon


def init_repo(path: Path, *, initial_value: str, replacement_value: str, strict: bool) -> None:
    path.mkdir(parents=True)
    (path / "capability.py").write_text(
        "def capability() -> str:\n" f"    return {initial_value!r}\n",
        encoding="utf-8",
    )
    tracked = ["capability.py"]
    if strict:
        tests = path / "tests"
        tests.mkdir()
        (tests / "test_capability.py").write_text(
            "from capability import capability\n\n"
            "def test_capability() -> None:\n"
            f"    assert capability() == {initial_value!r}\n",
            encoding="utf-8",
        )
        (path / "pyproject.toml").write_text(
            "[project]\nname='origins-phase7-proof'\nversion='0.0.0'\nrequires-python='>=3.10'\n",
            encoding="utf-8",
        )
        (path / "README.md").write_text(
            "# Origins Phase 7 Proof\n\n"
            "Disposable exact-host repository used to verify controlled capability evolution.\n",
            encoding="utf-8",
        )
        workflows = path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "name: Phase 7 proof fixture\n\n"
            "on:\n"
            "  push:\n"
            "  pull_request:\n\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n"
            "      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n"
            "        with:\n"
            "          python-version: '3.12'\n"
            "      - run: python -m pytest -q\n",
            encoding="utf-8",
        )
        tracked.extend(
            [
                "tests/test_capability.py",
                "pyproject.toml",
                "README.md",
                ".github/workflows/ci.yml",
            ]
        )
    run(["git", "init", "-b", "main"], cwd=path)
    run(["git", "config", "user.name", "Origins Phase 7 Proof"], cwd=path)
    run(["git", "config", "user.email", "origins-phase7-proof@invalid.local"], cwd=path)
    run(["git", "add", *tracked], cwd=path)
    run(["git", "commit", "-m", "proof baseline"], cwd=path)
    operations = [
        {
            "path": "capability.py",
            "action": "replace",
            "old": f"return {initial_value!r}",
            "new": f"return {replacement_value!r}",
            "required": True,
        }
    ]
    if strict:
        operations.append(
            {
                "path": "tests/test_capability.py",
                "action": "replace",
                "old": f"assert capability() == {initial_value!r}",
                "new": f"assert capability() == {replacement_value!r}",
                "required": True,
            }
        )
    (path / "upgrade-plan.json").write_text(
        json.dumps(
            {"operations": operations, "reason": "Phase 7 disposable capability proof", "require_review": True},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def workspace(client: OriginsClient) -> str:
    created = client._json(
        "POST",
        "/v1/workspaces",
        {"name": "Phase 7 live-owner proof", "authority_refs": [], "session_refs": []},
        expected_status=201,
    )
    workspace_id = created.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ProofError("originsd workspace creation omitted workspace_id")
    return workspace_id


def repository(client: OriginsClient, workspace_id: str, path: Path) -> str:
    observed = client.inspect_repository(workspace_id, str(path))
    repository_id = observed.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id:
        raise ProofError("repository inspection omitted repository_id")
    return repository_id


def approval_id(created: dict[str, object]) -> str:
    binding = created.get("binding")
    if not isinstance(binding, dict):
        raise ProofError("AgentOps approval binding is missing")
    value = binding.get("approval_id")
    if not isinstance(value, str) or not value:
        raise ProofError("AgentOps approval binding omitted approval_id")
    return value


def session_id(accepted: dict[str, Any]) -> str:
    session = accepted.get("session")
    if not isinstance(session, dict):
        raise ProofError("canary process was not accepted as an Origins Session")
    value = session.get("session_id")
    if not isinstance(value, str) or not value:
        raise ProofError("canary Session omitted session_id")
    return value
