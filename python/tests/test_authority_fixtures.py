from __future__ import annotations

import json
from pathlib import Path

import pytest

from origins_contracts.authority import validate_authority_contract
from origins_contracts.contracts import ContractError, contract_sha256

FIXTURES = json.loads(
    (Path(__file__).parents[2] / "contracts" / "authority-fixtures.json").read_text(encoding="utf-8")
)
EXPECTED_HASHES = {
    "workspace_candidate_scope": "69acd382b43d3aaee19c57e735ae735bc9c7c770cd4003cae6aec198ab647d9d",
    "bounded_process_lease": "c44ba1680fb24b92b1391260daa59adf02a799cbdb3e54c0f30c5a0fb24e1fe0",
}


def test_shared_valid_authority_corpus_and_hashes() -> None:
    for item in FIXTURES["valid"]:
        contract = item["contract"]
        validate_authority_contract(contract)
        assert contract_sha256(contract) == EXPECTED_HASHES[item["name"]]


def test_shared_invalid_authority_corpus_error_codes() -> None:
    for item in FIXTURES["invalid"]:
        with pytest.raises(ContractError) as captured:
            validate_authority_contract(item["contract"])
        assert captured.value.code == item["expected_error"], item["name"]
