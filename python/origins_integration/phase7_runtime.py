from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Mapping

from .capability_evolution import CapabilityEvolutionError, CapabilityEvolutionStore, sha256_json
from .capability_evolution_approvals import EvolutionApprovalBindings, EvolutionEngineeringApprovalBindings
from .capability_proposals import CapabilityProposal
from .engineering import OriginsClient
from .intelligence_runtime import IntelligenceRuntime


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
        approvals: EvolutionApprovalBindings | None = None,
        engineering_approvals: EvolutionEngineeringApprovalBindings | None = None,
    ) -> None:
        self.store = store
        self.intelligence = intelligence
        self.origins_client = origins_client
        self.approvals = approvals or EvolutionApprovalBindings(store.path)
        self.engineering_approvals = engineering_approvals or EvolutionEngineeringApprovalBindings(store.path)

    @classmethod
    def from_env(cls) -> "Phase7Runtime":
        state_raw = os.environ.get("ORIGINS_PHASE7_STATE", "").strip()
        if not state_raw:
            raise Phase7RuntimeError("ORIGINS_PHASE7_STATE is required")
        path = Path(state_raw).expanduser()
        client = OriginsClient.from_env()
        intelligence = IntelligenceRuntime.from_env()
        if intelligence.origins_client is None:
            intelligence.origins_client = client
        return cls(
            store=CapabilityEvolutionStore(path),
            approvals=EvolutionApprovalBindings(path),
            engineering_approvals=EvolutionEngineeringApprovalBindings(path),
            intelligence=intelligence,
            origins_client=client,
        )

    def health(self) -> dict[str, object]:
        return {
            "phase": 7,
            "mode": "controlled_capability_evolution",
            "runtime_authority_expansion": False,
            "model_self_approval": False,
            "owners": self.intelligence.health().get("owners", []),
        }

    def _project(self, record: dict[str, object]) -> dict[str, object]:
        projected = dict(record)
        evolution_id = str(record["evolution_id"])
        projected["approval_binding"] = self.approvals.get(evolution_id)
        projected["engineering_approval_binding"] = self.engineering_approvals.get(evolution_id)
        gap = _mapping(record, "gap")
        projected["active_generation"] = self.store.active_generation(str(gap["capability_id"]))
        return projected

    def list(self) -> dict[str, object]:
        return {"phase": 7, "evolutions": [self._project(item) for item in self.store.list()]}

    def get(self, evolution_id: str) -> dict[str, object]:
        return self._project(self.store.get(evolution_id))

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
        return self._project(self.store.bind_proposal(str(record["evolution_id"]), proposal.as_dict()))

    def create_approval(self, evolution_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "proposal_ready":
            raise CapabilityEvolutionError("approval may be requested only for a proposal-ready evolution")
        proposal = _mapping(record, "proposal")
        service = self.intelligence.agentops._stores().approval_service()
        existing = self.approvals.get(evolution_id)
        if existing is not None and existing["status"] in {"pending", "approved"}:
            approval_id = str(existing["approval_id"])
            return {
                "owner": "Hunter-AgentOps",
                "approval": service.get_state(approval_id).public_dict(),
                "binding": existing,
            }
        recovered_id = _find_pending_owner_approval(
            service,
            {
                "origins_approval_kind": "capability",
                "evolution_id": evolution_id,
                "proposal": dict(proposal),
            },
        )
        if recovered_id is not None:
            evidence = service.get_evidence(recovered_id).public_dict()
            binding = self.approvals.bind(evolution_id, evidence)
            return {
                "owner": "Hunter-AgentOps",
                "approval": service.get_state(recovered_id).public_dict(),
                "binding": binding,
                "recovered_pending": True,
            }
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
        evidence = service.get_evidence(request.approval_id).public_dict()
        binding = self.approvals.bind(evolution_id, evidence)
        return {
            "owner": "Hunter-AgentOps",
            "approval": service.get_state(request.approval_id).public_dict(),
            "binding": binding,
        }

    def decide_approval(
        self,
        evolution_id: str,
        *,
        approval_id: str,
        decision: str,
        decided_by: str,
    ) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "proposal_ready":
            raise CapabilityEvolutionError("approval decision requires a proposal-ready evolution")
        proposal = _mapping(record, "proposal")
        binding = self.approvals.get(evolution_id)
        if binding is None or binding["approval_id"] != approval_id:
            raise Phase7RuntimeError("AgentOps approval ID is not the durable binding for this evolution")
        service = self.intelligence.agentops._stores().approval_service()
        state = service.get_state(approval_id)
        metadata = state.request.metadata
        if metadata.get("origins_approval_kind") != "capability" or metadata.get("evolution_id") != evolution_id:
            raise Phase7RuntimeError("AgentOps approval is not bound to this evolution")
        if metadata.get("proposal") != dict(proposal):
            raise Phase7RuntimeError("AgentOps approval proposal binding changed")
        if state.status == "pending":
            state = service.decide(approval_id, decision, decided_by)
        elif state.status != decision:
            raise Phase7RuntimeError(f"AgentOps approval is already {state.status}")
        evidence = service.get_evidence(approval_id).public_dict()
        binding = self.approvals.bind(evolution_id, evidence)
        return {
            "owner": "Hunter-AgentOps",
            "approval": state.public_dict(),
            "evidence": evidence,
            "binding": binding,
        }

    def create_child_upgrade_operation(self, evolution_id: str, approval_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        proposal = _mapping(record, "proposal")
        gap = _mapping(record, "gap")
        binding = self.approvals.require_approved(evolution_id, approval_id)
        service = self.intelligence.agentops._stores().approval_service()
        evidence = service.get_evidence(approval_id).public_dict()
        if evidence.get("request_digest") != binding.get("request_digest"):
            raise Phase7RuntimeError("AgentOps approval digest changed after durable binding")
        request = evidence.get("request")
        metadata = request.get("metadata") if isinstance(request, dict) else None
        if evidence.get("status") != "approved" or not isinstance(metadata, dict):
            raise Phase7RuntimeError("approved AgentOps capability evidence is required")
        if metadata.get("evolution_id") != evolution_id or metadata.get("proposal") != dict(proposal):
            raise Phase7RuntimeError("AgentOps capability approval is not bound to this evolution/proposal")
        operation_id = f"cap-upgrade-{evolution_id}"
        child_payload = {
            "schema_version": "hunter.agentops.operation-request.v1",
            "operation_id": operation_id,
            "domain": "origins",
            "operation_type": "capability_upgrade",
            "action": "prepare_candidate",
            "mode": "code_ops",
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
        return self._project(
            self.store.bind_child_operation(
                evolution_id,
                approval={
                    "status": "approved",
                    "approval_id": approval_id,
                    "request_digest": binding["request_digest"],
                    "evidence_sha256": sha256_json(evidence),
                },
                child_operation=result,
            )
        )

    def create_engineering_approval(self, evolution_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "upgrade_operation_ready":
            raise CapabilityEvolutionError("engineering approval requires a ready child upgrade Operation")
        subject = _engineering_subject(record, payload)
        existing = self.engineering_approvals.get(evolution_id)
        if existing is not None and existing["status"] in {"pending", "approved"}:
            if existing["subject_sha256"] != sha256_json(subject):
                raise CapabilityEvolutionError("existing engineering approval is bound to a different candidate request")
            approval_id = str(existing["approval_id"])
            state = self.intelligence.agentops._stores().approval_service().get_state(approval_id)
            return {"owner": "Hunter-AgentOps", "approval": state.public_dict(), "binding": existing}
        service = self.intelligence.agentops._stores().approval_service()
        recovered_id = _find_pending_owner_approval(
            service,
            {"origins_approval_kind": "engineering", "subject": subject},
        )
        if recovered_id is not None:
            evidence = service.get_evidence(recovered_id).public_dict()
            binding = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
            return {
                "owner": "Hunter-AgentOps",
                "approval": service.get_state(recovered_id).public_dict(),
                "binding": binding,
                "engineering_subject": subject,
                "recovered_pending": True,
            }
        created = self.intelligence.create_approval(
            {
                "kind": "engineering",
                "subject": subject,
                "reason": "Implement the bounded CodeOps candidate for a confirmed Origins capability gap.",
                "requested_by": "origins-phase7",
            }
        )
        approval = created.get("approval")
        request = approval.get("request") if isinstance(approval, dict) else None
        approval_id = request.get("approval_id") if isinstance(request, dict) else None
        if not isinstance(approval_id, str) or not approval_id:
            raise Phase7RuntimeError("AgentOps engineering approval response omitted approval_id")
        evidence = self.intelligence.agentops._stores().approval_service().get_evidence(approval_id).public_dict()
        binding = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
        return {**created, "binding": binding, "engineering_subject": subject}

    def decide_engineering_approval(
        self,
        evolution_id: str,
        *,
        approval_id: str,
        decision: str,
        decided_by: str,
    ) -> dict[str, object]:
        binding = self.engineering_approvals.get(evolution_id)
        if binding is None or binding["approval_id"] != approval_id:
            raise Phase7RuntimeError("AgentOps engineering approval is not the durable binding for this evolution")
        service = self.intelligence.agentops._stores().approval_service()
        before = service.get_evidence(approval_id).public_dict()
        request = before.get("request")
        metadata = request.get("metadata") if isinstance(request, dict) else None
        subject = metadata.get("subject") if isinstance(metadata, dict) else None
        if metadata is None or metadata.get("origins_approval_kind") != "engineering" or not isinstance(subject, dict):
            raise Phase7RuntimeError("AgentOps engineering approval evidence is malformed")
        if sha256_json(subject) != binding["subject_sha256"]:
            raise Phase7RuntimeError("AgentOps engineering approval subject changed after binding")
        state = service.get_state(approval_id)
        if state.status == "pending":
            result = self.intelligence.decide_approval(
                {"approval_id": approval_id, "decision": decision, "decided_by": decided_by}
            )
        elif state.status == decision:
            result = {"owner": "Hunter-AgentOps", "approval": state.public_dict(), "evidence": before}
        else:
            raise Phase7RuntimeError(f"AgentOps engineering approval is already {state.status}")
        evidence = service.get_evidence(approval_id).public_dict()
        binding = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
        return {**result, "binding": binding, "engineering_subject": subject}

    def implement_candidate(self, evolution_id: str, payload: dict[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        state = str(record.get("state") or "")
        if state not in {"upgrade_operation_ready", "engineering_started"}:
            raise CapabilityEvolutionError(
                "candidate implementation requires a ready or restart-recoverable child upgrade Operation"
            )
        subject = _engineering_subject(record, payload)
        binding = self.engineering_approvals.require_approved(evolution_id, subject)
        repository_id = str(subject["repository_id"])
        subject_sha256 = sha256_json(subject)
        operation_id = str(subject["operation_id"])
        recovered_result: dict[str, object] | None = None

        if state == "upgrade_operation_ready":
            pre_repository = self.origins_client.refresh_repository(repository_id)
            record = self.store.begin_engineering(
                evolution_id,
                {
                    "operation_id": operation_id,
                    "repository_id": repository_id,
                    "approval_id": binding["approval_id"],
                    "subject_sha256": subject_sha256,
                    "pre_repository_status_sha256": pre_repository["status_sha256"],
                    "pre_repository_head_oid": pre_repository["head_oid"],
                    "pre_repository_revision": pre_repository["revision"],
                },
            )
        else:
            attempt = _mapping(record, "engineering_attempt")
            if attempt.get("operation_id") != operation_id or attempt.get("repository_id") != repository_id:
                raise Phase7RuntimeError("restart engineering request does not match the durable attempt identity")
            if attempt.get("approval_id") != binding["approval_id"]:
                raise Phase7RuntimeError("restart engineering approval does not match the durable attempt")
            if attempt.get("subject_sha256") != subject_sha256:
                raise Phase7RuntimeError("restart engineering subject changed after the durable attempt began")
            pre_repository = {
                "repository_id": repository_id,
                "status_sha256": attempt["pre_repository_status_sha256"],
                "head_oid": attempt["pre_repository_head_oid"],
                "revision": attempt["pre_repository_revision"],
            }
            recovered_result = _recover_completed_engineering_evidence(
                self.intelligence.agentops.snapshot(),
                operation_id=operation_id,
                repository_id=repository_id,
                subject_sha256=subject_sha256,
            )
            current = self.origins_client.refresh_repository(repository_id)
            changed = (
                current.get("status_sha256") != pre_repository.get("status_sha256")
                or current.get("head_oid") != pre_repository.get("head_oid")
            )
            if recovered_result is None and changed:
                raise Phase7RuntimeError(
                    "candidate engineering was interrupted after repository change without completed AgentOps evidence; "
                    "restore the candidate worktree to the durable pre-engineering state before retrying"
                )

        if recovered_result is None:
            command = dict(subject)
            command["approval_id"] = binding["approval_id"]
            result = self.intelligence.engineering_attempt(command)
        else:
            result = recovered_result

        post_repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        change_proof = _candidate_change_proof(pre_repository, post_repository, repository_diff)
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise Phase7RuntimeError("CodeOps engineering result omitted retained evidence")
        agentops_evidence = result.get("agentops_evidence")
        if not isinstance(agentops_evidence, dict):
            raise Phase7RuntimeError("AgentOps engineering evidence is missing")
        evidence_id = agentops_evidence.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise Phase7RuntimeError("AgentOps engineering evidence omitted canonical evidence_id")
        proposal = _mapping(record, "proposal")
        current = self.store.active_generation(str(proposal["capability_id"]))
        base_generation = int(current["generation"]) if current else 0
        base_manifest_sha256 = str(current["manifest_sha256"]) if current else None
        base_evolution_id = str(current["evolution_id"]) if current else None
        generation = base_generation + 1
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
            "repository_id": repository_id,
            "repository_revision": post_repository["revision"],
            "repository_head_oid": post_repository["head_oid"],
            "repository_status_sha256": post_repository["status_sha256"],
            "repository_diff_sha256": change_proof["diff_sha256"],
            "repository_diff_bytes": change_proof["diff_bytes"],
            "codeops_evidence_sha256": sha256_json(evidence),
        }
        manifest_sha = sha256_json(manifest)
        candidate = {
            "repository_id": repository_id,
            "repository_revision": post_repository["revision"],
            "repository_head_oid": post_repository["head_oid"],
            "repository_status_sha256": post_repository["status_sha256"],
            "repository_diff_sha256": change_proof["diff_sha256"],
            "repository_diff_bytes": change_proof["diff_bytes"],
            "base_generation": base_generation,
            "base_manifest_sha256": base_manifest_sha256,
            "base_evolution_id": base_evolution_id,
            "candidate_generation": generation,
            "manifest": manifest,
            "manifest_sha256": manifest_sha,
            "proof_sha256": sha256_json(
                {"engineering": evidence, "review_sha256": result["review_sha256"], "change_proof": change_proof}
            ),
            "codeops_evidence_ref": f"agentops:evidence:{evidence_id.strip()}",
            "engineering_recovered": recovered_result is not None,
        }
        self.store.bind_candidate(evolution_id, candidate)
        review = {
            "verdict": str(result["verdict"]).replace(" ", "_").upper(),
            "review_sha256": result["review_sha256"],
            "candidate_manifest_sha256": manifest_sha,
            "sergeant_evidence": result["evidence"],
        }
        return self._project(self.store.bind_sergeant_review(evolution_id, review))

    def record_canary_from_session(self, evolution_id: str, session_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        gap = _mapping(record, "gap")
        candidate = _mapping(record, "candidate")
        repository_id = str(candidate.get("repository_id") or "")
        if not repository_id:
            raise Phase7RuntimeError("candidate repository_id is missing")
        session = self.origins_client.wait_session(session_id)
        if session.get("state") != "completed" or session.get("exit_code") != 0 or bool(session.get("output_truncated")):
            raise Phase7RuntimeError("canary Session must complete successfully without truncation")
        output = self.origins_client.get_session_output(session_id)
        repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        canary_binding = _validate_canary_binding(gap, candidate, session, repository, repository_diff)
        proof = {
            "session_id": session_id,
            "session_stdout_sha256": session.get("stdout_sha256"),
            "session_stderr_sha256": session.get("stderr_sha256"),
            "candidate_binding": canary_binding,
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
        return self._project(self.store.record_canary(evolution_id, canary))

    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
        normalized = decision.strip().lower()
        candidate_revalidation: dict[str, object] | None = None
        if normalized == "promote":
            record = self.store.get(evolution_id)
            gap = _mapping(record, "gap")
            candidate = _mapping(record, "candidate")
            repository_id = str(candidate.get("repository_id") or "")
            if not repository_id:
                raise Phase7RuntimeError("candidate repository_id is missing")
            repository = self.origins_client.refresh_repository(repository_id)
            repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
            candidate_revalidation = _validate_candidate_repository(gap, candidate, repository, repository_diff)
        return self._project(
            self.store.decide(
                evolution_id,
                decision=normalized,
                decided_by=decided_by,
                candidate_revalidation=candidate_revalidation,
            )
        )

    def resume(self, evolution_id: str) -> dict[str, object]:
        existing = self.store.get(evolution_id)
        record = existing if existing.get("state") == "mission_resumed" else self.store.resume_mission(evolution_id)
        resume = _mapping(record, "resume")
        stores = self.intelligence.agentops._stores()
        stored = _find_resume_evidence(stores.snapshot(), evolution_id, resume)
        if stored is None:
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
        return {"evolution": self._project(record), "agentops_evidence": stored}


def _recover_completed_engineering_evidence(
    snapshot: Mapping[str, object],
    *,
    operation_id: str,
    repository_id: str,
    subject_sha256: str,
) -> dict[str, object] | None:
    raw_items = snapshot.get("evidence")
    if not isinstance(raw_items, list):
        raise Phase7RuntimeError("AgentOps evidence snapshot is malformed")
    matches: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, Mapping) or item.get("source_ref") != f"origins.operation:{operation_id}":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if metadata.get("operation_id") != operation_id or metadata.get("repository_id") != repository_id:
            continue
        if metadata.get("subject_sha256") != subject_sha256 or metadata.get("status") != "completed":
            continue
        if metadata.get("apply_plan") is not True:
            continue
        evidence = metadata.get("origins_attempt_evidence")
        if not isinstance(evidence, Mapping):
            continue
        if evidence.get("operation_id") != operation_id or evidence.get("repository_id") != repository_id:
            continue
        plan_apply_session_id = evidence.get("plan_apply_session_id")
        review_sha256 = evidence.get("review_sha256")
        verdict = str(metadata.get("verdict") or "").replace(" ", "_").upper()
        if not isinstance(plan_apply_session_id, str) or not plan_apply_session_id.strip():
            continue
        if not isinstance(review_sha256, str) or len(review_sha256) != 64:
            continue
        if verdict not in {"PASS", "NEEDS_WORK", "BLOCK"}:
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            continue
        matches.append(
            {
                "verdict": verdict.replace("_", " "),
                "review_sha256": review_sha256,
                "evidence": dict(evidence),
                "agentops_evidence": dict(item),
            }
        )
    if len(matches) > 1:
        raise Phase7RuntimeError("multiple completed AgentOps engineering evidence records match the durable attempt")
    return matches[0] if matches else None


def _find_resume_evidence(
    snapshot: Mapping[str, object], evolution_id: str, resume: Mapping[str, object]
) -> dict[str, object] | None:
    raw_items = snapshot.get("evidence")
    if not isinstance(raw_items, list):
        raise Phase7RuntimeError("AgentOps evidence snapshot is malformed")
    matches: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, Mapping) or item.get("source_ref") != f"origins.evolution:{evolution_id}":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if metadata.get("evolution_id") == evolution_id and metadata.get("resume") == dict(resume):
            matches.append(dict(item))
    if len(matches) > 1:
        raise Phase7RuntimeError("multiple AgentOps Mission-resume evidence records match this evolution")
    return matches[0] if matches else None


def _find_pending_owner_approval(service: object, expected_metadata: Mapping[str, object]) -> str | None:
    list_pending = getattr(service, "list_pending", None)
    if not callable(list_pending):
        raise Phase7RuntimeError("AgentOps approval service does not expose durable pending approvals")
    matches: list[str] = []
    for item in list_pending():
        if not isinstance(item, Mapping):
            continue
        request = item.get("request")
        metadata = request.get("metadata") if isinstance(request, Mapping) else None
        if not isinstance(metadata, Mapping):
            continue
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            continue
        approval_id = request.get("approval_id")
        if isinstance(approval_id, str) and approval_id.strip():
            matches.append(approval_id.strip())
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        raise Phase7RuntimeError("multiple pending AgentOps approvals match the same Phase 7 subject")
    return unique[0] if unique else None


def _engineering_subject(record: Mapping[str, object], payload: Mapping[str, object]) -> dict[str, object]:
    child = _mapping(record, "child_operation")
    command = dict(payload)
    command.pop("approval_id", None)
    command.pop("owner_approved", None)
    command.pop("approval_state", None)
    command["operation_id"] = str(child["operation_id"])
    command["apply_plan"] = True
    command.setdefault("review", "required")
    command.setdefault("client_kind", "terminal")
    command.setdefault("mode", "quick_edit")
    command.setdefault("config", "config/code_ops_switcher.example.json")
    command.setdefault("files", [])
    command.setdefault("plan", "")
    if not isinstance(command.get("plan"), str) or not str(command["plan"]).strip():
        raise Phase7RuntimeError("candidate engineering requires a non-empty CodeOps file-edit plan")
    command["plan"] = str(command["plan"]).strip()
    command.setdefault("provider_id", "")
    command.setdefault("required_capability", "")
    command.setdefault("review_mode", "pull_request")
    if not isinstance(command.get("repository_id"), str) or not str(command["repository_id"]).strip():
        raise Phase7RuntimeError("repository_id is required for candidate engineering")
    if not isinstance(command.get("task"), str) or not str(command["task"]).strip():
        raise Phase7RuntimeError("task is required for candidate engineering")
    return command


def _validate_candidate_repository(
    gap: Mapping[str, object],
    candidate: Mapping[str, object],
    repository: Mapping[str, object],
    diff: Mapping[str, object],
) -> dict[str, object]:
    candidate_repository_id = str(candidate.get("repository_id") or "")
    repository_id = str(repository.get("repository_id") or "")
    if not candidate_repository_id or repository_id != candidate_repository_id:
        raise Phase7RuntimeError("candidate Repository identity does not match the reviewed candidate")
    workspace_id = str(gap.get("workspace_id") or "")
    if not workspace_id or repository.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("candidate Repository is not owned by the original Mission Workspace")
    worktree_root = str(repository.get("worktree_root") or "")
    if not worktree_root:
        raise Phase7RuntimeError("candidate Repository worktree is missing")
    expected_head = str(candidate.get("repository_head_oid") or "")
    if not expected_head or repository.get("head_oid") != expected_head:
        raise Phase7RuntimeError("candidate Repository HEAD changed after review")
    expected_status = str(candidate.get("repository_status_sha256") or "")
    if len(expected_status) != 64 or repository.get("status_sha256") != expected_status:
        raise Phase7RuntimeError("candidate Repository status changed after review")
    if diff.get("kind") != "unstaged" or bool(diff.get("truncated")):
        raise Phase7RuntimeError("candidate requires the complete reviewed unstaged diff")
    expected_diff = str(candidate.get("repository_diff_sha256") or "")
    expected_bytes = candidate.get("repository_diff_bytes")
    if len(expected_diff) != 64 or diff.get("sha256") != expected_diff:
        raise Phase7RuntimeError("candidate Repository diff changed after review")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise Phase7RuntimeError("candidate Repository diff byte count is malformed")
    if diff.get("complete_bytes") != expected_bytes:
        raise Phase7RuntimeError("candidate Repository diff size changed after review")
    return {
        "repository_id": candidate_repository_id,
        "workspace_id": workspace_id,
        "worktree_root": worktree_root,
        "repository_head_oid": expected_head,
        "repository_status_sha256": expected_status,
        "repository_diff_sha256": expected_diff,
        "repository_diff_bytes": expected_bytes,
    }


def _validate_canary_binding(
    gap: Mapping[str, object],
    candidate: Mapping[str, object],
    session: Mapping[str, object],
    repository: Mapping[str, object],
    diff: Mapping[str, object],
) -> dict[str, object]:
    binding = _validate_candidate_repository(gap, candidate, repository, diff)
    workspace_id = str(binding["workspace_id"])
    if session.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("canary Session is not owned by the original Mission Workspace")
    if session.get("workspace_root") != binding["worktree_root"]:
        raise Phase7RuntimeError("canary Session did not execute in the reviewed candidate worktree")
    return binding


def _candidate_change_proof(before: Mapping[str, object], after: Mapping[str, object], diff: Mapping[str, object]) -> dict[str, object]:
    before_id = str(before.get("repository_id") or "")
    after_id = str(after.get("repository_id") or "")
    if not before_id or before_id != after_id:
        raise Phase7RuntimeError("candidate repository identity changed during engineering")
    before_status = str(before.get("status_sha256") or "")
    after_status = str(after.get("status_sha256") or "")
    if len(before_status) != 64 or len(after_status) != 64:
        raise Phase7RuntimeError("candidate repository status evidence is malformed")
    if before_status == after_status:
        raise Phase7RuntimeError("CodeOps candidate did not change repository status")
    if diff.get("kind") != "unstaged":
        raise Phase7RuntimeError("candidate proof requires an unstaged repository diff")
    if bool(diff.get("truncated")):
        raise Phase7RuntimeError("candidate repository diff is truncated")
    diff_bytes = diff.get("complete_bytes")
    if isinstance(diff_bytes, bool) or not isinstance(diff_bytes, int) or diff_bytes < 1:
        raise Phase7RuntimeError("candidate engineering must produce a non-empty tracked repository diff")
    diff_sha = str(diff.get("sha256") or "")
    if len(diff_sha) != 64:
        raise Phase7RuntimeError("candidate repository diff SHA-256 is malformed")
    try:
        int(diff_sha, 16)
    except ValueError as exc:
        raise Phase7RuntimeError("candidate repository diff SHA-256 is malformed") from exc
    return {"repository_id": after_id, "before_status_sha256": before_status, "after_status_sha256": after_status, "diff_sha256": diff_sha.lower(), "diff_bytes": diff_bytes, "post_revision": after.get("revision"), "post_head_oid": after.get("head_oid")}


def _mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise Phase7RuntimeError(f"{field} is missing or malformed")
    return value
