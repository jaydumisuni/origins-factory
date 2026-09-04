from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Mapping

from v1_mission_contract import (
    ACCEPTANCE_STEPS,
    V1MissionError,
    build_handover,
    build_sanitation_receipt,
    digest,
    operation_identity_projection,
    session_identity_projection,
)
from v1_mission_support import (
    _artifact,
    _artifact_projection,
    _audit_sanitation_scope,
    _remove_known_transients,
    _write_json,
)


def _require_equal(label: str, expected: object, actual: object) -> None:
    if expected != actual:
        raise V1MissionError(f"exact {label} recovery mismatch: expected={expected!r} actual={actual!r}")


def run_recovery_phase(
    *,
    client,
    mcp,
    state: Path,
    run_root: Path,
    repo: Path,
    output: Path,
    origins_token: str,
    start_daemon,
    origins_client_type,
    run_id: str,
    expected_head: str,
    authority: Mapping[str, object],
    mission: Mapping[str, object],
):
    steps = dict(mission["steps"])
    sessions = list(mission["sessions"])
    workspace_id = str(mission["workspace_id"])
    repository_id = str(mission["repository_id"])
    operation = mission["operation"]
    if not isinstance(operation, Mapping):
        raise V1MissionError("candidate phase omitted AgentOps Operation")
    operation_id = str(mission["operation_id"])
    loadout = mission["loadout"]
    hunter_evidence = mission["hunter_evidence"]
    failed_sid = str(mission["failed_sid"])
    candidate_artifact_ref = str(mission["candidate_artifact_ref"])
    candidate_path = Path(mission["candidate_path"])
    candidate_artifact_projection = mission["candidate_artifact_projection"]
    pre_restart_workspace = mission["pre_restart_workspace"]
    pre_restart_repository = mission["pre_restart_repository"]
    pre_restart_operation = mission["pre_restart_operation"]
    pre_restart_sessions = mission["pre_restart_sessions"]

    daemon = start_daemon(data_dir=state, workspace_root=run_root, token=origins_token)
    try:
        client = origins_client_type.from_env()
        health = client._json("GET", "/v1/health")
        hunter_status = client._json("GET", "/v1/hunter/status")
        if health.get("ok") is not True or hunter_status.get("configured") is not False:
            raise V1MissionError(
                "Origins restart did not prove standalone mechanical operation with Hunter absent"
            )

        recovered_workspace = client._json(
            "GET", f"/v1/workspaces/{urllib.parse.quote(workspace_id)}"
        )
        recovered_repository = client.get_repository(repository_id)
        recovered_operation_raw = mcp.get_external_operation(operation_id).get("operation")
        if not isinstance(recovered_operation_raw, Mapping):
            raise V1MissionError("AgentOps Operation unavailable after restart")
        recovered_operation = operation_identity_projection(recovered_operation_raw)
        recovered_sessions = {
            sid: session_identity_projection(client.wait_session(sid, timeout=5))
            for sid in sessions
            if sid
        }

        _require_equal("Workspace", pre_restart_workspace, recovered_workspace)
        _require_equal("Repository", pre_restart_repository, recovered_repository)
        _require_equal("AgentOps Operation", pre_restart_operation, recovered_operation)
        _require_equal("Session set", pre_restart_sessions, recovered_sessions)
        recovery_claims = {
            "workspace": True,
            "repository": True,
            "operation": True,
            "sessions": True,
        }

        candidate_artifact_id = candidate_artifact_ref.rsplit(":", 1)[-1]
        recovered_candidate_artifact = client._json(
            "GET", f"/v1/artifacts/{urllib.parse.quote(candidate_artifact_id)}"
        )
        _require_equal(
            "candidate Artifact", candidate_artifact_projection, recovered_candidate_artifact
        )

        steps["origins_restarted_without_hunter"] = {
            "health_ok": True,
            "hunter_configured": False,
        }
        steps["operation_and_sessions_reconnected"] = {
            "operation_id": operation_id,
            "repository_id": repository_id,
            "session_count": len(recovered_sessions),
            "exact_workspace_identity_recovered": True,
            "exact_repository_identity_recovered": True,
            "exact_operation_identity_recovered": True,
            "exact_session_identity_recovered": True,
            "candidate_artifact_recovered": True,
        }

        removed = _remove_known_transients(run_root, repo)
        remaining = _audit_sanitation_scope(
            run_root,
            repo,
            promoted_files=[candidate_path],
            registered_artifacts=[candidate_artifact_projection],
        )
        sanitation = build_sanitation_receipt(
            mission_id=run_id,
            operation_id=operation_id,
            retained=[
                f"agentops:operation:{operation_id}",
                f"origins:workspace:{workspace_id}",
                f"origins:repository:{repository_id}",
                *[f"origins:session:{item}" for item in sessions if item],
            ],
            promoted=[candidate_artifact_ref],
            failed_partial=[f"origins:session:{failed_sid}"],
            removed=removed,
            remaining=remaining,
        )
        if sanitation.get("sanitation_complete") is not True:
            raise V1MissionError(
                f"Mission sanitation remains incomplete: {sanitation.get('temporary_work_remaining')}"
            )
        sanitation_path = output / "sanitation-receipt.json"
        _write_json(sanitation_path, sanitation)
        sanitation_artifact = _artifact(
            client,
            workspace_id=workspace_id,
            path=sanitation_path,
            owner_ref=f"mission:{run_id}:sanitation",
        )
        sanitation_projection = _artifact_projection(sanitation_artifact)
        sanitation_ref = f"origins:artifact:{sanitation_projection.get('artifact_id')}"

        # Sanitation intentionally changes Repository status by removing untracked proof inputs.
        # Refresh after exact recovery so Handover records the truthful final clean projection.
        final_repository = client.refresh_repository(repository_id)
        handover = build_handover(
            mission_id=run_id,
            operation=operation,
            workspace_id=workspace_id,
            repository=final_repository,
            hunter=hunter_evidence,
            capability_loadout=loadout,
            sessions=sessions,
            artifact_refs=[candidate_artifact_ref, sanitation_ref],
            sanitation_ref=sanitation_ref,
            authority=authority,
            recovery=recovery_claims,
        )
        handover_path = output / "mission-handover.json"
        _write_json(handover_path, handover)
        handover_artifact = _artifact(
            client,
            workspace_id=workspace_id,
            path=handover_path,
            owner_ref=f"mission:{run_id}:handover",
        )
        handover_projection = _artifact_projection(handover_artifact)
        handover_ref = f"origins:artifact:{handover_projection.get('artifact_id')}"

        final_remaining = _audit_sanitation_scope(
            run_root,
            repo,
            promoted_files=[candidate_path, sanitation_path, handover_path],
            registered_artifacts=[
                candidate_artifact_projection,
                sanitation_projection,
                handover_projection,
            ],
        )
        if final_remaining:
            raise V1MissionError(
                f"post-handover sanitation audit found temporary files: {final_remaining}"
            )
        steps["accepted_artifacts_promoted"] = {
            "candidate": candidate_artifact_ref,
            "sanitation": sanitation_ref,
            "handover": handover_ref,
        }
        steps["sanitation_and_handover_produced"] = {
            "sanitation_sha256": sanitation["sha256"],
            "handover_sha256": handover["sha256"],
            "handover_ref": handover_ref,
            "final_temporary_paths": [],
        }

        final = mcp.finalize_external_operation(
            {
                "operation_id": operation_id,
                "outcome": "completed",
                "result_ref": handover_ref,
                "evidence_refs": [candidate_artifact_ref, sanitation_ref, handover_ref],
            }
        )
        final_op = final.get("operation")
        if not isinstance(final_op, Mapping) or final_op.get("state") != "completed":
            raise V1MissionError("AgentOps Operation did not finalize completed")

        missing = [step for step in ACCEPTANCE_STEPS if step not in steps]
        if missing:
            raise V1MissionError(f"acceptance evidence missing steps: {missing}")
        result = {
            "schema_version": "origins.v1-repository-mission-proof.v1",
            "proof": "ORIGINS_V1_REPOSITORY_MISSION_OK",
            "run_id": run_id,
            "source_head": expected_head,
            "authority": dict(authority),
            "workspace_id": workspace_id,
            "repository_id": repository_id,
            "operation_id": operation_id,
            "acceptance_steps": steps,
            "artifact_refs": [candidate_artifact_ref, sanitation_ref, handover_ref],
            "standalone_after_hunter_disconnect": True,
            "runtime_authority_expansion": False,
        }
        result["proof_sha256"] = digest(result)
        result_path = output / "v1-mission-proof.json"
        _write_json(result_path, result)
        return daemon, result
    except Exception:
        daemon.stop()
        raise
