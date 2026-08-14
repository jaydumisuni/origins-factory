from __future__ import annotations

import argparse
import importlib
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

from origins_integration.engineering import OriginsClient  # noqa: E402
from origins_integration.live_mount import CANONICAL_PROJECT_VERDICTS, LiveEngineeringMount  # noqa: E402

TOKEN = "origins-phase4-live-owner-proof-token"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove the actual AgentOps + CodeOps + Sergeant Phase-4 owner stack through originsd."
    )
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--agentops-root", required=True, type=Path)
    parser.add_argument("--codeops-root", required=True, type=Path)
    parser.add_argument("--sergeant-root", required=True, type=Path)
    args = parser.parse_args()

    binary = args.binary.resolve()
    agentops_root = _require_owner_root(args.agentops_root, "agentops", "hunter_agentops")
    codeops_root = _require_owner_root(args.codeops_root, "codeops", "hunter_codeops")
    sergeant_root = _require_owner_root(args.sergeant_root, "sergeant", "main_review")
    config = codeops_root / "config" / "code_ops_switcher.example.json"
    if not config.is_file():
        raise AssertionError(f"CodeOps config missing: {config}")
    if not binary.is_file():
        raise AssertionError(f"originsd binary missing: {binary}")

    # Python semantic contracts come directly from the reviewed owner checkouts.
    sys.path.insert(0, str(codeops_root))
    sys.path.insert(0, str(agentops_root))
    importlib.invalidate_caches()

    with tempfile.TemporaryDirectory(prefix="origins-phase4-live-owner-") as temp_dir:
        base = Path(temp_dir)
        state = base / "state"
        workspaces = base / "workspaces"
        repo = workspaces / "repo"
        owner_bin = base / "owner-bin"
        repo.mkdir(parents=True)
        owner_bin.mkdir()

        _write_owner_entrypoint(
            owner_bin / "hunter-codeops-switcher",
            codeops_root,
            "hunter_codeops.code_ops_switcher_cli",
        )
        _write_owner_entrypoint(owner_bin / "sergeant", sergeant_root, "main_review.cli")
        _init_repository(repo)

        port = _reserve_port()
        base_url = f"http://127.0.0.1:{port}"
        proof_path = os.pathsep.join([str(owner_bin), os.environ.get("PATH", "")])
        daemon_env = os.environ.copy()
        daemon_env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(state),
                "ORIGINS_LOCAL_TOKEN": TOKEN,
                "ORIGINS_WORKSPACE_ROOTS": str(workspaces),
                "PATH": proof_path,
            }
        )

        daemon = subprocess.Popen(
            [str(binary)],
            env=daemon_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            _wait_for_health(base_url, daemon)
            workspace = _request_json(
                base_url + "/v1/workspaces",
                token=TOKEN,
                method="POST",
                payload={
                    "name": "Phase 4 live owner proof",
                    "authority_refs": [],
                    "session_refs": [],
                },
                expected_status=201,
            )
            repository = _request_json(
                base_url + "/v1/repositories/inspect",
                token=TOKEN,
                method="POST",
                payload={"workspace_id": workspace["workspace_id"], "path": str(repo)},
            )
            repository_id = str(repository["repository_id"])

            # The production constructor is the only path that may emit live_owner proof scope.
            previous_path = os.environ.get("PATH")
            os.environ["PATH"] = proof_path
            try:
                client = OriginsClient(base_url, TOKEN)
                receipt = LiveEngineeringMount.production(client).run(
                    repository_id,
                    config=str(config),
                    files=("tracked.py",),
                    review_mode="pull_request",
                )
            finally:
                if previous_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = previous_path

            assert receipt.proof_scope == "live_owner"
            assert receipt.live_engineering_proven is True
            assert receipt.mount_status == "proven"
            assert receipt.project_verdict in CANONICAL_PROJECT_VERDICTS
            assert receipt.route_session_id
            assert receipt.sergeant_command_session_id
            assert receipt.sergeant_review_session_id
            assert len(receipt.receipt_sha256) == 64
            assert all(surface["status"] == "compatible" for surface in receipt.doctor_surfaces)

            route_output = client.get_session_output(receipt.route_session_id)
            route_payload = json.loads(str(route_output.get("stdout", "")))
            decision = route_payload.get("decision")
            if not isinstance(decision, dict):
                raise AssertionError("CodeOps route did not return an auditable decision")
            selected_provider = decision.get("provider_id")
            if not isinstance(selected_provider, str) or not selected_provider:
                raise AssertionError("CodeOps route did not identify the selected provider")

            config_payload = json.loads(config.read_text(encoding="utf-8"))
            providers = config_payload.get("providers")
            if not isinstance(providers, list):
                raise AssertionError("CodeOps owner config providers are unavailable")
            enabled_provider_ids = {
                str(provider.get("id"))
                for provider in providers
                if isinstance(provider, dict) and provider.get("enabled", True)
            }
            if len(enabled_provider_ids) < 2:
                raise AssertionError("Phase 4 requires at least two enabled provider routes")
            if selected_provider not in enabled_provider_ids:
                raise AssertionError("selected CodeOps provider is outside the owner registry")

            print(
                json.dumps(
                    {
                        "proof": "PHASE4_LIVE_OWNER_STACK_OK",
                        "proof_scope": receipt.proof_scope,
                        "mount_status": receipt.mount_status,
                        "live_engineering_proven": receipt.live_engineering_proven,
                        "project_verdict": receipt.project_verdict,
                        "selected_provider": selected_provider,
                        "enabled_provider_count": len(enabled_provider_ids),
                        "operation_id": receipt.operation_id,
                        "repository_id": receipt.repository_id,
                        "route_session_id": receipt.route_session_id,
                        "sergeant_command_session_id": receipt.sergeant_command_session_id,
                        "sergeant_review_session_id": receipt.sergeant_review_session_id,
                        "review_sha256": receipt.review_sha256,
                        "receipt_sha256": receipt.receipt_sha256,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        finally:
            stdout, stderr = _stop(daemon)
            combined = stdout + "\n" + stderr
            if TOKEN in combined:
                raise AssertionError("Origins local bearer token leaked into daemon output")

    return 0


def _require_owner_root(path: Path, label: str, package_dir: str) -> Path:
    root = path.resolve()
    if not root.is_dir() or not (root / package_dir).is_dir():
        raise AssertionError(f"{label} owner checkout is invalid: {root}")
    return root


def _write_owner_entrypoint(path: Path, owner_root: Path, module: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.path.insert(0, {str(owner_root)!r})\n"
        f"from {module} import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _init_repository(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Origins Proof"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "origins-proof@example.invalid"],
        check=True,
    )
    (repo / "tracked.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "tracked.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial live-owner proof fixture"],
        check=True,
        capture_output=True,
    )


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"originsd exited before health: {process.returncode}; stdout={stdout}; stderr={stderr}"
            )
        try:
            _request_json(base_url + "/v1/health")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"originsd health did not become ready: {last_error}")


def _stop(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            return process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.communicate(timeout=10)


def _request_json(
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
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("Origins endpoint returned a non-object")
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
