from __future__ import annotations

from pathlib import Path

import pytest

from origins_integration.capability_evolution import CapabilityEvolutionError, sha256_json
from origins_integration.capability_evolution_approvals import (
    EvolutionApprovalBindings,
    EvolutionEngineeringApprovalBindings,
)
from origins_integration.phase7_agentops import Phase7AgentOpsCoordinator, Phase7AgentOpsError

D = "d" * 64


def approval_evidence(
    approval_id: str,
    status: str,
    metadata: dict[str, object],
    *,
    gate: str,
) -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "status": status,
        "durable": True,
        "request_digest": D,
        "metadata_digest": "e" * 64,
        "record_digest": "" if status == "pending" else "f" * 64,
        "ledger_event_digest": "1" * 64,
        "request": {
            "approval_id": approval_id,
            "gate": gate,
            "metadata": metadata,
        },
        "record": None if status == "pending" else {
            "decision": status,
            "decided_by": "phase7-test-owner",
        },
    }


class FakeMcp:
    def __init__(self) -> None:
        self.approvals: dict[str, dict[str, object]] = {}
        self.operations: dict[str, dict[str, object]] = {}
        self.request_calls: list[dict[str, object]] = []
        self.finalize_calls: list[dict[str, object]] = []

    def request_approval(self, arguments):
        args = dict(arguments)
        self.request_calls.append(args)
        key = str(args["request_key"])
        approval_id = "approval-" + sha256_json({"key": key})[:16]
        metadata = dict(args.get("metadata") or {})
        evidence = self.approvals.setdefault(
            approval_id,
            approval_evidence(
                approval_id,
                "pending",
                metadata,
                gate=str(args["gate"]),
            ),
        )
        return {"ok": True, "approval": {"status": evidence["status"]}, "evidence": dict(evidence)}

    def get_approval(self, approval_id: str):
        evidence = self.approvals[approval_id]
        return {"ok": True, "approval": {"status": evidence["status"]}, "evidence": dict(evidence)}

    def list_pending_approvals(self):
        return {"ok": True, "pending": [item for item in self.approvals.values() if item["status"] == "pending"]}

    def start_external_operation(self, arguments):
        args = dict(arguments)
        correlation = str(args["correlation_id"])
        operation = self.operations.setdefault(
            correlation,
            {
                "operation_id": "ext-phase7-0001",
                "operation_ref": "agentops:operation:ext-phase7-0001",
                "kind": args["kind"],
                "title": args["title"],
                "requested_by": args["requested_by"],
                "conversation_ref": args["conversation_ref"],
                "workspace_ref": args["workspace_ref"],
                "correlation_id": correlation,
                "state": "running",
                "metadata": dict(args["metadata"]),
                "created_at": "2026-08-16T00:00:00Z",
                "evidence_refs": [],
            },
        )
        return {"ok": True, "operationRef": operation["operation_ref"], "operation": dict(operation)}

    def get_external_operation(self, operation_id: str):
        operation = next(item for item in self.operations.values() if item["operation_id"] == operation_id)
        return {"ok": True, "operationRef": operation["operation_ref"], "operation": dict(operation)}

    def finalize_external_operation(self, arguments):
        args = dict(arguments)
        self.finalize_calls.append(args)
        operation = next(item for item in self.operations.values() if item["operation_id"] == args["operation_id"])
        operation.update(
            state=args["outcome"],
            outcome=args["outcome"],
            result_ref=args.get("result_ref"),
            evidence_refs=list(args.get("evidence_refs") or []),
        )
        return {"ok": True, "operationRef": operation["operation_ref"], "operation": dict(operation)}

    def approve(self, approval_id: str, *, decided_by: str = "phase7-test-owner") -> None:
        evidence = self.approvals[approval_id]
        evidence["status"] = "approved"
        evidence["record_digest"] = "f" * 64
        evidence["record"] = {"decision": "approved", "decided_by": decided_by}


def coordinator(tmp_path: Path, mcp: FakeMcp) -> Phase7AgentOpsCoordinator:
    db = tmp_path / "phase7.sqlite"
    return Phase7AgentOpsCoordinator(
        mcp=mcp,
        approvals=EvolutionApprovalBindings(db),
        engineering_approvals=EvolutionEngineeringApprovalBindings(db),
    )


def proposal() -> dict[str, object]:
    return {
        "task_title": "Upgrade cap.usb",
        "capability_id": "cap.usb",
        "reason": "missing effect",
    }


def gap() -> dict[str, object]:
    return {
        "mission_id": "mission-7",
        "parent_operation_id": "parent-7",
        "workspace_id": "workspace-7",
        "attempt_id": "attempt-7",
        "evidence_refs": ["origins:evidence:a", "origins:evidence:b"],
    }


def engineering_subject() -> dict[str, object]:
    return {
        "operation_id": "ext-phase7-0001",
        "repository_id": "repo-7",
        "task": "bounded change",
        "plan": "plans/change.json",
        "apply_plan": True,
    }


def test_coordinator_exposes_no_approval_decision_method(tmp_path: Path) -> None:
    owner = coordinator(tmp_path, FakeMcp())
    assert not hasattr(owner, "decide_approval")
    assert not hasattr(owner, "decide_engineering_approval")


def test_capability_request_refresh_and_child_operation_observe_owner_state(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    requested = owner.request_capability_approval(evolution_id="evolution-7", proposal=proposal(), gap=gap())
    approval_id = str(requested["binding"]["approval_id"])
    assert requested["binding"]["status"] == "pending"
    assert mcp.request_calls[0]["gate"] == "owner_approval_required"

    with pytest.raises(CapabilityEvolutionError, match="not approved"):
        owner.start_upgrade_operation(
            evolution_id="evolution-7", proposal=proposal(), gap=gap(), approval_id=approval_id
        )

    mcp.approve(approval_id)
    refreshed = owner.refresh_capability_approval(evolution_id="evolution-7", proposal=proposal())
    assert refreshed["binding"]["status"] == "approved"

    child = owner.start_upgrade_operation(
        evolution_id="evolution-7", proposal=proposal(), gap=gap(), approval_id=approval_id
    )
    assert child["transport"] == "mcp/rpc"
    assert child["accepted"] is True
    assert child["execution_dispatched"] is False
    assert child["operation_id"] == "ext-phase7-0001"


def test_engineering_request_uses_review_gate_and_refresh_is_digest_bound(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    subject = engineering_subject()
    requested = owner.request_engineering_approval(evolution_id="evolution-7", subject=subject)
    approval_id = str(requested["binding"]["approval_id"])
    assert mcp.request_calls[-1]["gate"] == "review_required"
    assert mcp.request_calls[-1]["metadata"]["candidate_only"] is True
    assert mcp.request_calls[-1]["metadata"]["runtime_authority_expansion"] is False

    mcp.approve(approval_id, decided_by="reviewer-7")
    refreshed = owner.refresh_engineering_approval(evolution_id="evolution-7", subject=subject)
    assert refreshed["binding"]["status"] == "approved"

    changed = {**subject, "task": "different change"}
    with pytest.raises(CapabilityEvolutionError, match="changed after AgentOps approval binding"):
        owner.refresh_engineering_approval(evolution_id="evolution-7", subject=changed)


def test_wrong_agentops_gate_fails_closed(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    requested = owner.request_engineering_approval(evolution_id="evolution-7", subject=engineering_subject())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approvals[approval_id]["request"]["gate"] = "owner_approval_required"
    with pytest.raises(Phase7AgentOpsError, match="engineering approval gate changed"):
        owner.refresh_engineering_approval(evolution_id="evolution-7", subject=engineering_subject())


def test_approved_evidence_requires_approver_identity(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    requested = owner.request_engineering_approval(evolution_id="evolution-7", subject=engineering_subject())
    approval_id = str(requested["binding"]["approval_id"])
    evidence = mcp.approvals[approval_id]
    evidence["status"] = "approved"
    evidence["record"] = {"decision": "approved", "decided_by": ""}
    with pytest.raises(Phase7AgentOpsError, match="omitted approver identity"):
        owner.refresh_engineering_approval(evolution_id="evolution-7", subject=engineering_subject())


def test_external_operation_finalize_is_agentops_owned(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    requested = owner.request_capability_approval(evolution_id="evolution-7", proposal=proposal(), gap=gap())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approve(approval_id)
    child = owner.start_upgrade_operation(
        evolution_id="evolution-7", proposal=proposal(), gap=gap(), approval_id=approval_id
    )
    finalized = owner.finalize_upgrade_operation(
        child_operation=child,
        outcome="completed",
        result_ref="origins:candidate:abc",
        evidence_refs=["origins:codeops:abc", "sergeant:review:def"],
    )
    assert finalized["operation"]["state"] == "completed"
    assert mcp.finalize_calls == [{
        "operation_id": "ext-phase7-0001",
        "outcome": "completed",
        "result_ref": "origins:candidate:abc",
        "evidence_refs": ["origins:codeops:abc", "sergeant:review:def"],
    }]


def test_changed_owner_evidence_fails_closed(tmp_path: Path) -> None:
    mcp = FakeMcp()
    owner = coordinator(tmp_path, mcp)
    requested = owner.request_capability_approval(evolution_id="evolution-7", proposal=proposal(), gap=gap())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approvals[approval_id]["request_digest"] = "a" * 64
    with pytest.raises(Phase7AgentOpsError, match="request digest changed"):
        owner.refresh_capability_approval(evolution_id="evolution-7", proposal=proposal())
