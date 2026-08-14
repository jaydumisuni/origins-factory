#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))


def fail(message: str) -> None:
    raise SystemExit(f"PHASE4_AGENTOPS_OWNER_PROOF_FAIL: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove Origins Phase-4 against the real Hunter-AgentOps owner package."
    )
    parser.add_argument("--agentops-root", required=True)
    args = parser.parse_args()

    agentops_root = Path(args.agentops_root).expanduser().resolve()
    if not (agentops_root / "agentops" / "department_operation.py").is_file():
        fail(f"AgentOps owner root is invalid: {agentops_root}")
    if not (agentops_root / "playbooks" / "code_ops.yml").is_file():
        fail("AgentOps code_ops playbook is missing")

    sys.path.insert(0, str(agentops_root))

    from origins_integration.intelligence_runtime import AgentOpsMount
    from origins_integration.phase4_runtime import Phase4IntelligenceRuntime

    with TemporaryDirectory(prefix="origins-phase4-agentops-") as temporary:
        state_root = Path(temporary) / "agentops-state"
        runtime = Phase4IntelligenceRuntime(
            agentops=AgentOpsMount(state_root, agentops_root)
        )
        status = runtime.agentops.status()
        if not status.available:
            fail(status.detail)

        created = runtime.create_approval(
            {
                "kind": "operation",
                "reason": "Phase-4 immutable owner-mount proof.",
                "subject": {
                    "playbook": "code_ops",
                    "title": "Prove Origins AgentOps durable handoff",
                    "target": "jaydumisuni/origins-factory",
                    "requested_action": "review_and_prepare",
                    "risk": "medium",
                    "evidence": {},
                },
            }
        )
        approval = created.get("approval")
        if not isinstance(approval, dict):
            fail("approval response is not an object")
        request = approval.get("request")
        if not isinstance(request, dict):
            fail("approval request is missing")
        approval_id = str(request.get("approval_id") or "")
        if not approval_id:
            fail("approval_id is missing")

        prepared = created.get("prepared_operation")
        if not isinstance(prepared, dict):
            fail("prepared Operation is missing")
        operation_id = str(prepared.get("operation_id") or "")
        if not operation_id.startswith("origins-"):
            fail("Origins did not generate the Operation identity")
        if prepared.get("required_gate") != "review_required":
            fail("code_ops gate was not recovered from the owner playbook")

        runtime.decide_approval(
            {
                "approval_id": approval_id,
                "decision": "approved",
                "decided_by": "owner",
                "note": "Phase-4 owner-mount proof only.",
            }
        )
        first = runtime.run_agentops({"approval_id": approval_id})
        if first.get("accepted") is not True:
            fail(f"AgentOps did not accept approved Operation: {first}")
        if first.get("execution_dispatched") is not False:
            fail("disabled AgentOps foundation unexpectedly dispatched execution")
        operation_packet = first.get("operation")
        if not isinstance(operation_packet, dict):
            fail("AgentOps result omitted the canonical Operation packet")
        if operation_packet.get("operation_id") != operation_id:
            fail("AgentOps changed the Origins-generated Operation identity")
        if "playbook_id" in operation_packet or "title" in operation_packet:
            fail("Workspace-only metadata crossed the generic AgentOps boundary")

        recovered_runtime = Phase4IntelligenceRuntime(
            agentops=AgentOpsMount(state_root, agentops_root)
        )
        recovered = recovered_runtime.operations()
        durable_results = recovered.get("operations")
        if not isinstance(durable_results, list):
            fail("durable Operation results are not recoverable")
        matching = [
            value
            for value in durable_results
            if isinstance(value, dict) and value.get("operation_id") == operation_id
        ]
        if len(matching) != 1:
            fail("exact durable Operation was not recovered after runtime restart")

        replay = recovered_runtime.run_agentops({"approval_id": approval_id})
        if replay.get("operation_id") != operation_id:
            fail("exact replay changed Operation identity")
        if replay.get("idempotent_replay") is not True:
            fail("restart replay was not recognized as idempotent")
        if replay.get("execution_dispatched") is not False:
            fail("replay unexpectedly dispatched execution")

        print(
            json.dumps(
                {
                    "proof": "PHASE4_AGENTOPS_OWNER_MOUNT_OK",
                    "operation_id": operation_id,
                    "approval_id": approval_id,
                    "first_status": first.get("status"),
                    "replay_idempotent": replay.get("idempotent_replay"),
                    "execution_dispatched": replay.get("execution_dispatched"),
                    "durable_results": len(durable_results),
                },
                sort_keys=True,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
