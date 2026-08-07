from __future__ import annotations

import json
from pathlib import Path

import pytest

from origins_contracts import ContractError, canonical_json, contract_sha256, validate_contract

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / "contracts" / "fixtures.json").read_text(encoding="utf-8"))


def test_valid_contract_corpus() -> None:
    for case in FIXTURES["valid"]:
        contract = case["contract"]
        assert validate_contract(contract) is contract, case["name"]
        canonical = canonical_json(contract)
        assert " " not in canonical
        assert contract_sha256(contract) == contract_sha256(json.loads(canonical))


@pytest.mark.parametrize("case", FIXTURES["invalid"], ids=lambda case: case["name"])
def test_invalid_contract_corpus(case: dict) -> None:
    with pytest.raises(ContractError) as caught:
        validate_contract(case["contract"])
    assert caught.value.code == case["expected_error"]


def test_unicode_is_not_ascii_escaped() -> None:
    value = {"z": "Zambia", "a": "Origins — 工厂"}
    assert canonical_json(value) == '{"a":"Origins — 工厂","z":"Zambia"}'
