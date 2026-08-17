from __future__ import annotations

from typing import Mapping

from .agentops_mcp import AgentOpsMcpError, AgentOpsMcpPort
from .capability_evolution import CapabilityEvolutionError, sha256_json
from .capability_evolution_approvals import EvolutionApprovalBindings, EvolutionEngineeringApprovalBindings


class Phase7AgentOpsError(RuntimeError):
    pass


class Phase7AgentOpsCoordinator:
    """Phase 7 projection of AgentOps-owned approval and external-operation state.

    Origins may request and observe owner state, but this coordinator deliberately has
    no approval-decision method. Capability synthesis remains owner-approved semantic
    work; isolated CodeOps candidate construction uses AgentOps' review_required gate.
    """

    def __init__(
        self,
        *,
        mcp: AgentOpsMcpPort,
        approvals: EvolutionApprovalBindings,
        engineering_approvals: EvolutionEngineeringApprovalBindings,
    ) -> None:
        self.mcp = mcp
        self.approvals = approvals
        self.engineering_approvals = engineering_approvals

    def request_capability_approval(
        self,
        *,
        evolution_id: str,
        proposal: Mapping[str, object],
        gap: Mapping[str, object],
    ) -> dict[str, object]:
        proposal_digest = sha256_json(proposal)
        result = self._call(
            self.mcp.request_approval,
            {
                "request_key": f"origins:phase7:{evolution_id}:capability",
                "task_title": str(proposal["task_title"]),
                "mode": "capability_extension",
                "gate": "owner_approval_required",
                "reason": str(proposal["reason"]),
                "requested_by": "origins-phase7",
                "target": str(proposal["capability_id"]),
                "metadata": {
                    "origins_approval_kind": "capability",
                    "evolution_id": evolution_id,
                    "proposal_sha256": proposal_digest,
                    "mission_id": str(gap["mission_id"]),
                    "parent_operation_id": str(gap["parent_operation_id"]),
                },
            },
        )
        evidence = self._approval_evidence(result)
        self._validate_capability_evidence(evolution_id, proposal, evidence)
        binding = self.approvals.bind(evolution_id, evidence)
        return {"owner": "Hunter-AgentOps", "transport": "mcp/rpc", **result, "binding": binding}

    def refresh_capability_approval(
        self,
        *,
        evolution_id: str,
        proposal: Mapping[str, object],
    ) -> dict[str, object]:
        binding = self.approvals.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps capability approval binding")
        result = self._call(self.mcp.get_approval, str(binding["approval_id"]))
        evidence = self._approval_evidence(result)
        self._validate_capability_evidence(evolution_id, proposal, evidence)
        if evidence.get("request_digest") != binding.get("request_digest"):
            raise Phase7AgentOpsError("AgentOps capability approval request digest changed after durable binding")
        refreshed = self.approvals.bind(evolution_id, evidence)
        return {"owner": "Hunter-AgentOps", "transport": "mcp/rpc", **result, "binding": refreshed}

    def start_upgrade_operation(
        self,
        *,
        evolution_id: str,
        proposal: Mapping[str, object],
        gap: Mapping[str, object],
        approval_id: str,
    ) -> dict[str, object]:
        refreshed = self.refresh_capability_approval(evolution_id=evolution_id, proposal=proposal)
        evidence = self._approval_evidence(refreshed)
        if evidence.get("status") != "approved":
            raise CapabilityEvolutionError("AgentOps capability approval is not approved")
        if evidence.get("approval_id") != approval_id:
            raise Phase7AgentOpsError("AgentOps capability approval ID does not match requested child operation")
        request_digest = str(evidence["request_digest"])
        owner = self._call(
            self.mcp.start_external_operation,
            {
                "kind": "origins_capability_upgrade",
                "title": f"Upgrade {proposal['capability_id']} for Mission {gap['mission_id']}",
                "requested_by": "origins-phase7",
                "conversation_ref": f"origins:mission:{gap['mission_id']}",
                "workspace_ref": f"origins:workspace:{gap['workspace_id']}",
                "correlation_id": f"origins:phase7:{evolution_id}:capability-upgrade",
                "metadata": {
                    "evolution_id": evolution_id,
                    "capability_id": str(proposal["capability_id"]),
                    "parent_operation_id": str(gap["parent_operation_id"]),
                    "mission_id": str(gap["mission_id"]),
                    "attempt_id": str(gap["attempt_id"]),
                    "approval_id": approval_id,
                    "approval_request_digest": request_digest,
                    "proposal_sha256": sha256_json(proposal),
                    "evidence_refs": [str(item) for item in gap["evidence_refs"]],
                },
            },
        )
        operation = self._external_operation(owner)
        self._validate_upgrade_operation(evolution_id, proposal, gap, approval_id, request_digest, operation)
        return {
            "owner": "Hunter-AgentOps",
            "transport": "mcp/rpc",
            "accepted": operation.get("state") == "running",
            "execution_dispatched": False,
            "operation_id": str(operation["operation_id"]),
            "operation_ref": str(operation["operation_ref"]),
            "external_operation": operation,
            "operation": {
                "operation_id": str(operation["operation_id"]),
                "evidence": {
                    "evidence_refs": [
                        f"origins:parent-operation:{gap['parent_operation_id']}",
                        f"origins:evolution:{evolution_id}",
                        f"agentops:approval:{approval_id}",
                        *[str(item) for item in gap["evidence_refs"]],
                    ]
                },
            },
        }

    def get_upgrade_operation(self, child_operation: Mapping[str, object]) -> dict[str, object]:
        operation_id = str(child_operation.get("operation_id") or "").strip()
        if not operation_id:
            raise Phase7AgentOpsError("stored child operation omitted operation_id")
        return self._call(self.mcp.get_external_operation, operation_id)

    def request_engineering_approval(
        self,
        *,
        evolution_id: str,
        subject: Mapping[str, object],
    ) -> dict[str, object]:
        subject_digest = sha256_json(subject)
        operation_id = str(subject.get("operation_id") or "")
        repository_id = str(subject.get("repository_id") or "")
        result = self._call(
            self.mcp.request_approval,
            {
                "request_key": f"origins:phase7:{evolution_id}:engineering:{subject_digest}",
                "task_title": str(subject.get("task") or "Origins Phase 7 engineering approval"),
                "mode": "engineering_apply",
                "gate": "review_required",
                "reason": (
                    "Review the exact isolated CodeOps candidate request for a confirmed Origins capability gap. "
                    "Candidate construction is reversible and does not activate runtime authority."
                ),
                "requested_by": "origins-phase7",
                "target": f"{operation_id}:{repository_id}",
                "metadata": {
                    "origins_approval_kind": "engineering",
                    "evolution_id": evolution_id,
                    "subject_sha256": subject_digest,
                    "operation_id": operation_id,
                    "repository_id": repository_id,
                    "runtime_authority_expansion": False,
                    "candidate_only": True,
                },
            },
        )
        evidence = self._approval_evidence(result)
        self._validate_engineering_evidence(evolution_id, subject, evidence)
        binding = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
        return {
            "owner": "Hunter-AgentOps",
            "transport": "mcp/rpc",
            **result,
            "binding": binding,
            "engineering_subject": dict(subject),
        }

    def refresh_engineering_approval(
        self,
        *,
        evolution_id: str,
        subject: Mapping[str, object],
    ) -> dict[str, object]:
        binding = self.engineering_approvals.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps engineering approval binding")
        if binding.get("subject_sha256") != sha256_json(subject):
            raise CapabilityEvolutionError("engineering request changed after AgentOps approval binding")
        result = self._call(self.mcp.get_approval, str(binding["approval_id"]))
        evidence = self._approval_evidence(result)
        self._validate_engineering_evidence(evolution_id, subject, evidence)
        if evidence.get("request_digest") != binding.get("request_digest"):
            raise Phase7AgentOpsError("AgentOps engineering approval request digest changed after durable binding")
        refreshed = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
        return {
            "owner": "Hunter-AgentOps",
            "transport": "mcp/rpc",
            **result,
            "binding": refreshed,
            "engineering_subject": dict(subject),
        }

    def finalize_upgrade_operation(
        self,
        *,
        child_operation: Mapping[str, object],
        outcome: str,
        result_ref: str,
        evidence_refs: list[str],
    ) -> dict[str, object]:
        operation_id = str(child_operation.get("operation_id") or "").strip()
        if not operation_id:
            raise Phase7AgentOpsError("stored child operation omitted operation_id")
        return self._call(
            self.mcp.finalize_external_operation,
            {
                "operation_id": operation_id,
                "outcome": outcome,
                "result_ref": result_ref,
                "evidence_refs": evidence_refs,
            },
        )

    @staticmethod
    def _approval_evidence(result: Mapping[str, object]) -> dict[str, object]:
        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping):
            raise Phase7AgentOpsError("AgentOps MCP approval response omitted durable evidence")
        return dict(evidence)

    @staticmethod
    def _external_operation(result: Mapping[str, object]) -> dict[str, object]:
        operation = result.get("operation")
        if not isinstance(operation, Mapping):
            raise Phase7AgentOpsError("AgentOps MCP external-operation response omitted operation")
        return dict(operation)

    @staticmethod
    def _validate_decided_evidence(evidence: Mapping[str, object]) -> None:
        if evidence.get("status") != "approved":
            return
        record = evidence.get("record")
        if not isinstance(record, Mapping) or record.get("decision") != "approved":
            raise Phase7AgentOpsError("approved AgentOps evidence omitted its approval record")
        if not str(record.get("decided_by") or "").strip():
            raise Phase7AgentOpsError("approved AgentOps evidence omitted approver identity")

    @classmethod
    def _validate_capability_evidence(
        cls,
        evolution_id: str,
        proposal: Mapping[str, object],
        evidence: Mapping[str, object],
    ) -> None:
        request = evidence.get("request")
        metadata = request.get("metadata") if isinstance(request, Mapping) else None
        if not isinstance(request, Mapping) or not isinstance(metadata, Mapping):
            raise Phase7AgentOpsError("AgentOps capability approval metadata is malformed")
        if request.get("gate") != "owner_approval_required":
            raise Phase7AgentOpsError("AgentOps capability approval gate changed")
        if metadata.get("origins_approval_kind") != "capability" or metadata.get("evolution_id") != evolution_id:
            raise Phase7AgentOpsError("AgentOps capability approval is not bound to this evolution")
        if metadata.get("proposal_sha256") != sha256_json(proposal):
            raise Phase7AgentOpsError("AgentOps capability approval proposal digest changed")
        cls._validate_decided_evidence(evidence)

    @classmethod
    def _validate_engineering_evidence(
        cls,
        evolution_id: str,
        subject: Mapping[str, object],
        evidence: Mapping[str, object],
    ) -> None:
        request = evidence.get("request")
        metadata = request.get("metadata") if isinstance(request, Mapping) else None
        if not isinstance(request, Mapping) or not isinstance(metadata, Mapping):
            raise Phase7AgentOpsError("AgentOps engineering approval metadata is malformed")
        if request.get("gate") != "review_required":
            raise Phase7AgentOpsError("AgentOps engineering approval gate changed")
        if metadata.get("origins_approval_kind") != "engineering" or metadata.get("evolution_id") != evolution_id:
            raise Phase7AgentOpsError("AgentOps engineering approval is not bound to this evolution")
        if metadata.get("subject_sha256") != sha256_json(subject):
            raise Phase7AgentOpsError("AgentOps engineering approval subject digest changed")
        if metadata.get("candidate_only") is not True or metadata.get("runtime_authority_expansion") is not False:
            raise Phase7AgentOpsError("AgentOps engineering approval lost its candidate-only authority boundary")
        cls._validate_decided_evidence(evidence)

    @staticmethod
    def _validate_upgrade_operation(
        evolution_id: str,
        proposal: Mapping[str, object],
        gap: Mapping[str, object],
        approval_id: str,
        request_digest: str,
        operation: Mapping[str, object],
    ) -> None:
        if operation.get("state") != "running" or operation.get("kind") != "origins_capability_upgrade":
            raise Phase7AgentOpsError("AgentOps external operation is not an active Origins capability upgrade")
        if operation.get("correlation_id") != f"origins:phase7:{evolution_id}:capability-upgrade":
            raise Phase7AgentOpsError("AgentOps external operation correlation changed")
        if operation.get("workspace_ref") != f"origins:workspace:{gap['workspace_id']}":
            raise Phase7AgentOpsError("AgentOps external operation workspace binding changed")
        metadata = operation.get("metadata")
        if not isinstance(metadata, Mapping):
            raise Phase7AgentOpsError("AgentOps external operation metadata is malformed")
        expected = {
            "evolution_id": evolution_id,
            "capability_id": str(proposal["capability_id"]),
            "parent_operation_id": str(gap["parent_operation_id"]),
            "approval_id": approval_id,
            "approval_request_digest": request_digest,
            "proposal_sha256": sha256_json(proposal),
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise Phase7AgentOpsError(f"AgentOps external operation {key} binding changed")

    @staticmethod
    def _call(function, *args):
        try:
            return function(*args)
        except AgentOpsMcpError as exc:
            raise Phase7AgentOpsError(str(exc)) from exc
