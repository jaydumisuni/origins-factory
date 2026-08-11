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
ATTACKS = json.loads((ROOT / "contracts" / "authority-adversarial-fixtures.json").read_text(encoding="utf-8"))


def _base(name: str) -> dict:
    mapping = {
        "scope": FIXTURES["valid"][0]["contract"],
        "lease": FIXTURES["valid"][1]["contract"],
    }
    return deepcopy(mapping[name])


def _child_scope() -> dict:
    parent = _base("scope")
    child = deepcopy(parent)
    child.update(
        {
            "scope_id": "66666666-6666-4666-8666-666666666666",
            "candidate_id": "candidate-a",
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


def test_shared_invalid_contract_attack_corpus() -> None:
    for attack in ATTACKS["invalid_contracts"]:
        value = _base(attack["base"])
        value.update(deepcopy(attack["set"]))
        with pytest.raises(ContractError) as captured:
            validate_authority_contract(value)
        assert captured.value.code == attack["expected_error"], attack["name"]


def test_shared_relation_attack_corpus() -> None:
    for attack in ATTACKS["relations"]:
        relation = attack["relation"]
        if relation == "child_scope":
            parent = _base("scope")
            child = _child_scope()
            parent.update(deepcopy(attack.get("parent_set", {})))
            child.update(deepcopy(attack.get("child_set", {})))
            call = lambda: validate_child_scope(child, parent)
        elif relation == "lease_scope":
            parent = _base("scope")
            item = _base("lease")
            parent.update(deepcopy(attack.get("scope_set", {})))
            item.update(deepcopy(attack.get("lease_set", {})))
            call = lambda: validate_lease_within_scope(item, parent)
        elif relation == "scope_current":
            presented = _base("scope")
            current = _base("scope")
            presented.update(deepcopy(attack.get("presented_set", {})))
            current.update(deepcopy(attack.get("current_set", {})))
            call = lambda: validate_scope_current(presented, current)
        elif relation == "provider_binding":
            item = _base("lease")
            call = lambda: validate_provider_binding(
                item,
                provider_id=attack["provider_id"],
                provider_manifest_digest=attack["provider_manifest_digest"],
                provider_generation=attack["provider_generation"],
            )
        else:
            raise AssertionError(f"unknown relation {relation}")

        with pytest.raises(ContractError) as captured:
            call()
        assert captured.value.code == attack["expected_error"], attack["name"]
