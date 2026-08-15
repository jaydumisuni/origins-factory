from __future__ import annotations

import hashlib
import importlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from .capability_evolution import CapabilityEvolutionError, CapabilityEvolutionStore, sha256_json
from .capability_proposals import CapabilityProposal
from .engineering import BridgeError, OriginsClient
from .intelligence_runtime import IntelligenceMountError, IntelligenceRuntime


class Phase7RuntimeError(RuntimeError):
    pass


class Phase7Runtime:
    """Coordinates Phase-7 evolution while preserving owner authority boundaries."""

    def __init__(
        self,
        *,
        store: CapabilityEvolutionStore,
        intelligence: IntelligenceRuntime,
        origins_client: OriginsClient,
    ) -> None:
        self.store = store
        self.intelligence = intelligence
        self.origins_client = origins_client

    @classmethod
    def from_env(cls) -> "Phase7Runtime":
        state_raw = os.environ.get("ORIGINS_PHASE7_STATE", "").strip()
        if not state_raw:
            raise Phase7RuntimeError("ORIGINS_PHASE7_STATE is required")
        client = OriginsClient.from_env()
        intelligence = IntelligenceRuntime.from_env()
        if intelligence.origins_client is None:
            intelligence.origins_client = client
        return cls(store=CapabilityEvolutionStore(Path(state_raw).expanduser()), intelligence=intelligence, origins_client=client)

    def health(self) -> dict[str, object]:
        return {
            "phase": 7,
            "mode": "controlled_capability_evolution",
            "runtime_authority_expansion": False,
            "model_self_approval": False,
            "owners": self.intelligence.health().get("owners", []),
        }

    def list(self) -> dict[str, object]:
        return {"phase": 7, "evolutions": self.store.list()}

    def get(self, evolution_id: str) -> dict[str, object]:
        return self.store.get(evolution_id)

    def confirm_gap(self, payload: Mapping[str, object]) -> dict[str, object]:
        record = self.store.create_gap(payload)
        gap = _mapping(record, "gap")
        proposal = CapabilityProposal.create(
            workspace_id=str(gap["workspace_id"]),
            task_title=f"Upgrade {gap['capability_id']} for Mission {gap['mission_id']}",
            capability_id=str(gap["capability_id"]),
            reason=str(gap["summary"]),
            expected_benefit="Resume the original Mission without widening authority beyond its confirmed requirement.",
            requested_effects=tuple(str(item) for item in gap["expected_effects"]),
            alternatives=("Keep Mission blocked with bounded refusal",),
            risks=("Candidate capability may fail proof or canary and must remain rollback-safe",),
            requested_by="origins-phase7",
        )
        return self.store.bind_proposal(str(record["evolution_id"]), proposal.as_dict())

    def create_approval(self, evolution_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "proposal_ready":
            raise CapabilityEvolutionError("approval may be requested only for a proposal-ready evolution")
        proposal = _mapping(record, "proposal")
        stores = self.intelligence.agentops._stores()
        service = stores.approval_service()
        request = service.create_request(
            task_title=str(proposal["task_title"]),
            mode="capability_extension",
            gate="owner_approval_required",
            reason=str(proposal["reason"]),
            requested_by="origins-phase7",
            target=str(proposal["capability_id"]),
            metadata={
                "origins_approval_kind": "capability",
                "evolution_id": evolution_id,
                "proposal": dict(proposal),
            },
        )
        return {"owner": "Hunter-AgentOps", "approval": service.get_state(request.approval_id).public_dict()}

    def decide_approval(self, evolution_id: str, *, approval_id: str, decision: str, decided_by: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        proposal = _mapping(record, "proposal")
        service = self.intelligence.agentops._stores().approval_service()
        state = service.get_state(approval_id)
        metadata = state.request.metadata
        if metadata.get("origins_approval_kind") != "capability" or metadata.get("evolution_id") != evolution_id:
            raise Phase7RuntimeError("AgentOps approval is not bound to this evolution")
        if metadata.get("proposal") != dict(proposal):
            raise Phase7RuntimeError("AgentOps approval proposal binding changed")
        state = service.decide(approval_id, decision, decided_by)
        evidence = service.get_evidence(approval_id)
        return {"owner": "Hunter-AgentOps", "approval": state.public_dict(), "evidence": evidence.public_dict()}

    def create_child_upgrade_operation(self, evolution_id: str, approval_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        proposal = _mapping(record, "proposal")
        gap = _mapping(record, "gap")
        service = self.intelligence.agentops._stores().approval_service()
        evidence = service.get_evidence(approval_id).public_dict()
        request = evidence.get("request")
        metadata = request.get("metadata") if isinstance(request, dict) else None
        if evidence.get("status") != "approved" or not isinstance(metadata, dict):
            raise Phase7RuntimeError("approved AgentOps capability evidence is required")
        if metadata.get("evolution_id") != evolution_id or metadata.get("proposal") != dict(proposal):
            raise Phase7RuntimeError("AgentOps capability approval is not bound to this evolution/proposal")
        operation_id = f"cap-upgrade-{uuid.uuid4()}"
        child_payload = {
            "schema_version": "hunter.agentops.operation-request.v1",
            "operation_id": operation_id,
            "domain": "origins",
            "operation_type": "capability_upgrade",
            "action": "prepare_candidate",
            "mode": "capability_extension",
            "risk": "medium",
            "required_gate": "owner_approval_required",
            "target": str(proposal["capability_id"]),
            "subject": evolution_id,
            "subject_type": "capability_evolution",
            "requested_by": "origins-phase7",
            "authorization": {"approval_id": approval_id},
            "evidence": {
                "evidence_refs": [
                    f"origins:parent-operation:{gap['parent_operation_id']}",
                    f"origins:evolution:{evolution_id}",
                    f"agentops:approval:{approval_id}",
                    *[str(item) for item in gap["evidence_refs"]],
                ],
                "proposal_sha256": sha256_json(proposal),
                "mission_id": gap["mission_id"],
                "attempt_id": gap["attempt_id"],
            },
            "dry_run": True,
            "source": "origins-phase7",
            "created_at": record["updated_at"],
        }
        result = self.intelligence.agentops._stores().department_operation_service().submit_operation(child_payload)
        return self.store.bind_child_operation(
            evolution_id,
            approval={"status": "approved", "approval_id": approval_id, "evidence_sha256": sha256_json(evidence)},
            child_operation=result,
        )

    def implement_candidate(self, evolution_id: str, payload: dict[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "upgrade_operation_ready":
            raise CapabilityEvolutionError("candidate implementation requires a ready child upgrade Operation")
        child = _mapping(record, "child_operation")
        operation_id = str(child["operation_id"])
        command = dict(payload)
        command["operation_id"] = operation_id
        command.setdefault("apply_plan", True)
        command.setdefault("review", "required")
        result = self.intelligence.engineering_attempt(command)
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise Phase7RuntimeError("CodeOps engineering result omitted retained evidence")
        proposal = _mapping(record, "proposal")
        current = self.store.active_generation(str(proposal["capability_id"]))
        generation = (int(current["generation"]) if current else 0) + 1
        manifest = {
            "schema_version": "origins.capability-generation.v1",
            "capability_id": proposal["capability_id"],
            "generation": generation,
            "requested_effects": proposal["requested_effects"],
            "filesystem_read_scope": proposal["filesystem_read_scope"],
            "filesystem_write_scope": proposal["filesystem_write_scope"],
            "network_mode": proposal["network_mode"],
            "network_hosts": proposal["network_hosts"],
            "environment_names": proposal["environment_names"],
            "persistent_lease": proposal["persistent_lease"],
            "delegated_remote_authority": proposal["delegated_remote_authority"],
            "repository_id": result["repository_id"],
            "repository_revision": result["repository_revision"],
            "repository_head_oid": result["repository_head_oid"],
            "codeops_evidence_sha256": sha256_json(evidence),
        }
        manifest_sha = sha256_json(manifest)
        candidate = {
            "repository_id": result["repository_id"],
            "repository_revision": result["repository_revision"],
            "repository_head_oid": result["repository_head_oid"],
            "candidate_generation": generation,
            "manifest": manifest,
            "manifest_sha256": manifest_sha,
            "proof_sha256": sha256_json({"engineering": evidence, "review_sha256": result["review_sha256"]}),
            "codeops_evidence_ref": f"agentops:evidence:{sha256_json(result.get('agentops_evidence', {}))}",
        }
        record = self.store.bind_candidate(evolution_id, candidate)
        review = {
            "verdict": str(result["verdict"]).replace(" ", "_"),
            "review_sha256": result["review_sha256"],
            "candidate_manifest_sha256": manifest_sha,
            "sergeant_evidence": result["evidence"],
        }
        return self.store.bind_sergeant_review(evolution_id, review)

    def record_canary_from_session(self, evolution_id: str, session_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        gap = _mapping(record, "gap")
        candidate = _mapping(record, "candidate")
        session = self.origins_client.wait_session(session_id)
        output = self.origins_client.get_session_output(session_id)
        if session.get("state") != "completed" or session.get("exit_code") != 0 or bool(session.get("output_truncated")):
            raise Phase7RuntimeError("canary Session must complete successfully without truncation")
        proof = {
            "session_id": session_id,
            "session_stdout_sha256": session.get("stdout_sha256"),
            "session_stderr_sha256": session.get("stderr_sha256"),
            "output": output,
        }
        canary = {
            "mission_id": gap["mission_id"],
            "attempt_id": gap["attempt_id"],
            "manifest_sha256": candidate["manifest_sha256"],
            "outcome": "passed",
            "authority_expanded": False,
            "proof_sha256": sha256_json(proof),
            "session_id": session_id,
        }
        return self.store.record_canary(evolution_id, canary)

    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
        return self.store.decide(evolution_id, decision=decision, decided_by=decided_by)

    def resume(self, evolution_id: str) -> dict[str, object]:
        record = self.store.resume_mission(evolution_id)
        resume = _mapping(record, "resume")
        stores = self.intelligence.agentops._stores()
        evidence_module = importlib.import_module("agentops.evidence")
        evidence_type = getattr(evidence_module, "EvidenceItem")
        stored = stores.save_evidence(
            evidence_type(
                title="Origins capability evolution Mission resume",
                kind="tool_result",
                summary="Original Mission resume point preserved after controlled capability evolution.",
                source_ref=f"origins.evolution:{evolution_id}",
                metadata={"evolution_id": evolution_id, "resume": dict(resume)},
            )
        )
        return {"evolution": record, "agentops_evidence": stored}


def _mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise Phase7RuntimeError(f"{field} is missing or malformed")
    return value
