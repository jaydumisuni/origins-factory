from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from origins_contracts.authority_v11 import authority_sha256, validate_authority_contract
from origins_contracts.contracts import canonical_json, contract_sha256

from .capability_proposals import CapabilityProposal, CapabilityProposalError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,159}$")
MAX_SAFE_INTEGER = 9_007_199_254_740_991
BINDING_SCHEMA = "origins.lease-issuance-binding.v1"


class LeaseIssuerPreflightError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResourceGeneration:
    resource_id: str
    generation: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "generation": self.generation,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class LeaseIssuerPreflightReceipt:
    eligible: bool
    failure_codes: tuple[str, ...]
    observed_at: str
    workspace_id: str
    capability_id: str
    proposal_digest: str
    scope_id: str
    scope_digest: str
    scope_revision: int
    scope_fence: int
    approval_id: str
    approval_request_digest: str
    approval_metadata_digest: str
    approval_record_digest: str
    approval_ledger_event_digest: str
    auth_actor: str
    auth_method: str
    auth_proof_id: str
    issuance_binding_digest: str
    provider_id: str
    provider_manifest_digest: str
    provider_generation: int
    host_policy_digest: str
    host_policy_generation: int
    resource_bindings: tuple[ResourceGeneration, ...]
    issuer_enabled: bool = False
    lease_created: bool = False
    runtime_authority_activated: bool = False

    def body_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "failure_codes": list(self.failure_codes),
            "observed_at": self.observed_at,
            "workspace_id": self.workspace_id,
            "capability_id": self.capability_id,
            "proposal_digest": self.proposal_digest,
            "scope_id": self.scope_id,
            "scope_digest": self.scope_digest,
            "scope_revision": self.scope_revision,
            "scope_fence": self.scope_fence,
            "approval_id": self.approval_id,
            "approval_request_digest": self.approval_request_digest,
            "approval_metadata_digest": self.approval_metadata_digest,
            "approval_record_digest": self.approval_record_digest,
            "approval_ledger_event_digest": self.approval_ledger_event_digest,
            "auth_actor": self.auth_actor,
            "auth_method": self.auth_method,
            "auth_proof_id": self.auth_proof_id,
            "issuance_binding_digest": self.issuance_binding_digest,
            "provider_id": self.provider_id,
            "provider_manifest_digest": self.provider_manifest_digest,
            "provider_generation": self.provider_generation,
            "host_policy_digest": self.host_policy_digest,
            "host_policy_generation": self.host_policy_generation,
            "resource_bindings": [item.as_dict() for item in self.resource_bindings],
            "issuer_enabled": False,
            "lease_created": False,
            "runtime_authority_activated": False,
        }

    @property
    def receipt_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "receipt_sha256": self.receipt_sha256}


def evaluate_lease_issuer_preflight(
    *,
    proposal: dict[str, Any],
    current_scope: dict[str, Any],
    approval_evidence: dict[str, Any],
    authorization: dict[str, Any],
    provider: dict[str, Any],
    host_policy: dict[str, Any],
    resources: Iterable[dict[str, Any]],
    observed_at: str,
) -> LeaseIssuerPreflightReceipt:
    """Validate issuance prerequisites without creating, persisting or activating authority."""

    proposal = _validate_proposal(proposal)
    validate_authority_contract(current_scope)
    if current_scope.get("contract_type") != "execution_scope":
        raise LeaseIssuerPreflightError("INVALID_SCOPE", "current_scope must be execution_scope")

    observed = _timestamp(observed_at, "observed_at")
    proposal_digest = contract_sha256(proposal)
    scope_digest = authority_sha256(current_scope)

    approval = _validate_approval_evidence(approval_evidence)
    provider = _validate_provider(provider)
    host_policy = _validate_host_policy(host_policy)
    resource_bindings = _validate_resources(resources)
    authorization = _validate_authorization(authorization)

    approval_request = approval["request"]
    approval_record = approval["record"]
    expected_request_digest = contract_sha256(approval_request)
    expected_metadata_digest = contract_sha256(approval_request["metadata"])
    expected_record_digest = contract_sha256(
        {
            "request_digest": expected_request_digest,
            "record": approval_record,
        }
    )

    expected_resource_ids = _scope_resource_ids(current_scope)
    actual_resource_ids = {item.resource_id for item in resource_bindings}

    binding = issuance_binding_document(
        workspace_id=str(proposal["workspace_id"]),
        capability_id=str(proposal["capability_id"]),
        proposal_digest=proposal_digest,
        approval_id=str(approval["approval_id"]),
        approval_record_digest=expected_record_digest,
        scope_id=str(current_scope["scope_id"]),
        scope_digest=scope_digest,
        scope_revision=_safe_int(current_scope["revision"], "scope.revision"),
        scope_fence=_safe_int(current_scope["fence"], "scope.fence"),
        provider=provider,
        host_policy=host_policy,
        resources=resource_bindings,
    )
    binding_digest = contract_sha256(binding)

    failures: list[str] = []

    if current_scope.get("state") != "active":
        failures.append("SCOPE_NOT_ACTIVE")
    if current_scope.get("workspace_id") != proposal.get("workspace_id"):
        failures.append("SCOPE_WORKSPACE_MISMATCH")
    expires_at = str(current_scope.get("expires_at") or "")
    if expires_at and _timestamp(expires_at, "scope.expires_at") <= observed:
        failures.append("SCOPE_EXPIRED")

    if approval.get("durable") is not True:
        failures.append("APPROVAL_NOT_DURABLE")
    if approval.get("status") != "approved":
        failures.append("APPROVAL_NOT_APPROVED")
    if approval_request.get("approval_id") != approval.get("approval_id"):
        failures.append("APPROVAL_ID_MISMATCH")
    if approval_record.get("approval_id") != approval.get("approval_id"):
        failures.append("APPROVAL_RECORD_ID_MISMATCH")
    if approval_record.get("decision") != "approved":
        failures.append("APPROVAL_RECORD_NOT_APPROVED")
    if approval_request.get("gate") != "owner_approval_required":
        failures.append("APPROVAL_GATE_MISMATCH")
    if approval_request.get("mode") != "capability_extension":
        failures.append("APPROVAL_MODE_MISMATCH")
    if approval_request.get("target") != proposal.get("capability_id"):
        failures.append("APPROVAL_TARGET_MISMATCH")
    if approval_request.get("task_title") != proposal.get("task_title"):
        failures.append("APPROVAL_TASK_MISMATCH")
    if approval_request.get("reason") != proposal.get("reason"):
        failures.append("APPROVAL_REASON_MISMATCH")
    if approval_request.get("metadata") != proposal:
        failures.append("APPROVAL_PROPOSAL_MISMATCH")
    if approval.get("request_digest") != expected_request_digest:
        failures.append("APPROVAL_REQUEST_DIGEST_MISMATCH")
    if approval.get("metadata_digest") != expected_metadata_digest:
        failures.append("APPROVAL_METADATA_DIGEST_MISMATCH")
    if expected_metadata_digest != proposal_digest:
        failures.append("PROPOSAL_DIGEST_MISMATCH")
    if approval.get("record_digest") != expected_record_digest:
        failures.append("APPROVAL_RECORD_DIGEST_MISMATCH")

    if provider.get("capability_id") != proposal.get("capability_id"):
        failures.append("PROVIDER_CAPABILITY_MISMATCH")

    if actual_resource_ids != expected_resource_ids:
        failures.append("RESOURCE_SET_MISMATCH")

    if authorization.get("valid") is not True:
        failures.append("AUTH_NOT_VALID")
    if authorization.get("approval_id") != approval.get("approval_id"):
        failures.append("AUTH_APPROVAL_MISMATCH")
    if authorization.get("primary_actor") != approval_record.get("decided_by"):
        failures.append("AUTH_ACTOR_MISMATCH")
    if authorization.get("binding_digest") != binding_digest:
        failures.append("AUTH_BINDING_MISMATCH")

    failure_codes = tuple(sorted(set(failures)))
    return LeaseIssuerPreflightReceipt(
        eligible=not failure_codes,
        failure_codes=failure_codes,
        observed_at=observed_at,
        workspace_id=str(proposal["workspace_id"]),
        capability_id=str(proposal["capability_id"]),
        proposal_digest=proposal_digest,
        scope_id=str(current_scope["scope_id"]),
        scope_digest=scope_digest,
        scope_revision=_safe_int(current_scope["revision"], "scope.revision"),
        scope_fence=_safe_int(current_scope["fence"], "scope.fence"),
        approval_id=str(approval["approval_id"]),
        approval_request_digest=expected_request_digest,
        approval_metadata_digest=expected_metadata_digest,
        approval_record_digest=expected_record_digest,
        approval_ledger_event_digest=str(approval["ledger_event_digest"]),
        auth_actor=str(authorization["primary_actor"]),
        auth_method=str(authorization["method"]),
        auth_proof_id=str(authorization["proof_id"]),
        issuance_binding_digest=binding_digest,
        provider_id=str(provider["provider_id"]),
        provider_manifest_digest=str(provider["provider_manifest_digest"]),
        provider_generation=_safe_int(provider["provider_generation"], "provider_generation"),
        host_policy_digest=str(host_policy["digest"]),
        host_policy_generation=_safe_int(host_policy["generation"], "host_policy.generation"),
        resource_bindings=resource_bindings,
    )


def issuance_binding_document(
    *,
    workspace_id: str,
    capability_id: str,
    proposal_digest: str,
    approval_id: str,
    approval_record_digest: str,
    scope_id: str,
    scope_digest: str,
    scope_revision: int,
    scope_fence: int,
    provider: dict[str, Any],
    host_policy: dict[str, Any],
    resources: Iterable[ResourceGeneration],
) -> dict[str, Any]:
    normalized_resources = tuple(sorted(resources, key=lambda item: item.resource_id))
    return {
        "schema": BINDING_SCHEMA,
        "workspace_id": workspace_id,
        "capability_id": capability_id,
        "proposal_digest": _digest(proposal_digest, "proposal_digest"),
        "approval_id": _nonempty_string(approval_id, "approval_id"),
        "approval_record_digest": _digest(approval_record_digest, "approval_record_digest"),
        "scope_id": _canonical_uuid(scope_id, "scope_id"),
        "scope_digest": _digest(scope_digest, "scope_digest"),
        "scope_revision": _safe_int(scope_revision, "scope_revision", minimum=1),
        "scope_fence": _safe_int(scope_fence, "scope_fence", minimum=1),
        "provider_id": str(provider["provider_id"]),
        "provider_manifest_digest": str(provider["provider_manifest_digest"]),
        "provider_generation": _safe_int(provider["provider_generation"], "provider_generation", minimum=1),
        "host_policy_digest": str(host_policy["digest"]),
        "host_policy_generation": _safe_int(host_policy["generation"], "host_policy_generation", minimum=1),
        "resource_bindings": [item.as_dict() for item in normalized_resources],
    }


def _validate_proposal(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LeaseIssuerPreflightError("INVALID_PROPOSAL", "proposal must be an object")
    expected = {
        "proposal_id", "workspace_id", "task_title", "capability_id", "reason", "expected_benefit",
        "requested_effects", "filesystem_read_scope", "filesystem_write_scope", "network_mode",
        "network_hosts", "environment_names", "persistent_lease", "delegated_remote_authority",
        "alternatives", "risks", "requested_by", "created_at", "approval_required", "self_approvable",
    }
    _exact_fields(value, expected, "INVALID_PROPOSAL")
    try:
        proposal = CapabilityProposal(
            proposal_id=_canonical_uuid(value["proposal_id"], "proposal_id"),
            workspace_id=_canonical_uuid(value["workspace_id"], "workspace_id"),
            task_title=_nonempty_string(value["task_title"], "task_title"),
            capability_id=_nonempty_string(value["capability_id"], "capability_id"),
            reason=_nonempty_string(value["reason"], "reason"),
            expected_benefit=_nonempty_string(value["expected_benefit"], "expected_benefit"),
            requested_effects=tuple(_string_list(value["requested_effects"], "requested_effects")),
            filesystem_read_scope=tuple(_string_list(value["filesystem_read_scope"], "filesystem_read_scope")),
            filesystem_write_scope=tuple(_string_list(value["filesystem_write_scope"], "filesystem_write_scope")),
            network_mode=str(value["network_mode"]),
            network_hosts=tuple(_string_list(value["network_hosts"], "network_hosts")),
            environment_names=tuple(_string_list(value["environment_names"], "environment_names")),
            persistent_lease=_boolean(value["persistent_lease"], "persistent_lease"),
            delegated_remote_authority=_boolean(value["delegated_remote_authority"], "delegated_remote_authority"),
            alternatives=tuple(_string_list(value["alternatives"], "alternatives")),
            risks=tuple(_string_list(value["risks"], "risks")),
            requested_by=_nonempty_string(value["requested_by"], "requested_by"),
            created_at=str(value["created_at"]),
            approval_required=_boolean(value["approval_required"], "approval_required"),
            self_approvable=_boolean(value["self_approvable"], "self_approvable"),
        )
        proposal.validate()
        _timestamp(proposal.created_at, "proposal.created_at")
    except (CapabilityProposalError, KeyError, TypeError) as error:
        raise LeaseIssuerPreflightError("INVALID_PROPOSAL", str(error)) from error
    normalized = proposal.as_dict()
    if normalized != value:
        raise LeaseIssuerPreflightError("NONCANONICAL_PROPOSAL", "proposal is not in canonical projection form")
    return value


def _validate_approval_evidence(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LeaseIssuerPreflightError("INVALID_APPROVAL_EVIDENCE", "approval evidence must be an object")
    _exact_fields(
        value,
        {
            "approval_id", "status", "durable", "request_digest", "metadata_digest",
            "record_digest", "ledger_event_digest", "request", "record",
        },
        "INVALID_APPROVAL_EVIDENCE",
    )
    _nonempty_string(value["approval_id"], "approval_id")
    _nonempty_string(value["status"], "approval.status")
    _boolean(value["durable"], "approval.durable")
    for field in ("request_digest", "metadata_digest", "record_digest", "ledger_event_digest"):
        _digest(value[field], f"approval.{field}")
    request = value["request"]
    record = value["record"]
    if not isinstance(request, dict) or not isinstance(record, dict):
        raise LeaseIssuerPreflightError("INVALID_APPROVAL_EVIDENCE", "approval request and record must be objects")
    _exact_fields(
        request,
        {"approval_id", "task_title", "mode", "gate", "reason", "requested_by", "target", "metadata", "status", "created_at"},
        "INVALID_APPROVAL_REQUEST",
    )
    _exact_fields(record, {"approval_id", "decision", "decided_by", "note", "created_at"}, "INVALID_APPROVAL_RECORD")
    for field in ("approval_id", "task_title", "mode", "gate", "reason", "requested_by", "status", "created_at"):
        _nonempty_string(request[field], f"request.{field}")
    if request["target"] is not None:
        _nonempty_string(request["target"], "request.target")
    if not isinstance(request["metadata"], dict):
        raise LeaseIssuerPreflightError("INVALID_APPROVAL_REQUEST", "request.metadata must be an object")
    for field in ("approval_id", "decision", "decided_by", "created_at"):
        _nonempty_string(record[field], f"record.{field}")
    if record["note"] is not None and not isinstance(record["note"], str):
        raise LeaseIssuerPreflightError("INVALID_APPROVAL_RECORD", "record.note must be string or null")
    _timestamp(str(request["created_at"]), "request.created_at")
    _timestamp(str(record["created_at"]), "record.created_at")
    return value


def _validate_authorization(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LeaseIssuerPreflightError("INVALID_AUTHORIZATION", "authorization must be an object")
    _exact_fields(
        value,
        {"valid", "approval_id", "primary_actor", "method", "proof_id", "binding_digest"},
        "INVALID_AUTHORIZATION",
    )
    _boolean(value["valid"], "authorization.valid")
    for field in ("approval_id", "primary_actor", "method", "proof_id"):
        _nonempty_string(value[field], f"authorization.{field}")
    _digest(value["binding_digest"], "authorization.binding_digest")
    return value


def _validate_provider(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LeaseIssuerPreflightError("INVALID_PROVIDER", "provider observation must be an object")
    _exact_fields(value, {"capability_id", "provider_id", "provider_manifest_digest", "provider_generation"}, "INVALID_PROVIDER")
    capability_id = _nonempty_string(value["capability_id"], "provider.capability_id")
    if not SAFE_ID_RE.fullmatch(capability_id):
        raise LeaseIssuerPreflightError("INVALID_PROVIDER", "provider capability_id is not canonical")
    provider_id = _nonempty_string(value["provider_id"], "provider.provider_id")
    if not PROVIDER_ID_RE.fullmatch(provider_id):
        raise LeaseIssuerPreflightError("INVALID_PROVIDER", "provider_id is not canonical")
    _digest(value["provider_manifest_digest"], "provider.provider_manifest_digest")
    _safe_int(value["provider_generation"], "provider.provider_generation", minimum=1)
    return value


def _validate_host_policy(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LeaseIssuerPreflightError("INVALID_HOST_POLICY", "host policy observation must be an object")
    _exact_fields(value, {"digest", "generation"}, "INVALID_HOST_POLICY")
    _digest(value["digest"], "host_policy.digest")
    _safe_int(value["generation"], "host_policy.generation", minimum=1)
    return value


def _validate_resources(values: Iterable[dict[str, Any]]) -> tuple[ResourceGeneration, ...]:
    seen: set[str] = set()
    normalized: list[ResourceGeneration] = []
    for raw in values:
        if not isinstance(raw, dict):
            raise LeaseIssuerPreflightError("INVALID_RESOURCE_BINDING", "resource binding must be an object")
        _exact_fields(raw, {"resource_id", "generation", "digest"}, "INVALID_RESOURCE_BINDING")
        resource_id = _nonempty_string(raw["resource_id"], "resource_id")
        if resource_id in seen:
            raise LeaseIssuerPreflightError("DUPLICATE_RESOURCE_BINDING", f"duplicate resource binding {resource_id}")
        seen.add(resource_id)
        normalized.append(
            ResourceGeneration(
                resource_id=resource_id,
                generation=_safe_int(raw["generation"], "resource.generation", minimum=1),
                digest=_digest(raw["digest"], "resource.digest"),
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.resource_id))


def _scope_resource_ids(scope: dict[str, Any]) -> set[str]:
    return {
        str(item["resource_id"])
        for field in ("resource_reads", "resource_writes", "resource_denies")
        for item in scope[field]
    }


def _exact_fields(value: dict[str, Any], expected: set[str], code: str) -> None:
    actual = set(value)
    if actual != expected:
        raise LeaseIssuerPreflightError(
            code,
            f"field mismatch; missing={sorted(expected - actual)} unknown={sorted(actual - expected)}",
        )


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LeaseIssuerPreflightError("INVALID_STRING", f"{field} must be a non-empty string")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise LeaseIssuerPreflightError("INVALID_LIST", f"{field} must be a list of strings")
    return list(value)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LeaseIssuerPreflightError("INVALID_BOOLEAN", f"{field} must be boolean")
    return value


def _safe_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > MAX_SAFE_INTEGER:
        raise LeaseIssuerPreflightError("INVALID_INTEGER", f"{field} must be {minimum}..{MAX_SAFE_INTEGER}")
    return value


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise LeaseIssuerPreflightError("INVALID_DIGEST", f"{field} must be lowercase SHA-256")
    return value


def _canonical_uuid(value: Any, field: str) -> str:
    text = _nonempty_string(value, field)
    try:
        parsed = uuid.UUID(text)
    except ValueError as error:
        raise LeaseIssuerPreflightError("INVALID_UUID", f"{field} must be canonical UUID") from error
    canonical = str(parsed)
    if text != canonical:
        raise LeaseIssuerPreflightError("INVALID_UUID", f"{field} must use canonical UUID text")
    return text


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LeaseIssuerPreflightError("INVALID_TIMESTAMP", f"{field} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise LeaseIssuerPreflightError("INVALID_TIMESTAMP", f"{field} is not RFC3339") from error
    if parsed.tzinfo is None:
        raise LeaseIssuerPreflightError("INVALID_TIMESTAMP", f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)
