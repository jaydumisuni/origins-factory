from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from origins_contracts.authority import (
    validate_authority_contract,
    validate_child_scope,
    validate_lease_within_scope,
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
            "scope_id": "33333333-3333-4333-8333-333333333333",
            "candidate_id": "candidate-b",
            "parent_scope_id": parent["scope_id"],
            "effects": ["execute", "observe"],
            "resource_reads": [
                {
                    "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
                    "prefix": "src",
                }
            ],
            "resource_writes": [],
            "resource_denies": [
                {
                    "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
                    "prefix": ".origins",
                }
            ],
            "network_hosts": ["support.example.com"],
            "environment_names": ["LANG"],
            "delegation_allowed": False,
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
        if attack["relation"] == "child_scope":
            parent = _base("scope")
            parent.update(deepcopy(attack.get("parent_set", {})))
            child = _child_scope()
            child.update(deepcopy(attack.get("child_set", {})))
            call = lambda: validate_child_scope(child, parent)
        elif attack["relation"] == "lease_scope":
            scope = _base("scope")
            scope.update(deepcopy(attack.get("scope_set", {})))
            lease = _base("lease")
            lease.update(deepcopy(attack.get("lease_set", {})))
            call = lambda: validate_lease_within_scope(lease, scope)
        else:
            raise AssertionError(f"unknown relation {attack['relation']}")

        with pytest.raises(ContractError) as captured:
            call()
        assert captured.value.code == attack["expected_error"], attack["name"]
