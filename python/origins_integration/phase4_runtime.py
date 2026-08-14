from __future__ import annotations

from datetime import datetime, timezone
import importlib
from typing import Any, Mapping
import uuid

from .intelligence_runtime import (
    IntelligenceApprovalError,
    IntelligenceMountError,
    IntelligenceRequestError,
    IntelligenceRuntime,
)


class _UnavailableStepUpTransport:
    """Fail-closed TTG Auth placeholder. It never grants authority."""

    def consume_step_up_proof(
        self,
        proof_id: str,
        binding: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return {
            "valid": False,
            "reason": "TTG Auth step-up transport is not mounted in Origins Phase 4.",
        }


class Phase4IntelligenceRuntime(IntelligenceRuntime):
    """Phase-4 owner mount with restart-durable AgentOps Operation identity."""

    def operations(self) -> dict[str, object]:
        stores = self.agentops._stores()
        service = stores.department_operation_service(
            authorization_port=self._authorization_port(stores)
        )
        snapshot = stores.snapshot()
        return {
            "owner": "Hunter-AgentOps",
            "operations": service.list_durable_results(),
            "operation_ledger": snapshot.get("operations", []),
            "approvals": snapshot.get("approvals", []),
            "evidence": snapshot.get("evidence", []),
            "audit": snapshot.get("audit", []),
            "lessons": snapshot.get("lessons", []),
        }

    def create_approval(self, payload: dict[str, object]) -> dict[str, object]:
        kind = _required_text(payload, "kind")
        if kind != "operation":
            return super().create_approval(payload)

        subject = payload.get("subject")
        if not isinstance(subject, dict):
            raise IntelligenceRequestError("approval subject must be an object")
        prepared, gate = self._prepare_operation_subject(subject)
        if gate == "none":
            raise IntelligenceRequestError(
                "selected AgentOps playbook does not require an approval"
            )

        reason = _required_text(payload, "reason")
        requested_by = str(
            payload.get("requested_by", "origins-owner-ui")
        ).strip() or "origins-owner-ui"
        stores = self.agentops._stores()
        approval_service = stores.approval_service()
        request = approval_service.create_request(
            task_title=str(prepared["title"]),
            mode=str(prepared["mode"]),
            gate=gate,
            reason=reason,
            requested_by=requested_by,
            target=str(prepared["target"]),
            metadata={
                "origins_approval_kind": "operation",
                "subject": prepared,
            },
        )
        return {
            "owner": "Hunter-AgentOps",
            "approval": approval_service.get_state(request.approval_id).public_dict(),
            "prepared_operation": prepared,
        }

    def run_agentops(self, payload: dict[str, object]) -> dict[str, object]:
        allowed = {
            "approval_id",
            "auth_proof_id",
            "secondary_approval_id",
            "secondary_auth_proof_id",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise IntelligenceRequestError(
                "operation execution accepts only approval/proof references; "
                f"unsupported fields: {', '.join(unknown)}"
            )

        approval_id = _required_text(payload, "approval_id")
        stores = self.agentops._stores()
        approval_service = stores.approval_service()
        try:
            approval = approval_service.get_evidence(approval_id).public_dict()
        except (KeyError, ValueError) as exc:
            raise IntelligenceApprovalError(
                "AgentOps approval evidence is unavailable"
            ) from exc
        if approval.get("status") != "approved":
            raise IntelligenceApprovalError("AgentOps approval is not approved")

        request = approval.get("request")
        metadata = request.get("metadata") if isinstance(request, dict) else None
        if not isinstance(metadata, dict):
            raise IntelligenceApprovalError("AgentOps approval evidence is malformed")
        if metadata.get("origins_approval_kind") != "operation":
            raise IntelligenceApprovalError(
                "AgentOps approval is not an Origins Operation approval"
            )
        prepared = metadata.get("subject")
        if not isinstance(prepared, dict):
            raise IntelligenceApprovalError(
                "AgentOps approval does not contain a prepared Operation"
            )
        packet = dict(prepared)
        gate = str(packet.get("required_gate", ""))
        if gate in {"owner_approval_required", "break_glass_required"}:
            raise IntelligenceMountError(
                "TTG Auth step-up is required for this Operation gate but is not mounted in Origins Phase 4"
            )

        authorization: dict[str, object] = {"approval_id": approval_id}
        for key in (
            "auth_proof_id",
            "secondary_approval_id",
            "secondary_auth_proof_id",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                authorization[key] = value.strip()
        packet["authorization"] = authorization
        packet.pop("playbook_id", None)
        packet.pop("title", None)

        service = stores.department_operation_service(
            authorization_port=self._authorization_port(stores)
        )
        result = service.submit_operation(packet)
        if not isinstance(result, dict):
            raise IntelligenceMountError(
                "AgentOps DepartmentOperationService returned a non-object"
            )
        return result

    def _prepare_operation_subject(
        self,
        subject: dict[str, object],
    ) -> tuple[dict[str, object], str]:
        forbidden = {
            "operation_id",
            "created_at",
            "authorization",
            "required_gate",
            "mode",
            "domain",
            "operation_type",
            "source",
            "dry_run",
        }
        supplied_forbidden = sorted(forbidden.intersection(subject))
        if supplied_forbidden:
            raise IntelligenceRequestError(
                "Operation identity/authority fields are runtime-owned; remove: "
                + ", ".join(supplied_forbidden)
            )

        playbook_id = _required_text(subject, "playbook")
        path = self.agentops._playbook_path(playbook_id)
        try:
            playbook = self.agentops._load_playbook(path)
        except Exception as exc:
            raise IntelligenceMountError(
                f"AgentOps playbook rejected by its owner: {type(exc).__name__}"
            ) from exc

        title = _required_text(subject, "title")
        target = _required_text(subject, "target")
        action = _required_text(subject, "requested_action")
        risk = str(subject.get("risk", "medium")).strip().lower() or "medium"
        if risk not in {"low", "medium", "high", "critical"}:
            raise IntelligenceRequestError("risk must be low, medium, high, or critical")
        operation_subject = str(subject.get("subject", target)).strip() or target
        subject_type = str(subject.get("subject_type", "repository")).strip() or "repository"
        requested_by = str(subject.get("requested_by", "origins-factory")).strip() or "origins-factory"

        evidence_raw = subject.get("evidence", {})
        if not isinstance(evidence_raw, dict):
            raise IntelligenceRequestError("Operation evidence must be an object")
        evidence: dict[str, object] = dict(evidence_raw)
        evidence.setdefault("repo_path", target)
        evidence.setdefault("task_goal", title)
        missing = [
            name
            for name in playbook.requires
            if not isinstance(evidence.get(name), str) or not str(evidence.get(name)).strip()
        ]
        if missing:
            raise IntelligenceRequestError(
                "AgentOps playbook requirements are missing: " + ", ".join(missing)
            )

        operation_id = f"origins-{uuid.uuid4()}"
        evidence_refs_raw = evidence.get("evidence_refs", [])
        if evidence_refs_raw is None:
            evidence_refs_raw = []
        if not isinstance(evidence_refs_raw, list) or any(
            not isinstance(item, str) for item in evidence_refs_raw
        ):
            raise IntelligenceRequestError("evidence_refs must be a list of strings")
        evidence_refs = [item.strip() for item in evidence_refs_raw if item.strip()]
        evidence_refs.append(f"origins:operation:{operation_id}")
        evidence["evidence_refs"] = list(dict.fromkeys(evidence_refs))

        prepared: dict[str, object] = {
            "schema_version": "hunter.agentops.operation-request.v1",
            "operation_id": operation_id,
            "domain": str(playbook.name),
            "operation_type": f"{playbook.name}.operation",
            "action": action,
            "mode": str(playbook.mode),
            "risk": risk,
            "required_gate": str(playbook.approval),
            "target": target,
            "subject": operation_subject,
            "subject_type": subject_type,
            "requested_by": requested_by,
            "authorization": {},
            "evidence": evidence,
            "dry_run": False,
            "source": "origins-factory",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "playbook_id": playbook_id,
            "title": title,
        }
        return prepared, str(playbook.approval)

    @staticmethod
    def _authorization_port(stores: Any) -> Any:
        try:
            module = importlib.import_module("agentops.auth_step_up")
            port_type = getattr(module, "TtgAuthAuthorizationPort")
        except (ImportError, AttributeError) as exc:
            raise IntelligenceMountError(
                "AgentOps authorization owner interface is unavailable"
            ) from exc
        return port_type(stores.approval_service(), _UnavailableStepUpTransport())


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntelligenceRequestError(f"{key} is required")
    return value.strip()
