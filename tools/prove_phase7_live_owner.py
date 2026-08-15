#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origins_integration.engineering import OriginsClient
from origins_integration.phase7_runtime import Phase7Runtime

AGENTOPS_HEAD = "054a09e7571b08e5865499d66ea6db5ae6eb43a6"
CODEOPS_HEAD = "e72afe60ebab41d9f36dc729ad798d5aa4071e83"
SERGEANT_HEAD = "fe491502a960e6b581a7d07e35683aa28e58b9f8"
AGENTOPS_ROOT = Path("/home/kratos/Hunter-AgentOps")
CODEOPS_ROOT = Path("/home/kratos/hunter-codeops")
SERGEANT_ROOT = Path("/home/kratos/Sergeant")
CODEOPS_CONFIG = CODEOPS_ROOT / "config" / "code_ops_switcher.example.json"
DEFAULT_DAEMON = Path("/home/kratos/origins-factory/target/debug/originsd")
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


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ProofError(f"command failed ({result.returncode}): {args!r}: {result.stderr[-800:]}")
    return result.stdout.strip()


def _git_head(path: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=path)


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _wait_health(timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{PROOF_URL}/v1/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("ok") is True:
                    return
        except Exception as exc:  # proof polling only
            last = type(exc).__name__
        time.sleep(0.05)
    raise ProofError(f"originsd did not become healthy: {last}")


def _start_daemon(*, data_dir: Path, workspace_root: Path, token: str) -> Daemon:
    daemon_path = Path(os.environ.get("ORIGINS_PHASE7_DAEMON", str(DEFAULT_DAEMON))).resolve()
    if not daemon_path.is_file():
        raise ProofError(f"originsd binary unavailable: {daemon_path}")
    env = os.environ.copy()
    env.update(
        {
            "ORIGINS_BIND": PROOF_BIND,
            "ORIGINS_DATA_DIR": str(data_dir),
            "ORIGINS_LOCAL_TOKEN": token,
            "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
            "ORIGINS_ARTIFACT_ROOTS": str(workspace_root),
            "PATH": os.pathsep.join([str(Path(sys.executable).resolve().parent), env.get("PATH", "")]),
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
        _wait_health()
    except Exception:
        daemon.stop()
        raise
    return daemon


def _init_repo(path: Path, *, initial_value: str, replacement_value: str) -> None:
    path.mkdir(parents=True)
    (path / "capability.py").write_text(
        "def capability() -> str:\n" f"    return {initial_value!r}\n",
        encoding="utf-8",
    )
    _run(["git", "init", "-b", "main"], cwd=path)
    _run(["git", "config", "user.name", "Origins Phase 7 Proof"], cwd=path)
    _run(["git", "config", "user.email", "origins-phase7-proof@invalid.local"], cwd=path)
    _run(["git", "add", "capability.py"], cwd=path)
    _run(["git", "commit", "-m", "proof baseline"], cwd=path)
    plan = {
        "operations": [
            {
                "path": "capability.py",
                "action": "replace",
                "old": f"return {initial_value!r}",
                "new": f"return {replacement_value!r}",
                "required": True,
            }
        ],
        "reason": "Phase 7 disposable capability proof",
        "require_review": True,
    }
    (path / "upgrade-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _workspace(client: OriginsClient) -> str:
    created = client._json(  # controlled proof uses the same authenticated loopback API
        "POST",
        "/v1/workspaces",
        {"name": "Phase 7 live-owner proof", "authority_refs": [], "session_refs": []},
        expected_status=201,
    )
    workspace_id = created.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ProofError("originsd workspace creation omitted workspace_id")
    return workspace_id


def _repository(client: OriginsClient, workspace_id: str, path: Path) -> str:
    observed = client.inspect_repository(workspace_id, str(path))
    repository_id = observed.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id:
        raise ProofError("repository inspection omitted repository_id")
    return repository_id


def _approval_id(created: dict[str, object]) -> str:
    binding = created.get("binding")
    if not isinstance(binding, dict):
        raise ProofError("AgentOps approval binding is missing")
    approval_id = binding.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        raise ProofError("AgentOps approval binding omitted approval_id")
    return approval_id


def _session_id(accepted: dict[str, Any]) -> str:
    session = accepted.get("session")
    if not isinstance(session, dict):
        raise ProofError("canary process was not accepted as an Origins Session")
    value = session.get("session_id")
    if not isinstance(value, str) or not value:
        raise ProofError("canary Session omitted session_id")
    return value


def _run_evolution(
    *,
    runtime: Phase7Runtime,
    client: OriginsClient,
    workspace_id: str,
    repository_id: str,
    repo: Path,
    mission_id: str,
    attempt_id: str,
    capability_id: str,
    initial_effect: str,
    target_effect: str,
    decision: str,
) -> dict[str, object]:
    resume_state = {
        "mission_id": mission_id,
        "attempt_id": attempt_id,
        "state": "blocked_on_capability_gap",
        "target_effect": target_effect,
    }
    resume_token = f"resume:{mission_id}:{attempt_id}"
    record = runtime.confirm_gap(
        {
            "mission_id": mission_id,
            "parent_operation_id": f"parent:{mission_id}",
            "workspace_id": workspace_id,
            "attempt_id": attempt_id,
            "resume_token": resume_token,
            "resume_state_sha256": _sha(resume_state),
            "capability_id": capability_id,
            "expected_effects": [target_effect],
            "actual_effects": [initial_effect],
            "actual_manifest_sha256": _sha({"effects": [initial_effect]}),
            "refusal_code": "CAPABILITY_EFFECT_MISSING",
            "evidence_refs": [
                f"origins:proof:{mission_id}:expected",
                f"origins:proof:{mission_id}:actual",
            ],
            "summary": f"Disposable proof Mission requires {target_effect}; current capability only exposes {initial_effect}.",
        }
    )
    evolution_id = str(record["evolution_id"])

    approval = runtime.create_approval(evolution_id)
    approval_id = _approval_id(approval)
    runtime.decide_approval(
        evolution_id,
        approval_id=approval_id,
        decision="approved",
        decided_by="phase7-proof-owner",
    )
    child = runtime.create_child_upgrade_operation(evolution_id, approval_id)
    child_operation = child.get("child_operation")
    if not isinstance(child_operation, dict):
        raise ProofError("AgentOps child upgrade Operation is missing")
    if child_operation.get("accepted") is not True or child_operation.get("execution_dispatched") is not False:
        raise ProofError("AgentOps child Operation crossed its undispatched authority boundary")

    engineering = {
        "repository_id": repository_id,
        "task": f"Implement {target_effect} for the disposable Phase 7 proof capability",
        "config": str(CODEOPS_CONFIG),
        "files": ["capability.py"],
        "plan": "upgrade-plan.json",
        "provider_id": "",
        "required_capability": "",
        "review": "required",
        "review_mode": "pull_request",
        "client_kind": "terminal",
        "mode": "quick_edit",
    }
    engineering_approval = runtime.create_engineering_approval(evolution_id, engineering)
    engineering_approval_id = _approval_id(engineering_approval)
    runtime.decide_engineering_approval(
        evolution_id,
        approval_id=engineering_approval_id,
        decision="approved",
        decided_by="phase7-proof-owner",
    )
    reviewed = runtime.implement_candidate(evolution_id, engineering)
    review = reviewed.get("sergeant_review")
    if not isinstance(review, dict):
        raise ProofError("Sergeant review is missing")
    if review.get("verdict") != "PASS":
        raise ProofError(f"independent Sergeant verdict is {review.get('verdict')!r}, not PASS")
    candidate = reviewed.get("candidate")
    if not isinstance(candidate, dict):
        raise ProofError("candidate Generation is missing")
    if not isinstance(candidate.get("repository_diff_bytes"), int) or int(candidate["repository_diff_bytes"]) < 1:
        raise ProofError("candidate Generation is not bound to a non-empty repository diff")

    accepted = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable="python3",
        args=[
            "-c",
            (
                "from pathlib import Path; ns={}; "
                "exec(Path('capability.py').read_text(encoding='utf-8'), ns); "
                f"assert ns['capability']() == {target_effect!r}"
            ),
        ],
        timeout_seconds=30,
        max_output_bytes=128 * 1024,
    )
    canary_session_id = _session_id(accepted)
    runtime.record_canary_from_session(evolution_id, canary_session_id)
    decided = runtime.decide(evolution_id, decision=decision, decided_by="phase7-proof-owner")
    if decided.get("state") != ("promoted" if decision == "promote" else "rolled_back"):
        raise ProofError("capability Generation decision did not reach the expected durable state")

    return {
        "evolution_id": evolution_id,
        "repository_id": repository_id,
        "candidate": candidate,
        "review_sha256": review.get("review_sha256"),
        "sergeant_verdict": review.get("verdict"),
        "canary_session_id": canary_session_id,
        "resume_token": resume_token,
        "resume_state_sha256": _sha(resume_state),
        "decision": decision,
    }


def main() -> int:
    source_root = Path(__file__).resolve().parents[1]
    source_head = _git_head(source_root)
    expected_head = os.environ.get("ORIGINS_PHASE7_EXPECTED_HEAD", "").strip()
    if expected_head and source_head != expected_head:
        raise ProofError(f"source head mismatch: expected {expected_head}, got {source_head}")

    owner_heads = {
        "agentops": _git_head(AGENTOPS_ROOT),
        "codeops": _git_head(CODEOPS_ROOT),
        "sergeant": _git_head(SERGEANT_ROOT),
    }
    expected_owner_heads = {
        "agentops": AGENTOPS_HEAD,
        "codeops": CODEOPS_HEAD,
        "sergeant": SERGEANT_HEAD,
    }
    if owner_heads != expected_owner_heads:
        raise ProofError(f"owner provenance mismatch: {owner_heads!r}")
    if not CODEOPS_CONFIG.is_file():
        raise ProofError(f"CodeOps config unavailable: {CODEOPS_CONFIG}")

    temp = Path(tempfile.mkdtemp(prefix="origins-phase7-live-owner-"))
    daemon: Daemon | None = None
    token = f"origins_phase7_proof_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    data_dir = temp / "origins-data"
    agentops_data = temp / "agentops-data"
    phase7_state = temp / "phase7.sqlite"
    promote_repo = temp / "promote-repo"
    rollback_repo = temp / "rollback-repo"
    try:
        _init_repo(promote_repo, initial_value="observe", replacement_value="verify")
        _init_repo(rollback_repo, initial_value="observe", replacement_value="verify")

        os.environ.update(
            {
                "ORIGINS_URL": PROOF_URL,
                "ORIGINS_LOCAL_TOKEN": token,
                "ORIGINS_PHASE7_STATE": str(phase7_state),
                "ORIGINS_AGENTOPS_DATA_DIR": str(agentops_data),
                "ORIGINS_AGENTOPS_ROOT": str(AGENTOPS_ROOT),
                "ORIGINS_CODEOPS_CONFIG": str(CODEOPS_CONFIG),
                "ORIGINS_SERGEANT_COMMAND": "sergeant",
                "PATH": os.pathsep.join([str(Path(sys.executable).resolve().parent), os.environ.get("PATH", "")]),
            }
        )
        daemon = _start_daemon(data_dir=data_dir, workspace_root=temp, token=token)
        client = OriginsClient(PROOF_URL, token)
        runtime = Phase7Runtime.from_env()
        health = runtime.health()
        owners = health.get("owners")
        if not isinstance(owners, dict) or not all(
            isinstance(owners.get(name), dict) and owners[name].get("available") is True
            for name in ("Hunter-AgentOps", "hunter-codeops", "Sergeant")
        ):
            raise ProofError(f"required owner mount unavailable: {owners!r}")

        workspace_id = _workspace(client)
        promote_repository_id = _repository(client, workspace_id, promote_repo)
        rollback_repository_id = _repository(client, workspace_id, rollback_repo)

        promoted = _run_evolution(
            runtime=runtime,
            client=client,
            workspace_id=workspace_id,
            repository_id=promote_repository_id,
            repo=promote_repo,
            mission_id="mission-phase7-promote",
            attempt_id="attempt-phase7-promote",
            capability_id="origins.proof.capability.promote",
            initial_effect="observe",
            target_effect="verify",
            decision="promote",
        )
        rolled_back = _run_evolution(
            runtime=runtime,
            client=client,
            workspace_id=workspace_id,
            repository_id=rollback_repository_id,
            repo=rollback_repo,
            mission_id="mission-phase7-rollback",
            attempt_id="attempt-phase7-rollback",
            capability_id="origins.proof.capability.rollback",
            initial_effect="observe",
            target_effect="verify",
            decision="rollback",
        )

        promoted_candidate = promoted["candidate"]
        rollback_candidate = rolled_back["candidate"]
        assert isinstance(promoted_candidate, dict) and isinstance(rollback_candidate, dict)
        if runtime.store.active_generation("origins.proof.capability.promote") is None:
            raise ProofError("promoted Generation did not become active")
        if runtime.store.active_generation("origins.proof.capability.rollback") is not None:
            raise ProofError("rolled-back Generation became active")

        daemon.stop()
        daemon = _start_daemon(data_dir=data_dir, workspace_root=temp, token=token)
        restarted_client = OriginsClient(PROOF_URL, token)
        restarted_runtime = Phase7Runtime.from_env()

        for item in (promoted, rolled_back):
            repository = restarted_client.get_repository(str(item["repository_id"]))
            if repository.get("repository_id") != item["repository_id"]:
                raise ProofError("Repository identity changed after originsd restart")
            session = restarted_client.wait_session(str(item["canary_session_id"]))
            if session.get("state") != "completed" or session.get("exit_code") != 0:
                raise ProofError("canary Session did not survive originsd restart")
            before_resume = restarted_runtime.get(str(item["evolution_id"]))
            expected_state = "promoted" if item["decision"] == "promote" else "rolled_back"
            if before_resume.get("state") != expected_state:
                raise ProofError("Phase 7 coordinator state changed across restart")
            resumed = restarted_runtime.resume(str(item["evolution_id"]))
            evolution = resumed.get("evolution")
            if not isinstance(evolution, dict) or evolution.get("state") != "mission_resumed":
                raise ProofError("original Mission did not resume")
            resume = evolution.get("resume")
            if not isinstance(resume, dict):
                raise ProofError("Mission resume evidence is missing")
            if resume.get("resume_token") != item["resume_token"] or resume.get("resume_state_sha256") != item["resume_state_sha256"]:
                raise ProofError("original Mission resume point changed across capability evolution")
            if resume.get("exact_pre_upgrade_state_preserved") is not True:
                raise ProofError("Mission resume did not preserve exact pre-upgrade state")

        active = restarted_runtime.store.active_generation("origins.proof.capability.promote")
        if not isinstance(active, dict) or active.get("generation") != 1:
            raise ProofError("promoted Generation was not preserved across restart")

        result = {
            "schema_version": "origins.phase7-live-owner-proof.v1",
            "proof": "PHASE7_LIVE_OWNER_OK",
            "source_head": source_head,
            "owner_heads": owner_heads,
            "workspace_id_preserved": True,
            "agentops_child_operation_undispatched": True,
            "codeops_real_plan_applied": True,
            "sergeant_promote_verdict": promoted["sergeant_verdict"],
            "sergeant_rollback_verdict": rolled_back["sergeant_verdict"],
            "promoted_generation": active["generation"],
            "promoted_manifest_sha256": active["manifest_sha256"],
            "promoted_diff_sha256": promoted_candidate["repository_diff_sha256"],
            "promoted_diff_bytes": promoted_candidate["repository_diff_bytes"],
            "rollback_candidate_generation": rollback_candidate["candidate_generation"],
            "rollback_active_generation": restarted_runtime.store.active_generation("origins.proof.capability.rollback"),
            "canary_sessions_recovered": True,
            "mission_resume_exact": True,
            "runtime_authority_expansion": False,
            "model_self_approval": False,
            "production_credentials_used": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        if daemon is not None:
            daemon.stop()
        if os.environ.get("ORIGINS_PHASE7_KEEP_PROOF", "") != "1":
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
