from __future__ import annotations

import hashlib
import json
import socketserver
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from origins_integration.device_readonly import (
    DeviceReadOnlyError,
    HuaweiGatewayReadOnlyMount,
    READ_ONLY_GATEWAY_COMMANDS,
    XRayBundleReadOnlyMount,
)
from origins_integration.phase6_server import Phase6Service


MUTATING_GATEWAY_COMMANDS = {
    "open_physical_session",
    "close_physical_session",
    "record_endpoint",
    "open_operation",
    "transition_operation",
    "resume_operation",
    "register_provider",
    "publish_contract",
    "register_worker",
    "heartbeat_worker",
    "sweep_workers",
    "shutdown",
}


class _GatewayState:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def response(self, name: str, params: dict[str, Any]) -> Any:
        self.commands.append(name)
        if name == "health":
            return {
                "status": "ready",
                "schema_version": 1,
                "device_authority": "none",
                "xray_authority": "read_only",
            }
        if name == "doctor":
            return {
                "healthy": True,
                "schema_version": 1,
                "journal_valid": True,
                "active_physical_sessions": 1,
                "active_operation_sessions": 1,
                "recovering_operation_sessions": 0,
                "registered_providers": 1,
                "timed_out_workers": 0,
                "device_authority": "none",
                "xray_authority": "read_only",
                "errors": [],
            }
        if name == "snapshot":
            return {
                "schema_version": 1,
                "physical_sessions": [
                    {
                        "session_id": "device-session-1",
                        "fingerprint_sha256": "1" * 64,
                        "state": "active",
                        "created_at": "2026-08-15T05:00:00Z",
                        "updated_at": "2026-08-15T05:05:00Z",
                        "recovery_count": 1,
                    }
                ],
                "operation_sessions": [
                    {
                        "operation_id": "gateway-operation-1",
                        "physical_session_id": "device-session-1",
                        "request_sha256": "2" * 64,
                        "stage": "evidence_collection",
                        "status": "active",
                        "created_at": "2026-08-15T05:01:00Z",
                        "updated_at": "2026-08-15T05:05:00Z",
                        "recovery_count": 1,
                    }
                ],
                "providers": [],
                "workers": [],
                "last_event_sequence": 3,
                "device_authority": "none",
                "xray_authority": "read_only",
            }
        if name == "verify_journal":
            return {"journal_valid": True}
        if name == "get_physical_session":
            return {"session_id": params["session_id"], "state": "active"}
        if name == "get_operation":
            return {"operation_id": params["operation_id"], "status": "active"}
        if name == "list_events":
            if int(params.get("after_sequence", 0)) > 0:
                return []
            twin = {
                "schema_version": 1,
                "contract_type": "device_twin",
                "contract_id": "11111111-1111-4111-8111-111111111111",
                "producer": "kirin_xray",
                "created_at": "2026-08-15T05:03:00Z",
                "physical_session_id": "22222222-2222-4222-8222-222222222222",
                "evidence_hashes": [],
                "confidence_bps": 9900,
                "expires_at": None,
                "authority": "verification",
                "single_use": False,
                "consumed_at": None,
                "payload": {
                    "twin_state": "pre_operation",
                    "identity_fingerprint": "3" * 64,
                    "firmware_fingerprint": "4" * 64,
                    "storage_fingerprint": "5" * 64,
                    "verification_status": "certified",
                    "write_allowed": False,
                },
            }
            recovery = {
                "schema_version": 1,
                "contract_type": "recovery_plan",
                "contract_id": "33333333-3333-4333-8333-333333333333",
                "producer": "ttg.device-gateway",
                "created_at": "2026-08-15T05:04:00Z",
                "physical_session_id": "22222222-2222-4222-8222-222222222222",
                "evidence_hashes": [],
                "confidence_bps": None,
                "expires_at": "2026-08-15T06:04:00Z",
                "authority": "recovery",
                "single_use": False,
                "consumed_at": None,
                "payload": {
                    "plan_id": "44444444-4444-4444-8444-444444444444",
                    "operation_request_id": "55555555-5555-4555-8555-555555555555",
                    "recipe_hash": "6" * 64,
                    "current_stage": "evidence_collection",
                    "state": "in_progress",
                    "journal_sha256": "7" * 64,
                    "next_action_code": "VERIFY_EVIDENCE",
                },
            }
            return [
                {
                    "sequence": 1,
                    "event_id": "event-1",
                    "event_type": "endpoint_observed",
                    "producer": "ttg.device-gateway",
                    "physical_session_id": "device-session-1",
                    "operation_id": None,
                    "timestamp": "2026-08-15T05:02:00Z",
                    "payload": {
                        "observation_id": "observation-1",
                        "session_id": "device-session-1",
                        "endpoint_key": "usb:vog",
                        "mode": "normal_fastboot",
                        "transport": "fastboot",
                        "observed_at": "2026-08-15T05:02:00Z",
                        "payload": {"read_only": True},
                    },
                    "previous_hash": None,
                    "event_hash": "8" * 64,
                },
                {
                    "sequence": 2,
                    "event_id": "event-2",
                    "event_type": "contract_accepted",
                    "producer": "ttg.device-gateway",
                    "physical_session_id": "device-session-1",
                    "operation_id": None,
                    "timestamp": "2026-08-15T05:03:00Z",
                    "payload": {
                        "canonical": json.dumps(twin, sort_keys=True, separators=(",", ":")),
                        "contract_sha256": "9" * 64,
                        "contract_type": "device_twin",
                    },
                    "previous_hash": "8" * 64,
                    "event_hash": "a" * 64,
                },
                {
                    "sequence": 3,
                    "event_id": "event-3",
                    "event_type": "contract_accepted",
                    "producer": "ttg.device-gateway",
                    "physical_session_id": "device-session-1",
                    "operation_id": None,
                    "timestamp": "2026-08-15T05:04:00Z",
                    "payload": {
                        "canonical": json.dumps(recovery, sort_keys=True, separators=(",", ":")),
                        "contract_sha256": "b" * 64,
                        "contract_type": "recovery_plan",
                    },
                    "previous_hash": "a" * 64,
                    "event_hash": "c" * 64,
                },
            ]
        raise AssertionError(f"unexpected command {name}")


class _GatewayHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request = json.loads(self.rfile.readline().decode("utf-8"))
        request_id = request["request_id"]
        command = request["command"]
        try:
            result = self.server.state.response(command["name"], command.get("params", {}))  # type: ignore[attr-defined]
            response = {"request_id": request_id, "ok": True, "result": result}
        except Exception as exc:  # pragma: no cover - fixture failure path
            response = {
                "request_id": request_id,
                "ok": False,
                "error": {"code": "FIXTURE_ERROR", "message": str(exc)},
            }
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")


class _GatewayFixture:
    def __init__(self) -> None:
        self.state = _GatewayState()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _GatewayHandler)
        self.server.daemon_threads = True
        self.server.state = self.state  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "_GatewayFixture":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


def _write_xray_bundle(root: Path, *, signed: bool = False, key: bytes = b"") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    evidence = {
        "certification.json": {"verdict": "CERTIFIED", "write_allowed": False},
        "profile_match.json": {"status": "MATCHED", "write_allowed": False},
        "recommended_plan.json": {"recommendation": "inspect_only", "write_allowed": False},
        "device_identity.json": {"model": "VOG-L29"},
    }
    files: list[dict[str, Any]] = []
    for name, value in evidence.items():
        path = root / name
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        data = path.read_bytes()
        files.append(
            {
                "path": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    manifest: dict[str, Any] = {
        "bundle_schema_version": "2.0",
        "scan_schema_version": "2.0",
        "scanner": {"name": "ttg-device-xray", "version": "0.4.0"},
        "scan_id": "scan-vog-1",
        "device_candidate_id": "candidate-vog-1",
        "candidate_count": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds"),
        "signer_key_id": "fixture-key",
        "hash_algorithm": "sha256",
        "signature_algorithm": "hmac-sha256",
        "write_allowed": False,
        "files": sorted(files, key=lambda item: item["path"]),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_sha = hashlib.sha256(canonical).hexdigest()
    manifest["manifest_sha256"] = manifest_sha
    (root / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    signature = {
        "status": "SIGNED" if signed else "UNSIGNED",
        "algorithm": "hmac-sha256",
        "signer_key_id": "fixture-key",
        "manifest_sha256": manifest_sha,
        "signature_hex": "",
    }
    if signed:
        signature["signature_hex"] = __import__("hmac").new(
            key,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    else:
        signature["reason"] = "fixture unsigned"
    (root / "bundle_manifest.sig").write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return root


def test_phase6_gateway_projection_uses_read_only_commands_only() -> None:
    assert READ_ONLY_GATEWAY_COMMANDS.isdisjoint(MUTATING_GATEWAY_COMMANDS)
    with _GatewayFixture() as fixture:
        mount = HuaweiGatewayReadOnlyMount(port=fixture.port)
        projection = mount.projection()
    assert projection["available"] is True
    assert projection["gateway"]["snapshot"]["device_authority"] == "none"
    assert projection["gateway"]["snapshot"]["xray_authority"] == "read_only"
    assert projection["write_execution"]["available"] is False
    assert projection["agentops_operation_link"]["available"] is False
    assert projection["endpoint_observations"][0]["transport"] == "fastboot"
    assert projection["contracts"]["device_twin"][0]["contract"]["payload"]["write_allowed"] is False
    assert projection["contracts"]["recovery_plan"][0]["contract"]["payload"]["state"] == "in_progress"
    assert set(fixture.state.commands).issubset(READ_ONLY_GATEWAY_COMMANDS)


def test_phase6_refuses_gateway_mutation_before_network() -> None:
    mount = HuaweiGatewayReadOnlyMount(port=9, timeout=0.1)
    with pytest.raises(DeviceReadOnlyError, match="refuses non-read"):
        mount.request("open_operation", {"physical_session_id": "x"})


def test_phase6_fails_closed_if_gateway_authority_expands() -> None:
    with _GatewayFixture() as fixture:
        original = fixture.state.response

        def expanded(name: str, params: dict[str, Any]) -> Any:
            value = original(name, params)
            if name == "health":
                value = dict(value)
                value["device_authority"] = "write"
            return value

        fixture.state.response = expanded  # type: ignore[method-assign]
        mount = HuaweiGatewayReadOnlyMount(port=fixture.port)
        with pytest.raises(DeviceReadOnlyError, match="expanded device_authority"):
            mount.projection()


def test_xray_bundle_hashes_and_read_only_boundary_are_verified(tmp_path: Path) -> None:
    bundle = _write_xray_bundle(tmp_path / "bundle")
    projection = XRayBundleReadOnlyMount(bundle).projection()
    assert projection["integrity_verified"] is True
    assert projection["write_allowed"] is False
    assert projection["signature"]["status"] == "UNSIGNED"
    assert projection["signature"]["cryptographically_verified"] is False
    assert "signature_hex" not in projection["signature"]
    assert projection["evidence"]["certification"]["verdict"] == "CERTIFIED"


def test_xray_bundle_tampering_is_rejected(tmp_path: Path) -> None:
    bundle = _write_xray_bundle(tmp_path / "bundle")
    (bundle / "certification.json").write_text('{"verdict":"UNSAFE"}', encoding="utf-8")
    with pytest.raises(DeviceReadOnlyError, match="size mismatch|SHA-256 mismatch"):
        XRayBundleReadOnlyMount(bundle).projection()


def test_xray_signed_bundle_verifies_only_with_server_key_reference(tmp_path: Path) -> None:
    key = b"fixture-signing-key"
    bundle = _write_xray_bundle(tmp_path / "bundle", signed=True, key=key)
    key_file = tmp_path / "xray.key"
    key_file.write_bytes(key)
    projection = XRayBundleReadOnlyMount(bundle, signing_key_file=str(key_file)).projection()
    assert projection["signature"]["cryptographically_verified"] is True


def test_phase6_service_keeps_write_and_agentops_link_unavailable(tmp_path: Path) -> None:
    bundle = _write_xray_bundle(tmp_path / "bundle")
    with _GatewayFixture() as fixture:
        service = Phase6Service(
            gateway=HuaweiGatewayReadOnlyMount(port=fixture.port),
            xray=XRayBundleReadOnlyMount(bundle),
        )
        projection = service.device_projection()
    assert projection["mode"] == "device_read_only"
    assert projection["write_execution"]["available"] is False
    assert projection["agentops_operation_link"]["available"] is False
    assert projection["xray"]["integrity_verified"] is True
