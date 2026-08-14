#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from origins_integration.oracle_live import OracleRemoteNodeMount


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(256 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Origins Phase 5 Oracle remote Node/file retrieval")
    parser.add_argument("--remote-path", required=True)
    args = parser.parse_args()

    mount = OracleRemoteNodeMount.from_env()
    if mount is None:
        raise SystemExit("Oracle remote Node mount is not configured")

    node = mount.snapshot()
    if not node.get("available") or not node.get("file_retrieval"):
        raise SystemExit("Oracle remote Node/file retrieval is not available")
    application = node.get("remote_application_attachment") or {}
    if application.get("available") is not False:
        raise SystemExit("remote application attachment must remain unavailable until Oracle owns that contract")

    receipt = mount.retrieve_file(args.remote_path, approved=True)
    local_path = Path(str(receipt["local_path"]))
    actual_sha = sha256_file(local_path)
    if actual_sha != receipt.get("sha256"):
        raise SystemExit("retrieved file digest mismatch")
    if local_path.stat().st_size != int(receipt.get("bytes_transferred") or -1):
        raise SystemExit("retrieved file byte count mismatch")

    token = str(os.environ.get("ORACLE_LIVE_TOKEN") or "").strip()
    proof = {
        "schema_version": "origins.phase5-oracle-remote-proof.v1",
        "proof": "PHASE5_ORACLE_REMOTE_FILE_OK",
        "owner": "oracle",
        "node_id": receipt["node_id"],
        "remote_path": receipt["remote_path"],
        "bytes": receipt["bytes_transferred"],
        "sha256": receipt["sha256"],
        "chunks": receipt["chunks"],
        "artifact_candidate": bool(receipt.get("artifact_candidate")),
        "remote_application_attachment_available": False,
        "live_token_exposed": bool(token and token in json.dumps(receipt, sort_keys=True)),
    }
    if proof["live_token_exposed"]:
        raise SystemExit("Oracle Live token leaked into proof projection")
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
