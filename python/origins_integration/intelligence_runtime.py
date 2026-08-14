from __future__ import annotations

import importlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capability_proposals import CapabilityProposal, CapabilityProposalError
from .engineering import BridgeError, EngineeringAttemptRequest, EngineeringBridge, IntegrationUnavailable, OriginsClient


class IntelligenceMountError(RuntimeError):
    """Raised when an owning intelligence/assurance runtime cannot be used safely."""


@dataclass(frozen=True)
class OwnerStatus:
    owner: str
    configured: bool
    available: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "configured": self.configured,
            "available": self.available,
            "detail": self.detail,
        }


class AgentOpsMount:
    """Thin mount over AgentOps-owned durable stores, approvals, evidence, and BridgeApi."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self._stores_type: Any | None = None
        self._bridge_type: Any | None = None
        self._evidence_type: Any | None = None
        self._import_error = ""
        try:
            storage = importlib.import_module("agentops.storage")
            bridge = importlib.import_module("agentops.bridge_api")
            evidence = importlib.import_module("agentops.evidence")
            self._stores_type = getattr(storage, "PersistentAgentOpsStores")
            self._bridge_type = getattr(bridge, "BridgeApi")
            self._evidence_type = getattr(evidence, "EvidenceItem")
        except (ImportError, AttributeError) as exc:
            self._import_error = str(exc)

    @classmethod
    def from_env(cls) -> "AgentOpsMount":
        raw = os.environ.get("ORIGINS_AGENTOPS_DATA_DIR", "").strip()
        return cls(Path(raw).expanduser() if raw else None)

    def status(self) -> OwnerStatus:
        configured = self.data_dir is not None
        available = (
            configured
            and self._stores_type is not None
            and self._bridge_type is not None
            and self._evidence_type is not None
        )
        if not configured:
            detail = "ORIGINS_AGENTOPS_DATA_DIR is not configured"
        elif not available:
            detail = f"AgentOps owner package unavailable: {self._import_error or 'incomplete owner interface'}"
        else:
            detail = "AgentOps durable owner mounted"
        return OwnerStatus("Hunter-AgentOps", configured, available, detail)

    def _stores(self) -> Any:
        self._require_available()
        return self._stores_type(self.data_dir)

    def snapshot(self) -> dict[str, object]:
        snapshot = self._stores().snapshot()
        return {
            "owner": "Hunter-AgentOps",
            "operations": snapshot.get("operations", []),
            "approvals": snapshot.get("approvals", []),
            "evidence": snapshot.get("evidence", []),
            "audit": snapshot.get("audit", []),
            "lessons": snapshot.get("lessons", []),
        }

    def pending_approvals(self) -> dict[str, object]:
        service = self._stores().approval_service()
        return {"owner": "Hunter-AgentOps", "pending": service.list_pending()}

    def create_approval(self, payload: dict[str, object]) -> dict[str, object]:
        kind = _required_text(payload, "kind")
        if kind not in {"operation", "engineering"}:
            raise IntelligenceMountError("approval kind must be operation or engineering")
        subject = payload.get("subject")
        if not isinstance(subject, dict):
            raise IntelligenceMountError("approval subject must be an object")
        canonical = _approval_subject(kind, subject)
        reason = _required_text(payload, "reason")
        requested_by = str(payload.get("requested_by", "origins-owner-ui")).strip() or "origins-owner-ui"
        service = self._stores().approval_service()
        request = service.create_request(
            task_title=_approval_task_title(kind, canonical),
            mode=f"origins_{kind}",
            gate="owner_approval_required",
            reason=reason,
            requested_by=requested_by,
            target=_approval_target(kind, canonical),
            metadata={"origins_approval_kind": kind, "subject": canonical},
        )
        return {"owner": "Hunter-AgentOps", "approval": service.get_state(request.approval_id).public_dict()}

    def decide_approval(self, payload: dict[str, object]) -> dict[str, object]:
        approval_id = _required_text(payload, "approval_id")
        decision = _required_text(payload, "decision")
        if decision not in {"approved", "rejected"}:
            raise IntelligenceMountError("decision must be approved or rejected")
        decided_by = _required_text(payload, "decided_by")
        note_raw = payload.get("note")
        note = None if note_raw is None else str(note_raw).strip() or None
        service = self._stores().approval_service()
        state = service.decide(approval_id, decision, decided_by, note=note)
        evidence = service.get_evidence(approval_id)
        return {
            "owner": "Hunter-AgentOps",
            "approval": state.public_dict(),
            "evidence": evidence.public_dict(),
        }

    def record_engineering_attempt(
        self,
        *,
        subject: dict[str, object],
        status: str,
        verdict: str = "",
        recommendation: str = "",
        evidence: dict[str, object] | None = None,
        failure_type: str = "",
    ) -> dict[str, object]:
        operation_id = str(subject.get("operation_id", "")).strip()
        repository_id = str(subject.get("repository_id", "")).strip()
        metadata: dict[str, object] = {
            "operation_id": operation_id,
            "repository_id": repository_id,
            "provider_id": str(subject.get("provider_id", "")),
            "mode": str(subject.get("mode", "quick_edit")),
            "apply_plan": bool(subject.get("apply_plan", False)),
            "status": status,
        }
        if verdict:
            metadata["verdict"] = verdict
        if recommendation:
            metadata["recommended_agentops_action"] = recommendation
        if evidence is not None:
            metadata["origins_attempt_evidence"] = evidence
        if failure_type:
            metadata["failure_type"] = failure_type
        summary = (
            f"Sergeant verdict {verdict}; AgentOps recommendation {recommendation}."
            if status == "completed"
            else f"Engineering attempt retained as {status}; see Origins mechanical Session evidence."
        )
        item = self._evidence_type(
            title="Origins engineering attempt",
            kind="tool_result",
            summary=summary,
            source_ref=f"origins.operation:{operation_id}" if operation_id else None,
            metadata=metadata,
        )
        stored = self._stores().save_evidence(item)
        if not isinstance(stored, dict):
            raise IntelligenceMountError("AgentOps evidence store returned a non-object")
        return stored

    def _approved(self, kind: str, subject: dict[str, object], approval_id: str) -> bool:
        service = self._stores().approval_service()
        try:
            evidence = service.get_evidence(approval_id)
        except (KeyError, ValueError) as exc:
            raise IntelligenceMountError(f"AgentOps approval unavailable: {exc}") from exc
        public = evidence.public_dict()
        request = public.get("request")
        if not isinstance(request, dict):
            raise IntelligenceMountError("AgentOps approval evidence is malformed")
        metadata = request.get("metadata")
        if not isinstance(metadata, dict):
            raise IntelligenceMountError("AgentOps approval evidence metadata is malformed")
        if metadata.get("origins_approval_kind") != kind or metadata.get("subject") != _approval_subject(kind, subject):
            raise IntelligenceMountError("AgentOps approval is not bound to this exact request")
        if public.get("status") != "approved":
            raise IntelligenceMountError("AgentOps approval is not approved")
        return True

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        if "owner_approved" in payload:
            raise IntelligenceMountError("owner_approved cannot be asserted by the client; use AgentOps approval evidence")
        command = dict(payload)
        approval_id = str(command.pop("approval_id", "")).strip()
        command["owner_approved"] = bool(approval_id and self._approved("operation", command, approval_id))
        stores = self._stores()
        response = self._bridge_type(stores=stores).run(command)
        public = response.public_dict()
        if not isinstance(public, dict):
            raise IntelligenceMountError("AgentOps BridgeApi returned a non-object public payload")
        return public

    def approval_state_for_engineering(self, payload: dict[str, object]) -> str:
        if "approval_state" in payload:
            raise IntelligenceMountError("approval_state cannot be asserted by the client; use AgentOps approval evidence")
        if not bool(payload.get("apply_plan", False)):
            return "not_required"
        approval_id = str(payload.get("approval_id", "")).strip()
        if not approval_id:
            raise IntelligenceMountError("apply_plan requires an approved AgentOps approval_id")
        return "approved" if self._approved("engineering", payload, approval_id) else "required"

    def _require_available(self) -> None:
        status = self.status()
        if not status.available:
            raise IntelligenceMountError(status.detail)


class CodeOpsMount:
    """Safe provider-registry projection owned by Hunter CodeOps."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path
        self._loader: Any | None = None
        self._import_error = ""
        try:
            module = importlib.import_module("hunter_codeops.code_ops_switcher")
            self._loader = getattr(module, "load_switcher_config")
        except (ImportError, AttributeError) as exc:
            self._import_error = str(exc)

    @classmethod
    def from_env(cls) -> "CodeOpsMount":
        raw = os.environ.get("ORIGINS_CODEOPS_CONFIG", "").strip()
        return cls(Path(raw).expanduser() if raw else None)

    def status(self) -> OwnerStatus:
        configured = self.config_path is not None
        available = configured and self._loader is not None and self.config_path.is_file()
        if not configured:
            detail = "ORIGINS_CODEOPS_CONFIG is not configured"
        elif self._loader is None:
            detail = f"CodeOps owner package unavailable: {self._import_error or 'unknown import failure'}"
        elif not self.config_path.is_file():
            detail = "CodeOps config path is configured but unavailable"
        else:
            detail = "CodeOps provider registry mounted"
        return OwnerStatus("hunter-codeops", configured, available, detail)

    def providers(self) -> dict[str, object]:
        status = self.status()
        if not status.available:
            raise IntelligenceMountError(status.detail)
        config = self._loader(self.config_path)
        providers: list[dict[str, object]] = []
        for provider in config.providers:
            providers.append(
                {
                    "id": provider.id,
                    "kind": provider.kind.value,
                    "model": provider.model,
                    "priority": provider.priority,
                    "endpoint": provider.endpoint,
                    "enabled": provider.enabled,
                    "local": provider.local,
                    "credential_env": provider.credential_env,
                    "credential_present": bool(provider.credential_env and os.environ.get(provider.credential_env)),
                    "capabilities": list(provider.capabilities),
                    "notes": provider.notes,
                }
            )
        return {
            "owner": "hunter-codeops",
            "default_review": config.default_review.value,
            "providers": providers,
        }


class SergeantMount:
    """Availability projection only; verdict semantics remain Sergeant-owned."""

    def __init__(self, command: str = "sergeant") -> None:
        self.command = command

    def status(self) -> OwnerStatus:
        resolved = shutil.which(self.command)
        return OwnerStatus(
            owner="Sergeant",
            configured=True,
            available=resolved is not None,
            detail=("Sergeant CLI mounted" if resolved else "Sergeant CLI not found"),
        )


class IntelligenceRuntime:
    """Phase-4 semantic plane. It projects owner state; it does not become owner."""

    def __init__(
        self,
        *,
        agentops: AgentOpsMount | None = None,
        codeops: CodeOpsMount | None = None,
        sergeant: SergeantMount | None = None,
        origins_client: OriginsClient | None = None,
    ) -> None:
        self.agentops = agentops or AgentOpsMount.from_env()
        self.codeops = codeops or CodeOpsMount.from_env()
        self.sergeant = sergeant or SergeantMount(os.environ.get("ORIGINS_SERGEANT_COMMAND", "sergeant"))
        self.origins_client = origins_client

    @classmethod
    def from_env(cls) -> "IntelligenceRuntime":
        client: OriginsClient | None = None
        try:
            client = OriginsClient.from_env()
        except Exception:
            client = None
        return cls(origins_client=client)

    def health(self) -> dict[str, object]:
        owners = [self.agentops.status(), self.codeops.status(), self.sergeant.status()]
        return {
            "ok": True,
            "service": "origins-intelligence",
            "api_version": "v1",
            "owners": {status.owner: status.as_dict() for status in owners},
            "mechanical_originsd_configured": self.origins_client is not None,
        }

    def operations(self) -> dict[str, object]:
        return self.agentops.snapshot()

    def approvals(self) -> dict[str, object]:
        return self.agentops.pending_approvals()

    def create_approval(self, payload: dict[str, object]) -> dict[str, object]:
        return self.agentops.create_approval(payload)

    def decide_approval(self, payload: dict[str, object]) -> dict[str, object]:
        return self.agentops.decide_approval(payload)

    def run_agentops(self, payload: dict[str, object]) -> dict[str, object]:
        return self.agentops.run(payload)

    def providers(self) -> dict[str, object]:
        return self.codeops.providers()

    def compile_capability(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            proposal = CapabilityProposal.create(
                workspace_id=_required_text(payload, "workspace_id"),
                task_title=_required_text(payload, "task_title"),
                capability_id=_required_text(payload, "capability_id"),
                reason=_required_text(payload, "reason"),
                expected_benefit=_required_text(payload, "expected_benefit"),
                requested_effects=_string_tuple(payload.get("requested_effects")),
                filesystem_read_scope=_string_tuple(payload.get("filesystem_read_scope")),
                filesystem_write_scope=_string_tuple(payload.get("filesystem_write_scope")),
                network_mode=str(payload.get("network_mode", "deny")),  # type: ignore[arg-type]
                network_hosts=_string_tuple(payload.get("network_hosts")),
                environment_names=_string_tuple(payload.get("environment_names")),
                persistent_lease=bool(payload.get("persistent_lease", False)),
                delegated_remote_authority=bool(payload.get("delegated_remote_authority", False)),
                alternatives=_string_tuple(payload.get("alternatives")),
                risks=_string_tuple(payload.get("risks")),
                requested_by=str(payload.get("requested_by", "hunter")),
            )
        except (CapabilityProposalError, TypeError, ValueError) as exc:
            raise IntelligenceMountError(f"capability proposal rejected: {exc}") from exc
        return {
            "proposal": proposal.as_dict(),
            "agentops_approval_request": proposal.agentops_approval_request(),
            "activation": "not_activated",
            "owner_approval_required": True,
        }

    def engineering_attempt(self, payload: dict[str, object]) -> dict[str, object]:
        if self.origins_client is None:
            raise IntelligenceMountError("originsd mechanical client is not configured")
        approval_state = self.agentops.approval_state_for_engineering(payload)
        request = EngineeringAttemptRequest(
            operation_id=_required_text(payload, "operation_id"),
            repository_id=_required_text(payload, "repository_id"),
            task=_required_text(payload, "task"),
            config=str(payload.get("config", "config/code_ops_switcher.example.json")),
            files=_string_tuple(payload.get("files")),
            plan=str(payload.get("plan", "")),
            apply_plan=bool(payload.get("apply_plan", False)),
            approval_state=approval_state,
            client_kind=str(payload.get("client_kind", "terminal")),
            mode=str(payload.get("mode", "quick_edit")),
            provider_id=str(payload.get("provider_id", "")),
            required_capability=str(payload.get("required_capability", "")),
            review=str(payload.get("review", "required")),
            review_mode=str(payload.get("review_mode", "pull_request")),
        )
        try:
            result = EngineeringBridge(self.origins_client).run_attempt(request)
        except (IntegrationUnavailable, BridgeError) as exc:
            self.agentops.record_engineering_attempt(
                subject=payload,
                status="failed",
                failure_type=type(exc).__name__,
            )
            raise IntelligenceMountError(str(exc)) from exc
        evidence_record = result.evidence_record()
        stored_evidence = self.agentops.record_engineering_attempt(
            subject=payload,
            status="completed",
            verdict=result.verdict,
            recommendation=result.recommended_agentops_action,
            evidence=evidence_record,
        )
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
            "evidence": evidence_record,
            "agentops_evidence": stored_evidence,
        }


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntelligenceMountError(f"{key} is required")
    return value.strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise IntelligenceMountError("expected a list of strings")
    return tuple(item for item in value if item)


def _approval_subject(kind: str, subject: dict[str, object]) -> dict[str, object]:
    canonical = dict(subject)
    canonical.pop("approval_id", None)
    canonical.pop("owner_approved", None)
    canonical.pop("approval_state", None)
    if kind == "engineering" and not bool(canonical.get("apply_plan", False)):
        raise IntelligenceMountError("engineering approval is only valid for apply_plan=true")
    return canonical


def _approval_task_title(kind: str, subject: dict[str, object]) -> str:
    key = "title" if kind == "operation" else "task"
    value = subject.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"Origins {kind} approval"


def _approval_target(kind: str, subject: dict[str, object]) -> str:
    if kind == "engineering":
        operation_id = subject.get("operation_id")
        repository_id = subject.get("repository_id")
        if isinstance(operation_id, str) and operation_id and isinstance(repository_id, str) and repository_id:
            return f"{operation_id}:{repository_id}"
    target = subject.get("target")
    return target.strip() if isinstance(target, str) and target.strip() else f"origins:{kind}"
