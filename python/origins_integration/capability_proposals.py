from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

Effect = Literal["draft", "execute", "mutate", "observe", "publish", "verify"]
NetworkMode = Literal["deny", "allowlist", "delegated_remote"]

EFFECT_ORDER = ("draft", "execute", "mutate", "observe", "publish", "verify")
EFFECT_SET = set(EFFECT_ORDER)
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class CapabilityProposalError(ValueError):
    """Raised when a model capability proposal is unsafe or incomplete."""


@dataclass(frozen=True)
class CapabilityProposal:
    proposal_id: str
    workspace_id: str
    task_title: str
    capability_id: str
    reason: str
    expected_benefit: str
    requested_effects: tuple[Effect, ...]
    filesystem_read_scope: tuple[str, ...]
    filesystem_write_scope: tuple[str, ...]
    network_mode: NetworkMode
    network_hosts: tuple[str, ...]
    environment_names: tuple[str, ...]
    persistent_lease: bool
    delegated_remote_authority: bool
    alternatives: tuple[str, ...]
    risks: tuple[str, ...]
    requested_by: str
    created_at: str
    approval_required: bool = True
    self_approvable: bool = False

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        task_title: str,
        capability_id: str,
        reason: str,
        expected_benefit: str,
        requested_effects: tuple[str, ...],
        filesystem_read_scope: tuple[str, ...] = (),
        filesystem_write_scope: tuple[str, ...] = (),
        network_mode: NetworkMode = "deny",
        network_hosts: tuple[str, ...] = (),
        environment_names: tuple[str, ...] = (),
        persistent_lease: bool = False,
        delegated_remote_authority: bool = False,
        alternatives: tuple[str, ...] = (),
        risks: tuple[str, ...] = (),
        requested_by: str = "hunter",
    ) -> "CapabilityProposal":
        proposal = cls(
            proposal_id=str(uuid.uuid4()),
            workspace_id=workspace_id.strip(),
            task_title=task_title.strip(),
            capability_id=capability_id.strip(),
            reason=reason.strip(),
            expected_benefit=expected_benefit.strip(),
            requested_effects=_effects(requested_effects),
            filesystem_read_scope=_scope(filesystem_read_scope, "filesystem_read_scope"),
            filesystem_write_scope=_scope(filesystem_write_scope, "filesystem_write_scope"),
            network_mode=network_mode,
            network_hosts=_scope(network_hosts, "network_hosts"),
            environment_names=_environment_names(environment_names),
            persistent_lease=bool(persistent_lease),
            delegated_remote_authority=bool(delegated_remote_authority),
            alternatives=_text_items(alternatives, "alternatives"),
            risks=_text_items(risks, "risks"),
            requested_by=requested_by.strip(),
            created_at=_utc_now(),
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        if not self.workspace_id:
            raise CapabilityProposalError("workspace_id is required")
        if not self.task_title:
            raise CapabilityProposalError("task_title is required")
        if not CAPABILITY_ID_RE.fullmatch(self.capability_id):
            raise CapabilityProposalError("capability_id must use safe identifier characters")
        if not self.reason:
            raise CapabilityProposalError("reason is required; a model must explain why the capability is needed")
        if not self.expected_benefit:
            raise CapabilityProposalError("expected_benefit is required")
        if not self.requested_effects:
            raise CapabilityProposalError("requested_effects cannot be empty")
        if self.network_mode not in {"deny", "allowlist", "delegated_remote"}:
            raise CapabilityProposalError("unsupported network_mode")
        if self.network_mode == "deny" and self.network_hosts:
            raise CapabilityProposalError("network_hosts must be empty when network_mode is deny")
        if self.network_mode in {"allowlist", "delegated_remote"} and not self.network_hosts:
            raise CapabilityProposalError("network_hosts are required when network access is requested")
        if self.delegated_remote_authority and self.network_mode != "delegated_remote":
            raise CapabilityProposalError(
                "delegated_remote_authority requires network_mode delegated_remote"
            )
        if self.network_mode == "delegated_remote" and not self.delegated_remote_authority:
            raise CapabilityProposalError(
                "delegated_remote network mode must be marked as delegated remote authority"
            )
        if not self.requested_by:
            raise CapabilityProposalError("requested_by is required")
        if not self.approval_required or self.self_approvable:
            raise CapabilityProposalError("model capability proposals must require approval and cannot self-approve")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "proposal_id": self.proposal_id,
            "workspace_id": self.workspace_id,
            "task_title": self.task_title,
            "capability_id": self.capability_id,
            "reason": self.reason,
            "expected_benefit": self.expected_benefit,
            "requested_effects": list(self.requested_effects),
            "filesystem_read_scope": list(self.filesystem_read_scope),
            "filesystem_write_scope": list(self.filesystem_write_scope),
            "network_mode": self.network_mode,
            "network_hosts": list(self.network_hosts),
            "environment_names": list(self.environment_names),
            "persistent_lease": self.persistent_lease,
            "delegated_remote_authority": self.delegated_remote_authority,
            "alternatives": list(self.alternatives),
            "risks": list(self.risks),
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "approval_required": True,
            "self_approvable": False,
        }

    def agentops_approval_request(self) -> dict[str, object]:
        """Return arguments compatible with AgentOps ApprovalService.create_request()."""
        self.validate()
        return {
            "task_title": self.task_title,
            "mode": "capability_extension",
            "gate": "owner_approval_required",
            "reason": self.reason,
            "requested_by": self.requested_by,
            "target": self.capability_id,
            "metadata": self.as_dict(),
        }


def _effects(values: tuple[str, ...]) -> tuple[Effect, ...]:
    unique = set(values)
    unknown = sorted(unique - EFFECT_SET)
    if unknown:
        raise CapabilityProposalError(f"unsupported effects: {', '.join(unknown)}")
    return tuple(effect for effect in EFFECT_ORDER if effect in unique)  # type: ignore[return-value]


def _scope(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    clean = tuple(sorted({item.strip() for item in values if item.strip()}))
    if any("\x00" in item for item in clean):
        raise CapabilityProposalError(f"{field} cannot contain null bytes")
    return clean


def _environment_names(values: tuple[str, ...]) -> tuple[str, ...]:
    clean = _scope(values, "environment_names")
    for item in clean:
        if not ENV_NAME_RE.fullmatch(item):
            raise CapabilityProposalError(
                "environment_names may contain variable names only, never secret values"
            )
    return clean


def _text_items(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    clean = tuple(item.strip() for item in values if item.strip())
    if any(len(item) > 1000 for item in clean):
        raise CapabilityProposalError(f"{field} entries are too long")
    return clean


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
