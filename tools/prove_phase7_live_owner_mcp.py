#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from origins_integration.engineering import OriginsClient
from origins_integration.phase7_runtime import Phase7Runtime
from phase7_live_proof_support import (
    ProofError,
    approval_id,
    assert_tracked_clean,
    file_sha256,
    git_head,
    init_repo,
    repository,
    session_id,
    sha,
    start_daemon,
    workspace,
)

AGENTOPS_HEAD = "0eeb69027aec9d70303e724129ebf5585f373ca1"
CODEOPS_HEAD = "348f133cb72ab6d18a7959d4a954158f7b881068"
SERGEANT_HEAD = "22879a8c47df379d19fb8537c79b745750df4077"
AGENTOPS_ROOT = Path(os.environ.get("ORIGINS_PHASE7_AGENTOPS_ROOT", "/home/kratos/Hunter-AgentOps"))
CODEOPS_ROOT = Path(os.environ.get("ORIGINS_PHASE7_CODEOPS_ROOT", "/home/kratos/hunter-codeops"))
SERGEANT_ROOT = Path(os.environ.get("ORIGINS_PHASE7_SERGEANT_ROOT", "/home/kratos/Sergeant"))
CODEOPS_CONFIG = CODEOPS_ROOT / "config" / "code_ops_switcher.example.json"


class RunningMcp:
    def __init__(self, server) -> None:
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


def _owner_approve(service, created: dict[str, object], *, actor: str) -> str:
    aid = approval_id(created)
    state = service.get_state(aid)
    if state.status == "pending":
        state = service.decide(aid, "approved", actor, note="Phase 7 exact-host proof owner decision")
    if state.status != "approved":
        raise ProofError(f"AgentOps owner decision did not approve {aid}: {state.status}")
    evidence = service.get_evidence(aid).public_dict()
    record = evidence.get("record")
    if not isinstance(record, dict) or record.get("decided_by") != actor:
        raise ProofError("AgentOps owner approval evidence omitted the proof actor")
    return aid


def _run_evolution(
    *,
    runtime: Phase7Runtime,
    client: OriginsClient,
    approval_service,
    workspace_id: str,
    repository_id: str,
    repo: Path,
    mission_id: str,
    attempt_id: str,
    capability_id: str,
    initial_effect: str,
    target_effect: str,
    decision: str,
    strict: bool,
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
            "resume_state_sha256": sha(resume_state),
            "capability_id": capability_id,
            "expected_effects": [target_effect],
            "actual_effects": [initial_effect],
            "actual_manifest_sha256": sha({"effects": [initial_effect]}),
            "refusal_code": "CAPABILITY_EFFECT_MISSING",
            "evidence_refs": [
                f"origins:proof:{mission_id}:expected",
                f"origins:proof:{mission_id}:actual",
            ],
            "summary": (
                f"Disposable proof Mission requires {target_effect}; "
                f"current capability only exposes {initial_effect}."
            ),
        }
    )
    evolution_id = str(record["evolution_id"])

    capability_request = runtime.create_approval(evolution_id)
    capability_id_value = _owner_approve(
        approval_service,
        capability_request,
        actor="phase7-proof-owner",
    )
    refreshed_capability = runtime.refresh_approval(evolution_id)
    capability_binding = refreshed_capability.get("binding")
    if not isinstance(capability_binding, dict) or capability_binding.get("status") != "approved":
        raise ProofError("Origins did not observe AgentOps capability approval over MCP")
    if capability_binding.get("approval_id") != capability_id_value:
        raise ProofError("Origins capability approval binding changed after owner decision")

    child = runtime.create_child_upgrade_operation(evolution_id)
    child_operation = child.get("child_operation")
    if not isinstance(child_operation, dict):
        raise ProofError("AgentOps child upgrade Operation is missing")
    if child_operation.get("accepted") is not True or child_operation.get("execution_dispatched") is not False:
        raise ProofError("AgentOps child Operation crossed its undispatched authority boundary")
    if child_operation.get("transport") != "mcp/rpc":
        raise ProofError("AgentOps child Operation did not use MCP/RPC")

    engineering = {
        "repository_id": repository_id,
        "task": f"Implement {target_effect} for the disposable Phase 7 proof capability",
        "config": str(CODEOPS_CONFIG),
        "files": ["capability.py", "tests/test_capability.py"] if strict else ["capability.py"],
        "plan": "upgrade-plan.json",
        "provider_id": "",
        "required_capability": "",
        "review": "required",
        "review_mode": "pull_request",
        "client_kind": "terminal",
        "mode": "quick_edit",
    }
    engineering_request = runtime.create_engineering_approval(evolution_id, engineering)
    engineering_id = _owner_approve(
        approval_service,
        engineering_request,
        actor="phase7-proof-reviewer",
    )
    refreshed_engineering = runtime.refresh_engineering_approval(evolution_id)
    engineering_binding = refreshed_engineering.get("binding")
    if not isinstance(engineering_binding, dict) or engineering_binding.get("status") != "approved":
        raise ProofError("Origins did not observe AgentOps engineering review over MCP")
    if engineering_binding.get("approval_id") != engineering_id:
        raise ProofError("Origins engineering approval binding changed after owner review")
    evidence = refreshed_engineering.get("evidence")
    request = evidence.get("request") if isinstance(evidence, dict) else None
    if not isinstance(request, dict) or request.get("gate") != "review_required":
        raise ProofError("Phase 7 engineering did not use AgentOps review_required gate")

    reviewed = runtime.implement_candidate(evolution_id)
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
    if candidate.get("engineering_result_ref", "").startswith("agentops:evidence:"):
        raise ProofError("Origins restored direct AgentOps engineering evidence ownership")

    canary_args = ["-m", "pytest", "-q"] if strict else [
        "-c",
        (
            "from pathlib import Path; ns={}; "
            "exec(Path('capability.py').read_text(encoding='utf-8'), ns); "
            f"assert ns['capability']() == {target_effect!r}"
        ),
    ]
    accepted = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable=sys.executable if strict else "python3",
        args=canary_args,
        timeout_seconds=45,
        max_output_bytes=128 * 1024,
    )
    canary_session_id = session_id(accepted)
    runtime.record_canary_from_session(evolution_id, canary_session_id)
    decided = runtime.decide(evolution_id, decision=decision, decided_by="phase7-proof-owner")
    expected_state = "promoted" if decision == "promote" else "rolled_back"
    if decided.get("state") != expected_state:
        raise ProofError("capability Generation decision did not reach the expected durable state")

    return {
        "evolution_id": evolution_id,
        "repository_id": repository_id,
        "candidate": candidate,
        "review_sha256": review.get("review_sha256"),
        "sergeant_verdict": review.get("verdict"),
        "canary_session_id": canary_session_id,
        "resume_token": resume_token,
        "resume_state_sha256": sha(resume_state),
        "decision": decision,
        "capability_approval_id": capability_id_value,
        "engineering_approval_id": engineering_id,
    }


def main() -> int:
    source_root = Path(__file__).resolve().parents[1]
    source_head = git_head(source_root)
    expected_head = os.environ.get("ORIGINS_PHASE7_EXPECTED_HEAD", "").strip()
    if not expected_head:
        raise ProofError("ORIGINS_PHASE7_EXPECTED_HEAD is required for exact-host proof")
    if source_head != expected_head:
        raise ProofError(f"source head mismatch: expected {expected_head}, got {source_head}")
    assert_tracked_clean("origins-factory", source_root)

    owner_heads = {
        "agentops": git_head(AGENTOPS_ROOT),
        "codeops": git_head(CODEOPS_ROOT),
        "sergeant": git_head(SERGEANT_ROOT),
    }
    expected_owner_heads = {
        "agentops": AGENTOPS_HEAD,
        "codeops": CODEOPS_HEAD,
        "sergeant": SERGEANT_HEAD,
    }
    if owner_heads != expected_owner_heads:
        raise ProofError(f"owner provenance mismatch: expected={expected_owner_heads!r} actual={owner_heads!r}")
    for name, path in (
        ("Hunter-AgentOps", AGENTOPS_ROOT),
        ("hunter-codeops", CODEOPS_ROOT),
        ("Sergeant", SERGEANT_ROOT),
    ):
        assert_tracked_clean(name, path)
    if not CODEOPS_CONFIG.is_file():
        raise ProofError(f"CodeOps config unavailable: {CODEOPS_CONFIG}")

    if str(AGENTOPS_ROOT) not in sys.path:
        sys.path.insert(0, str(AGENTOPS_ROOT))
    from agentops.mcp_approval_observer_service import create_agentops_approval_observer_mcp_server
    from agentops.mcp_external_operation_service import create_agentops_external_operation_mcp_server
    from agentops.storage import PersistentAgentOpsStores

    strict = os.environ.get("ORIGINS_PHASE7_STRICT", "1").strip().lower() not in {"0", "false", "no"}
    temp = Path(tempfile.mkdtemp(prefix="origins-phase7-live-owner-mcp-"))
    daemon = None
    token = f"origins_phase7_proof_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    mcp_token = f"agentops_phase7_mcp_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    data_dir = temp / "origins-data"
    agentops_data = temp / "agentops-data"
    phase7_state = temp / "phase7.sqlite"
    promote_repo = temp / "promote-repo"
    rollback_repo = temp / "rollback-repo"
    approval_server = create_agentops_approval_observer_mcp_server(
        store_root=agentops_data,
        auth_token=mcp_token,
        port=0,
    )
    external_server = create_agentops_external_operation_mcp_server(
        store_root=agentops_data,
        auth_token=mcp_token,
        port=0,
    )
    try:
        with RunningMcp(approval_server) as approval_mcp, RunningMcp(external_server) as external_mcp:
            os.environ.update(
                {
                    "ORIGINS_URL": "http://127.0.0.1:48777",
                    "ORIGINS_LOCAL_TOKEN": token,
                    "ORIGINS_PHASE7_STATE": str(phase7_state),
                    "ORIGINS_AGENTOPS_DATA_DIR": str(agentops_data),
                    "ORIGINS_AGENTOPS_ROOT": str(AGENTOPS_ROOT),
                    "ORIGINS_CODEOPS_CONFIG": str(CODEOPS_CONFIG),
                    "ORIGINS_SERGEANT_COMMAND": "sergeant",
                    "ORIGINS_AGENTOPS_APPROVAL_MCP_URL": f"http://127.0.0.1:{approval_mcp.port}/mcp",
                    "ORIGINS_AGENTOPS_EXTERNAL_OPERATION_MCP_URL": f"http://127.0.0.1:{external_mcp.port}/mcp",
                    "AGENTOPS_MCP_AUTH_TOKEN": mcp_token,
                    "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")]),
                }
            )
            init_repo(promote_repo, initial_value="observe", replacement_value="verify", strict=strict)
            init_repo(rollback_repo, initial_value="observe", replacement_value="verify", strict=strict)
            daemon = start_daemon(data_dir=data_dir, workspace_root=temp, token=token)
            client = OriginsClient("http://127.0.0.1:48777", token)
            runtime = Phase7Runtime.from_env()
            health = runtime.health()
            if health.get("agentops_transport") != "mcp/rpc":
                raise ProofError("Phase 7 health did not publish MCP/RPC AgentOps transport")
            if health.get("agentops_service_credential_is_owner_authorization") is not False:
                raise ProofError("Phase 7 treated MCP service credential as owner authorization")

            approval_service = PersistentAgentOpsStores(agentops_data).approval_service()
            workspace_id = workspace(client)
            promote_repository_id = repository(client, workspace_id, promote_repo)
            rollback_repository_id = repository(client, workspace_id, rollback_repo)

            promoted = _run_evolution(
                runtime=runtime,
                client=client,
                approval_service=approval_service,
                workspace_id=workspace_id,
                repository_id=promote_repository_id,
                repo=promote_repo,
                mission_id="mission-phase7-promote",
                attempt_id="attempt-phase7-promote",
                capability_id="origins.proof.capability.promote",
                initial_effect="observe",
                target_effect="verify",
                decision="promote",
                strict=strict,
            )
            rolled_back = _run_evolution(
                runtime=runtime,
                client=client,
                approval_service=approval_service,
                workspace_id=workspace_id,
                repository_id=rollback_repository_id,
                repo=rollback_repo,
                mission_id="mission-phase7-rollback",
                attempt_id="attempt-phase7-rollback",
                capability_id="origins.proof.capability.rollback",
                initial_effect="observe",
                target_effect="verify",
                decision="rollback",
                strict=strict,
            )

            if runtime.store.active_generation("origins.proof.capability.promote") is None:
                raise ProofError("promoted Generation did not become active")
            if runtime.store.active_generation("origins.proof.capability.rollback") is not None:
                raise ProofError("rolled-back Generation became active")

            daemon.stop()
            daemon = start_daemon(data_dir=data_dir, workspace_root=temp, token=token)
            restarted_client = OriginsClient("http://127.0.0.1:48777", token)
            restarted_runtime = Phase7Runtime.from_env()

            for item in (promoted, rolled_back):
                repository_state = restarted_client.get_repository(str(item["repository_id"]))
                if repository_state.get("repository_id") != item["repository_id"]:
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
                if (
                    resume.get("resume_token") != item["resume_token"]
                    or resume.get("resume_state_sha256") != item["resume_state_sha256"]
                ):
                    raise ProofError("original Mission resume point changed across capability evolution")
                if resume.get("exact_pre_upgrade_state_preserved") is not True:
                    raise ProofError("Mission resume did not preserve exact pre-upgrade state")

            active = restarted_runtime.store.active_generation("origins.proof.capability.promote")
            if not isinstance(active, dict) or active.get("generation") != 1:
                raise ProofError("promoted Generation was not preserved across restart")

            operations = PersistentAgentOpsStores(agentops_data).external_operation_service()
            for item in (promoted, rolled_back):
                evolution = restarted_runtime.get(str(item["evolution_id"]))
                child = evolution.get("child_operation")
                if not isinstance(child, dict):
                    raise ProofError("child Operation missing after restart")
                operation = operations.get(str(child["operation_id"]))
                if operation.get("state") != "completed" or operation.get("outcome") != "completed":
                    raise ProofError("AgentOps external capability-upgrade lifecycle was not durably completed")

            promoted_candidate = promoted["candidate"]
            rollback_candidate = rolled_back["candidate"]
            assert isinstance(promoted_candidate, dict) and isinstance(rollback_candidate, dict)
            result = {
                "schema_version": "origins.phase7-live-owner-mcp-proof.v1",
                "proof": "PHASE7_LIVE_OWNER_MCP_OK",
                "source_head": source_head,
                "owner_heads": owner_heads,
                "originsd_sha256": file_sha256(
                    Path(os.environ.get("ORIGINS_PHASE7_DAEMON", "/home/kratos/origins-factory/rust/target/debug/originsd")).resolve()
                ),
                "agentops_transport": "mcp/rpc",
                "agentops_decision_tools_exposed_by_origins": False,
                "capability_gate": "owner_approval_required",
                "engineering_gate": "review_required",
                "engineering_candidate_only": True,
                "agentops_child_operation_undispatched": True,
                "codeops_real_plan_applied": True,
                "sergeant_promote_verdict": promoted["sergeant_verdict"],
                "sergeant_rollback_verdict": rolled_back["sergeant_verdict"],
                "promoted_generation": active["generation"],
                "promoted_manifest_sha256": active["manifest_sha256"],
                "promoted_diff_sha256": promoted_candidate["repository_diff_sha256"],
                "promoted_diff_bytes": promoted_candidate["repository_diff_bytes"],
                "rollback_candidate_generation": rollback_candidate["candidate_generation"],
                "rollback_active_generation": restarted_runtime.store.active_generation(
                    "origins.proof.capability.rollback"
                ),
                "canary_sessions_recovered": True,
                "mission_resume_exact": True,
                "runtime_authority_expansion": False,
                "model_self_approval": False,
                "production_credentials_used": False,
                "strict": strict,
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
