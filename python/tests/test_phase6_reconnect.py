from __future__ import annotations

import json
import socketserver
import threading
from typing import Any

from origins_integration.device_readonly import HuaweiGatewayReadOnlyMount, READ_ONLY_GATEWAY_COMMANDS


class _StableGatewayState:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def response(self, name: str, params: dict[str, Any]) -> Any:
        self.commands.append(name)
        if name == "health":
            return {
                "status": "ready",
                "device_authority": "none",
                "xray_authority": "read_only",
            }
        if name == "doctor":
            return {
                "healthy": True,
                "journal_valid": True,
                "device_authority": "none",
                "xray_authority": "read_only",
                "recovering_operation_sessions": 1,
            }
        if name == "snapshot":
            return {
                "physical_sessions": [
                    {
                        "session_id": "stable-device-session",
                        "fingerprint_sha256": "1" * 64,
                        "state": "active",
                        "recovery_count": 2,
                    }
                ],
                "operation_sessions": [
                    {
                        "operation_id": "stable-gateway-operation",
                        "physical_session_id": "stable-device-session",
                        "request_sha256": "2" * 64,
                        "stage": "evidence_collection",
                        "status": "recovering",
                        "recovery_count": 2,
                    }
                ],
                "device_authority": "none",
                "xray_authority": "read_only",
            }
        if name == "verify_journal":
            return {"journal_valid": True}
        if name == "list_events":
            return []
        if name == "get_physical_session":
            return {"session_id": params["session_id"], "state": "active"}
        if name == "get_operation":
            return {"operation_id": params["operation_id"], "status": "recovering"}
        raise AssertionError(f"unexpected command {name}")


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request = json.loads(self.rfile.readline().decode("utf-8"))
        command = request["command"]
        result = self.server.state.response(command["name"], command.get("params", {}))  # type: ignore[attr-defined]
        response = {"request_id": request["request_id"], "ok": True, "result": result}
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")


class _GatewayFixture:
    def __init__(self) -> None:
        self.state = _StableGatewayState()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
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


def _identity(projection: dict[str, Any]) -> tuple[str, str, str, int, int]:
    snapshot = projection["gateway"]["snapshot"]
    physical = snapshot["physical_sessions"][0]
    operation = snapshot["operation_sessions"][0]
    return (
        physical["session_id"],
        operation["operation_id"],
        operation["request_sha256"],
        physical["recovery_count"],
        operation["recovery_count"],
    )


def test_phase6_client_reconnect_preserves_owner_identity_without_mutation() -> None:
    with _GatewayFixture() as fixture:
        first = HuaweiGatewayReadOnlyMount(port=fixture.port).projection()
        second = HuaweiGatewayReadOnlyMount(port=fixture.port).projection()

        assert _identity(first) == _identity(second) == (
            "stable-device-session",
            "stable-gateway-operation",
            "2" * 64,
            2,
            2,
        )
        assert first["gateway"]["snapshot"]["operation_sessions"][0]["status"] == "recovering"
        assert second["gateway"]["snapshot"]["operation_sessions"][0]["status"] == "recovering"
        assert set(fixture.state.commands).issubset(READ_ONLY_GATEWAY_COMMANDS)
