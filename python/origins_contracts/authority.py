from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from .contracts import ContractError, contract_sha256

SCHEMA_VERSION = "1.0.0"
EFFECTS = ("draft", "execute", "mutate", "observe", "publish", "verify")
NETWORK_MODES = ("allowlist", "delegated_remote", "deny")
LEASE_STATES = ("active", "expired", "revoked", "suspended")
HOLDER_KINDS = ("candidate", "operation", "provider", "session")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
RESOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}:[A-Za-z0-9_.:-]{1,160}$")
HOST_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]{1,5})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_authority_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("INVALID_ROOT", "authority contract root must be an object")
    contract_type = value.get("contract_type")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA_VERSION", "schema_version must be 1.0.0")
    if contract_type == "execution_scope":
        _validate_execution_scope(value)
    elif contract_type == "capability_lease":
        _validate_capability_lease(value)
    else:
        raise ContractError("UNKNOWN_CONTRACT_TYPE", f"unsupported authority contract_type: {contract_type}")
    contract_sha256(value)
    return value


def validate_child_scope(child: dict[str, Any], parent: dict[str, Any]) -> None:
    validate_authority_contract(parent)
    validate_authority_contract(child)
    if parent["contract_type"] != "execution_scope" or child["contract_type"] != "execution_scope":
        raise ContractError("INVALID_SCOPE_RELATION", "child and parent must both be execution_scope")
    if child["workspace_id"] != parent["workspace_id"]:
        raise ContractError("SCOPE_ESCALATION", "child scope cannot change workspace")
    if child["parent_scope_id"] != parent["scope_id"]:
        raise ContractError("SCOPE_ESCALATION", "child parent_scope_id must reference parent scope")
    if not parent["delegation_allowed"]:
        raise ContractError("SCOPE_ESCALATION", "parent scope forbids delegation")
    _require_subset(child["effects"], parent["effects"], "effects")
    _require_grants_within(child["resource_reads"], parent["resource_reads"], "resource_reads")
    _require_grants_within(child["resource_writes"], parent["resource_writes"], "resource_writes")
    _require_parent_denies(child["resource_denies"], parent["resource_denies"])
    _require_subset(child["environment_names"], parent["environment_names"], "environment_names")
    _require_network_narrowing(child, parent)
    if child["process_execution_allowed"] and not parent["process_execution_allowed"]:
        raise ContractError("SCOPE_ESCALATION", "child cannot enable process execution")
    if child["persistent_process_allowed"] and not parent["persistent_process_allowed"]:
        raise ContractError("SCOPE_ESCALATION", "child cannot enable persistent processes")
    if child["delegation_allowed"] and not parent["delegation_allowed"]:
        raise ContractError("SCOPE_ESCALATION", "child cannot enable delegation")
    if child["delegated_remote_authority"] and not parent["delegated_remote_authority"]:
        raise ContractError("SCOPE_ESCALATION", "child cannot enable delegated remote authority")
    _require_expiry_not_extended(child["expires_at"], parent["expires_at"])


def validate_lease_within_scope(lease: dict[str, Any], scope: dict[str, Any]) -> None:
    validate_authority_contract(scope)
    validate_authority_contract(lease)
    if scope["contract_type"] != "execution_scope" or lease["contract_type"] != "capability_lease":
        raise ContractError("INVALID_LEASE_RELATION", "lease must be checked against execution_scope")
    if lease["scope_id"] != scope["scope_id"] or lease["workspace_id"] != scope["workspace_id"]:
        raise ContractError("LEASE_ESCALATION", "lease scope/workspace identity does not match")
    _require_subset(lease["effects"], scope["effects"], "effects")
    _require_grants_within(lease["resource_reads"], scope["resource_reads"], "resource_reads")
    _require_grants_within(lease["resource_writes"], scope["resource_writes"], "resource_writes")
    _require_parent_denies(lease["resource_denies"], scope["resource_denies"])
    _require_subset(lease["environment_names"], scope["environment_names"], "environment_names")
    _require_network_narrowing(lease, scope)
    if lease["persistent_process_allowed"] and not scope["persistent_process_allowed"]:
        raise ContractError("LEASE_ESCALATION", "lease cannot enable persistent processes")
    if lease["delegated_remote_authority"] and not scope["delegated_remote_authority"]:
        raise ContractError("LEASE_ESCALATION", "lease cannot enable delegated remote authority")
    if "execute" in lease["effects"] and not scope["process_execution_allowed"]:
        raise ContractError("LEASE_ESCALATION", "scope forbids process execution")
    _require_expiry_not_extended(lease["expires_at"], scope["expires_at"])


def _validate_execution_scope(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "scope_id",
            "workspace_id",
            "operation_id",
            "candidate_id",
            "parent_scope_id",
            "effects",
            "resource_reads",
            "resource_writes",
            "resource_denies",
            "network_mode",
            "network_hosts",
            "environment_names",
            "process_execution_allowed",
            "persistent_process_allowed",
            "delegation_allowed",
            "delegated_remote_authority",
            "issued_at",
            "updated_at",
            "expires_at",
            "revision",
        },
    )
    _uuid(value, "scope_id")
    _uuid(value, "workspace_id")
    _nonempty_string(value, "operation_id")
    _string(value, "candidate_id")
    _optional_uuid(value, "parent_scope_id")
    _sorted_unique_enum_list(value, "effects", EFFECTS, allow_empty=False)
    reads = _resource_grants(value, "resource_reads")
    writes = _resource_grants(value, "resource_writes")
    denies = _resource_grants(value, "resource_denies")
    _require_grants_within(writes, reads, "resource_writes")
    _reject_fully_denied_grants(reads, denies, "resource_reads")
    _reject_fully_denied_grants(writes, denies, "resource_writes")
    _network(value)
    _environment_names(value, "environment_names")
    process_allowed = _bool(value, "process_execution_allowed")
    persistent_allowed = _bool(value, "persistent_process_allowed")
    _bool(value, "delegation_allowed")
    _bool(value, "delegated_remote_authority")
    if persistent_allowed and not process_allowed:
        raise ContractError("INVALID_SCOPE", "persistent processes require process execution")
    _validate_network_remote_flag(value)
    issued = _timestamp(value, "issued_at")
    updated = _timestamp(value, "updated_at")
    if updated < issued:
        raise ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede issued_at")
    expires = _optional_timestamp(value, "expires_at")
    if expires is not None and expires <= issued:
        raise ContractError("INVALID_TIMESTAMP_ORDER", "expires_at must be later than issued_at")
    if _nonnegative_integer(value, "revision", "INVALID_REVISION") < 1:
        raise ContractError("INVALID_REVISION", "revision must be at least 1")


def _validate_capability_lease(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "lease_id",
            "scope_id",
            "workspace_id",
            "parent_lease_id",
            "capability_id",
            "holder_kind",
            "holder_id",
            "effects",
            "resource_reads",
            "resource_writes",
            "resource_denies",
            "network_mode",
            "network_hosts",
            "environment_names",
            "persistent_process_allowed",
            "delegated_remote_authority",
            "approval_authority",
            "approval_id",
            "approval_digest",
            "proposal_digest",
            "state",
            "fence",
            "issued_at",
            "updated_at",
            "expires_at",
            "revision",
        },
    )
    _uuid(value, "lease_id")
    _uuid(value, "scope_id")
    _uuid(value, "workspace_id")
    _optional_uuid(value, "parent_lease_id")
    _nonempty_string(value, "capability_id")
    _enum(value, "holder_kind", HOLDER_KINDS)
    _nonempty_string(value, "holder_id")
    effects = _sorted_unique_enum_list(value, "effects", EFFECTS, allow_empty=False)
    reads = _resource_grants(value, "resource_reads")
    writes = _resource_grants(value, "resource_writes")
    denies = _resource_grants(value, "resource_denies")
    _require_grants_within(writes, reads, "resource_writes")
    _reject_fully_denied_grants(reads, denies, "resource_reads")
    _reject_fully_denied_grants(writes, denies, "resource_writes")
    _network(value)
    _environment_names(value, "environment_names")
    persistent = _bool(value, "persistent_process_allowed")
    _bool(value, "delegated_remote_authority")
    if persistent and "execute" not in effects:
        raise ContractError("INVALID_LEASE", "persistent process lease requires execute effect")
    _validate_network_remote_flag(value)
    _nonempty_string(value, "approval_authority")
    _nonempty_string(value, "approval_id")
    _digest(value, "approval_digest")
    _digest(value, "proposal_digest")
    state = _enum(value, "state", LEASE_STATES)
    if _nonnegative_integer(value, "fence", "INVALID_FENCE") < 1:
        raise ContractError("INVALID_FENCE", "fence must be at least 1")
    issued = _timestamp(value, "issued_at")
    updated = _timestamp(value, "updated_at")
    if updated < issued:
        raise ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede issued_at")
    expires = _optional_timestamp(value, "expires_at")
    if expires is not None and expires <= issued:
        raise ContractError("INVALID_TIMESTAMP_ORDER", "expires_at must be later than issued_at")
    if state == "expired" and expires is None:
        raise ContractError("INVALID_LEASE", "expired lease requires expires_at")
    if _nonnegative_integer(value, "revision", "INVALID_REVISION") < 1:
        raise ContractError("INVALID_REVISION", "revision must be at least 1")


def _resource_grants(value: dict[str, Any], field: str) -> list[dict[str, str]]:
    items = value.get(field)
    if not isinstance(items, list):
        raise ContractError("INVALID_RESOURCE_GRANTS", f"{field} must be a list")
    grants: list[dict[str, str]] = []
    keys: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"resource_id", "prefix"}:
            raise ContractError(
                "INVALID_RESOURCE_GRANT",
                f"{field} entries must contain resource_id and prefix only",
            )
        resource_id = item.get("resource_id")
        prefix = item.get("prefix")
        if not isinstance(resource_id, str) or not RESOURCE_ID_RE.fullmatch(resource_id):
            raise ContractError("INVALID_RESOURCE_ID", f"invalid resource_id in {field}")
        if not isinstance(prefix, str):
            raise ContractError("INVALID_RESOURCE_PREFIX", f"prefix in {field} must be a string")
        _validate_prefix(prefix, field)
        grants.append({"resource_id": resource_id, "prefix": prefix})
        keys.append((resource_id, prefix))
    if keys != sorted(set(keys)):
        raise ContractError(
            "UNSORTED_OR_DUPLICATE_LIST",
            f"{field} must be sorted by resource_id/prefix and unique",
        )
    return grants


def _validate_prefix(prefix: str, field: str) -> None:
    if "\x00" in prefix or "\\" in prefix or prefix.startswith("/") or "//" in prefix:
        raise ContractError("INVALID_RESOURCE_PREFIX", f"unsafe resource prefix in {field}")
    if prefix.endswith("/"):
        raise ContractError("INVALID_RESOURCE_PREFIX", f"resource prefix in {field} cannot end with /")
    if any(part in {".", ".."} or part == "" for part in prefix.split("/")) and prefix:
        raise ContractError("INVALID_RESOURCE_PREFIX", f"resource prefix in {field} must be normalized")


def _grant_within(child: dict[str, str], parent: dict[str, str]) -> bool:
    if child["resource_id"] != parent["resource_id"]:
        return False
    parent_prefix = parent["prefix"]
    child_prefix = child["prefix"]
    return parent_prefix == "" or child_prefix == parent_prefix or child_prefix.startswith(parent_prefix + "/")


def _require_grants_within(children: Iterable[dict[str, str]], parents: Iterable[dict[str, str]], field: str) -> None:
    parent_list = list(parents)
    for child in children:
        if not any(_grant_within(child, parent) for parent in parent_list):
            raise ContractError("SCOPE_ESCALATION", f"{field} contains authority outside its parent")


def _require_parent_denies(children: list[dict[str, str]], parents: list[dict[str, str]]) -> None:
    child_keys = {(item["resource_id"], item["prefix"]) for item in children}
    for parent in parents:
        key = (parent["resource_id"], parent["prefix"])
        if key not in child_keys:
            raise ContractError("SCOPE_ESCALATION", "child/lease cannot drop a parent resource deny")


def _reject_fully_denied_grants(grants: Iterable[dict[str, str]], denies: Iterable[dict[str, str]], field: str) -> None:
    deny_list = list(denies)
    for grant in grants:
        if any(_grant_within(grant, deny) for deny in deny_list):
            raise ContractError("CONTRADICTORY_SCOPE", f"{field} contains a grant fully covered by a deny")


def _network(value: dict[str, Any]) -> None:
    mode = _enum(value, "network_mode", NETWORK_MODES)
    hosts = _sorted_unique_string_list(value, "network_hosts")
    for host in hosts:
        if not HOST_RE.fullmatch(host) or host.startswith(".") or host.endswith(".") or ".." in host:
            raise ContractError("INVALID_NETWORK_HOST", f"invalid exact network host: {host}")
        if ":" in host:
            port = int(host.rsplit(":", 1)[1])
            if not 1 <= port <= 65535:
                raise ContractError("INVALID_NETWORK_HOST", f"invalid network port in {host}")
    if mode == "deny" and hosts:
        raise ContractError("INVALID_NETWORK_SCOPE", "deny mode cannot include network hosts")
    if mode != "deny" and not hosts:
        raise ContractError("INVALID_NETWORK_SCOPE", f"{mode} mode requires exact network hosts")


def _validate_network_remote_flag(value: dict[str, Any]) -> None:
    mode = value["network_mode"]
    delegated = value["delegated_remote_authority"]
    if mode == "delegated_remote" and not delegated:
        raise ContractError("INVALID_NETWORK_SCOPE", "delegated_remote mode must mark delegated remote authority")
    if mode != "delegated_remote" and delegated:
        raise ContractError("INVALID_NETWORK_SCOPE", "delegated remote authority requires delegated_remote mode")


def _require_network_narrowing(child: dict[str, Any], parent: dict[str, Any]) -> None:
    child_mode = child["network_mode"]
    parent_mode = parent["network_mode"]
    if child_mode == "deny":
        return
    if child_mode != parent_mode:
        raise ContractError("SCOPE_ESCALATION", "network authority class cannot change while delegating")
    _require_subset(child["network_hosts"], parent["network_hosts"], "network_hosts")


def _require_subset(children: Iterable[str], parents: Iterable[str], field: str) -> None:
    parent_set = set(parents)
    if not set(children).issubset(parent_set):
        raise ContractError("SCOPE_ESCALATION", f"{field} cannot expand parent authority")


def _require_expiry_not_extended(child_text: str, parent_text: str) -> None:
    child = _parse_optional_timestamp_text(child_text, "expires_at")
    parent = _parse_optional_timestamp_text(parent_text, "expires_at")
    if parent is None:
        return
    if child is None or child > parent:
        raise ContractError("SCOPE_ESCALATION", "child/lease expiry cannot extend beyond parent")


def _environment_names(value: dict[str, Any], field: str) -> list[str]:
    names = _sorted_unique_string_list(value, field)
    for name in names:
        if not ENV_NAME_RE.fullmatch(name):
            raise ContractError("INVALID_ENVIRONMENT_NAME", f"{field} may contain variable names only")
    return names


def _exact_fields(value: dict[str, Any], expected: set[str]) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise ContractError("MISSING_FIELD", f"missing fields: {', '.join(missing)}")
    if unknown:
        raise ContractError("UNKNOWN_FIELD", f"unknown fields: {', '.join(unknown)}")


def _string(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise ContractError("INVALID_STRING", f"{field} must be a string")
    return item


def _nonempty_string(value: dict[str, Any], field: str) -> str:
    item = _string(value, field)
    if not item.strip():
        raise ContractError("EMPTY_STRING", f"{field} cannot be empty")
    return item


def _bool(value: dict[str, Any], field: str) -> bool:
    item = value.get(field)
    if not isinstance(item, bool):
        raise ContractError("INVALID_BOOLEAN", f"{field} must be boolean")
    return item


def _uuid(value: dict[str, Any], field: str) -> str:
    item = _nonempty_string(value, field)
    try:
        parsed = uuid.UUID(item)
    except ValueError as exc:
        raise ContractError("INVALID_UUID", f"{field} must be a UUID") from exc
    if str(parsed) != item.lower():
        raise ContractError("INVALID_UUID", f"{field} must use canonical UUID text")
    return item


def _optional_uuid(value: dict[str, Any], field: str) -> str:
    item = _string(value, field)
    if not item:
        return item
    try:
        parsed = uuid.UUID(item)
    except ValueError as exc:
        raise ContractError("INVALID_UUID", f"{field} must be empty or a UUID") from exc
    if str(parsed) != item.lower():
        raise ContractError("INVALID_UUID", f"{field} must use canonical UUID text")
    return item


def _enum(value: dict[str, Any], field: str, allowed: tuple[str, ...]) -> str:
    item = _nonempty_string(value, field)
    if item not in allowed:
        raise ContractError("INVALID_ENUM", f"{field} must be one of: {', '.join(allowed)}")
    return item


def _sorted_unique_string_list(value: dict[str, Any], field: str) -> list[str]:
    items = value.get(field)
    if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items):
        raise ContractError("INVALID_LIST", f"{field} must be a list of non-empty strings")
    if items != sorted(set(items)):
        raise ContractError("UNSORTED_OR_DUPLICATE_LIST", f"{field} must be sorted and unique")
    return items


def _sorted_unique_enum_list(
    value: dict[str, Any], field: str, allowed: tuple[str, ...], *, allow_empty: bool
) -> list[str]:
    items = _sorted_unique_string_list(value, field)
    if not allow_empty and not items:
        raise ContractError("EMPTY_LIST", f"{field} cannot be empty")
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise ContractError("INVALID_ENUM", f"{field} contains unsupported values: {', '.join(invalid)}")
    return items


def _nonnegative_integer(value: dict[str, Any], field: str, code: str) -> int:
    item = value.get(field)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ContractError(code, f"{field} must be a non-negative integer")
    if item > 9_007_199_254_740_991:
        raise ContractError("INTEGER_OUT_OF_RANGE", f"{field} exceeds cross-language safe range")
    return item


def _digest(value: dict[str, Any], field: str) -> str:
    item = _nonempty_string(value, field)
    if not SHA256_RE.fullmatch(item):
        raise ContractError("INVALID_DIGEST", f"{field} must be lowercase SHA-256")
    return item


def _timestamp(value: dict[str, Any], field: str) -> datetime:
    return _parse_timestamp_text(_nonempty_string(value, field), field)


def _optional_timestamp(value: dict[str, Any], field: str) -> datetime | None:
    return _parse_optional_timestamp_text(_string(value, field), field)


def _parse_optional_timestamp_text(text: str, field: str) -> datetime | None:
    return None if text == "" else _parse_timestamp_text(text, field)


def _parse_timestamp_text(text: str, field: str) -> datetime:
    if not text.endswith("Z"):
        raise ContractError("INVALID_TIMESTAMP", f"{field} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("INVALID_TIMESTAMP", f"{field} is not valid RFC3339") from exc
    return parsed.astimezone(timezone.utc)
