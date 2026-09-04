#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from v1_mission_candidate import run_candidate_phase
from v1_mission_contract import (
    AGENTOPS_HEAD,
    CODEOPS_HEAD,
    SERGEANT_HEAD,
    V1MissionError,
    file_sha256,
    require_two_enabled_providers,
)
from v1_mission_recovery import run_recovery_phase
from v1_mission_support import (
    _assert_clean,
    _git_head,
    _module_authority_record,
    _running_http_server,
    _tracked_file_record,
    _write_owner_entrypoint,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove the final standalone Origins v1 repository Mission on an exact host"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--agentops-root", type=Path, required=True)
    parser.add_argument("--codeops-root", type=Path, required=True)
    parser.add_argument("--sergeant-root", type=Path, required=True)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("/home/kratos/origins-v1-evidence"),
    )
    args = parser.parse_args(argv)

    source_root = Path(__file__).resolve().parents[1]
    agentops_root = args.agentops_root.resolve()
    codeops_root = args.codeops_root.resolve()
    sergeant_root = args.sergeant_root.resolve()
    expected_head = os.environ.get("ORIGINS_V1_EXPECTED_HEAD", "").strip()
    if not expected_head:
        raise V1MissionError("ORIGINS_V1_EXPECTED_HEAD is required")

    repository_heads = {
        "origins": _git_head(source_root),
        "agentops": _git_head(agentops_root),
        "codeops": _git_head(codeops_root),
        "sergeant": _git_head(sergeant_root),
    }
    expected_heads = {
        "origins": expected_head,
        "agentops": AGENTOPS_HEAD,
        "codeops": CODEOPS_HEAD,
        "sergeant": SERGEANT_HEAD,
    }
    if repository_heads != expected_heads:
        raise V1MissionError(
            f"authority mismatch: expected={expected_heads} actual={repository_heads}"
        )
    for label, root in (
        ("Origins", source_root),
        ("AgentOps", agentops_root),
        ("CodeOps", codeops_root),
        ("Sergeant", sergeant_root),
    ):
        _assert_clean(label, root)

    daemon_binary = args.binary.resolve()
    if not daemon_binary.is_file():
        raise V1MissionError(f"Origins daemon binary is unavailable: {daemon_binary}")

    hunter_url = os.environ.get("ORIGINS_HUNTER_URL", "").strip()
    hunter_token = os.environ.get("ORIGINS_HUNTER_TOKEN", "").strip()
    if not hunter_url.startswith("https://") or not hunter_token:
        raise V1MissionError(
            "final v1 Mission requires live production Hunter URL/token for the initial semantic turn"
        )

    # Prevent imports from mutating clean owner trees, then resolve every owner module that
    # will execute and prove that the resolved bytes are tracked by the pinned owner revision.
    sys.dont_write_bytecode = True
    for path in (source_root / "python", source_root / "tools", codeops_root, agentops_root, sergeant_root):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    module_authority = [
        _module_authority_record("Origins AgentOps MCP client", source_root, "origins_integration.agentops_mcp"),
        _module_authority_record("Origins engineering bridge", source_root, "origins_integration.engineering"),
        _module_authority_record("Origins Hunter mount", source_root, "origins_integration.hunter"),
        _module_authority_record("Origins Phase7 proof support", source_root, "phase7_live_proof_support"),
        _module_authority_record("AgentOps approval MCP", agentops_root, "agentops.mcp_approval_observer_service"),
        _module_authority_record("AgentOps external-operation MCP", agentops_root, "agentops.mcp_external_operation_service"),
        _module_authority_record("AgentOps storage", agentops_root, "agentops.storage"),
        _module_authority_record("CodeOps switcher CLI", codeops_root, "hunter_codeops.code_ops_switcher_cli"),
        _module_authority_record("Sergeant CLI", sergeant_root, "main_review.cli"),
    ]

    from origins_integration.agentops_mcp import AgentOpsMcpClient
    from origins_integration.engineering import EngineeringAttemptRequest, EngineeringBridge, OriginsClient
    from origins_integration.hunter import HunterIntelligenceMount
    from phase7_live_proof_support import init_repo, repository, start_daemon, workspace
    from agentops.mcp_approval_observer_service import create_agentops_approval_observer_mcp_server
    from agentops.mcp_external_operation_service import create_agentops_external_operation_mcp_server
    from agentops.storage import PersistentAgentOpsStores

    run_id = (
        f"v1-mission-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    run_root = args.evidence_root.resolve() / run_id
    workspaces = run_root / "workspaces"
    repo = workspaces / "repository"
    state = run_root / "origins-state"
    agentops_data = run_root / "agentops-state"
    output = run_root / "promoted"
    owner_bin = run_root / "owner-bin"
    for path in (workspaces, output, owner_bin):
        path.mkdir(parents=True, exist_ok=True)

    init_repo(repo, initial_value="observe", replacement_value="verify", strict=True)
    codeops_entrypoint = _write_owner_entrypoint(
        owner_bin / "hunter-codeops-switcher", codeops_root, "hunter_codeops.code_ops_switcher_cli"
    )
    sergeant_entrypoint = _write_owner_entrypoint(
        owner_bin / "sergeant", sergeant_root, "main_review.cli"
    )
    config = codeops_root / "config" / "code_ops_switcher.example.json"
    config_authority = _tracked_file_record("CodeOps provider config", codeops_root, config)
    provider_ids = require_two_enabled_providers(json.loads(config.read_text(encoding="utf-8")))

    authority = {
        "repository_heads": repository_heads,
        "modules": module_authority,
        "daemon_binary": {
            "resolved_path": str(daemon_binary),
            "sha256": file_sha256(daemon_binary),
            "source_head": expected_head,
        },
        "codeops_config": config_authority,
        "generated_entrypoints": [codeops_entrypoint, sergeant_entrypoint],
    }

    mcp_token = f"agentops_v1_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    origins_token = f"origins_v1_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    approval_server = create_agentops_approval_observer_mcp_server(
        store_root=agentops_data, auth_token=mcp_token, port=0
    )
    external_server = create_agentops_external_operation_mcp_server(
        store_root=agentops_data, auth_token=mcp_token, port=0
    )

    previous_env = os.environ.copy()
    daemon = None
    try:
        with (
            _running_http_server(approval_server) as approval_mcp,
            _running_http_server(external_server) as external_mcp,
        ):
            os.environ.update(
                {
                    "ORIGINS_URL": "http://127.0.0.1:48777",
                    "ORIGINS_LOCAL_TOKEN": origins_token,
                    "ORIGINS_PHASE7_DAEMON": str(daemon_binary),
                    "ORIGINS_AGENTOPS_APPROVAL_MCP_URL": (
                        f"http://127.0.0.1:{approval_mcp.server_address[1]}/mcp"
                    ),
                    "ORIGINS_AGENTOPS_EXTERNAL_OPERATION_MCP_URL": (
                        f"http://127.0.0.1:{external_mcp.server_address[1]}/mcp"
                    ),
                    "AGENTOPS_MCP_AUTH_TOKEN": mcp_token,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": os.pathsep.join(
                        [str(owner_bin), str(Path(sys.executable).parent), previous_env.get("PATH", "")]
                    ),
                }
            )

            daemon = start_daemon(data_dir=state, workspace_root=run_root, token=origins_token)
            client = OriginsClient.from_env()
            mission = run_candidate_phase(
                client=client,
                workspace_fn=workspace,
                repository_fn=repository,
                hunter_mount_type=HunterIntelligenceMount,
                agentops_mcp_type=AgentOpsMcpClient,
                persistent_agentops_stores=PersistentAgentOpsStores,
                engineering_bridge_type=EngineeringBridge,
                engineering_attempt_request_type=EngineeringAttemptRequest,
                workspace_id=None,
                repo=repo,
                config=config,
                provider_ids=provider_ids,
                run_id=run_id,
                expected_head=expected_head,
                authority=authority,
                agentops_data=agentops_data,
                output=output,
            )

            daemon.stop()
            daemon = None
            # Mechanical recovery must work after Hunter is deliberately removed.
            saved_hunter_url = os.environ.pop("ORIGINS_HUNTER_URL", None)
            saved_hunter_token = os.environ.pop("ORIGINS_HUNTER_TOKEN", None)
            daemon, result = run_recovery_phase(
                client=client,
                mcp=mission["mcp"],
                state=state,
                run_root=run_root,
                repo=repo,
                output=output,
                origins_token=origins_token,
                start_daemon=start_daemon,
                origins_client_type=OriginsClient,
                run_id=run_id,
                expected_head=expected_head,
                authority=authority,
                mission=mission,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            if saved_hunter_url is not None:
                os.environ["ORIGINS_HUNTER_URL"] = saved_hunter_url
            if saved_hunter_token is not None:
                os.environ["ORIGINS_HUNTER_TOKEN"] = saved_hunter_token
    finally:
        if daemon is not None:
            daemon.stop()
        os.environ.clear()
        os.environ.update(previous_env)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (V1MissionError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
