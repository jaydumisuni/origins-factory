from __future__ import annotations

import pytest

from origins_integration.phase7_runtime import Phase7RuntimeError, _candidate_change_proof, _engineering_subject

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
