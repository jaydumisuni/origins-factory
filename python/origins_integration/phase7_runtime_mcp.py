from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .agentops_mcp import AgentOpsMcpClient
from .capability_evolution import CapabilityEvolutionError, CapabilityEvolutionStore, sha256_json
from .capability_evolution_approvals import EvolutionApprovalBindings, EvolutionEngineeringApprovalBindings
from .capability_proposals import CapabilityProposal
from .engineering import BridgeError, EngineeringAttemptRequest, EngineeringBridge, IntegrationUnavailable, OriginsClient
from .intelligence_runtime import IntelligenceRuntime
from .phase7_agentops import Phase7AgentOpsCoordinator
from .phase7_mcp_state import Phase7McpState, Phase7McpStateError


class Phase7RuntimeError(RuntimeError):
    pass


class Phase7Runtime:
    """Coordinates Phase 7 while preserving cross-owner MCP/RPC authority boundaries."""

    def __init__(
        self,
        *,
        store: CapabilityEvolutionStore,
        intelligence: IntelligenceRuntime,
        origins_client: OriginsClient,
        approvals: EvolutionApprovalBindings | None = None,
        engineering_approvals: EvolutionEngineeringApprovalBindings | None = None,
        agentops: Phase7AgentOpsCoordinator | None = None,
        mcp_state: Phase7McpState | None = None,
        engineering_bridge: object | None = None,
    ) -> None:
        self.store = store
        self.intelligence = intelligence
        self.origins_client = origins_client
        self.approvals = approvals or EvolutionApprovalBindings(store.path)
        self.engineering_approvals = engineering_approvals or EvolutionEngineeringApprovalBindings(store.path)
        self.agentops = agentops
        self.mcp_state = mcp_state or Phase7McpState(store.path)
        self.engineering_bridge = engineering_bridge

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
        approvals = EvolutionApprovalBindings(path)
        engineering_approvals = EvolutionEngineeringApprovalBindings(path)
        agentops = Phase7AgentOpsCoordinator(
            mcp=AgentOpsMcpClient.from_env(),
            approvals=approvals,
            engineering_approvals=engineering_approvals,
        )
        return cls(
            store=CapabilityEvolutionStore(path),
            approvals=approvals,
            engineering_approvals=engineering_approvals,
            intelligence=intelligence,
            origins_client=client,
            agentops=agentops,
            mcp_state=Phase7McpState(path),
        )

    def _agentops(self) -> Phase7AgentOpsCoordinator:
        if self.agentops is None:
            raise Phase7RuntimeError("AgentOps MCP coordinator is not configured")
        return self.agentops

    def _bridge(self):
        if self.engineering_bridge is not None:
            return self.engineering_bridge
        return EngineeringBridge(self.origins_client)

    def health(self) -> dict[str, object]:
        return {
            "phase": 7,
            "mode": "controlled_capability_evolution",
            "runtime_authority_expansion": False,
            "model_self_approval": False,
            "agentops_transport": "mcp/rpc",
            "agentops_service_credential_is_owner_authorization": False,
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
        return self._agentops().request_capability_approval(
            evolution_id=evolution_id,
            proposal=_mapping(record, "proposal"),
            gap=_mapping(record, "gap"),
        )

    def refresh_approval(self, evolution_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "proposal_ready":
            raise CapabilityEvolutionError("capability approval refresh requires a proposal-ready evolution")
        return self._agentops().refresh_capability_approval(
            evolution_id=evolution_id,
            proposal=_mapping(record, "proposal"),
        )

    def create_child_upgrade_operation(self, evolution_id: str, approval_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "proposal_ready":
            raise CapabilityEvolutionError("child upgrade Operation requires a proposal-ready evolution")
        proposal = _mapping(record, "proposal")
        gap = _mapping(record, "gap")
        refreshed = self._agentops().refresh_capability_approval(evolution_id=evolution_id, proposal=proposal)
        evidence = _mapping(refreshed, "evidence")
        binding = _mapping(refreshed, "binding")
        if evidence.get("status") != "approved" or binding.get("status") != "approved":
            raise CapabilityEvolutionError("AgentOps capability approval is not approved")
        if binding.get("approval_id") != approval_id:
            raise Phase7RuntimeError("AgentOps capability approval ID does not match the durable binding")
        child = self._agentops().start_upgrade_operation(
            evolution_id=evolution_id,
            proposal=proposal,
            gap=gap,
            approval_id=approval_id,
        )
        return self._project(
            self.store.bind_child_operation(
                evolution_id,
                approval={
                    "status": "approved",
                    "approval_id": approval_id,
                    "request_digest": binding["request_digest"],
                    "evidence_sha256": sha256_json(evidence),
                    "transport": "mcp/rpc",
                },
                child_operation=child,
            )
        )

    def create_engineering_approval(self, evolution_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") != "upgrade_operation_ready":
            raise CapabilityEvolutionError("engineering approval requires a ready child upgrade Operation")
        subject = _engineering_subject(record, payload)
        return self._agentops().request_engineering_approval(evolution_id=evolution_id, subject=subject)

    def refresh_engineering_approval(self, evolution_id: str) -> dict[str, object]:
        record = self.store.get(evolution_id)
        if record.get("state") not in {"upgrade_operation_ready", "engineering_started", "candidate_proven"}:
            raise CapabilityEvolutionError("engineering approval refresh requires an active engineering evolution")
        binding = self.engineering_approvals.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps engineering approval binding")
        subject = binding.get("subject")
        if not isinstance(subject, Mapping) or not subject:
            raise Phase7RuntimeError("durable engineering approval binding omitted the exact subject")
        return self._agentops().refresh_engineering_approval(evolution_id=evolution_id, subject=subject)

    def implement_candidate(self, evolution_id: str, payload: dict[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        state = str(record.get("state") or "")
        if state not in {"upgrade_operation_ready", "engineering_started", "candidate_proven"}:
            raise CapabilityEvolutionError(
                "candidate implementation requires a ready or restart-recoverable child upgrade Operation"
            )
        subject = _engineering_subject(record, payload)
        refreshed = self._agentops().refresh_engineering_approval(evolution_id=evolution_id, subject=subject)
        binding = _mapping(refreshed, "binding")
        if binding.get("status") != "approved":
            raise CapabilityEvolutionError("AgentOps engineering approval binding is not approved")
        self.engineering_approvals.require_approved(evolution_id, subject)

        repository_id = str(subject["repository_id"])
        subject_sha256 = sha256_json(subject)
        operation_id = str(subject["operation_id"])
        recovered_result: dict[str, object] | None = None
        stored_result: dict[str, object] | None = None

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
            state = "engineering_started"
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
            stored_result = self.mcp_state.get_engineering_result(evolution_id)
            if stored_result is not None:
                if (
                    stored_result.get("operation_id") != operation_id
                    or stored_result.get("repository_id") != repository_id
                    or stored_result.get("subject_sha256") != subject_sha256
                ):
                    raise Phase7RuntimeError("stored engineering result does not match the durable attempt identity")
                recovered = stored_result.get("result")
                if not isinstance(recovered, dict):
                    raise Phase7RuntimeError("stored engineering result is malformed")
                recovered_result = recovered
            current = self.origins_client.refresh_repository(repository_id)
            changed = (
                current.get("status_sha256") != pre_repository.get("status_sha256")
                or current.get("head_oid") != pre_repository.get("head_oid")
            )
            if recovered_result is None and changed:
                raise Phase7RuntimeError(
                    "candidate engineering was interrupted after repository change without completed Origins recovery evidence; "
                    "restore the candidate worktree to the durable pre-engineering state before retrying"
                )

        if recovered_result is None:
            result = self._run_engineering(subject)
            stored_result = self.mcp_state.bind_engineering_result(
                evolution_id,
                operation_id=operation_id,
                repository_id=repository_id,
                subject_sha256=subject_sha256,
                result=result,
            )
        else:
            result = recovered_result
            assert stored_result is not None

        post_repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        change_proof = _candidate_change_proof(pre_repository, post_repository, repository_diff)
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise Phase7RuntimeError("CodeOps engineering result omitted retained evidence")
        review_sha = str(result.get("review_sha256") or "")
        if len(review_sha) != 64:
            raise Phase7RuntimeError("Sergeant review SHA-256 is missing or malformed")
        verdict = str(result.get("verdict") or "").replace("_", " ").upper()
        if verdict not in {"PASS", "NEEDS WORK", "BLOCK"}:
            raise Phase7RuntimeError("CodeOps engineering result returned an unsupported Sergeant verdict")

        proposal = _mapping(record, "proposal")
        current = self.store.active_generation(str(proposal["capability_id"]))
        base_generation = int(current["generation"]) if current else 0
        base_manifest_sha256 = str(current["manifest_sha256"]) if current else None
        base_evolution_id = str(current["evolution_id"]) if current else None
        generation = base_generation + 1
        engineering_ref = f"origins:phase7-engineering:{stored_result['result_sha256']}"
        codeops_ref = f"origins:codeops-evidence:{sha256_json(evidence)}"
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
                {"engineering": evidence, "review_sha256": review_sha, "change_proof": change_proof}
            ),
            "codeops_evidence_ref": codeops_ref,
            "engineering_result_ref": engineering_ref,
            "engineering_recovered": recovered_result is not None,
        }
        review = {
            "verdict": verdict.replace(" ", "_"),
            "review_sha256": review_sha,
            "candidate_manifest_sha256": manifest_sha,
            "sergeant_evidence": evidence,
        }
        child = _mapping(record, "child_operation")
        outcome = "completed" if verdict == "PASS" else "blocked" if verdict == "BLOCK" else "failed"
        self._agentops().finalize_upgrade_operation(
            child_operation=child,
            outcome=outcome,
            result_ref=f"origins:candidate:{manifest_sha}",
            evidence_refs=[engineering_ref, codeops_ref, f"sergeant:review:{review_sha}"],
        )

        current_record = self.store.get(evolution_id)
        current_state = str(current_record.get("state") or "")
        if current_state == "engineering_started":
            self.store.bind_candidate(evolution_id, candidate)
            return self._project(self.store.bind_sergeant_review(evolution_id, review))
        if current_state == "candidate_proven":
            existing_candidate = _mapping(current_record, "candidate")
            if existing_candidate.get("manifest_sha256") != manifest_sha:
                raise Phase7RuntimeError("candidate recovery does not match the already-proven manifest")
            return self._project(self.store.bind_sergeant_review(evolution_id, review))
        raise Phase7RuntimeError(f"unexpected evolution state during candidate recovery: {current_state}")

    def _run_engineering(self, subject: Mapping[str, object]) -> dict[str, object]:
        request = EngineeringAttemptRequest(
            operation_id=str(subject["operation_id"]),
            repository_id=str(subject["repository_id"]),
            task=str(subject["task"]),
            config=str(subject.get("config", "config/code_ops_switcher.example.json")),
            files=tuple(str(item) for item in subject.get("files", [])),
            plan=str(subject.get("plan", "")),
            apply_plan=True,
            approval_state="approved",
            client_kind=str(subject.get("client_kind", "terminal")),
            mode=str(subject.get("mode", "quick_edit")),
            provider_id=str(subject.get("provider_id", "")),
            required_capability=str(subject.get("required_capability", "")),
            review=str(subject.get("review", "required")),
            review_mode=str(subject.get("review_mode", "pull_request")),
        )
        try:
            result = self._bridge().run_attempt(request)
        except IntegrationUnavailable as exc:
            raise Phase7RuntimeError(str(exc)) from exc
        except BridgeError as exc:
            raise Phase7RuntimeError("engineering attempt failed; inspect retained Origins Session evidence") from exc
        evidence = result.evidence_record()
        return {
            "operation_id": result.operation_id,
            "repository_id": result.repository_id,
            "repository_revision": result.repository_revision,
            "repository_head_oid": result.repository_head_oid,
            "verdict": result.verdict,
            "needs_loop": result.needs_loop,
            "blocked": result.blocked,
            "summary": result.summary,
            "recommended_agentops_action": result.recommended_agentops_action,
            "review_sha256": result.review_sha256,
            "evidence": evidence,
        }

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
        child = _mapping(existing, "child_operation")
        owner = self._agentops().get_upgrade_operation(child)
        operation = _mapping(owner, "operation")
        if operation.get("state") != "completed" or operation.get("outcome") != "completed":
            raise Phase7RuntimeError("AgentOps capability-upgrade operation is not durably completed")
        record = existing if existing.get("state") == "mission_resumed" else self.store.resume_mission(evolution_id)
        return {"evolution": self._project(record), "agentops_operation": owner}


def _engineering_subject(record: Mapping[str, object], payload: Mapping[str, object]) -> dict[str, object]:
    child = _mapping(record, "child_operation")
    command = dict(payload)
    for field in ("approval_id", "owner_approved", "approval_state", "decided_by", "decision"):
        command.pop(field, None)
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
    files = command.get("files")
    if not isinstance(files, list) or any(not isinstance(item, str) for item in files):
        raise Phase7RuntimeError("files must be a list of strings")
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


def _candidate_change_proof(
    before: Mapping[str, object], after: Mapping[str, object], diff: Mapping[str, object]
) -> dict[str, object]:
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
    return {
        "repository_id": after_id,
        "before_status_sha256": before_status,
        "after_status_sha256": after_status,
        "diff_sha256": diff_sha.lower(),
        "diff_bytes": diff_bytes,
        "post_revision": after.get("revision"),
        "post_head_oid": after.get("head_oid"),
    }


def _mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise Phase7RuntimeError(f"{field} is missing or malformed")
    return value
