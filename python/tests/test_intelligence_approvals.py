from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from origins_integration.intelligence_runtime import AgentOpsMount, IntelligenceMountError


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
        return [
            self.get_state(approval_id).public_dict()
            for approval_id in self.requests
            if approval_id not in self.records
        ]


class FakeStores:
    def __init__(self) -> None:
        self.service = FakeApprovalService()

    def approval_service(self) -> FakeApprovalService:
        return self.service

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {"operations": [], "approvals": [], "evidence": [], "audit": [], "lessons": []}


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


def mounted_agentops() -> tuple[AgentOpsMount, FakeStores]:
    stores = FakeStores()
    mount = AgentOpsMount(Path("/durable/agentops"))
    mount._stores_type = lambda _path: stores  # type: ignore[assignment]
    mount._bridge_type = FakeBridge  # type: ignore[assignment]
    FakeBridge.calls.clear()
    return mount, stores


def approve(mount: AgentOpsMount, approval_id: str) -> None:
    result = mount.decide_approval({
        "approval_id": approval_id,
        "decision": "approved",
        "decided_by": "owner",
    })
    assert result["evidence"]["status"] == "approved"  # type: ignore[index]


def test_operation_approval_is_exactly_bound_and_cannot_be_injected() -> None:
    mount, _stores = mounted_agentops()
    operation = {
        "playbook_path": "playbooks/codeops.json",
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

    with pytest.raises(IntelligenceMountError, match="not approved"):
        mount.run({**operation, "approval_id": approval_id})

    approve(mount, approval_id)
    result = mount.run({**operation, "approval_id": approval_id})
    assert result["ok"] is True
    assert FakeBridge.calls[-1]["owner_approved"] is True
    assert "approval_id" not in FakeBridge.calls[-1]

    with pytest.raises(IntelligenceMountError, match="not bound"):
        mount.run({**operation, "target": "repo-2", "approval_id": approval_id})

    with pytest.raises(IntelligenceMountError, match="cannot be asserted"):
        mount.run({**operation, "owner_approved": True})


def test_engineering_apply_requires_approved_exact_subject() -> None:
    mount, _stores = mounted_agentops()
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

    with pytest.raises(IntelligenceMountError, match="not approved"):
        mount.approval_state_for_engineering({**attempt, "approval_id": approval_id})

    approve(mount, approval_id)
    assert mount.approval_state_for_engineering({**attempt, "approval_id": approval_id}) == "approved"

    with pytest.raises(IntelligenceMountError, match="not bound"):
        mount.approval_state_for_engineering({
            **attempt,
            "provider_id": "different-provider",
            "approval_id": approval_id,
        })

    with pytest.raises(IntelligenceMountError, match="cannot be asserted"):
        mount.approval_state_for_engineering({**attempt, "approval_state": "approved"})


def test_non_mutating_engineering_attempt_needs_no_approval() -> None:
    mount, _stores = mounted_agentops()
    assert mount.approval_state_for_engineering({
        "operation_id": "op-read",
        "repository_id": "repo-read",
        "task": "Route and review only",
        "apply_plan": False,
    }) == "not_required"
