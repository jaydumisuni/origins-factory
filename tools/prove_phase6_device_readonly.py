from __future__ import annotations

import argparse
import json
import os
import subprocess
from typing import Any

from origins_integration.device_readonly import (
    DeviceReadOnlyError,
    HuaweiGatewayReadOnlyMount,
    XRayBundleReadOnlyMount,
)


def _head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return "unknown"


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove Origins Phase 6 device read-only integration")
    parser.add_argument("--require-xray", action="store_true")
    args = parser.parse_args(argv)

    gateway = HuaweiGatewayReadOnlyMount.from_env()
    gateway_projection = gateway.projection()
    owner = gateway_projection["gateway"]
    health = owner["health"]
    doctor = owner["doctor"]
    snapshot = owner["snapshot"]
    journal = owner["journal"]

    if health.get("device_authority") != "none":
        raise DeviceReadOnlyError("device authority is not none")
    if health.get("xray_authority") != "read_only":
        raise DeviceReadOnlyError("X-Ray authority is not read_only")
    if doctor.get("journal_valid") is not True or journal.get("journal_valid") is not True:
        raise DeviceReadOnlyError("Gateway journal did not verify")
    if gateway_projection["write_execution"].get("available") is not False:
        raise DeviceReadOnlyError("Phase 6 unexpectedly exposes write execution")

    xray_mount = XRayBundleReadOnlyMount.from_env()
    xray: dict[str, Any]
    if xray_mount is None:
        if args.require_xray:
            raise DeviceReadOnlyError("--require-xray requested but ORIGINS_XRAY_BUNDLE_DIR is unset")
        xray = {"available": False, "reason": "XRAY_BUNDLE_NOT_CONFIGURED"}
    else:
        xray = xray_mount.projection()
        if xray.get("integrity_verified") is not True or xray.get("write_allowed") is not False:
            raise DeviceReadOnlyError("X-Ray bundle did not preserve verified read-only boundary")

    contracts = gateway_projection.get("contracts")
    contract_types = sorted(contracts) if isinstance(contracts, dict) else []
    summary = {
        "schema_version": "origins.phase6-device-readonly-proof.v1",
        "proof": "PHASE6_DEVICE_READONLY_OK",
        "source_head": _head(),
        "gateway_owner_revision": gateway_projection.get("owner_revision_recovered"),
        "gateway_status": health.get("status"),
        "device_authority": health.get("device_authority"),
        "xray_authority": health.get("xray_authority"),
        "journal_valid": journal.get("journal_valid"),
        "physical_session_count": _count(snapshot.get("physical_sessions")),
        "gateway_operation_count": _count(snapshot.get("operation_sessions")),
        "endpoint_observation_count": _count(gateway_projection.get("endpoint_observations")),
        "projected_contract_types": contract_types,
        "write_execution_available": False,
        "agentops_gateway_link_available": gateway_projection["agentops_operation_link"].get("available"),
        "xray_bundle_available": xray.get("available"),
        "xray_integrity_verified": xray.get("integrity_verified", False),
        "xray_write_allowed": xray.get("write_allowed", False),
        "xray_expired": xray.get("expired"),
        "production_secret_values_printed": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
