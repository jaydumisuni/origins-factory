from __future__ import annotations

import json
from pathlib import Path

import pytest

from origins_contracts.authority import validate_authority_contract
from origins_contracts.contracts import ContractError, contract_sha256

FIXTURES = json.loads(
    (Path(__file__).parents[2] / "contracts" / "authority-fixtures.json").read_text(encoding="utf-8")
)


def test_shared_valid_authority_corpus_and_hashes() -> None:
    for item in FIXTURES["valid"]:
        contract = item["contract"]
        validate_authority_contract(contract)
        assert contract_sha256(contract) == item["sha256"]


def test_shared_invalid_authority_corpus_error_codes() -> None:
    for item in FIXTURES["invalid"]:
        with pytest.raises(ContractError) as captured:
            validate_authority_contract(item["contract"])
        assert captured.value.code == item["expected_error"], item["name"]
