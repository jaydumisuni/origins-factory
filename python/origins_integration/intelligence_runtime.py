from __future__ import annotations

import importlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capability_proposals import CapabilityProposal, CapabilityProposalError
from .engineering import EngineeringAttemptRequest, EngineeringBridge, IntegrationUnavailable, OriginsClient


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
    """Thin mount over AgentOps-owned durable stores and BridgeApi."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self._stores_type: Any | None = None
        self._bridge_type: Any | None = None
        self._import_error = ""
        try:
            storage = importlib.import_module("agentops.storage")
            bridge = importlib.import_module("agentops.bridge_api")
            self._stores_type = getattr(storage, "PersistentAgentOpsStores")
            self._bridge_type = getattr(bridge, "BridgeApi")
        except (ImportError, AttributeError) as exc:
            self._import_error = str(exc)

    @classmethod
    def from_env(cls) -> "AgentOpsMount":
        raw = os.environ.get("ORIGINS_AGENTOPS_DATA_DIR", "").strip()
        return cls(Path(raw).expanduser() if raw else None)

    def status(self) -> OwnerStatus:
        configured = self.data_dir is not None
        available = configured and self._stores_type is not None and self._bridge_type is not None
        if not configured:
            detail = "ORIGINS_AGENTOPS_DATA_DIR is not configured"
        elif self._stores_type is None or self._bridge_type is None:
            detail = f"AgentOps owner package unavailable: {self._import_error or 'unknown import failure'}"
        else:
            detail = "AgentOps durable owner mounted"
        return OwnerStatus("Hunter-AgentOps", configured, available, detail)

    def snapshot(self) -> dict[str, object]:
        self._require_available()
        stores = self._stores_type(self.data_dir)
        snapshot = stores.snapshot()
        return {
            "owner": "Hunter-AgentOps",
            "data_dir": str(self.data_dir),
            "operations": snapshot.get("operations", []),
            "approvals": snapshot.get("approvals", []),
            "evidence": snapshot.get("evidence", []),
            "audit": snapshot.get("audit", []),
            "lessons": snapshot.get("lessons", []),
        }

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        self._require_available()
        stores = self._stores_type(self.data_dir)
        response = self._bridge_type(stores=stores).run(payload)
        public = response.public_dict()
        if not isinstance(public, dict):
            raise IntelligenceMountError("AgentOps BridgeApi returned a non-object public payload")
        return public

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
            detail = f"CodeOps config does not exist: {self.config_path}"
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
                    "credential_present": bool(
                        provider.credential_env and os.environ.get(provider.credential_env)
                    ),
                    "capabilities": list(provider.capabilities),
                    "notes": provider.notes,
                }
            )
        return {
            "owner": "hunter-codeops",
            "config": str(self.config_path),
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
            detail=(f"Sergeant CLI mounted at {resolved}" if resolved else f"Sergeant CLI not found: {self.command}"),
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
            # Model-free / semantic-plane-only startup remains valid. Engineering attempts
            # will report the missing mechanical authority truthfully when invoked.
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
        request = EngineeringAttemptRequest(
            operation_id=_required_text(payload, "operation_id"),
            repository_id=_required_text(payload, "repository_id"),
            task=_required_text(payload, "task"),
            config=str(payload.get("config", "config/code_ops_switcher.example.json")),
            files=_string_tuple(payload.get("files")),
            plan=str(payload.get("plan", "")),
            apply_plan=bool(payload.get("apply_plan", False)),
            approval_state=str(payload.get("approval_state", "not_required")),
            client_kind=str(payload.get("client_kind", "terminal")),
            mode=str(payload.get("mode", "quick_edit")),
            provider_id=str(payload.get("provider_id", "")),
            required_capability=str(payload.get("required_capability", "")),
            review=str(payload.get("review", "required")),
            review_mode=str(payload.get("review_mode", "pull_request")),
        )
        try:
            result = EngineeringBridge(self.origins_client).run_attempt(request)
        except IntegrationUnavailable as exc:
            raise IntelligenceMountError(str(exc)) from exc
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
            "evidence": result.evidence_record(),
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
