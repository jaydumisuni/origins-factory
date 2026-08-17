from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from origins_integration.agentops_mcp import AgentOpsMcpClient, AgentOpsMcpEndpoints, AgentOpsMcpError
from origins_integration.capability_evolution import CapabilityEvolutionError, sha256_json
from origins_integration.capability_evolution_approvals import (
    EvolutionApprovalBindings,
    EvolutionEngineeringApprovalBindings,
)
from origins_integration.phase7_agentops import Phase7AgentOpsCoordinator, Phase7AgentOpsError
from origins_integration.phase7_runtime_authority import Phase7Runtime

D = "d" * 64


def _approval(approval_id: str, *, gate: str, metadata: dict[str, object], status: str = "pending") -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "status": status,
        "durable": True,
        "request_digest": D,
        "metadata_digest": "e" * 64,
        "record_digest": "" if status == "pending" else "f" * 64,
        "ledger_event_digest": "1" * 64,
        "request": {"approval_id": approval_id, "gate": gate, "metadata": metadata},
        "record": None if status == "pending" else {"decision": "approved", "decided_by": "reviewer"},
    }


class HostileMcp:
    def __init__(self) -> None:
        self.approvals: dict[str, dict[str, object]] = {}
        self.operation: dict[str, object] | None = None

    def request_approval(self, arguments):
        args = dict(arguments)
        approval_id = "approval-" + sha256_json({"key": str(args["request_key"])})[:16]
        evidence = self.approvals.setdefault(
            approval_id,
            _approval(
                approval_id,
                gate=str(args["gate"]),
                metadata=dict(args.get("metadata") or {}),
            ),
        )
        return {"ok": True, "approval": {"status": evidence["status"]}, "evidence": dict(evidence)}

    def get_approval(self, approval_id: str):
        evidence = self.approvals[approval_id]
        return {"ok": True, "approval": {"status": evidence["status"]}, "evidence": dict(evidence)}

    def list_pending_approvals(self):
        return {"ok": True, "pending": []}

    def start_external_operation(self, arguments):
        args = dict(arguments)
        self.operation = {
            "operation_id": "ext-adversarial",
            "operation_ref": "agentops:operation:ext-adversarial",
            "kind": args["kind"],
            "title": args["title"],
            "requested_by": args["requested_by"],
            "conversation_ref": args["conversation_ref"],
            "workspace_ref": args["workspace_ref"],
            "correlation_id": args["correlation_id"],
            "state": "running",
            "metadata": dict(args["metadata"]),
            "created_at": "2026-08-17T00:00:00Z",
            "evidence_refs": [],
        }
        return {"ok": True, "operationRef": self.operation["operation_ref"], "operation": dict(self.operation)}

    def get_external_operation(self, operation_id: str):
        assert self.operation is not None and self.operation["operation_id"] == operation_id
        return {"ok": True, "operationRef": self.operation["operation_ref"], "operation": dict(self.operation)}

    def finalize_external_operation(self, arguments):
        raise AssertionError("finalize is not used by adversarial tests")

    def approve(self, approval_id: str, *, actor: str = "reviewer") -> None:
        evidence = self.approvals[approval_id]
        evidence["status"] = "approved"
        evidence["record_digest"] = "f" * 64
        evidence["record"] = {"decision": "approved", "decided_by": actor}


def _coordinator(tmp_path: Path, mcp: HostileMcp) -> Phase7AgentOpsCoordinator:
    state = tmp_path / "phase7.sqlite"
    return Phase7AgentOpsCoordinator(
        mcp=mcp,
        approvals=EvolutionApprovalBindings(state),
        engineering_approvals=EvolutionEngineeringApprovalBindings(state),
    )


def _proposal() -> dict[str, object]:
    return {"task_title": "Upgrade cap.usb", "capability_id": "cap.usb", "reason": "missing effect"}


def _gap() -> dict[str, object]:
    return {
        "mission_id": "mission-7",
        "parent_operation_id": "parent-7",
        "workspace_id": "workspace-7",
        "attempt_id": "attempt-7",
        "evidence_refs": ["origins:evidence:a"],
    }


def _subject() -> dict[str, object]:
    return {
        "operation_id": "ext-adversarial",
        "repository_id": "repo-7",
        "task": "bounded change",
        "plan": "plans/change.json",
        "apply_plan": True,
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8792/mcp",
        "http://example.com:8792/mcp",
        "http://127.0.0.1:8792/other",
        "http://user:pass@127.0.0.1:8792/mcp",
        "http://127.0.0.1:8792/mcp?tool=approve",
        "http://127.0.0.1:8792/mcp#fragment",
    ],
)
def test_agentops_mcp_endpoint_escape_is_rejected(url: str) -> None:
    with pytest.raises(AgentOpsMcpError):
        AgentOpsMcpClient(
            endpoints=AgentOpsMcpEndpoints(approval=url, external_operation="http://127.0.0.1:8791/mcp"),
            token="x" * 64,
        )


def test_agentops_service_credential_cannot_be_short_or_owner_authority() -> None:
    with pytest.raises(AgentOpsMcpError, match="at least 32"):
        AgentOpsMcpClient(
            endpoints=AgentOpsMcpEndpoints(
                approval="http://127.0.0.1:8792/mcp",
                external_operation="http://127.0.0.1:8791/mcp",
            ),
            token="short",
        )
    client = AgentOpsMcpClient(
        endpoints=AgentOpsMcpEndpoints(
            approval="http://127.0.0.1:8792/mcp",
            external_operation="http://127.0.0.1:8791/mcp",
        ),
        token="x" * 64,
    )
    assert client.public_status()["service_credential_is_owner_authorization"] is False
    assert not hasattr(client, "decide_approval")


def test_public_runtime_cannot_accept_client_reasserted_owner_authority() -> None:
    assert tuple(inspect.signature(Phase7Runtime.create_child_upgrade_operation).parameters) == (
        "self",
        "evolution_id",
    )
    assert tuple(inspect.signature(Phase7Runtime.implement_candidate).parameters) == (
        "self",
        "evolution_id",
    )


def test_counterfeit_capability_approval_evidence_fails_closed(tmp_path: Path) -> None:
    mcp = HostileMcp()
    owner = _coordinator(tmp_path, mcp)
    requested = owner.request_capability_approval(evolution_id="evolution-7", proposal=_proposal(), gap=_gap())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approve(approval_id)
    mcp.approvals[approval_id]["request"]["metadata"]["proposal_sha256"] = "0" * 64
    with pytest.raises(Phase7AgentOpsError, match="proposal digest changed"):
        owner.refresh_capability_approval(evolution_id="evolution-7", proposal=_proposal())


def test_engineering_authority_expansion_or_wrong_gate_fails_closed(tmp_path: Path) -> None:
    mcp = HostileMcp()
    owner = _coordinator(tmp_path, mcp)
    requested = owner.request_engineering_approval(evolution_id="evolution-7", subject=_subject())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approve(approval_id)
    evidence = mcp.approvals[approval_id]
    evidence["request"]["metadata"]["runtime_authority_expansion"] = True
    with pytest.raises(Phase7AgentOpsError, match="candidate-only authority boundary"):
        owner.refresh_engineering_approval(evolution_id="evolution-7", subject=_subject())

    evidence["request"]["metadata"]["runtime_authority_expansion"] = False
    evidence["request"]["gate"] = "owner_approval_required"
    with pytest.raises(Phase7AgentOpsError, match="engineering approval gate changed"):
        owner.refresh_engineering_approval(evolution_id="evolution-7", subject=_subject())


def test_mutated_external_operation_binding_is_rejected(tmp_path: Path) -> None:
    mcp = HostileMcp()
    owner = _coordinator(tmp_path, mcp)
    requested = owner.request_capability_approval(evolution_id="evolution-7", proposal=_proposal(), gap=_gap())
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approve(approval_id)

    original = mcp.start_external_operation

    def mutated(arguments):
        result = original(arguments)
        operation = dict(result["operation"])
        metadata = dict(operation["metadata"])
        metadata["approval_id"] = "approval-attacker"
        operation["metadata"] = metadata
        return {**result, "operation": operation}

    mcp.start_external_operation = mutated  # type: ignore[method-assign]
    with pytest.raises(Phase7AgentOpsError, match="approval_id binding changed"):
        owner.start_upgrade_operation(
            evolution_id="evolution-7",
            proposal=_proposal(),
            gap=_gap(),
            approval_id=approval_id,
        )


def test_changed_engineering_subject_cannot_replay_approval(tmp_path: Path) -> None:
    mcp = HostileMcp()
    owner = _coordinator(tmp_path, mcp)
    subject = _subject()
    requested = owner.request_engineering_approval(evolution_id="evolution-7", subject=subject)
    approval_id = str(requested["binding"]["approval_id"])
    mcp.approve(approval_id)
    with pytest.raises(CapabilityEvolutionError, match="changed after AgentOps approval binding"):
        owner.refresh_engineering_approval(
            evolution_id="evolution-7",
            subject={**subject, "task": "attacker-changed-task"},
        )
