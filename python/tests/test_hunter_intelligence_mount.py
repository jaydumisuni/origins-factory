from __future__ import annotations

import inspect
from copy import deepcopy

import pytest

from origins_integration import hunter
from origins_integration.hunter import (
    HunterConversationConflict,
    HunterIntelligenceMount,
    HunterMountError,
    _ProofScope,
    hunter_session_id,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"


def relay(operation: str, body: dict, *, status: int = 200, request_id: str | None = None) -> dict:
    return {
        "ok": 200 <= status < 300,
        "transport": {
            "request_id": request_id or f"req-{operation}",
            "operation": operation,
            "http_status": status,
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "response_bytes": 123,
        },
        "body": body,
    }


class FakeTransport:
    def __init__(
        self,
        *,
        identity: dict | None = None,
        core_context: str = "hunter_core_chat",
        origin: str = "http://127.0.0.1:9999",
        environment: str = "production",
        existing_messages: list[dict[str, str]] | None = None,
        save_conflict: bool = False,
    ) -> None:
        self.identity = identity or {
            "authenticated": True,
            "role": "owner_admin",
            "status": "approved",
        }
        self.core_context = core_context
        self.origin = origin
        self.environment = environment
        self.existing_messages = existing_messages
        self.save_conflict = save_conflict
        self.calls: list[tuple[str, dict]] = []
        self.saved_session: dict | None = None

    def get_workspace(self, workspace_id: str) -> dict:
        return {"workspace_id": workspace_id}

    def status(self) -> dict:
        return {
            "ok": True,
            "configured": True,
            "base_origin": self.origin,
            "token_exposed": False,
        }

    def request(self, workspace_id: str, operation: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.calls.append((operation, deepcopy(payload)))
        if operation == "version":
            return relay(
                operation,
                {
                    "ok": True,
                    "service": "hunter-api-worker",
                    "environment": self.environment,
                    "deployment": {"gitCommit": "c" * 40},
                },
            )
        if operation == "session":
            return relay(operation, {"ok": True, "identity": self.identity})
        if operation == "core_status":
            return relay(operation, {"ok": True, "context": self.core_context})
        if operation == "providers_status":
            return relay(operation, {"ok": True, "providers": [{"id": "cloudflare-ai"}]})
        if operation == "chat_load":
            if self.existing_messages is None:
                return relay(operation, {"ok": False, "error": "CHAT_NOT_FOUND"}, status=404)
            return relay(
                operation,
                {
                    "ok": True,
                    "session": {
                        "id": payload["id"],
                        "title": "Existing",
                        "messages": deepcopy(self.existing_messages),
                        "createdAt": 1,
                        "updatedAt": 2,
                    },
                },
            )
        if operation == "core_chat":
            return relay(
                operation,
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion",
                    "model": "hunter-cloudflare",
                    "provider": "cloudflare-workers-ai",
                    "context": "hunter_core_chat",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hunter reply"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        if operation == "chat_save":
            self.saved_session = deepcopy(payload["session"])
            body = {"ok": True, "session": self.saved_session}
            if self.save_conflict:
                body = {"ok": True, "skipped": "server_newer", "session": self.saved_session}
            return relay(operation, body)
        raise AssertionError(operation)


def mount(transport: FakeTransport, scope: _ProofScope = _ProofScope.FIXTURE) -> HunterIntelligenceMount:
    return HunterIntelligenceMount(transport, proof_scope=scope)  # type: ignore[arg-type]


def test_python_mount_has_no_direct_hunter_network_client() -> None:
    source = inspect.getsource(hunter)
    for forbidden in ("urllib.request", "requests.", "httpx.", "aiohttp.", "ORIGINS_HUNTER_TOKEN"):
        assert forbidden not in source
    assert "/v1/hunter/request" in source


def test_doctor_accepts_approved_owner_but_never_proves_by_itself() -> None:
    result = mount(FakeTransport(), _ProofScope.LIVE_OWNER).doctor(WORKSPACE_ID)
    assert result.compatible is True
    assert result.live_hunter_proven is False
    assert result.identity_authenticated is True
    assert result.identity_role == "owner_admin"
    assert result.identity_status == "approved"
    assert result.core_context == "hunter_core_chat"
    assert len(result.transport_receipts) == 4


@pytest.mark.parametrize(
    "identity",
    [
        {"authenticated": False, "role": "guest", "status": "guest"},
        {"authenticated": True, "role": "tester", "status": "approved"},
        {"authenticated": True, "role": "owner_admin", "status": "pending"},
    ],
)
def test_doctor_fails_closed_for_non_owner_identity(identity: dict) -> None:
    with pytest.raises(HunterMountError):
        mount(FakeTransport(identity=identity)).doctor(WORKSPACE_ID)


def test_doctor_rejects_wrong_core_context() -> None:
    with pytest.raises(HunterMountError):
        mount(FakeTransport(core_context="website_customer_assistant")).doctor(WORKSPACE_ID)


def test_workspace_session_ids_are_stable_and_bounded() -> None:
    assert hunter_session_id(WORKSPACE_ID) == f"origins-{WORKSPACE_ID}-main"
    assert hunter_session_id(WORKSPACE_ID, "phase-4") == f"origins-{WORKSPACE_ID}-phase-4"
    with pytest.raises(HunterMountError):
        hunter_session_id(WORKSPACE_ID, "../escape")


def test_turn_sends_only_last_twelve_messages_but_saves_retained_history() -> None:
    previous = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}"}
        for index in range(20)
    ]
    transport = FakeTransport(existing_messages=previous)
    receipt = mount(transport).send_turn(WORKSPACE_ID, "new turn")
    core_call = next(payload for operation, payload in transport.calls if operation == "core_chat")
    assert len(core_call["messages"]) == 12
    assert core_call["messages"][-1] == {"role": "user", "content": "new turn"}
    assert transport.saved_session is not None
    assert len(transport.saved_session["messages"]) == 22
    assert transport.saved_session["messages"][-1] == {
        "role": "assistant",
        "content": "Hunter reply",
    }
    assert receipt.saved is True
    assert receipt.provider == "cloudflare-workers-ai"
    assert receipt.model == "hunter-cloudflare"
    assert receipt.receipt_sha256 == receipt.receipt_sha256


def test_fixture_turn_can_never_claim_live_hunter_proof() -> None:
    receipt = mount(FakeTransport()).send_turn(WORKSPACE_ID, "hello")
    assert receipt.proof_scope == "fixture"
    assert receipt.live_hunter_proven is False


def test_production_turn_requires_https_production_transport_to_prove() -> None:
    loopback = mount(FakeTransport(), _ProofScope.LIVE_OWNER).send_turn(WORKSPACE_ID, "hello")
    assert loopback.live_hunter_proven is False

    production = mount(
        FakeTransport(origin="https://hunter.thetechguyds.com", environment="production"),
        _ProofScope.LIVE_OWNER,
    ).send_turn(WORKSPACE_ID, "hello")
    assert production.live_hunter_proven is True


def test_server_newer_is_conflict_not_overwrite_success() -> None:
    with pytest.raises(HunterConversationConflict):
        mount(FakeTransport(save_conflict=True)).send_turn(WORKSPACE_ID, "hello")


def test_turn_receipt_hash_excludes_assistant_body() -> None:
    receipt = mount(FakeTransport()).send_turn(WORKSPACE_ID, "hello")
    evidence = receipt.evidence_body()
    assert "assistant_text" not in evidence
    assert len(receipt.receipt_sha256) == 64
