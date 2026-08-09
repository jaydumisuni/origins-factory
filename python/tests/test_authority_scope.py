from __future__ import annotations

from copy import deepcopy

import pytest

from origins_contracts.authority import (
    validate_authority_contract,
    validate_child_scope,
    validate_lease_within_scope,
)
from origins_contracts.contracts import ContractError, contract_sha256

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
SCOPE_ID = "22222222-2222-4222-8222-222222222222"
CHILD_SCOPE_ID = "33333333-3333-4333-8333-333333333333"
LEASE_ID = "44444444-4444-4444-8444-444444444444"
EMPTY_DIGEST = "0" * 64
PROPOSAL_DIGEST = "1" * 64


def grant(resource_id: str, prefix: str = "") -> dict[str, str]:
    return {"resource_id": resource_id, "prefix": prefix}


def scope() -> dict:
    return {
        "contract_type": "execution_scope",
        "schema_version": "1.0.0",
        "scope_id": SCOPE_ID,
        "workspace_id": WORKSPACE_ID,
        "operation_id": "agentops:op-42",
        "candidate_id": "candidate-a",
        "parent_scope_id": "",
        "effects": ["execute", "mutate", "observe", "verify"],
        "resource_reads": [
            grant(f"worktree:{CHILD_SCOPE_ID}"),
        ],
        "resource_writes": [
            grant(f"worktree:{CHILD_SCOPE_ID}", "src"),
        ],
        "resource_denies": [
            grant(f"worktree:{CHILD_SCOPE_ID}", ".origins"),
        ],
        "network_mode": "allowlist",
        "network_hosts": ["api.example.com", "support.example.com"],
        "environment_names": ["LANG", "PATH"],
        "process_execution_allowed": True,
        "persistent_process_allowed": False,
        "delegation_allowed": True,
        "delegated_remote_authority": False,
        "issued_at": "2026-08-09T12:00:00Z",
        "updated_at": "2026-08-09T12:00:00Z",
        "expires_at": "2026-08-09T14:00:00Z",
        "revision": 1,
    }


def child_scope() -> dict:
    value = scope()
    value.update(
        {
            "scope_id": CHILD_SCOPE_ID,
            "candidate_id": "candidate-b",
            "parent_scope_id": SCOPE_ID,
            "effects": ["execute", "observe"],
            "resource_reads": [grant(f"worktree:{CHILD_SCOPE_ID}", "src")],
            "resource_writes": [],
            "resource_denies": [grant(f"worktree:{CHILD_SCOPE_ID}", ".origins")],
            "network_hosts": ["support.example.com"],
            "environment_names": ["LANG"],
            "delegation_allowed": False,
            "expires_at": "2026-08-09T13:30:00Z",
        }
    )
    return value


def lease() -> dict:
    return {
        "contract_type": "capability_lease",
        "schema_version": "1.0.0",
        "lease_id": LEASE_ID,
        "scope_id": SCOPE_ID,
        "workspace_id": WORKSPACE_ID,
        "parent_lease_id": "",
        "capability_id": "origins.process.run",
        "holder_kind": "session",
        "holder_id": "candidate-a-build",
        "effects": ["execute", "observe"],
        "resource_reads": [grant(f"worktree:{CHILD_SCOPE_ID}", "src")],
        "resource_writes": [],
        "resource_denies": [grant(f"worktree:{CHILD_SCOPE_ID}", ".origins")],
        "network_mode": "deny",
        "network_hosts": [],
        "environment_names": ["LANG"],
        "persistent_process_allowed": False,
        "delegated_remote_authority": False,
        "approval_authority": "jaydumisuni/Hunter-AgentOps",
        "approval_id": "approval-42",
        "approval_digest": EMPTY_DIGEST,
        "proposal_digest": PROPOSAL_DIGEST,
        "state": "active",
        "fence": 1,
        "issued_at": "2026-08-09T12:05:00Z",
        "updated_at": "2026-08-09T12:05:00Z",
        "expires_at": "2026-08-09T13:00:00Z",
        "revision": 1,
    }


def test_valid_scope_and_lease_are_canonical_hashable_candidates() -> None:
    parent = scope()
    item = lease()
    validate_authority_contract(parent)
    validate_authority_contract(item)
    validate_lease_within_scope(item, parent)
    assert len(contract_sha256(parent)) == 64
    assert len(contract_sha256(item)) == 64


def test_child_scope_can_only_narrow_parent_authority() -> None:
    parent = scope()
    child = child_scope()
    validate_child_scope(child, parent)


def test_child_scope_cannot_write_outside_parent_write_grant() -> None:
    parent = scope()
    child = child_scope()
    child["resource_reads"] = [grant(f"worktree:{CHILD_SCOPE_ID}", "docs")]
    child["resource_writes"] = [grant(f"worktree:{CHILD_SCOPE_ID}", "docs")]
    with pytest.raises(ContractError, match="outside its parent"):
        validate_child_scope(child, parent)


def test_child_scope_cannot_drop_parent_deny() -> None:
    child = child_scope()
    child["resource_denies"] = []
    with pytest.raises(ContractError, match="cannot drop a parent resource deny"):
        validate_child_scope(child, scope())


def test_child_scope_cannot_change_network_authority_class() -> None:
    child = child_scope()
    child["network_mode"] = "delegated_remote"
    child["network_hosts"] = ["support.example.com"]
    child["delegated_remote_authority"] = True
    with pytest.raises(ContractError, match="network authority class"):
        validate_child_scope(child, scope())


def test_child_scope_cannot_extend_expiry() -> None:
    child = child_scope()
    child["expires_at"] = "2026-08-09T15:00:00Z"
    with pytest.raises(ContractError, match="expiry cannot extend"):
        validate_child_scope(child, scope())


def test_child_scope_cannot_exist_when_parent_forbids_delegation() -> None:
    parent = scope()
    parent["delegation_allowed"] = False
    with pytest.raises(ContractError, match="forbids delegation"):
        validate_child_scope(child_scope(), parent)


def test_lease_cannot_expand_effects_environment_or_network() -> None:
    parent = scope()
    item = lease()
    item["effects"] = ["execute", "observe", "publish"]
    with pytest.raises(ContractError, match="effects cannot expand"):
        validate_lease_within_scope(item, parent)

    item = lease()
    item["environment_names"] = ["LANG", "SECRET_TOKEN"]
    with pytest.raises(ContractError, match="environment_names cannot expand"):
        validate_lease_within_scope(item, parent)

    item = lease()
    item["network_mode"] = "delegated_remote"
    item["network_hosts"] = ["support.example.com"]
    item["delegated_remote_authority"] = True
    with pytest.raises(ContractError, match="network authority class"):
        validate_lease_within_scope(item, parent)


def test_lease_requires_approval_and_proposal_digests() -> None:
    item = lease()
    item["approval_digest"] = ""
    with pytest.raises(ContractError, match="approval_digest"):
        validate_authority_contract(item)

    item = lease()
    item["proposal_digest"] = "abc"
    with pytest.raises(ContractError, match="proposal_digest"):
        validate_authority_contract(item)


def test_persistent_process_cannot_appear_without_execute_effect() -> None:
    item = lease()
    item["effects"] = ["observe"]
    item["persistent_process_allowed"] = True
    with pytest.raises(ContractError, match="requires execute effect"):
        validate_authority_contract(item)


def test_resource_prefixes_are_relative_normalized_and_portable() -> None:
    bad_prefixes = ["/etc", "../escape", "src/../secret", r"src\\secret", "src//secret", "src/"]
    for prefix in bad_prefixes:
        value = scope()
        value["resource_reads"] = [grant(f"worktree:{CHILD_SCOPE_ID}", prefix)]
        value["resource_writes"] = []
        with pytest.raises(ContractError):
            validate_authority_contract(value)


def test_deny_can_carve_hole_but_full_grant_cannot_be_denied() -> None:
    value = scope()
    validate_authority_contract(value)

    blocked = deepcopy(value)
    blocked["resource_reads"] = [grant(f"worktree:{CHILD_SCOPE_ID}", ".origins")]
    blocked["resource_writes"] = []
    with pytest.raises(ContractError, match="fully covered by a deny"):
        validate_authority_contract(blocked)


def test_network_hosts_are_exact_not_urls_or_wildcards() -> None:
    for host in ("https://example.com", "*.example.com", "user@example.com", "example.com/path"):
        value = scope()
        value["network_hosts"] = [host]
        with pytest.raises(ContractError):
            validate_authority_contract(value)


def test_fence_and_revision_must_be_positive() -> None:
    item = lease()
    item["fence"] = 0
    with pytest.raises(ContractError, match="fence"):
        validate_authority_contract(item)

    item = lease()
    item["revision"] = 0
    with pytest.raises(ContractError, match="revision"):
        validate_authority_contract(item)


def test_expired_lease_requires_expiry_timestamp() -> None:
    item = lease()
    item["state"] = "expired"
    item["expires_at"] = ""
    with pytest.raises(ContractError, match="expired lease requires"):
        validate_authority_contract(item)
