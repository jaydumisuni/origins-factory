from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
import json
import threading
from typing import Iterator

import pytest

from origins_integration.intelligence_runtime import IntelligenceMountError, IntelligenceRuntime
from origins_integration.intelligence_server import (
    MAX_BODY_BYTES,
    IntelligenceServerError,
    serve,
)


class FakeRuntime:
    def __init__(self) -> None:
        self.operation_payloads: list[dict[str, object]] = []

    def health(self) -> dict[str, object]:
        return {
            "ok": True,
            "service": "origins-intelligence",
            "api_version": "v1",
            "mechanical_originsd_configured": True,
            "owners": {
                "Hunter-AgentOps": {
                    "owner": "Hunter-AgentOps",
                    "configured": True,
                    "available": True,
                    "detail": "/home/kratos/private-agentops-state",
                },
                "hunter-codeops": {
                    "owner": "hunter-codeops",
                    "configured": True,
                    "available": False,
                    "detail": "API_KEY=must-not-leak",
                },
            },
        }

    def operations(self) -> dict[str, object]:
        return {"owner": "Hunter-AgentOps", "operations": [{"id": "op-1"}]}

    def providers(self) -> dict[str, object]:
        return {"owner": "hunter-codeops", "providers": [{"id": "local"}]}

    def run_agentops(self, payload: dict[str, object]) -> dict[str, object]:
        self.operation_payloads.append(payload)
        return {"status_code": 200, "ok": True, "body": {"accepted": True}}

    def compile_capability(self, payload: dict[str, object]) -> dict[str, object]:
        return {"activation": "not_activated", "owner_approval_required": True, "proposal": payload}

    def engineering_attempt(self, payload: dict[str, object]) -> dict[str, object]:
        return {"operation_id": payload["operation_id"], "verdict": "PASS"}


class BrokenRuntime(FakeRuntime):
    def operations(self) -> dict[str, object]:
        raise IntelligenceMountError("AgentOps durable owner is unavailable")

    def providers(self) -> dict[str, object]:
        raise RuntimeError("secret provider exception text")


@contextmanager
def running_server(runtime: FakeRuntime) -> Iterator[tuple[str, int]]:
    server = serve(host="127.0.0.1", port=0, runtime=runtime, local_token="phase4-test-token")  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request_json(
    address: tuple[str, int],
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(address[0], address[1], timeout=3)
    request_headers = {"Accept": "application/json", **(headers or {})}
    payload = None
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    value = json.loads(raw.decode("utf-8"))
    assert isinstance(value, dict)
    return response.status, value


def test_server_refuses_non_loopback_and_empty_token() -> None:
    with pytest.raises(IntelligenceServerError, match="non-loopback"):
        serve(host="0.0.0.0", port=0, runtime=FakeRuntime(), local_token="token")  # type: ignore[arg-type]
    with pytest.raises(IntelligenceServerError, match="ORIGINS_LOCAL_TOKEN"):
        serve(host="127.0.0.1", port=0, runtime=FakeRuntime(), local_token="")  # type: ignore[arg-type]


def test_public_health_is_sanitized_and_protected_routes_require_bearer() -> None:
    with running_server(FakeRuntime()) as address:
        status, health = request_json(address, "GET", "/v1/health")
        assert status == 200
        assert health == {
            "ok": True,
            "service": "origins-intelligence",
            "api_version": "v1",
            "owners": {
                "Hunter-AgentOps": {"configured": True, "available": True},
                "hunter-codeops": {"configured": True, "available": False},
            },
            "mechanical_originsd_configured": True,
        }
        assert "private-agentops-state" not in json.dumps(health)
        assert "API_KEY" not in json.dumps(health)

        status, denied = request_json(address, "GET", "/v1/operations")
        assert status == 401
        assert denied["error_code"] == "UNAUTHORIZED"

        status, operations = request_json(
            address,
            "GET",
            "/v1/operations",
            token="phase4-test-token",
        )
        assert status == 200
        assert operations["owner"] == "Hunter-AgentOps"


def test_authenticated_post_delegates_without_minting_owner_authority() -> None:
    runtime = FakeRuntime()
    with running_server(runtime) as address:
        payload = {"playbook_path": "playbooks/codeops.json", "title": "Review repository"}
        status, result = request_json(
            address,
            "POST",
            "/v1/operations",
            token="phase4-test-token",
            body=payload,
        )
        assert status == 200
        assert runtime.operation_payloads == [payload]
        assert result["ok"] is True

        status, capability = request_json(
            address,
            "POST",
            "/v1/capability-proposals",
            token="phase4-test-token",
            body={"workspace_id": "workspace-1"},
        )
        assert status == 200
        assert capability["activation"] == "not_activated"
        assert capability["owner_approval_required"] is True


def test_owner_failures_are_contained_and_unexpected_detail_is_not_reflected() -> None:
    with running_server(BrokenRuntime()) as address:
        status, unavailable = request_json(
            address,
            "GET",
            "/v1/operations",
            token="phase4-test-token",
        )
        assert status == 503
        assert unavailable["error_code"] == "OWNER_UNAVAILABLE"

        status, failed = request_json(
            address,
            "GET",
            "/v1/providers",
            token="phase4-test-token",
        )
        assert status == 503
        assert failed["error_code"] == "OWNER_FAILURE"
        assert failed["error"] == "owning runtime rejected or failed request: RuntimeError"
        assert "secret provider exception text" not in json.dumps(failed)


def test_json_body_limit_is_enforced_before_body_read() -> None:
    with running_server(FakeRuntime()) as address:
        status, result = request_json(
            address,
            "POST",
            "/v1/operations",
            token="phase4-test-token",
            headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
        )
        assert status == 413
        assert result["error_code"] == "BODY_TOO_LARGE"


def test_real_capability_compiler_never_self_activates() -> None:
    runtime = IntelligenceRuntime()
    result = runtime.compile_capability(
        {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "task_title": "Need bounded provider evidence",
            "capability_id": "origins.provider.example",
            "reason": "The current loadout cannot recover the required evidence.",
            "expected_benefit": "Allow one explicit provider observation after owner review.",
            "requested_effects": ["observe"],
            "network_mode": "deny",
            "requested_by": "hunter",
        }
    )
    proposal = result["proposal"]
    assert isinstance(proposal, dict)
    assert result["activation"] == "not_activated"
    assert result["owner_approval_required"] is True
    assert proposal["approval_required"] is True
    assert proposal["self_approvable"] is False
