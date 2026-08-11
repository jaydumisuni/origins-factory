from __future__ import annotations

import copy
import json
from pathlib import Path

from origins_contracts.authority_v11 import authority_sha256
from origins_contracts.contracts import contract_sha256
from origins_integration.lease_preflight import (
    evaluate_lease_issuer_preflight,
    issuance_binding_document,
    ResourceGeneration,
)

ROOT = Path(__file__).parents[2]


def _scope() -> dict:
    fixtures = json.loads((ROOT / "contracts" / "authority-fixtures.json").read_text(encoding="utf-8"))
    return copy.deepcopy(fixtures["valid"][0]["contract"])


def _proposal() -> dict:
    return {
        "proposal_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "task_title": "Bounded process capability",
        "capability_id": "origins.process.run",
        "reason": "The operation requires a bounded process capability.",
        "expected_benefit": "Run the approved proof command without widening host authority.",
        "requested_effects": ["execute", "observe"],
        "filesystem_read_scope": ["src"],
        "filesystem_write_scope": [],
        "network_mode": "allowlist",
        "network_hosts": ["api.example.com", "support.example.com"],
        "environment_names": ["LANG"],
        "persistent_lease": False,
        "delegated_remote_authority": False,
        "alternatives": ["manual operator execution"],
        "risks": ["process execution"],
        "requested_by": "hunter",
        "created_at": "2026-08-09T12:01:00Z",
        "approval_required": True,
        "self_approvable": False,
    }


def _approval(proposal: dict) -> dict:
    request = {
        "approval_id": "approval-42",
        "task_title": proposal["task_title"],
        "mode": "capability_extension",
        "gate": "owner_approval_required",
        "reason": proposal["reason"],
        "requested_by": proposal["requested_by"],
        "target": proposal["capability_id"],
        "metadata": copy.deepcopy(proposal),
        "status": "pending",
        "created_at": "2026-08-09T12:02:00Z",
    }
    record = {
        "approval_id": "approval-42",
        "decision": "approved",
        "decided_by": "owner-1",
        "note": "Approved for this bounded capability proposal.",
        "created_at": "2026-08-09T12:03:00Z",
    }
    request_digest = contract_sha256(request)
    return {
        "approval_id": "approval-42",
        "status": "approved",
        "durable": True,
        "request_digest": request_digest,
        "metadata_digest": contract_sha256(request["metadata"]),
        "record_digest": contract_sha256({"request_digest": request_digest, "record": record}),
        "ledger_event_digest": "d" * 64,
        "request": request,
        "record": record,
    }


def _provider() -> dict:
    return {
        "capability_id": "origins.process.run",
        "provider_id": "origins.process.local",
        "provider_manifest_digest": "2" * 64,
        "provider_generation": 4,
    }


def _host_policy() -> dict:
    return {"digest": "3" * 64, "generation": 9}


def _resources() -> list[dict]:
    return [
        {
            "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
            "generation": 7,
            "digest": "4" * 64,
        }
    ]


def _authorization(proposal: dict, scope: dict, approval: dict, provider: dict, host_policy: dict, resources: list[dict]) -> dict:
    normalized_resources = tuple(
        ResourceGeneration(item["resource_id"], item["generation"], item["digest"])
        for item in resources
    )
    binding = issuance_binding_document(
        workspace_id=proposal["workspace_id"],
        capability_id=proposal["capability_id"],
        proposal_digest=contract_sha256(proposal),
        approval_id=approval["approval_id"],
        approval_record_digest=approval["record_digest"],
        scope_id=scope["scope_id"],
        scope_digest=authority_sha256(scope),
        scope_revision=scope["revision"],
        scope_fence=scope["fence"],
        provider=provider,
        host_policy=host_policy,
        resources=normalized_resources,
    )
    return {
        "valid": True,
        "approval_id": approval["approval_id"],
        "primary_actor": approval["record"]["decided_by"],
        "method": "totp",
        "proof_id": "proof-42",
        "binding_digest": contract_sha256(binding),
    }


def _inputs() -> dict:
    proposal = _proposal()
    scope = _scope()
    approval = _approval(proposal)
    provider = _provider()
    host_policy = _host_policy()
    resources = _resources()
    authorization = _authorization(proposal, scope, approval, provider, host_policy, resources)
    return {
        "proposal": proposal,
        "current_scope": scope,
        "approval_evidence": approval,
        "authorization": authorization,
        "provider": provider,
        "host_policy": host_policy,
        "resources": resources,
        "observed_at": "2026-08-09T12:30:00Z",
    }


def test_eligible_preflight_is_integrity_addressed_but_cannot_activate_authority():
    receipt = evaluate_lease_issuer_preflight(**_inputs())

    assert receipt.eligible is True
    assert receipt.failure_codes == ()
    assert receipt.issuer_enabled is False
    assert receipt.lease_created is False
    assert receipt.runtime_authority_activated is False
    assert len(receipt.receipt_sha256) == 64
    assert receipt.as_dict()["receipt_sha256"] == receipt.receipt_sha256
    assert receipt.scope_digest == "43f53c0053a14e7403d2b38f7dfbff6e4dda6ed238e6a673551d31c407bc24ae"


def test_auth_binding_cannot_be_replayed_after_scope_generation_changes():
    values = _inputs()
    values["current_scope"]["revision"] = 2
    values["current_scope"]["fence"] = 2
    values["current_scope"]["updated_at"] = "2026-08-09T12:10:00Z"

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "AUTH_BINDING_MISMATCH" in receipt.failure_codes


def test_approval_metadata_must_be_exact_proposal():
    values = _inputs()
    values["approval_evidence"]["request"]["metadata"]["capability_id"] = "origins.browser.observe"

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "APPROVAL_PROPOSAL_MISMATCH" in receipt.failure_codes
    assert "APPROVAL_REQUEST_DIGEST_MISMATCH" in receipt.failure_codes


def test_in_memory_approval_can_never_pass_preflight():
    values = _inputs()
    values["approval_evidence"]["durable"] = False

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "APPROVAL_NOT_DURABLE" in receipt.failure_codes


def test_wrong_auth_actor_cannot_pass_even_with_durable_approved_record():
    values = _inputs()
    values["authorization"]["primary_actor"] = "owner-2"

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "AUTH_ACTOR_MISMATCH" in receipt.failure_codes


def test_resource_generation_set_must_exactly_cover_current_scope_resources():
    values = _inputs()
    values["resources"] = []

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "RESOURCE_SET_MISMATCH" in receipt.failure_codes
    assert "AUTH_BINDING_MISMATCH" in receipt.failure_codes


def test_provider_substitution_breaks_capability_and_auth_binding():
    values = _inputs()
    values["provider"]["provider_id"] = "origins.process.alternate"

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "AUTH_BINDING_MISMATCH" in receipt.failure_codes


def test_expired_scope_cannot_pass_even_if_every_digest_matches():
    values = _inputs()
    values["observed_at"] = "2026-08-09T14:00:01Z"

    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "SCOPE_EXPIRED" in receipt.failure_codes


def test_failed_receipt_remains_nonactivating():
    values = _inputs()
    values["authorization"]["valid"] = False
    receipt = evaluate_lease_issuer_preflight(**values)

    assert receipt.eligible is False
    assert "AUTH_NOT_VALID" in receipt.failure_codes
    assert receipt.as_dict()["issuer_enabled"] is False
    assert receipt.as_dict()["lease_created"] is False
    assert receipt.as_dict()["runtime_authority_activated"] is False
