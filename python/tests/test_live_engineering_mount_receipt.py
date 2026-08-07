from __future__ import annotations

import hashlib

from origins_contracts import canonical_json
from origins_integration.live_mount import LiveEngineeringMountReceipt


def make_receipt(*, verdict: str = "PASS") -> LiveEngineeringMountReceipt:
    return LiveEngineeringMountReceipt(
        proof_scope="fixture",
        mount_status="compatible",
        live_engineering_proven=False,
        repository_id="11111111-1111-4111-8111-111111111111",
        repository_revision=9,
        repository_head_oid="a" * 40,
        operation_id="origins-live-mount-proof",
        doctor_surfaces=(
            {
                "surface": "agentops_python",
                "status": "compatible",
                "version": "0.3.0",
                "session_id": "",
                "evidence_sha256": "",
            },
            {
                "surface": "codeops_cli",
                "status": "compatible",
                "version": "0.3.0",
                "session_id": "session-codeops",
                "evidence_sha256": "b" * 64,
            },
        ),
        route_session_id="session-route",
        sergeant_command_session_id="session-command",
        sergeant_review_session_id="session-review",
        review_sha256="c" * 64,
        project_verdict=verdict,
        recommended_agentops_action="complete_candidate" if verdict == "PASS" else "correct",
    )


def test_receipt_sha256_is_canonical_and_exposed_once() -> None:
    receipt = make_receipt()
    expected = hashlib.sha256(canonical_json(receipt.body_dict()).encode("utf-8")).hexdigest()
    assert receipt.receipt_sha256 == expected
    assert len(receipt.receipt_sha256) == 64
    payload = receipt.as_dict()
    assert payload["receipt_sha256"] == expected
    assert "receipt_sha256" not in receipt.body_dict()


def test_receipt_digest_is_deterministic_and_body_sensitive() -> None:
    first = make_receipt()
    same = make_receipt()
    changed = make_receipt(verdict="NEEDS WORK")
    assert first.receipt_sha256 == same.receipt_sha256
    assert first.receipt_sha256 != changed.receipt_sha256


def test_receipt_does_not_store_raw_config_or_review_output() -> None:
    payload = make_receipt().as_dict()
    assert "config" not in payload
    assert "stdout" not in payload
    assert "summary" not in payload
