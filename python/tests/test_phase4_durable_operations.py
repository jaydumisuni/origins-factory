from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

import pytest

from origins_integration.intelligence_runtime import (
    AgentOpsMount,
    IntelligenceMountError,
    IntelligenceRequestError,
)
from origins_integration.phase4_runtime import Phase4IntelligenceRuntime


@dataclass
class PublicValue:
    value: dict[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return self.value

    @property
    def approval_id(self) -> str:
        return str(self.value["approval_id"])


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
        return PublicValue(
            {
                "request": {**request, "status": status},
                "record": record,
                "approved": status == "approved",
            }
        )

    def decide(
        self,
        approval_id: str,
        decision: str,
        decided_by: str,
        note: str | None = None,
    ) -> PublicValue:
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
        return PublicValue(
            {
                "approval_id": approval_id,
                "status": "approved" if state["approved"] else "pending",
                "durable": True,
                "request": state["request"],
                "record": state["record"],
            }
        )

    def list_pending(self) -> list[dict[str, Any]]:
        return [
            self.get_state(approval_id).public_dict()
            for approval_id in self.requests
            if approval_id not in self.records
        ]


class FakeOperationService:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []

    def submit_operation(self, packet: dict[str, Any]) -> dict[str, Any]:
        self.submitted.append(dict(packet))
        result = {
            "schema_version": "hunter.agentops.operation-result.v1",
            "operation_id": packet["operation_id"],
            "operation": dict(packet),
            "status": "accepted",
            "accepted": True,
            "reason": "proof",
            "execution_dispatched": False,
            "idempotent_replay": False,
        }
        self.results.append(result)
        return result

    def list_durable_results(self) -> list[dict[str, Any]]:
        return list(self.results)


class FakeStores:
    def __init__(self) -> None:
        self.approvals = FakeApprovalService()
        self.operations = FakeOperationService()

    def approval_service(self) -> FakeApprovalService:
        return self.approvals

    def department_operation_service(self, *, authorization_port: Any = None, engine: Any = None) -> FakeOperationService:
        assert authorization_port is not None
        return self.operations

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "operations": [{"schema_version": "hunter.agentops.operation-ledger.v1"}],
            "approvals": [],
            "evidence": [],
            "audit": [],
            "lessons": [],
        }


class FakePlaybook:
    def __init__(self, approval: str = "review_required") -> None:
        self.name = "code_ops"
        self.mode = "code_ops"
        self.approval = approval
        self.requires = ["repo_path", "task_goal"]

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "purpose": "proof",
            "agents": [],
            "requires": list(self.requires),
            "approval": self.approval,
            "blocked_actions": [],
            "proof": [],
        }


class FakeAuthorizationPort:
    def __init__(self, approvals: Any, transport: Any) -> None:
        self.approvals = approvals
        self.transport = transport


def mounted_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    approval_gate: str = "review_required",
) -> tuple[Phase4IntelligenceRuntime, FakeStores, TemporaryDirectory[str]]:
    temporary = TemporaryDirectory()
    root = Path(temporary.name)
    (root / "playbooks").mkdir()
    (root / "playbooks" / "code_ops.yml").write_text("name: code_ops\n", encoding="utf-8")
    stores = FakeStores()
    mount = AgentOpsMount(root / "state", root)
    mount._stores_type = lambda _path: stores  # type: ignore[assignment]
    mount._bridge_type = object  # type: ignore[assignment]
    mount._evidence_type = object  # type: ignore[assignment]
    mount._load_playbook = lambda _path: FakePlaybook(approval_gate)  # type: ignore[assignment]
    monkeypatch.setitem(
        sys.modules,
        "agentops.auth_step_up",
        SimpleNamespace(TtgAuthAuthorizationPort=FakeAuthorizationPort),
    )
    return Phase4IntelligenceRuntime(agentops=mount), stores, temporary


def approve(runtime: Phase4IntelligenceRuntime, approval_id: str) -> None:
    runtime.decide_approval(
        {
            "approval_id": approval_id,
            "decision": "approved",
            "decided_by": "owner",
        }
    )


def test_operation_identity_is_generated_bound_and_submitted_from_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, stores, temporary = mounted_runtime(monkeypatch)
    try:
        created = runtime.create_approval(
            {
                "kind": "operation",
                "reason": "Review exact CodeOps mission.",
                "subject": {
                    "playbook": "code_ops",
                    "title": "Repair Origins repository",
                    "target": "jaydumisuni/origins-factory",
                    "requested_action": "review_and_prepare",
                    "risk": "medium",
                    "evidence": {},
                },
            }
        )
        approval = created["approval"]
        approval_id = approval["request"]["approval_id"]  # type: ignore[index]
        prepared = created["prepared_operation"]
        assert str(prepared["operation_id"]).startswith("origins-")  # type: ignore[index]
        assert prepared["required_gate"] == "review_required"  # type: ignore[index]
        assert prepared["mode"] == "code_ops"  # type: ignore[index]
        assert prepared["evidence"]["repo_path"] == "jaydumisuni/origins-factory"  # type: ignore[index]
        assert prepared["evidence"]["task_goal"] == "Repair Origins repository"  # type: ignore[index]

        approve(runtime, str(approval_id))
        result = runtime.run_agentops({"approval_id": str(approval_id)})
        assert result["accepted"] is True
        assert result["execution_dispatched"] is False
        packet = stores.operations.submitted[-1]
        assert packet["operation_id"] == prepared["operation_id"]  # type: ignore[index]
        assert packet["created_at"] == prepared["created_at"]  # type: ignore[index]
        assert packet["authorization"] == {"approval_id": approval_id}
        assert packet["target"] == "jaydumisuni/origins-factory"

        projected = runtime.operations()
        assert projected["operations"][0]["operation_id"] == prepared["operation_id"]  # type: ignore[index]
        assert projected["operation_ledger"][0]["schema_version"] == "hunter.agentops.operation-ledger.v1"  # type: ignore[index]
    finally:
        temporary.cleanup()


def test_execution_cannot_override_approved_operation_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _stores, temporary = mounted_runtime(monkeypatch)
    try:
        created = runtime.create_approval(
            {
                "kind": "operation",
                "reason": "Review exact mission.",
                "subject": {
                    "playbook": "code_ops",
                    "title": "Mission",
                    "target": "repo-a",
                    "requested_action": "review_and_prepare",
                },
            }
        )
        approval_id = created["approval"]["request"]["approval_id"]  # type: ignore[index]
        approve(runtime, str(approval_id))
        with pytest.raises(IntelligenceRequestError, match="only approval/proof references"):
            runtime.run_agentops(
                {
                    "approval_id": str(approval_id),
                    "target": "repo-b",
                }
            )
    finally:
        temporary.cleanup()


def test_client_cannot_supply_operation_identity_or_authority_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _stores, temporary = mounted_runtime(monkeypatch)
    try:
        with pytest.raises(IntelligenceRequestError, match="runtime-owned"):
            runtime.create_approval(
                {
                    "kind": "operation",
                    "reason": "bad",
                    "subject": {
                        "playbook": "code_ops",
                        "title": "Mission",
                        "target": "repo-a",
                        "requested_action": "review_and_prepare",
                        "operation_id": "client-owned-id",
                    },
                }
            )
    finally:
        temporary.cleanup()


def test_higher_auth_gate_fails_before_durable_operation_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, stores, temporary = mounted_runtime(
        monkeypatch,
        approval_gate="owner_approval_required",
    )
    try:
        created = runtime.create_approval(
            {
                "kind": "operation",
                "reason": "Owner reviewed mission.",
                "subject": {
                    "playbook": "code_ops",
                    "title": "Mission",
                    "target": "repo-a",
                    "requested_action": "review_and_prepare",
                },
            }
        )
        approval_id = created["approval"]["request"]["approval_id"]  # type: ignore[index]
        approve(runtime, str(approval_id))
        with pytest.raises(IntelligenceMountError, match="TTG Auth step-up"):
            runtime.run_agentops({"approval_id": str(approval_id)})
        assert stores.operations.submitted == []
    finally:
        temporary.cleanup()
