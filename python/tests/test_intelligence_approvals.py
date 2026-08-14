from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from origins_integration.intelligence_runtime import (
    AgentOpsMount,
    IntelligenceApprovalError,
    IntelligenceRequestError,
)


@dataclass
class PublicValue:
    value: dict[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return self.value


class FakeApprovalService:
    def __init__(self) -> None:
        self.requests: dict[str, dict[str, Any]] = {}
        self.records: dict[str, dict[str, Any]] = {}
        self.counter = 0

    def create_request(self, **kwargs: Any) -> PublicValue:
        self.counter += 1
        approval_id = f"approval-{self.counter}"
        request = {
            "approval_id": approval_id,
            **kwargs,
            "status": "pending",
            "created_at": "2026-08-14T00:00:00Z",
        }
        self.requests[approval_id] = request
        return PublicValue(request)

    def get_state(self, approval_id: str) -> PublicValue:
        request = self.requests[approval_id]
        record = self.records.get(approval_id)
        status = "pending" if record is None else record["decision"]
        return PublicValue({"request": {**request, "status": status}, "record": record, "approved": status == "approved"})

    def decide(self, approval_id: str, decision: str, decided_by: str, note: str | None = None) -> PublicValue:
        if approval_id not in self.requests:
            raise ValueError(f"Unknown approval request: {approval_id}")
        if approval_id in self.records:
            raise ValueError(f"Approval request already decided: {approval_id}")
        self.records[approval_id] = {
            "approval_id": approval_id,
            "decision": decision,
            "decided_by": decided_by,
            "note": note,
            "created_at": "2026-08-14T00:00:01Z",
        }
        return self.get_state(approval_id)

    def get_evidence(self, approval_id: str) -> PublicValue:
        state = self.get_state(approval_id).public_dict()
        return PublicValue({
            "approval_id": approval_id,
            "status": "approved" if state["approved"] else (state["record"] or {}).get("decision", "pending"),
            "durable": True,
            "request": state["request"],
            "record": state["record"],
        })

    def list_pending(self) -> list[dict[str, Any]]:
        return [self.get_state(item).public_dict() for item in self.requests if item not in self.records]


class FakeStores:
    def __init__(self) -> None:
        self.service = FakeApprovalService()
        self.evidence: list[dict[str, Any]] = []

    def approval_service(self) -> FakeApprovalService:
        return self.service

    def save_evidence(self, value: Any) -> dict[str, Any]:
        payload = value.public_dict()
        self.evidence.append(payload)
        return payload

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {"operations": [], "approvals": [], "evidence": self.evidence, "audit": [], "lessons": []}


class FakeEvidenceItem:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def public_dict(self) -> dict[str, Any]:
        return {"evidence_id": "evidence-1", **self.kwargs}


class FakePlaybook:
    def public_dict(self) -> dict[str, Any]:
        return {"name": "code_ops", "mode": "code_ops", "purpose": "proof", "agents": [], "requires": [], "approval": "review_required", "blocked_actions": [], "proof": []}


class FakeBridgeResponse:
    def public_dict(self) -> dict[str, Any]:
        return {"status_code": 200, "ok": True, "body": {"accepted": True}}


class FakeBridge:
    calls: list[dict[str, object]] = []

    def __init__(self, *, stores: FakeStores) -> None:
        self.stores = stores

    def run(self, payload: dict[str, object]) -> FakeBridgeResponse:
        self.calls.append(dict(payload))
        return FakeBridgeResponse()


def mounted_agentops() -> tuple[AgentOpsMount, FakeStores, TemporaryDirectory[str]]:
    temporary = TemporaryDirectory()
    root = Path(temporary.name)
    (root / "playbooks").mkdir()
    (root / "playbooks" / "code_ops.yml").write_text("name: code_ops\n", encoding="utf-8")
    stores = FakeStores()
    mount = AgentOpsMount(root / "state", root)
    mount._stores_type = lambda _path: stores  # type: ignore[assignment]
    mount._bridge_type = FakeBridge  # type: ignore[assignment]
    mount._evidence_type = FakeEvidenceItem  # type: ignore[assignment]
    mount._load_playbook = lambda _path: FakePlaybook()  # type: ignore[assignment]
    FakeBridge.calls.clear()
    return mount, stores, temporary


def approve(mount: AgentOpsMount, approval_id: str) -> None:
    result = mount.decide_approval({"approval_id": approval_id, "decision": "approved", "decided_by": "owner"})
    assert result["evidence"]["status"] == "approved"  # type: ignore[index]


def test_operation_approval_is_exactly_bound_and_playbook_path_is_internal() -> None:
    mount, _stores, temporary = mounted_agentops()
    try:
        operation = {
            "playbook": "code_ops",
            "title": "Repair repository",
            "target": "repo-1",
            "requested_action": "apply",
        }
        created = mount.create_approval({
            "kind": "operation",
            "subject": operation,
            "reason": "Owner reviewed the exact operation request.",
        })
        approval_id = created["approval"]["request"]["approval_id"]  # type: ignore[index]

        with pytest.raises(IntelligenceApprovalError, match="not approved"):
            mount.run({**operation, "approval_id": approval_id})
        approve(mount, approval_id)
        result = mount.run({**operation, "approval_id": approval_id})
        assert result["ok"] is True
        assert FakeBridge.calls[-1]["owner_approved"] is True
        assert FakeBridge.calls[-1]["playbook_path"].endswith("playbooks/code_ops.yml")  # type: ignore[union-attr]
        assert "approval_id" not in FakeBridge.calls[-1]
        assert "playbook" not in FakeBridge.calls[-1]

        with pytest.raises(IntelligenceApprovalError, match="not bound"):
            mount.run({**operation, "target": "repo-2", "approval_id": approval_id})
        with pytest.raises(IntelligenceRequestError, match="cannot assert"):
            mount.run({**operation, "owner_approved": True})
        with pytest.raises(IntelligenceRequestError, match="cannot assert"):
            mount.run({**operation, "playbook_path": "/tmp/rogue.yml"})
        with pytest.raises(IntelligenceRequestError, match="unsupported"):
            mount.run({**operation, "playbook": "../rogue"})
    finally:
        temporary.cleanup()


def test_engineering_apply_requires_approved_exact_subject() -> None:
    mount, _stores, temporary = mounted_agentops()
    try:
        attempt = {
            "operation_id": "op-42",
            "repository_id": "repo-7",
            "task": "Apply reviewed correction",
            "plan": "plans/correction.json",
            "apply_plan": True,
            "provider_id": "local-coder",
        }
        created = mount.create_approval({
            "kind": "engineering",
            "subject": attempt,
            "reason": "Owner approved this exact CodeOps plan application.",
        })
        approval_id = created["approval"]["request"]["approval_id"]  # type: ignore[index]
        with pytest.raises(IntelligenceApprovalError, match="not approved"):
            mount.approval_state_for_engineering({**attempt, "approval_id": approval_id})
        approve(mount, approval_id)
        assert mount.approval_state_for_engineering({**attempt, "approval_id": approval_id}) == "approved"
        with pytest.raises(IntelligenceApprovalError, match="not bound"):
            mount.approval_state_for_engineering({**attempt, "provider_id": "other", "approval_id": approval_id})
        with pytest.raises(IntelligenceRequestError, match="cannot be asserted"):
            mount.approval_state_for_engineering({**attempt, "approval_state": "approved"})
    finally:
        temporary.cleanup()


def test_non_mutating_engineering_attempt_needs_no_approval() -> None:
    mount, _stores, temporary = mounted_agentops()
    try:
        assert mount.approval_state_for_engineering({
            "operation_id": "op-read",
            "repository_id": "repo-read",
            "task": "Route and review only",
            "apply_plan": False,
        }) == "not_required"
    finally:
        temporary.cleanup()


def test_engineering_attempt_evidence_is_compact_owner_schema() -> None:
    mount, stores, temporary = mounted_agentops()
    try:
        stored = mount.record_engineering_attempt(
            subject={"operation_id": "op-42", "repository_id": "repo-7", "provider_id": "local-coder", "mode": "quick_edit", "apply_plan": False},
            status="completed",
            verdict="PASS",
            recommendation="complete_candidate",
            evidence={"route_session_id": "session-route", "sergeant_review_session_id": "session-review", "review_sha256": "abc123"},
        )
        assert stored["kind"] == "tool_result"
        assert stored["source_ref"] == "origins.operation:op-42"
        assert stored["metadata"]["verdict"] == "PASS"
        assert stored["metadata"]["origins_attempt_evidence"]["review_sha256"] == "abc123"
        assert stores.evidence == [stored]
    finally:
        temporary.cleanup()
