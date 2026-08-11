from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from origins_contracts.authority import (
    validate_authority_contract,
    validate_child_scope,
    validate_lease_within_scope,
    validate_provider_binding,
    validate_scope_current,
)
from origins_contracts.contracts import ContractError

ROOT = Path(__file__).parents[2]
FIXTURES = json.loads((ROOT / "contracts" / "authority-fixtures.json").read_text(encoding="utf-8"))


def scope() -> dict:
    return deepcopy(FIXTURES["valid"][0]["contract"])


def lease() -> dict:
    return deepcopy(FIXTURES["valid"][1]["contract"])


def child_scope(*, candidate_id: str = "candidate-a") -> dict:
    parent = scope()
    child = deepcopy(parent)
    child.update(
        {
            "scope_id": "66666666-6666-4666-8666-666666666666",
            "candidate_id": candidate_id,
            "parent_scope_id": parent["scope_id"],
            "effects": ["execute", "observe"],
            "resource_reads": [
                {
                    "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
                    "prefix": "src",
                }
            ],
            "resource_writes": [],
            "network_endpoints": [
                {"protocol": "https", "host": "support.example.com", "port": 443}
            ],
            "environment_names": ["LANG"],
            "delegation_allowed": False,
            "issued_at": "2026-08-09T12:10:00Z",
            "updated_at": "2026-08-09T12:10:00Z",
            "expires_at": "2026-08-09T13:30:00Z",
        }
    )
    return child


def test_v11_valid_scope_and_lease() -> None:
    parent = scope()
    item = lease()
    validate_authority_contract(parent)
    validate_authority_contract(item)
    validate_lease_within_scope(item, parent)


def test_sec001_parent_lease_id_is_not_part_of_v11() -> None:
    item = lease()
    item["parent_lease_id"] = "66666666-6666-4666-8666-666666666666"
    with pytest.raises(ContractError) as captured:
        validate_authority_contract(item)
    assert captured.value.code == "UNKNOWN_FIELD"


def test_sec002_operation_identity_is_immutable() -> None:
    child = child_scope()
    child["operation_id"] = "agentops:other"
    with pytest.raises(ContractError) as captured:
        validate_child_scope(child, scope())
    assert captured.value.code == "SCOPE_ESCALATION"


def test_sec002_candidate_can_bind_once_then_cannot_switch_or_clear() -> None:
    root = scope()
    bound = child_scope(candidate_id="candidate-a")
    validate_child_scope(bound, root)

    grandchild = deepcopy(bound)
    grandchild.update(
        {
            "scope_id": "77777777-7777-4777-8777-777777777777",
            "parent_scope_id": bound["scope_id"],
            "issued_at": "2026-08-09T12:20:00Z",
            "updated_at": "2026-08-09T12:20:00Z",
        }
    )
    bound["delegation_allowed"] = True
    validate_child_scope(grandchild, bound)

    switched = deepcopy(grandchild)
    switched["candidate_id"] = "candidate-b"
    with pytest.raises(ContractError, match="candidate identity"):
        validate_child_scope(switched, bound)

    cleared = deepcopy(grandchild)
    cleared["candidate_id"] = ""
    with pytest.raises(ContractError, match="candidate identity"):
        validate_child_scope(cleared, bound)


def test_sec003_provider_binding_is_exact_and_generation_fenced() -> None:
    item = lease()
    validate_provider_binding(
        item,
        provider_id="origins.process.local",
        provider_manifest_digest="2" * 64,
        provider_generation=1,
    )
    for provider_id, digest, generation in (
        ("origins.process.other", "2" * 64, 1),
        ("origins.process.local", "3" * 64, 1),
        ("origins.process.local", "2" * 64, 2),
    ):
        with pytest.raises(ContractError) as captured:
            validate_provider_binding(
                item,
                provider_id=provider_id,
                provider_manifest_digest=digest,
                provider_generation=generation,
            )
        assert captured.value.code == "PROVIDER_SUBSTITUTION"


def test_sec004_scope_state_and_fence_reject_stale_generation() -> None:
    current = scope()
    validate_scope_current(current, current)

    stale = deepcopy(current)
    current["fence"] = 2
    current["revision"] = 2
    current["updated_at"] = "2026-08-09T12:01:00Z"
    with pytest.raises(ContractError) as captured:
        validate_scope_current(stale, current)
    assert captured.value.code == "STALE_SCOPE"

    revoked = deepcopy(current)
    revoked["state"] = "revoked"
    with pytest.raises(ContractError) as captured:
        validate_scope_current(revoked, revoked)
    assert captured.value.code == "SCOPE_UNUSABLE"


def test_sec005_network_endpoint_requires_protocol_host_port() -> None:
    parent = scope()
    parent["network_endpoints"] = [{"protocol": "http", "host": "support.example.com", "port": 443}]
    validate_authority_contract(parent)

    child = child_scope()
    child["network_endpoints"] = [{"protocol": "https", "host": "support.example.com", "port": 443}]
    with pytest.raises(ContractError, match="network_endpoints"):
        validate_child_scope(child, scope())

    bad = scope()
    bad["network_endpoints"] = [{"protocol": "https", "host": "support.example.com", "port": 0}]
    with pytest.raises(ContractError) as captured:
        validate_authority_contract(bad)
    assert captured.value.code == "INVALID_NETWORK_PORT"


def test_holder_identity_is_uuid_and_generation_bound() -> None:
    item = lease()
    item["holder_id"] = "candidate-a-build"
    with pytest.raises(ContractError) as captured:
        validate_authority_contract(item)
    assert captured.value.code == "INVALID_UUID"

    item = lease()
    item["holder_generation"] = 0
    with pytest.raises(ContractError) as captured:
        validate_authority_contract(item)
    assert captured.value.code == "INVALID_HOLDER_GENERATION"


def test_relational_issuance_chronology_fails_closed() -> None:
    child = child_scope()
    child["issued_at"] = "2026-08-09T11:59:00Z"
    child["updated_at"] = "2026-08-09T12:10:00Z"
    with pytest.raises(ContractError) as captured:
        validate_child_scope(child, scope())
    assert captured.value.code == "INVALID_ISSUANCE_CHRONOLOGY"

    item = lease()
    item["issued_at"] = "2026-08-09T11:59:00Z"
    item["updated_at"] = "2026-08-09T12:05:00Z"
    with pytest.raises(ContractError) as captured:
        validate_lease_within_scope(item, scope())
    assert captured.value.code == "INVALID_ISSUANCE_CHRONOLOGY"


def test_child_scope_still_cannot_widen_resources_denies_environment_or_expiry() -> None:
    parent = scope()

    widened = child_scope()
    widened["resource_reads"] = [
        {"resource_id": "worktree:99999999-9999-4999-8999-999999999999", "prefix": "src"}
    ]
    with pytest.raises(ContractError, match="outside its parent"):
        validate_child_scope(widened, parent)

    dropped = child_scope()
    dropped["resource_denies"] = []
    with pytest.raises(ContractError, match="cannot drop"):
        validate_child_scope(dropped, parent)

    environment = child_scope()
    environment["environment_names"] = ["LANG", "SECRET"]
    with pytest.raises(ContractError, match="environment_names"):
        validate_child_scope(environment, parent)

    expiry = child_scope()
    expiry["expires_at"] = "2026-08-09T15:00:00Z"
    with pytest.raises(ContractError, match="expiry"):
        validate_child_scope(expiry, parent)
