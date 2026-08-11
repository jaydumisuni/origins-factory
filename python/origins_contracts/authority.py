from __future__ import annotations

from typing import Any

from .authority_v11 import (
    SCHEMA_VERSION,
    authority_sha256 as _authority_sha256,
    validate_authority_contract as _validate_authority_contract,
    validate_child_scope as _validate_child_scope,
    validate_lease_within_scope as _validate_lease_within_scope,
    validate_provider_binding as _validate_provider_binding,
    validate_scope_current as _validate_scope_current,
)
from .contracts import ContractError

_ENDPOINT_FIELDS = {"protocol", "host", "port"}


def _precheck_endpoint_fields(value: Any) -> None:
    if not isinstance(value, dict):
        return
    endpoints = value.get("network_endpoints")
    if not isinstance(endpoints, list):
        return
    for item in endpoints:
        if not isinstance(item, dict):
            raise ContractError("INVALID_NETWORK_ENDPOINT", "network endpoint must be an object")
        actual = set(item)
        missing = sorted(_ENDPOINT_FIELDS - actual)
        unknown = sorted(actual - _ENDPOINT_FIELDS)
        if missing:
            raise ContractError("MISSING_FIELD", f"missing fields: {', '.join(missing)}")
        if unknown:
            raise ContractError("UNKNOWN_FIELD", f"unknown fields: {', '.join(unknown)}")


def validate_authority_contract(value: Any) -> dict[str, Any]:
    _precheck_endpoint_fields(value)
    return _validate_authority_contract(value)


def authority_sha256(value: Any) -> str:
    _precheck_endpoint_fields(value)
    return _authority_sha256(value)


def validate_child_scope(child: dict[str, Any], parent: dict[str, Any]) -> None:
    _precheck_endpoint_fields(child)
    _precheck_endpoint_fields(parent)
    _validate_child_scope(child, parent)


def validate_lease_within_scope(lease: dict[str, Any], scope: dict[str, Any]) -> None:
    _precheck_endpoint_fields(lease)
    _precheck_endpoint_fields(scope)
    _validate_lease_within_scope(lease, scope)


def validate_scope_current(presented: dict[str, Any], current: dict[str, Any]) -> None:
    _precheck_endpoint_fields(presented)
    _precheck_endpoint_fields(current)
    _validate_scope_current(presented, current)


def validate_provider_binding(
    lease: dict[str, Any], *, provider_id: str, provider_manifest_digest: str, provider_generation: int
) -> None:
    _precheck_endpoint_fields(lease)
    _validate_provider_binding(
        lease,
        provider_id=provider_id,
        provider_manifest_digest=provider_manifest_digest,
        provider_generation=provider_generation,
    )


__all__ = [
    "SCHEMA_VERSION",
    "authority_sha256",
    "validate_authority_contract",
    "validate_child_scope",
    "validate_lease_within_scope",
    "validate_provider_binding",
    "validate_scope_current",
]
