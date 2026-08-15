from __future__ import annotations

from pathlib import Path

import pytest

from origins_integration.capability_evolution import (
    CapabilityEvolutionError,
    CapabilityEvolutionStore,
    sha256_json,
)

D = "a" * 64
E = "b" * 64
F = "c" * 64


def gap_payload() -> dict[str, object]:
    return {
        "mission_id": "mission-7",
        "parent_operation_id": "agentops-parent-7",
        "workspace_id": "workspace-7",
        "attempt_id": "attempt-7",
        "resume_token": "resume-opaque-7",
        "resume_state_sha256": D,
        "capability_id": "origins.fixture.transform",
        "expected_effects": ["verify"],
        "actual_effects": ["observe"],
        "actual_manifest_sha256": E,
        "refusal_code": "CAPABILITY_EFFECT_UNAVAILABLE",
        "evidence_refs": ["origins:session:s1", "agentops:evidence:e1"],
        "summary": "Mission needs deterministic verification but current manifest only observes.",
    }


def proposal() -> dict[str, object]:
    return {
        "proposal_id": "proposal-7",
        "workspace_id": "workspace-7",
        "task_title": "Upgrade fixture transform",
        "capability_id": "origins.fixture.transform",
        "reason": "confirmed gap",
        "expected_benefit": "resume mission",
        "requested_effects": ["verify"],
        "filesystem_read_scope": [],
        "filesystem_write_scope": [],
        "network_mode": "deny",
        "network_hosts": [],
        "environment_names": [],
        "persistent_lease": False,
        "delegated_remote_authority": False,
        "alternatives": ["stay blocked"],
        "risks": ["candidate may fail"],
        "requested_by": "origins-phase7",
        "created_at": "2026-08-15T00:00:00Z",
        "approval_required": True,
        "self_approvable": False,
    }


def child(evolution_id: str) -> dict[str, object]:
    return {
        "status": "dry_run",
        "accepted": True,
        "reason": "validated",
        "operation_id": "child-7",
        "execution_dispatched": False,
        "operation": {
            "evidence": {
                "evidence_refs": [
                    "origins:parent-operation:agentops-parent-7",
                    f"origins:evolution:{evolution_id}",
                ]
            }
        },
    }


def build_reviewed(store: CapabilityEvolutionStore) -> str:
    record = store.create_gap(gap_payload())
    evolution_id = str(record["evolution_id"])
    store.bind_proposal(evolution_id, proposal())
    store.bind_child_operation(
        evolution_id,
        approval={"status": "approved", "approval_id": "approval-7"},
        child_operation=child(evolution_id),
    )
    manifest = {"capability_id": "origins.fixture.transform", "generation": 1, "effects": ["verify"]}
    manifest_sha = sha256_json(manifest)
    store.bind_candidate(
        evolution_id,
        {
            "repository_id": "repo-7",
            "repository_revision": 8,
            "candidate_generation": 1,
            "manifest": manifest,
            "manifest_sha256": manifest_sha,
            "proof_sha256": F,
            "codeops_evidence_ref": "agentops:evidence:codeops-7",
        },
    )
    store.bind_sergeant_review(
        evolution_id,
        {
            "verdict": "PASS",
            "review_sha256": D,
            "candidate_manifest_sha256": manifest_sha,
        },
    )
    return evolution_id


def test_confirmed_gap_must_be_evidence_backed(tmp_path: Path) -> None:
    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")
    bad = gap_payload()
    bad["actual_effects"] = ["observe", "verify"]
    with pytest.raises(CapabilityEvolutionError, match="expected effect"):
        store.create_gap(bad)
    bad = gap_payload()
    bad["evidence_refs"] = ["one"]
    with pytest.raises(CapabilityEvolutionError, match="two distinct"):
        store.create_gap(bad)


def test_full_promote_and_resume_preserves_exact_mission_state(tmp_path: Path) -> None:
    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")
    evolution_id = build_reviewed(store)
    record = store.get(evolution_id)
    candidate = record["candidate"]
    assert isinstance(candidate, dict)
    record = store.record_canary(
        evolution_id,
        {
            "mission_id": "mission-7",
            "attempt_id": "attempt-7",
            "manifest_sha256": candidate["manifest_sha256"],
            "outcome": "passed",
            "authority_expanded": False,
            "proof_sha256": E,
        },
    )
    assert record["state"] == "canary_passed"
    record = store.decide(evolution_id, decision="promote", decided_by="owner")
    assert record["state"] == "promoted"
    active = store.active_generation("origins.fixture.transform")
    assert active is not None and active["generation"] == 1
    record = store.resume_mission(evolution_id)
    assert record["state"] == "mission_resumed"
    resume = record["resume"]
    assert isinstance(resume, dict)
    assert resume["resume_token"] == "resume-opaque-7"
    assert resume["resume_state_sha256"] == D
    assert resume["exact_pre_upgrade_state_preserved"] is True


def test_canary_cannot_expand_authority_or_change_mission(tmp_path: Path) -> None:
    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")
    evolution_id = build_reviewed(store)
    candidate = store.get(evolution_id)["candidate"]
    assert isinstance(candidate, dict)
    with pytest.raises(CapabilityEvolutionError, match="must not expand authority"):
        store.record_canary(
            evolution_id,
            {
                "mission_id": "mission-7",
                "attempt_id": "attempt-7",
                "manifest_sha256": candidate["manifest_sha256"],
                "outcome": "passed",
                "authority_expanded": True,
                "proof_sha256": E,
            },
        )
    with pytest.raises(CapabilityEvolutionError, match="Mission/Attempt"):
        store.record_canary(
            evolution_id,
            {
                "mission_id": "different-mission",
                "attempt_id": "attempt-7",
                "manifest_sha256": candidate["manifest_sha256"],
                "outcome": "passed",
                "authority_expanded": False,
                "proof_sha256": E,
            },
        )


def test_non_pass_sergeant_verdict_blocks_canary(tmp_path: Path) -> None:
    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")
    record = store.create_gap(gap_payload())
    evolution_id = str(record["evolution_id"])
    store.bind_proposal(evolution_id, proposal())
    store.bind_child_operation(
        evolution_id,
        approval={"status": "approved"},
        child_operation=child(evolution_id),
    )
    manifest_sha = sha256_json({"candidate": 1})
    store.bind_candidate(
        evolution_id,
        {
            "repository_id": "repo-7",
            "repository_revision": 2,
            "candidate_generation": 1,
            "manifest_sha256": manifest_sha,
            "proof_sha256": F,
            "codeops_evidence_ref": "agentops:evidence:7",
        },
    )
    record = store.bind_sergeant_review(
        evolution_id,
        {
            "verdict": "BLOCK",
            "review_sha256": D,
            "candidate_manifest_sha256": manifest_sha,
        },
    )
    assert record["state"] == "reviewed_rejected"
    with pytest.raises(CapabilityEvolutionError, match="reviewed_pass"):
        store.record_canary(
            evolution_id,
            {
                "mission_id": "mission-7",
                "attempt_id": "attempt-7",
                "manifest_sha256": manifest_sha,
                "outcome": "passed",
                "authority_expanded": False,
                "proof_sha256": E,
            },
        )


def test_generation_rollback_is_explicit_and_does_not_resume_implicitly(tmp_path: Path) -> None:
    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")
    evolution_id = build_reviewed(store)
    candidate = store.get(evolution_id)["candidate"]
    assert isinstance(candidate, dict)
    store.record_canary(
        evolution_id,
        {
            "mission_id": "mission-7",
            "attempt_id": "attempt-7",
            "manifest_sha256": candidate["manifest_sha256"],
            "outcome": "passed",
            "authority_expanded": False,
            "proof_sha256": E,
        },
    )
    record = store.decide(evolution_id, decision="rollback", decided_by="owner")
    assert record["state"] == "rolled_back"
    assert record["resume"] is None
    record = store.resume_mission(evolution_id)
    assert record["state"] == "mission_resumed"
