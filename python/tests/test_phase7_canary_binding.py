from __future__ import annotations

from pathlib import Path

import pytest

from origins_integration.phase7_runtime import (
    Phase7Runtime,
    Phase7RuntimeError,
    _validate_canary_binding,
    _validate_candidate_repository,
)

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


def test_candidate_repository_binding_is_reusable_for_promotion() -> None:
    gap, candidate, _session, repository, diff = values()
    binding = _validate_candidate_repository(gap, candidate, repository, diff)
    assert binding["repository_id"] == "repo-7"
    assert binding["repository_status_sha256"] == D


class _Bindings:
    def get(self, _evolution_id: str) -> None:
        return None


class _Store:
    path = Path("/tmp/unused-phase7-test.sqlite")

    def __init__(self, record: dict[str, object]) -> None:
        self.record = record
        self.decisions: list[dict[str, object]] = []

    def get(self, _evolution_id: str) -> dict[str, object]:
        return self.record

    def record_canary(self, _evolution_id: str, canary: dict[str, object]) -> dict[str, object]:
        value = dict(self.record)
        value["state"] = "canary_passed"
        value["canary"] = dict(canary)
        return value

    def active_generation(self, _capability_id: str) -> None:
        return None

    def decide(self, _evolution_id: str, **kwargs: object) -> dict[str, object]:
        self.decisions.append(dict(kwargs))
        value = dict(self.record)
        value["state"] = "promoted" if kwargs["decision"] == "promote" else "rolled_back"
        return value


class _Client:
    def __init__(self, *, changed: bool = False) -> None:
        self.calls: list[str] = []
        self.changed = changed

    def wait_session(self, _session_id: str) -> dict[str, object]:
        self.calls.append("wait")
        return {
            "state": "completed",
            "exit_code": 0,
            "output_truncated": False,
            "workspace_id": "workspace-7",
            "workspace_root": "/tmp/candidate",
            "stdout_sha256": D,
            "stderr_sha256": E,
        }

    def get_session_output(self, _session_id: str) -> dict[str, object]:
        self.calls.append("output")
        return {"stdout": "ok", "stderr": ""}

    def refresh_repository(self, _repository_id: str) -> dict[str, object]:
        self.calls.append("refresh")
        return {
            "repository_id": "repo-7",
            "workspace_id": "workspace-7",
            "worktree_root": "/tmp/candidate",
            "head_oid": "abc123",
            "status_sha256": ("f" * 64 if self.changed else D),
        }

    def get_repository_diff(self, _repository_id: str, *, kind: str) -> dict[str, object]:
        self.calls.append("diff")
        return {"kind": kind, "truncated": False, "sha256": E, "complete_bytes": 42}


def _runtime(changed: bool = False) -> tuple[Phase7Runtime, _Store, _Client]:
    gap, candidate, _session, _repository, _diff = values()
    record: dict[str, object] = {
        "evolution_id": "evolution-7",
        "state": "reviewed_pass",
        "gap": {**gap, "mission_id": "mission-7", "attempt_id": "attempt-7", "capability_id": "capability-7"},
        "candidate": {**candidate, "manifest_sha256": "a" * 64},
    }
    store = _Store(record)
    client = _Client(changed=changed)
    runtime = object.__new__(Phase7Runtime)
    runtime.store = store
    runtime.origins_client = client
    runtime.approvals = _Bindings()
    runtime.engineering_approvals = _Bindings()
    return runtime, store, client


def test_canary_waits_for_terminal_session_before_repository_revalidation() -> None:
    runtime, _store, client = _runtime()
    result = runtime.record_canary_from_session("evolution-7", "session-7")
    assert result["state"] == "canary_passed"
    assert client.calls.index("wait") < client.calls.index("refresh")


def test_promote_revalidates_candidate_and_persists_evidence() -> None:
    runtime, store, client = _runtime()
    store.record["state"] = "canary_passed"
    result = runtime.decide("evolution-7", decision="promote", decided_by="owner")
    assert result["state"] == "promoted"
    assert client.calls[:2] == ["refresh", "diff"]
    assert store.decisions[0]["candidate_revalidation"]["repository_status_sha256"] == D


def test_promote_rejects_candidate_changed_after_canary() -> None:
    runtime, store, _client = _runtime(changed=True)
    store.record["state"] = "canary_passed"
    with pytest.raises(Phase7RuntimeError, match="status changed after review"):
        runtime.decide("evolution-7", decision="promote", decided_by="owner")
    assert store.decisions == []


def test_rollback_does_not_require_candidate_revalidation() -> None:
    runtime, store, client = _runtime(changed=True)
    store.record["state"] = "canary_passed"
    result = runtime.decide("evolution-7", decision="rollback", decided_by="owner")
    assert result["state"] == "rolled_back"
    assert client.calls == []
    assert store.decisions[0]["candidate_revalidation"] is None
