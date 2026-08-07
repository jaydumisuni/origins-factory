from __future__ import annotations

from types import SimpleNamespace

from origins_integration.engineering import (
    EngineeringAttemptRequest,
    EngineeringBridge,
    MechanicalResult,
)


class FakeClient:
    def __init__(self) -> None:
        self.inspections = []

    def get_repository(self, repository_id: str):
        return {
            "repository_id": repository_id,
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "worktree_root": "/repo",
            "revision": 4,
            "head_oid": "a" * 40,
        }

    def inspect_repository(self, workspace_id: str, path: str):
        self.inspections.append((workspace_id, path))
        return {
            "repository_id": "repo-1",
            "workspace_id": workspace_id,
            "worktree_root": path,
            "revision": 5,
            "head_oid": "b" * 40,
        }


class FakeContracts:
    def build_agentops_packet(self, request, *, workspace: str):
        return SimpleNamespace(
            operation_id=request.operation_id,
            task=request.task,
            workspace=workspace,
            files=request.files,
            plan=request.plan,
            apply_plan=request.apply_plan,
        )

    def ingest_sergeant_result_text(self, text: str):
        return SimpleNamespace(verdict="PASS", needs_loop=False, blocked=False, summary="pass")


class ProofBridge(EngineeringBridge):
    def _run_json_process(self, *, executable: str, label: str, **_kwargs):
        if label == "CodeOps Sergeant command":
            payload = {
                "ok": True,
                "command": ["sergeant", "app-review", "/repo", "--mode", "pull_request", "--pretty"],
            }
        else:
            payload = {"ok": True}
        return MechanicalResult(
            session_id=f"{executable}-{label}",
            session={"stdout_sha256": "c" * 64},
            output={"stdout": "{}"},
            payload=payload,
        )

    def _run_text_process(self, *, executable: str, label: str, **_kwargs):
        return MechanicalResult(
            session_id=f"{executable}-{label}",
            session={"stdout_sha256": "d" * 64},
            output={"stdout": '{"verdict":"PASS"}'},
            payload=None,
        )


def test_attempt_uses_fresh_repository_revision_and_head() -> None:
    client = FakeClient()
    bridge = ProofBridge(client, FakeContracts())
    result = bridge.run_attempt(
        EngineeringAttemptRequest(
            operation_id="op-1",
            repository_id="repo-1",
            task="read-only proof",
        )
    )
    assert client.inspections == [("11111111-1111-4111-8111-111111111111", "/repo")]
    assert result.repository_revision == 5
    assert result.repository_head_oid == "b" * 40
