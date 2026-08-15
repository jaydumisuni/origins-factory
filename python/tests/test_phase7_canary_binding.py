from __future__ import annotations

import pytest

from origins_integration.phase7_runtime import Phase7RuntimeError, _validate_canary_binding

D = "d" * 64
E = "e" * 64


def values() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    gap = {"workspace_id": "workspace-7"}
    candidate = {
        "repository_id": "repo-7",
        "repository_head_oid": "abc123",
        "repository_status_sha256": D,
        "repository_diff_sha256": E,
        "repository_diff_bytes": 42,
    }
    session = {"workspace_id": "workspace-7", "workspace_root": "/tmp/candidate"}
    repository = {
        "repository_id": "repo-7",
        "workspace_id": "workspace-7",
        "worktree_root": "/tmp/candidate",
        "head_oid": "abc123",
        "status_sha256": D,
    }
    diff = {"kind": "unstaged", "truncated": False, "sha256": E, "complete_bytes": 42}
    return gap, candidate, session, repository, diff


def test_canary_binding_accepts_exact_reviewed_candidate() -> None:
    binding = _validate_canary_binding(*values())
    assert binding["repository_id"] == "repo-7"
    assert binding["repository_diff_sha256"] == E


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("session", "workspace_id", "other", "original Mission Workspace"),
        ("session", "workspace_root", "/tmp/other", "reviewed candidate worktree"),
        ("repository", "workspace_id", "other", "original Mission Workspace"),
        ("repository", "head_oid", "changed", "HEAD changed"),
        ("repository", "status_sha256", "f" * 64, "status changed"),
        ("diff", "sha256", "f" * 64, "diff changed"),
        ("diff", "complete_bytes", 43, "diff size changed"),
    ],
)
def test_canary_binding_rejects_wrong_session_or_changed_candidate(
    target: str, field: str, value: object, message: str
) -> None:
    gap, candidate, session, repository, diff = values()
    objects = {"session": session, "repository": repository, "diff": diff}
    objects[target][field] = value
    with pytest.raises(Phase7RuntimeError, match=message):
        _validate_canary_binding(gap, candidate, session, repository, diff)


def test_canary_binding_rejects_truncated_diff() -> None:
    gap, candidate, session, repository, diff = values()
    diff["truncated"] = True
    with pytest.raises(Phase7RuntimeError, match="complete reviewed"):
        _validate_canary_binding(gap, candidate, session, repository, diff)
