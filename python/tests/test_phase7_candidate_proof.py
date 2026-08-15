from __future__ import annotations

import pytest

from origins_integration.phase7_runtime import (
    Phase7RuntimeError,
    _candidate_change_proof,
    _engineering_subject,
    _find_resume_evidence,
    _recover_completed_engineering_evidence,
)

D = "d" * 64
E = "e" * 64
F = "f" * 64

def _record() -> dict[str, object]:
    return {"child_operation": {"operation_id": "child-7"}}

def test_engineering_subject_requires_nonempty_plan() -> None:
    with pytest.raises(Phase7RuntimeError, match="non-empty CodeOps file-edit plan"):
        _engineering_subject(_record(), {"repository_id": "repo-7", "task": "upgrade"})

def test_candidate_change_proof_requires_real_untruncated_tracked_diff() -> None:
    before = {"repository_id": "repo-7", "status_sha256": D}
    after = {"repository_id": "repo-7", "status_sha256": E, "revision": 8, "head_oid": "abc123"}
    proof = _candidate_change_proof(before, after, {"kind": "unstaged", "complete_bytes": 42, "sha256": F, "truncated": False})
    assert proof["diff_bytes"] == 42
    assert proof["diff_sha256"] == F
    with pytest.raises(Phase7RuntimeError, match="non-empty tracked repository diff"):
        _candidate_change_proof(before, after, {"kind": "unstaged", "complete_bytes": 0, "sha256": F, "truncated": False})
    with pytest.raises(Phase7RuntimeError, match="truncated"):
        _candidate_change_proof(before, after, {"kind": "unstaged", "complete_bytes": 42, "sha256": F, "truncated": True})
    with pytest.raises(Phase7RuntimeError, match="did not change repository status"):
        _candidate_change_proof(before, {**after, "status_sha256": D}, {"kind": "unstaged", "complete_bytes": 42, "sha256": F, "truncated": False})


def test_completed_engineering_evidence_recovery_is_exact() -> None:
    subject_sha = "+" * 64
    review_sha = "a" * 64
    item = {
        "evidence_id": "evidence-7",
        "source_ref": "origins.operation:child-7",
        "metadata": {
            "operation_id": "child-7",
            "repository_id": "repo-7",
            "subject_sha256": subject_sha,
            "status": "completed",
            "apply_plan": True,
            "verdict": "PASS",
            "origins_attempt_evidence": {
                "operation_id": "child-7",
                "repository_id": "repo-7",
                "plan_apply_session_id": "session-apply",
                "review_sha256": review_sha,
            },
        },
    }
    recovered = _recover_completed_engineering_evidence(
        {"evidence": [item]}, operation_id="child-7", repository_id="repo-7", subject_sha256=subject_sha
    )
    assert recovered is not None
    assert recovered["review_sha256"] == review_sha
    assert recovered["agentops_evidence"]["evidence_id"] == "evidence-7"
    assert _recover_completed_engineering_evidence(
        {"evidence": [item]}, operation_id="child-7", repository_id="repo-7", subject_sha256="b" * 64
    ) is None
    with pytest.raises(Phase7RuntimeError, match="multiple completed"):
        _recover_completed_engineering_evidence(
            {"evidence": [item, {**item, "evidence_id": "evidence-8"}]},
            operation_id="child-7", repository_id="repo-7", subject_sha256=subject_sha,
        )


def test_resume_evidence_recovery_is_exact() -> None:
    resume = {"resume_token": "token-7", "resume_state_sha256": "c" * 64}
    item = {
        "evidence_id": "resume-evidence-7",
        "source_ref": "origins.evolution:evolution-7",
        "metadata": {"evolution_id": "evolution-7", "resume": resume},
    }
    assert _find_resume_evidence({"evidence": [item]}, "evolution-7", resume) == item
    assert _find_resume_evidence({"evidence": [item]}, "other", resume) is None
