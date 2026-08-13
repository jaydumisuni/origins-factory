from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
ORIGINSD = ROOT / "rust" / "originsd"


def test_originsd_has_no_scope_lease_or_authority_activation_route() -> None:
    source = (ORIGINSD / "src" / "http.rs").read_text(encoding="utf-8")
    forbidden_routes = (
        '"/v1/scopes',
        '"/v1/leases',
        '"/v1/authority',
        '"/v1/capability-leases',
    )
    for route in forbidden_routes:
        assert route not in source


def test_stage2_authority_runtime_remains_dormant() -> None:
    runtime_source = (ORIGINSD / "src" / "authority_runtime.rs").read_text(encoding="utf-8")
    admission_source = (ORIGINSD / "src" / "authority_process.rs").read_text(encoding="utf-8")

    assert '"runtime_authority_activated": false' in runtime_source
    assert "runtime_authority_activated: false" in runtime_source
    assert "runtime_authority_activated: false" in admission_source
    assert "if decision.runtime_authority_activated" in admission_source
    assert "if plan.runtime_authority_activated" in admission_source


def test_stage2_contracts_exist_without_public_activation() -> None:
    assert (ROOT / "python" / "origins_contracts" / "authority.py").is_file()
    assert (ROOT / "typescript" / "authority.ts").is_file()
    assert (ROOT / "rust" / "origins-authority-contracts" / "src" / "lib.rs").is_file()
    assert (ORIGINSD / "src" / "authority_runtime.rs").is_file()
    assert (ORIGINSD / "src" / "authority_process.rs").is_file()
