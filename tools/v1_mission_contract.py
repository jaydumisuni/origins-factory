from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

AGENTOPS_HEAD = "0eeb69027aec9d70303e724129ebf5585f373ca1"
CODEOPS_HEAD = "348f133cb72ab6d18a7959d4a954158f7b881068"
SERGEANT_HEAD = "22879a8c47df379d19fb8537c79b745750df4077"
REQUIRED_CAPABILITIES = (
    "origins.workspace.persistence",
    "origins.journal.verify",
    "origins.process.run",
)
ACCEPTANCE_STEPS = (
    "workspace_recovered",
    "hunter_turn_live",
    "canonical_authority_recovered",
    "agentops_operation_durable",
    "minimal_capability_loadout_compiled",
    "repository_editor_terminal_opened",
    "codeops_invoked",
    "two_providers_routed_without_state_loss",
    "failed_attempt_retained",
    "candidate_frozen",
    "sergeant_reviewed",
    "bounded_correction_processed_if_needed",
    "origins_restarted_without_hunter",
    "operation_and_sessions_reconnected",
    "accepted_artifacts_promoted",
    "sanitation_and_handover_produced",
)
REPOSITORY_STABLE_FIELDS = (
    "repository_id",
    "workspace_id",
    "worktree_root",
    "git_dir",
    "common_dir",
    "head_oid",
    "head_ref",
    "branch",
    "detached",
    "unborn",
    "staged_count",
    "unstaged_count",
    "untracked_count",
    "status_sha256",
)
OPERATION_IDENTITY_FIELDS = (
    "operation_id",
    "operation_ref",
    "kind",
    "title",
    "requested_by",
    "conversation_ref",
    "workspace_ref",
    "correlation_id",
    "state",
    "metadata",
    "created_at",
)


class V1MissionError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repository_stable_projection(repository: Mapping[str, object]) -> dict[str, object]:
    return {field: repository.get(field) for field in REPOSITORY_STABLE_FIELDS}


def operation_identity_projection(operation: Mapping[str, object]) -> dict[str, object]:
    return {field: operation.get(field) for field in OPERATION_IDENTITY_FIELDS}


def session_identity_projection(session: Mapping[str, object]) -> dict[str, object]:
    # A terminal Session is immutable. Exclude no persisted identity fields except any
    # future presentation-only keys that are not part of the durable projection.
    fields = (
        "contract_type", "schema_version", "session_id", "workspace_id", "command_id",
        "capability_id", "kind", "workspace_root", "state", "pid", "started_at",
        "updated_at", "ended_at", "exit_code", "timed_out", "stdout_bytes",
        "stderr_bytes", "stdout_sha256", "stderr_sha256", "output_truncated",
    )
    return {field: session.get(field) for field in fields}


def require_two_enabled_providers(config: Mapping[str, object]) -> tuple[str, str]:
    providers = config.get("providers")
    if not isinstance(providers, list):
        raise V1MissionError("CodeOps owner config providers are unavailable")
    enabled: list[str] = []
    for item in providers:
        if not isinstance(item, Mapping) or item.get("enabled", True) is not True:
            continue
        provider_id = str(item.get("id") or "").strip()
        if provider_id and provider_id not in enabled:
            enabled.append(provider_id)
    if len(enabled) < 2:
        raise V1MissionError("v1 acceptance requires at least two enabled CodeOps provider routes")
    return enabled[0], enabled[1]


def compile_minimal_loadout(
    capabilities: Iterable[Mapping[str, object]], provider_ids: tuple[str, str]
) -> dict[str, object]:
    by_id = {str(item.get("capability_id") or ""): dict(item) for item in capabilities}
    missing = [item for item in REQUIRED_CAPABILITIES if item not in by_id]
    if missing:
        raise V1MissionError(f"required standalone capabilities unavailable: {missing}")
    selected = [by_id[item] for item in REQUIRED_CAPABILITIES]
    if any(item.get("model_dependency") != "none" for item in selected):
        raise V1MissionError("standalone mechanical capability loadout gained a model dependency")
    body = {
        "schema_version": "origins.v1-capability-loadout.v1",
        "capabilities": [
            {
                "capability_id": item["capability_id"],
                "version": item.get("version"),
                "owner": item.get("owner"),
                "effects": item.get("effects"),
                "model_dependency": item.get("model_dependency"),
            }
            for item in selected
        ],
        "codeops_provider_ids": list(provider_ids),
        "runtime_authority_expansion": False,
    }
    return {**body, "sha256": digest(body)}


def build_candidate_record(
    *,
    mission_id: str,
    operation_id: str,
    repository: Mapping[str, object],
    diff_text: str,
    sessions: Iterable[str],
) -> dict[str, object]:
    diff_raw = diff_text.encode("utf-8")
    if not diff_raw:
        raise V1MissionError("candidate freeze requires a non-empty repository diff")
    body = {
        "schema_version": "origins.v1-candidate-freeze.v2",
        "mission_id": mission_id,
        "operation_id": operation_id,
        "repository_stable": repository_stable_projection(repository),
        "repository_revision_at_freeze": repository.get("revision"),
        "diff_sha256": hashlib.sha256(diff_raw).hexdigest(),
        "diff_bytes": len(diff_raw),
        "diff_text": diff_text,
        "session_refs": sorted(set(str(item) for item in sessions if str(item))),
        "candidate_only": True,
        "runtime_authority_expansion": False,
    }
    return {**body, "sha256": digest(body)}


def build_sanitation_receipt(
    *,
    mission_id: str,
    operation_id: str,
    retained: Iterable[str],
    promoted: Iterable[str],
    failed_partial: Iterable[str],
    removed: Iterable[str],
    remaining: Iterable[str],
) -> dict[str, object]:
    remaining_items = sorted(set(str(item) for item in remaining if str(item)))
    body = {
        "schema_version": "origins.sanitation-receipt.v1",
        "mission_id": mission_id,
        "operation_id": operation_id,
        "retained_canonical_records": sorted(set(str(item) for item in retained if str(item))),
        "promoted_artifact_refs": sorted(set(str(item) for item in promoted if str(item))),
        "failed_partial_evidence_retained": sorted(set(str(item) for item in failed_partial if str(item))),
        "temporary_work_removed": sorted(set(str(item) for item in removed if str(item))),
        "temporary_work_remaining": remaining_items,
        "sanitation_complete": not remaining_items,
    }
    return {**body, "sha256": digest(body)}


def build_handover(
    *,
    mission_id: str,
    operation: Mapping[str, object],
    workspace_id: str,
    repository: Mapping[str, object],
    hunter: Mapping[str, object],
    capability_loadout: Mapping[str, object],
    sessions: Iterable[str],
    artifact_refs: Iterable[str],
    sanitation_ref: str,
    authority: Mapping[str, object],
    recovery: Mapping[str, bool],
) -> dict[str, object]:
    body = {
        "schema_version": "origins.mission-handover.v1",
        "mission_id": mission_id,
        "purpose": "Prove Origins v1 standalone repository Mission end to end",
        "accepted_intent": (
            "Origins remains useful before Prime OS/Ptah integration; optional intelligence/owner "
            "mounts must not become mechanical runtime prerequisites."
        ),
        "agentops_operation_id": operation.get("operation_id"),
        "agentops_operation_ref": operation.get("operation_ref"),
        "workspace_id": workspace_id,
        "repository": {
            "repository_id": repository.get("repository_id"),
            "worktree_root": repository.get("worktree_root"),
            "branch": repository.get("branch"),
            "head_oid": repository.get("head_oid"),
            "revision": repository.get("revision"),
            "status_sha256": repository.get("status_sha256"),
        },
        "hunter": dict(hunter),
        "capability_loadout_ref": f"sha256:{capability_loadout.get('sha256')}",
        "session_refs": sorted(set(str(item) for item in sessions if str(item))),
        "artifact_refs": sorted(set(str(item) for item in artifact_refs if str(item))),
        "sanitation_ref": sanitation_ref,
        "authority": dict(authority),
        "resume": {
            "origins_restarted": True,
            "hunter_required_for_mechanical_resume": False,
            "exact_workspace_identity_recovered": bool(recovery.get("workspace")),
            "exact_repository_identity_recovered": bool(recovery.get("repository")),
            "exact_operation_identity_recovered": bool(recovery.get("operation")),
            "exact_session_identity_recovered": bool(recovery.get("sessions")),
        },
        "nonclaims": {
            "prime_installed": False,
            "ptah_integrated": False,
            "device_write_execution": False,
            "public_distribution": False,
            "code_signed": False,
        },
    }
    return {**body, "sha256": digest(body)}
