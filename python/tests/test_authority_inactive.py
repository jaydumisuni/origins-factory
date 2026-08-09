from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
ORIGINSD = ROOT / "rust" / "originsd"


def test_candidate_authority_crate_is_not_an_originsd_dependency() -> None:
    cargo = (ORIGINSD / "Cargo.toml").read_text(encoding="utf-8")
    assert "origins-authority-contracts" not in cargo


def test_originsd_has_no_scope_lease_or_authority_activation_route() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ORIGINSD / "src").glob("*.rs"))
    )
    forbidden_routes = (
        '"/v1/scopes',
        '"/v1/leases',
        '"/v1/authority',
        '"/v1/capability-leases',
    )
    for route in forbidden_routes:
        assert route not in source


def test_originsd_has_no_production_lease_issuer_symbols() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ORIGINSD / "src").glob("*.rs"))
    ).lower()
    forbidden_symbols = (
        "mint_capability_lease",
        "issue_capability_lease",
        "activate_capability_lease",
        "create_execution_scope",
        "origins_authority_contracts",
    )
    for symbol in forbidden_symbols:
        assert symbol not in source


def test_candidate_contracts_exist_only_as_nonactivating_review_semantics() -> None:
    assert (ROOT / "python" / "origins_contracts" / "authority.py").is_file()
    assert (ROOT / "typescript" / "authority.ts").is_file()
    assert (ROOT / "rust" / "origins-authority-contracts" / "src" / "lib.rs").is_file()

    # The candidate may validate/hash authority documents, but originsd itself must
    # remain mechanically unaware of those candidate contracts until review is reconciled.
    originsd_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ORIGINSD / "src").glob("*.rs"))
    )
    assert "execution_scope" not in originsd_source
    assert "capability_lease" not in originsd_source
