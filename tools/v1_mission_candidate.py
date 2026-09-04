from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Mapping

from v1_mission_candidate_review import review_frozen_candidate
from v1_mission_contract import (
    V1MissionError,
    build_candidate_record,
    compile_minimal_loadout,
    file_sha256,
    operation_identity_projection,
    session_identity_projection,
)
from v1_mission_support import (
    _artifact,
    _artifact_projection,
    _expect_session,
    _route_provider,
    _session_id,
    _write_json,
)


def run_candidate_phase(
    *,
    client,
    workspace_fn,
    repository_fn,
    hunter_mount_type,
    agentops_mcp_type,
    persistent_agentops_stores,
    engineering_bridge_type,
    engineering_attempt_request_type,
    workspace_id: str | None,
    repo: Path,
    config: Path,
    provider_ids: tuple[str, str],
    run_id: str,
    expected_head: str,
    authority: Mapping[str, object],
    agentops_data: Path,
    output: Path,
) -> dict[str, object]:
    steps: dict[str, dict[str, object]] = {}
    sessions: list[str] = []

    workspace_id = workspace_id or workspace_fn(client)
    steps["workspace_recovered"] = {"workspace_id": workspace_id}

    hunter_mount = hunter_mount_type.production(client)
    hunter_doctor = hunter_mount.doctor(workspace_id)
    hunter_turn = hunter_mount.send_turn(
        workspace_id,
        (
            f"Origins v1 acceptance Mission {run_id}: identify the repository engineering "
            "objective and preserve this Workspace context."
        ),
    )
    if hunter_turn.live_hunter_proven is not True:
        raise V1MissionError("Hunter turn did not prove live production owner transport")
    hunter_evidence = {
        "session_id": hunter_turn.hunter_session_id,
        "provider": hunter_turn.provider,
        "model": hunter_turn.model,
        "response_sha256": hunter_turn.response_sha256,
        "receipt_sha256": hunter_turn.receipt_sha256,
        "doctor_receipt_sha256": hunter_doctor.receipt_sha256,
        "deployment_service": hunter_doctor.deployment_service,
        "deployment_environment": hunter_doctor.deployment_environment,
        "deployment_git_commit": hunter_doctor.deployment_git_commit,
        "provider_count": hunter_doctor.provider_count,
    }
    steps["hunter_turn_live"] = hunter_evidence

    repository_id = repository_fn(client, workspace_id, repo)
    repository_state = client.get_repository(repository_id)
    steps["canonical_authority_recovered"] = {
        "authority": dict(authority),
        "repository_id": repository_id,
        "head_oid": repository_state.get("head_oid"),
    }

    mcp = agentops_mcp_type.from_env()
    started = mcp.start_external_operation(
        {
            "kind": "origins_v1_repository_mission",
            "title": "Origins v1 standalone repository acceptance Mission",
            "requested_by": "origins-v1-proof",
            "conversation_ref": f"hunter:session:{hunter_turn.hunter_session_id}",
            "workspace_ref": f"origins:workspace:{workspace_id}",
            "correlation_id": run_id,
            "metadata": {
                "mission_id": run_id,
                "repository_id": repository_id,
                "origins_head": expected_head,
            },
        }
    )
    operation = started.get("operation")
    if not isinstance(operation, Mapping) or operation.get("state") != "running":
        raise V1MissionError("AgentOps durable external Operation did not enter running state")
    operation_id = str(operation["operation_id"])
    steps["agentops_operation_durable"] = {
        "operation_id": operation_id,
        "operation_ref": operation.get("operation_ref"),
    }

    capabilities = client._json("GET", "/v1/capabilities").get("capabilities")
    if not isinstance(capabilities, list):
        raise V1MissionError("Origins capability registry unavailable")
    loadout = compile_minimal_loadout(capabilities, provider_ids)
    steps["minimal_capability_loadout_compiled"] = loadout

    quoted_repository = urllib.parse.quote(repository_id)
    files = client._json("GET", f"/v1/repositories/{quoted_repository}/files?path=")
    readme = client._json("GET", f"/v1/repositories/{quoted_repository}/file?path=README.md")
    if not files or not readme:
        raise V1MissionError("repository/editor surface did not return evidence")
    terminal = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable=sys.executable,
        args=[
            "-c",
            (
                "from pathlib import Path; p=Path('capability.py'); assert p.is_file(); "
                "print(p.read_text(encoding='utf-8').strip())"
            ),
        ],
        timeout_seconds=30,
        max_output_bytes=64 * 1024,
    )
    terminal_sid = _session_id(terminal)
    sessions.append(terminal_sid)
    _expect_session(client, terminal_sid, 0)
    steps["repository_editor_terminal_opened"] = {
        "repository_id": repository_id,
        "terminal_session_id": terminal_sid,
    }

    approval_service = persistent_agentops_stores(agentops_data).approval_service()
    approval = approval_service.create_request(
        task_title="Apply exact Origins v1 acceptance candidate",
        mode="engineering_apply",
        gate="review_required",
        reason="Bounded disposable repository candidate for standalone Origins v1 acceptance",
        requested_by="origins-v1-proof",
        target=f"{operation_id}:{repository_id}",
        metadata={
            "mission_id": run_id,
            "operation_id": operation_id,
            "repository_id": repository_id,
            "candidate_only": True,
            "runtime_authority_expansion": False,
        },
    )
    approval_id = approval.approval_id
    approved = approval_service.decide(
        approval_id,
        "approved",
        "origins-v1-proof-owner",
        note="Exact-host v1 acceptance engineering approval",
    )
    if approved.status != "approved":
        raise V1MissionError("AgentOps engineering approval did not reach approved state")

    applied = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable="hunter-codeops-switcher",
        args=[
            "--config", str(config), "apply-plan", "--root", str(repo),
            "--plan", "upgrade-plan.json", "--apply",
        ],
        timeout_seconds=60,
        max_output_bytes=256 * 1024,
    )
    applied_sid = _session_id(applied)
    sessions.append(applied_sid)
    _expect_session(client, applied_sid, 0)
    steps["codeops_invoked"] = {
        "plan_apply_session_id": applied_sid,
        "approval_id": approval_id,
        "operation_id": operation_id,
    }

    provider_sessions = [
        _route_provider(
            client,
            workspace_id=workspace_id,
            repo=repo,
            config=config,
            provider_id=provider_id,
            mission_id=run_id,
        )
        for provider_id in provider_ids
    ]
    sessions.extend(provider_sessions)
    route_operation = mcp.get_external_operation(operation_id).get("operation")
    route_repository = client.get_repository(repository_id)
    if not isinstance(route_operation, Mapping) or route_operation.get("state") != "running":
        raise V1MissionError("AgentOps Operation state changed during multi-provider routing")
    if route_repository.get("repository_id") != repository_id:
        raise V1MissionError("Repository identity changed during multi-provider routing")
    steps["two_providers_routed_without_state_loss"] = {
        "provider_ids": list(provider_ids),
        "session_ids": provider_sessions,
        "operation_id": operation_id,
        "repository_id": repository_id,
    }

    failed = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable=sys.executable,
        args=["-c", "raise SystemExit(23)"],
        timeout_seconds=30,
        max_output_bytes=64 * 1024,
    )
    failed_sid = _session_id(failed)
    sessions.append(failed_sid)
    _expect_session(client, failed_sid, 23)
    steps["failed_attempt_retained"] = {"session_id": failed_sid, "exit_code": 23}

    # Freeze the exact mutable worktree before Sergeant and materialize that freeze as an
    # immutable Origins Artifact. Hosted/static proof cannot manufacture this live Artifact.
    repository_state = client.refresh_repository(repository_id)
    diff = client.get_repository_diff(repository_id, kind="unstaged")
    if diff.get("truncated") is True:
        raise V1MissionError("candidate diff is truncated and cannot be frozen")
    diff_text = str(diff.get("retained_text") or "")
    local_diff_sha = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    if diff.get("sha256") != local_diff_sha:
        raise V1MissionError("Origins Repository diff digest does not match retained candidate bytes")
    if diff.get("complete_bytes") != len(diff_text.encode("utf-8")):
        raise V1MissionError("Origins Repository diff byte count does not match retained candidate bytes")
    candidate_record = build_candidate_record(
        mission_id=run_id,
        operation_id=operation_id,
        repository=repository_state,
        diff_text=diff_text,
        sessions=sessions,
    )
    candidate_path = output / "candidate-freeze.json"
    _write_json(candidate_path, candidate_record)
    candidate_artifact = _artifact(
        client,
        workspace_id=workspace_id,
        path=candidate_path,
        owner_ref=f"mission:{run_id}:candidate-freeze",
    )
    candidate_artifact_projection = _artifact_projection(candidate_artifact)
    if candidate_artifact_projection.get("content_sha256") != file_sha256(candidate_path):
        raise V1MissionError("candidate Artifact content digest does not match frozen candidate file")
    candidate_artifact_ref = f"origins:artifact:{candidate_artifact_projection.get('artifact_id')}"
    steps["candidate_frozen"] = {
        "artifact_ref": candidate_artifact_ref,
        "freeze_sha256": candidate_record["sha256"],
        "diff_sha256": candidate_record["diff_sha256"],
        "repository_revision": candidate_record["repository_revision_at_freeze"],
    }

    attempt, post_review_repository = review_frozen_candidate(
        client=client,
        bridge_type=engineering_bridge_type,
        request_type=engineering_attempt_request_type,
        operation_id=operation_id,
        repository_id=repository_id,
        config=config,
        candidate_record=candidate_record,
        candidate_artifact_ref=candidate_artifact_ref,
        sessions=sessions,
    )
    steps["sergeant_reviewed"] = {
        "verdict": attempt.verdict,
        "review_sha256": attempt.review_sha256,
        "session_id": attempt.sergeant_review.session_id,
        "candidate_artifact_ref": candidate_artifact_ref,
        "candidate_sha256": candidate_record["sha256"],
    }
    steps["bounded_correction_processed_if_needed"] = {
        "required": False,
        "verdict": attempt.verdict,
    }

    # Freeze canonical recovery projections only after every review Session is terminal.
    pre_restart_workspace = client._json(
        "GET", f"/v1/workspaces/{urllib.parse.quote(workspace_id)}"
    )
    pre_restart_repository = client.get_repository(repository_id)
    if pre_restart_repository != post_review_repository:
        raise V1MissionError("Repository projection changed between post-review verification and restart freeze")
    pre_restart_operation_raw = mcp.get_external_operation(operation_id).get("operation")
    if not isinstance(pre_restart_operation_raw, Mapping):
        raise V1MissionError("AgentOps Operation unavailable before restart")
    pre_restart_operation = operation_identity_projection(pre_restart_operation_raw)
    pre_restart_sessions = {
        sid: session_identity_projection(client.wait_session(sid, timeout=5))
        for sid in sessions
        if sid
    }

    return {
        "steps": steps,
        "sessions": sessions,
        "workspace_id": workspace_id,
        "repository_id": repository_id,
        "operation": dict(operation),
        "operation_id": operation_id,
        "mcp": mcp,
        "loadout": loadout,
        "hunter_evidence": hunter_evidence,
        "failed_sid": failed_sid,
        "candidate_record": candidate_record,
        "candidate_path": candidate_path,
        "candidate_artifact_ref": candidate_artifact_ref,
        "candidate_artifact_projection": dict(candidate_artifact_projection),
        "pre_restart_workspace": pre_restart_workspace,
        "pre_restart_repository": pre_restart_repository,
        "pre_restart_operation": pre_restart_operation,
        "pre_restart_sessions": pre_restart_sessions,
    }
