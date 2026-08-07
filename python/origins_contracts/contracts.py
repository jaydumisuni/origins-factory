from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0.0"
EFFECTS = ("draft", "execute", "mutate", "observe", "publish", "verify")
NODE_OS = ("any", "linux", "macos", "windows")
MATURITY = ("experimental", "frozen", "planned", "proven")
MODEL_DEPENDENCY = ("none", "optional", "required")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def canonical_json(value: Any) -> str:
    _reject_floats(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def contract_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("INVALID_ROOT", "contract root must be an object")
    _reject_floats(value)

    contract_type = value.get("contract_type")
    if not isinstance(contract_type, str) or not contract_type:
        raise ContractError("MISSING_CONTRACT_TYPE", "contract_type is required")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("UNSUPPORTED_SCHEMA_VERSION", "schema_version must be 1.0.0")

    validators = {
        "authority_ref": _validate_authority_ref,
        "workspace_projection": _validate_workspace_projection,
        "capability_descriptor": _validate_capability_descriptor,
        "command_envelope": _validate_command_envelope,
        "event_envelope": _validate_event_envelope,
    }
    validator = validators.get(contract_type)
    if validator is None:
        raise ContractError("UNKNOWN_CONTRACT_TYPE", f"unsupported contract_type: {contract_type}")
    validator(value)
    return value


def _validate_authority_ref(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "authority",
            "kind",
            "id",
            "revision",
            "uri",
            "digest",
            "observed_at",
        },
    )
    _nonempty_string(value, "authority")
    _nonempty_string(value, "kind")
    _nonempty_string(value, "id")
    _string(value, "revision")
    _string(value, "uri")
    digest = _string(value, "digest")
    if digest and not SHA256_RE.fullmatch(digest):
        raise ContractError("INVALID_DIGEST", "digest must be empty or lowercase SHA-256")
    _timestamp(value, "observed_at")


def _validate_workspace_projection(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "workspace_id",
            "name",
            "revision",
            "authority_refs",
            "session_refs",
            "created_at",
            "updated_at",
        },
    )
    _uuid(value, "workspace_id")
    _nonempty_string(value, "name")
    revision = value.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ContractError("INVALID_REVISION", "revision must be a non-negative integer")
    _authority_ref_list(value, "authority_refs")
    _authority_ref_list(value, "session_refs")
    created = _timestamp(value, "created_at")
    updated = _timestamp(value, "updated_at")
    if updated < created:
        raise ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede created_at")


def _validate_capability_descriptor(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "capability_id",
            "version",
            "owner",
            "effects",
            "permissions",
            "node_os",
            "maturity",
            "model_dependency",
            "review_required",
            "self_promotable",
        },
    )
    _nonempty_string(value, "capability_id")
    version = _nonempty_string(value, "version")
    if not SEMVER_RE.fullmatch(version):
        raise ContractError("INVALID_SEMVER", "version must be ASCII semantic version X.Y.Z")
    _nonempty_string(value, "owner")
    _sorted_unique_enum_list(value, "effects", EFFECTS, allow_empty=False)
    _sorted_unique_string_list(value, "permissions")
    _sorted_unique_enum_list(value, "node_os", NODE_OS, allow_empty=False)
    _enum(value, "maturity", MATURITY)
    _enum(value, "model_dependency", MODEL_DEPENDENCY)
    _bool(value, "review_required")
    self_promotable = _bool(value, "self_promotable")
    if self_promotable:
        raise ContractError("SELF_PROMOTION_FORBIDDEN", "capabilities cannot self-promote")


def _validate_command_envelope(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "command_id",
            "workspace_id",
            "capability_id",
            "effect",
            "payload",
            "created_at",
        },
    )
    _uuid(value, "command_id")
    _uuid(value, "workspace_id")
    _nonempty_string(value, "capability_id")
    _enum(value, "effect", EFFECTS)
    if not isinstance(value.get("payload"), dict):
        raise ContractError("INVALID_PAYLOAD", "payload must be an object")
    _timestamp(value, "created_at")


def _validate_event_envelope(value: dict[str, Any]) -> None:
    _exact_fields(
        value,
        {
            "contract_type",
            "schema_version",
            "event_id",
            "workspace_id",
            "producer",
            "kind",
            "sequence",
            "payload",
            "evidence_refs",
            "created_at",
        },
    )
    _uuid(value, "event_id")
    _uuid(value, "workspace_id")
    _nonempty_string(value, "producer")
    _nonempty_string(value, "kind")
    sequence = value.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ContractError("INVALID_SEQUENCE", "sequence must be a non-negative integer")
    if not isinstance(value.get("payload"), dict):
        raise ContractError("INVALID_PAYLOAD", "payload must be an object")
    _authority_ref_list(value, "evidence_refs")
    _timestamp(value, "created_at")


def _reject_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise ContractError("FLOAT_FORBIDDEN", f"floating-point value forbidden at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError("INVALID_OBJECT_KEY", f"object key at {path} must be a string")
            _reject_floats(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_floats(child, f"{path}[{index}]")


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


def _timestamp(value: dict[str, Any], field: str) -> datetime:
    item = _nonempty_string(value, field)
    if not item.endswith("Z"):
        raise ContractError("INVALID_TIMESTAMP", f"{field} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(item[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("INVALID_TIMESTAMP", f"{field} is not valid RFC3339") from exc
    if parsed.tzinfo != timezone.utc:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _enum(value: dict[str, Any], field: str, allowed: tuple[str, ...]) -> str:
    item = _nonempty_string(value, field)
    if item not in allowed:
        raise ContractError("INVALID_ENUM", f"{field} must be one of: {', '.join(allowed)}")
    return item


def _sorted_unique_string_list(value: dict[str, Any], field: str) -> list[str]:
    items = value.get(field)
    if not isinstance(items, list) or any(not isinstance(item, str) or not item for item in items):
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


def _authority_ref_list(value: dict[str, Any], field: str) -> list[dict[str, Any]]:
    items = value.get(field)
    if not isinstance(items, list):
        raise ContractError("INVALID_LIST", f"{field} must be a list")
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        validate_contract(item)
        if item.get("contract_type") != "authority_ref":
            raise ContractError("INVALID_REFERENCE", f"{field} may contain authority_ref contracts only")
        identity = (item["authority"], item["kind"], item["id"])
        if identity in seen:
            raise ContractError("DUPLICATE_REFERENCE", f"duplicate authority reference in {field}")
        seen.add(identity)
    return items
