from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from origins_contracts.authority_v11 import authority_sha256
from origins_contracts.contracts import contract_sha256
from origins_integration.lease_preflight import (
    ResourceGeneration,
    evaluate_lease_issuer_preflight,
    issuance_binding_document,
)


class BindingAwareTransport:
    def __init__(self, proofs: dict[str, dict[str, Any]]) -> None:
        self.proofs = proofs
        self.used: set[str] = set()

    def consume_step_up_proof(
        self,
        proof_id: str,
        binding: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if proof_id in self.used:
            return {"valid": False, "reason": "STEP_UP_PROOF_ALREADY_CONSUMED"}
        proof = self.proofs.get(proof_id)
        if proof is None:
            return {"valid": False, "reason": "STEP_UP_PROOF_NOT_FOUND"}
        if proof["binding"] != dict(binding):
            return {"valid": False, "reason": "STEP_UP_BINDING_MISMATCH"}
        self.used.add(proof_id)
        return {
            "valid": True,
            "proofId": proof_id,
            "userId": proof["user_id"],
            "methodType": "totp",
        }


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def scope_fixture() -> dict[str, Any]:
    fixtures = json.loads(
        (ROOT / "contracts" / "authority-fixtures.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(fixtures["valid"][0]["contract"])


def proposal_fixture() -> dict[str, Any]:
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


def provider_fixture() -> dict[str, Any]:
    return {
        "capability_id": "origins.process.run",
        "provider_id": "origins.process.local",
        "provider_manifest_digest": "2" * 64,
        "provider_generation": 4,
    }


def host_policy_fixture() -> dict[str, Any]:
    return {"digest": "3" * 64, "generation": 9}


def resources_fixture() -> list[dict[str, Any]]:
    return [
        {
            "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
            "generation": 7,
            "digest": "4" * 64,
        }
    ]


def auth_binding(approval_id: str, capability_id: str, digest: str) -> dict[str, Any]:
    return {
        "operationId": f"origins-lease:{approval_id}",
        "action": "origins_lease_issue",
        "target": capability_id,
        "subject": digest,
        "subjectType": "issuance_binding_sha256",
        "risk": "high",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentops-root", required=True)
    parser.add_argument("--expected-agentops-head", default="")
    parser.add_argument("--expected-origins-head", default="")
    args = parser.parse_args()

    agentops_root = Path(args.agentops_root).resolve()
    if not (agentops_root / "agentops").is_dir():
        raise SystemExit("AGENTOPS_ROOT_INVALID")
    sys.path.insert(0, str(agentops_root))

    from agentops import ApprovalService, TtgAuthAuthorizationPort

    agentops_head = git_head(agentops_root)
    origins_head = git_head(ROOT)
    if args.expected_agentops_head and agentops_head != args.expected_agentops_head:
        raise SystemExit(
            f"AGENTOPS_HEAD_MISMATCH expected={args.expected_agentops_head} actual={agentops_head}"
        )
    if args.expected_origins_head and origins_head != args.expected_origins_head:
        raise SystemExit(
            f"ORIGINS_HEAD_MISMATCH expected={args.expected_origins_head} actual={origins_head}"
        )

    proposal = proposal_fixture()
    scope = scope_fixture()
    provider = provider_fixture()
    host_policy = host_policy_fixture()
    resources = resources_fixture()

    with tempfile.TemporaryDirectory(prefix="origins-agentops-preflight-") as temp:
        approvals_path = Path(temp) / "approvals.json"
        service = ApprovalService.durable(approvals_path)
        request = service.create_request(
            task_title=proposal["task_title"],
            mode="capability_extension",
            gate="owner_approval_required",
            reason=proposal["reason"],
            requested_by=proposal["requested_by"],
            target=proposal["capability_id"],
            metadata=copy.deepcopy(proposal),
        )
        service.approve(
            request.approval_id,
            decided_by="owner-1",
            note="Approved for exact cross-repo non-activating preflight proof.",
        )
        evidence = service.get_evidence(request.approval_id).public_dict()
        if evidence["durable"] is not True or evidence["status"] != "approved":
            raise SystemExit("AGENTOPS_DURABLE_APPROVAL_NOT_PROVEN")

        restarted = ApprovalService.durable(approvals_path)
        recovered = restarted.get_evidence(request.approval_id).public_dict()
        for field in (
            "request_digest",
            "metadata_digest",
            "record_digest",
            "ledger_event_digest",
        ):
            if recovered[field] != evidence[field]:
                raise SystemExit(f"AGENTOPS_RESTART_DIGEST_MISMATCH:{field}")

        normalized_resources = tuple(
            ResourceGeneration(item["resource_id"], item["generation"], item["digest"])
            for item in resources
        )
        binding_document = issuance_binding_document(
            workspace_id=proposal["workspace_id"],
            capability_id=proposal["capability_id"],
            proposal_digest=contract_sha256(proposal),
            approval_id=evidence["approval_id"],
            approval_record_digest=evidence["record_digest"],
            scope_id=scope["scope_id"],
            scope_digest=authority_sha256(scope),
            scope_revision=scope["revision"],
            scope_fence=scope["fence"],
            provider=provider,
            host_policy=host_policy,
            resources=normalized_resources,
        )
        binding_digest = contract_sha256(binding_document)
        proof_id = "cross-repo-proof-1"
        transport = BindingAwareTransport(
            {
                proof_id: {
                    "user_id": "owner-1",
                    "binding": auth_binding(
                        evidence["approval_id"], proposal["capability_id"], binding_digest
                    ),
                }
            }
        )
        auth_port = TtgAuthAuthorizationPort(restarted, transport)
        authorization = dict(
            auth_port.verify_origins_issuance_authorization(
                {"auth_proof_id": proof_id},
                approval_id=evidence["approval_id"],
                capability_id=proposal["capability_id"],
                binding_digest=binding_digest,
            )
        )
        if authorization.get("valid") is not True:
            raise SystemExit(f"AGENTOPS_AUTHORIZATION_FAILED:{authorization}")

        receipt = evaluate_lease_issuer_preflight(
            proposal=proposal,
            current_scope=scope,
            approval_evidence=evidence,
            authorization=authorization,
            provider=provider,
            host_policy=host_policy,
            resources=resources,
            observed_at="2026-08-09T12:30:00Z",
        )
        if not receipt.eligible:
            raise SystemExit(f"ORIGINS_PREFLIGHT_NOT_ELIGIBLE:{receipt.failure_codes}")
        if receipt.issuer_enabled or receipt.lease_created or receipt.runtime_authority_activated:
            raise SystemExit("ORIGINS_PREFLIGHT_ACTIVATED_AUTHORITY")

        replay = dict(
            auth_port.verify_origins_issuance_authorization(
                {"auth_proof_id": proof_id},
                approval_id=evidence["approval_id"],
                capability_id=proposal["capability_id"],
                binding_digest=binding_digest,
            )
        )
        if replay.get("valid") is not False:
            raise SystemExit("AGENTOPS_AUTH_PROOF_REPLAY_ACCEPTED")

    print(
        json.dumps(
            {
                "status": "PASS",
                "agentops_head": agentops_head,
                "origins_head": origins_head,
                "durable_approval": True,
                "restart_digest_continuity": True,
                "one_time_auth_binding": True,
                "auth_replay_rejected": True,
                "preflight_eligible": True,
                "issuer_enabled": False,
                "lease_created": False,
                "runtime_authority_activated": False,
                "receipt_sha256": receipt.receipt_sha256,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
