from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from origins_contracts import canonical_json

from .engineering import BridgeError, OriginsClient

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
MAX_THREAD_ID = 60
MAX_USER_TEXT = 32_000
INFERENCE_MESSAGE_LIMIT = 12
EXPECTED_CORE_CONTEXT = "hunter_core_chat"


class HunterMountError(BridgeError):
    """Raised when Hunter cannot be safely mounted through originsd."""


class HunterConversationConflict(HunterMountError):
    """Raised when Hunter already has a newer semantic conversation state."""


class _ProofScope(Enum):
    FIXTURE = "fixture"
    LIVE_OWNER = "live_owner"


@dataclass(frozen=True)
class HunterDoctorResult:
    workspace_id: str
    proof_scope: str
    transport_origin: str
    compatible: bool
    live_hunter_proven: bool
    deployment_service: str
    deployment_environment: str
    deployment_git_commit: str
    identity_role: str
    identity_status: str
    identity_authenticated: bool
    core_context: str
    provider_count: int
    transport_receipts: tuple[dict[str, Any], ...]

    def body_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "proof_scope": self.proof_scope,
            "transport_origin": self.transport_origin,
            "compatible": self.compatible,
            "live_hunter_proven": self.live_hunter_proven,
            "deployment_service": self.deployment_service,
            "deployment_environment": self.deployment_environment,
            "deployment_git_commit": self.deployment_git_commit,
            "identity_role": self.identity_role,
            "identity_status": self.identity_status,
            "identity_authenticated": self.identity_authenticated,
            "core_context": self.core_context,
            "provider_count": self.provider_count,
            "transport_receipts": [dict(item) for item in self.transport_receipts],
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def as_dict(self) -> dict[str, Any]:
        return {**self.body_dict(), "receipt_sha256": self.receipt_sha256}


@dataclass(frozen=True)
class HunterTurnReceipt:
    workspace_id: str
    hunter_session_id: str
    proof_scope: str
    live_hunter_proven: bool
    provider: str
    model: str
    context: str
    response_sha256: str
    load_request_id: str
    chat_request_id: str
    save_request_id: str
    saved: bool
    conflict: bool
    assistant_text: str

    def evidence_body(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "hunter_session_id": self.hunter_session_id,
            "proof_scope": self.proof_scope,
            "live_hunter_proven": self.live_hunter_proven,
            "provider": self.provider,
            "model": self.model,
            "context": self.context,
            "response_sha256": self.response_sha256,
            "load_request_id": self.load_request_id,
            "chat_request_id": self.chat_request_id,
            "save_request_id": self.save_request_id,
            "saved": self.saved,
            "conflict": self.conflict,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.evidence_body())

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.evidence_body(),
            "assistant_text": self.assistant_text,
            "receipt_sha256": self.receipt_sha256,
        }


class HunterOriginsTransport:
    """Local-only client for originsd's narrow Hunter transport."""

    def __init__(self, origins: OriginsClient) -> None:
        self.origins = origins

    def status(self) -> dict[str, Any]:
        return self.origins._json("GET", "/v1/hunter/status")

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        return self.origins._json("GET", f"/v1/workspaces/{workspace_id}")

    def request(
        self,
        workspace_id: str,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.origins._json(
            "POST",
            "/v1/hunter/request",
            {
                "workspace_id": workspace_id,
                "operation": operation,
                "payload": payload or {},
            },
        )


class HunterIntelligenceMount:
    def __init__(
        self,
        transport: HunterOriginsTransport,
        *,
        proof_scope: _ProofScope,
    ) -> None:
        if not isinstance(proof_scope, _ProofScope):
            raise TypeError("proof_scope must be an internal Origins Hunter proof token")
        self.transport = transport
        self._proof_scope = proof_scope

    @classmethod
    def production(cls, origins: OriginsClient) -> "HunterIntelligenceMount":
        return cls(HunterOriginsTransport(origins), proof_scope=_ProofScope.LIVE_OWNER)

    @classmethod
    def _for_fixture(cls, origins: OriginsClient) -> "HunterIntelligenceMount":
        return cls(HunterOriginsTransport(origins), proof_scope=_ProofScope.FIXTURE)

    def doctor(self, workspace_id: str) -> HunterDoctorResult:
        _require_workspace(self.transport.get_workspace(workspace_id), workspace_id)
        transport_status = self.transport.status()
        if transport_status.get("configured") is not True:
            raise HunterMountError("originsd Hunter transport is not configured")
        origin = _required_string(transport_status, "base_origin")

        version = self.transport.request(workspace_id, "version")
        session = self.transport.request(workspace_id, "session")
        core = self.transport.request(workspace_id, "core_status")
        providers = self.transport.request(workspace_id, "providers_status")

        version_body = _successful_remote(version, "Hunter version")
        session_body = _successful_remote(session, "Hunter auth session")
        core_body = _successful_remote(core, "Hunter Core status")
        provider_body = _successful_remote(providers, "Hunter provider status")

        service = _required_string(version_body, "service")
        if service != "hunter-api-worker":
            raise HunterMountError(f"unexpected Hunter service identity {service!r}")
        environment = str(version_body.get("environment") or "")
        deployment = version_body.get("deployment") if isinstance(version_body.get("deployment"), dict) else {}
        git_commit = str(deployment.get("gitCommit") or "")

        identity = session_body.get("identity")
        if not isinstance(identity, dict):
            raise HunterMountError("Hunter Auth V2 session omitted identity")
        authenticated = identity.get("authenticated") is True
        role = str(identity.get("role") or "")
        status = str(identity.get("status") or "")
        if not authenticated:
            raise HunterMountError("Hunter owner session is not authenticated")
        if role != "owner_admin" or status != "approved":
            raise HunterMountError(
                f"Hunter owner session is not approved owner_admin: role={role!r} status={status!r}"
            )

        core_context = str(core_body.get("context") or "")
        if core_context != EXPECTED_CORE_CONTEXT:
            raise HunterMountError(
                f"Hunter Core context changed: expected {EXPECTED_CORE_CONTEXT!r}, got {core_context!r}"
            )

        provider_values = provider_body.get("providers")
        providers_list = provider_values if isinstance(provider_values, list) else []
        production_origin = origin.startswith("https://")
        live_proven = (
            self._proof_scope is _ProofScope.LIVE_OWNER
            and production_origin
            and environment == "production"
        )

        return HunterDoctorResult(
            workspace_id=workspace_id,
            proof_scope=self._proof_scope.value,
            transport_origin=origin,
            compatible=True,
            live_hunter_proven=live_proven,
            deployment_service=service,
            deployment_environment=environment,
            deployment_git_commit=git_commit,
            identity_role=role,
            identity_status=status,
            identity_authenticated=authenticated,
            core_context=core_context,
            provider_count=len(providers_list),
            transport_receipts=tuple(
                _compact_transport(item)
                for item in (version, session, core, providers)
            ),
        )

    def send_turn(
        self,
        workspace_id: str,
        text: str,
        *,
        thread_id: str = "main",
        title: str = "Origins Workspace",
    ) -> HunterTurnReceipt:
        text = text.strip()
        if not text:
            raise HunterMountError("Hunter turn text is required")
        if len(text) > MAX_USER_TEXT:
            raise HunterMountError(f"Hunter turn exceeds {MAX_USER_TEXT} characters")

        doctor = self.doctor(workspace_id)
        session_id = hunter_session_id(workspace_id, thread_id)
        load = self.transport.request(workspace_id, "chat_load", {"id": session_id})
        remote_status = _remote_status(load)
        if remote_status == 404:
            session = _new_session(session_id, title)
        elif 200 <= remote_status < 300:
            load_body = _remote_body(load)
            loaded = load_body.get("session")
            if not isinstance(loaded, dict):
                raise HunterMountError("Hunter chat_load did not return a session")
            session = dict(loaded)
        else:
            raise HunterMountError(f"Hunter chat_load failed with HTTP {remote_status}")

        messages = _clean_messages(session.get("messages"))
        messages.append({"role": "user", "content": text})
        inference_messages = messages[-INFERENCE_MESSAGE_LIMIT:]

        chat = self.transport.request(
            workspace_id,
            "core_chat",
            {"messages": inference_messages},
        )
        chat_body = _successful_remote(chat, "Hunter Core chat")
        assistant_text = _completion_text(chat_body)
        provider = str(chat_body.get("provider") or "")
        model = str(chat_body.get("model") or "")
        context = str(chat_body.get("context") or EXPECTED_CORE_CONTEXT)
        if context != EXPECTED_CORE_CONTEXT:
            raise HunterMountError(f"Hunter chat returned unexpected context {context!r}")

        messages.append({"role": "assistant", "content": assistant_text})
        now = int(time.time() * 1000)
        session["id"] = session_id
        session["title"] = str(session.get("title") or title)[:160]
        session["messages"] = messages[-300:]
        session["createdAt"] = int(session.get("createdAt") or now)
        session["updatedAt"] = now
        session["archived"] = bool(session.get("archived", False))
        session["pinned"] = bool(session.get("pinned", False))

        save = self.transport.request(workspace_id, "chat_save", {"session": session})
        save_body = _successful_remote(save, "Hunter chat save")
        if save_body.get("skipped") == "server_newer":
            raise HunterConversationConflict(
                "Hunter has a newer semantic conversation; reload before continuing"
            )
        if save_body.get("ok") is not True:
            raise HunterMountError("Hunter chat save did not confirm success")

        return HunterTurnReceipt(
            workspace_id=workspace_id,
            hunter_session_id=session_id,
            proof_scope=self._proof_scope.value,
            live_hunter_proven=doctor.live_hunter_proven,
            provider=provider,
            model=model,
            context=context,
            response_sha256=_compact_transport(chat)["response_sha256"],
            load_request_id=_compact_transport(load)["request_id"],
            chat_request_id=_compact_transport(chat)["request_id"],
            save_request_id=_compact_transport(save)["request_id"],
            saved=True,
            conflict=False,
            assistant_text=assistant_text,
        )


def hunter_session_id(workspace_id: str, thread_id: str = "main") -> str:
    if not workspace_id or not SAFE_ID_RE.fullmatch(workspace_id):
        raise HunterMountError("workspace_id contains unsupported Hunter session characters")
    thread = thread_id.strip()
    if not thread or len(thread) > MAX_THREAD_ID or not SAFE_ID_RE.fullmatch(thread):
        raise HunterMountError("thread_id must be 1..60 safe identifier characters")
    value = f"origins-{workspace_id}-{thread}"
    if len(value) > 140:
        raise HunterMountError("derived Hunter session id exceeds Hunter's 140-byte limit")
    return value


def _new_session(session_id: str, title: str) -> dict[str, Any]:
    now = int(time.time() * 1000)
    return {
        "id": session_id,
        "title": title[:160] or "Origins Workspace",
        "messages": [],
        "createdAt": now,
        "updatedAt": now,
        "archived": False,
        "pinned": False,
    }


def _clean_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    clean: list[dict[str, str]] = []
    for item in value[-300:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = item.get("content")
        if role not in {"user", "assistant", "system"} or not isinstance(content, str):
            continue
        clean.append({"role": role, "content": content})
    return clean


def _completion_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HunterMountError("Hunter completion omitted choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise HunterMountError("Hunter completion choice is invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise HunterMountError("Hunter completion omitted assistant message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HunterMountError("Hunter completion assistant content is empty")
    return content


def _require_workspace(workspace: dict[str, Any], workspace_id: str) -> None:
    if workspace.get("workspace_id") != workspace_id:
        raise HunterMountError("Origins Workspace identity changed during Hunter mount")


def _successful_remote(value: dict[str, Any], label: str) -> dict[str, Any]:
    status = _remote_status(value)
    body = _remote_body(value)
    if not 200 <= status < 300:
        error = body.get("error") or body.get("error_code") or body.get("message") or "remote failure"
        raise HunterMountError(f"{label} failed HTTP {status}: {error}")
    if body.get("ok") is False:
        error = body.get("error") or body.get("error_code") or body.get("message") or "Hunter reported failure"
        raise HunterMountError(f"{label} reported failure: {error}")
    return body


def _remote_status(value: dict[str, Any]) -> int:
    transport = value.get("transport")
    if not isinstance(transport, dict):
        raise HunterMountError("originsd Hunter response omitted transport receipt")
    status = transport.get("http_status")
    if not isinstance(status, int) or isinstance(status, bool):
        raise HunterMountError("originsd Hunter transport status is invalid")
    return status


def _remote_body(value: dict[str, Any]) -> dict[str, Any]:
    body = value.get("body")
    if not isinstance(body, dict):
        raise HunterMountError("originsd Hunter response body is not an object")
    return body


def _compact_transport(value: dict[str, Any]) -> dict[str, Any]:
    transport = value.get("transport")
    if not isinstance(transport, dict):
        raise HunterMountError("originsd Hunter response omitted transport receipt")
    required = ("request_id", "operation", "http_status", "request_sha256", "response_sha256", "response_bytes")
    compact: dict[str, Any] = {}
    for field in required:
        if field not in transport:
            raise HunterMountError(f"originsd Hunter transport receipt omitted {field}")
        compact[field] = transport[field]
    return compact


def _required_string(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise HunterMountError(f"required string field {field} missing")
    return item


def _canonical_sha256(value: dict[str, Any]) -> str:
    canonical = canonical_json(value)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
