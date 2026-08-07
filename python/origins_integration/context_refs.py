from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .hunter import HunterIntelligenceMount, HunterMountError

ContextKind = Literal["chat", "memory"]
ContextStatus = Literal["resolved", "unavailable"]

SAFE_CHAT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,140}$")
SAFE_MEMORY_PART_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
REFERENCE_RE = re.compile(r"(?<!\S)@(chat|memory):([^\s]+)")


class ContextReferenceError(HunterMountError):
    """Raised when a context reference is malformed or cannot be safely interpreted."""


@dataclass(frozen=True)
class ContextReference:
    raw: str
    kind: ContextKind
    target: str
    project: str = ""
    key: str = ""

    @property
    def authority(self) -> str:
        return "hunter.chat" if self.kind == "chat" else "hunter.memory.lesson"


@dataclass(frozen=True)
class ResolvedContextReference:
    reference: ContextReference
    status: ContextStatus
    title: str
    payload: dict[str, Any]
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference": {
                "raw": self.reference.raw,
                "kind": self.reference.kind,
                "target": self.reference.target,
                "project": self.reference.project,
                "key": self.reference.key,
                "authority": self.reference.authority,
            },
            "status": self.status,
            "title": self.title,
            "payload": dict(self.payload),
            "reason": self.reason,
        }


def parse_context_reference(value: str) -> ContextReference:
    raw = value.strip()
    if raw.startswith("@chat:"):
        target = raw[len("@chat:") :]
        if not SAFE_CHAT_ID_RE.fullmatch(target):
            raise ContextReferenceError("@chat reference contains an unsupported Hunter session id")
        return ContextReference(raw=raw, kind="chat", target=target)

    if raw.startswith("@memory:"):
        body = raw[len("@memory:") :]
        if ":" not in body:
            raise ContextReferenceError("@memory reference must be @memory:<project>:<key>")
        project, key = body.split(":", 1)
        if not SAFE_MEMORY_PART_RE.fullmatch(project) or not SAFE_MEMORY_PART_RE.fullmatch(key):
            raise ContextReferenceError("@memory project and key must use safe identifier characters")
        return ContextReference(
            raw=raw,
            kind="memory",
            target=f"{project}:{key}",
            project=project,
            key=key,
        )

    raise ContextReferenceError("unsupported context reference; expected @chat: or @memory:")


def extract_context_references(text: str) -> tuple[ContextReference, ...]:
    references: list[ContextReference] = []
    seen: set[str] = set()
    for match in REFERENCE_RE.finditer(text):
        raw = f"@{match.group(1)}:{match.group(2)}"
        if raw in seen:
            continue
        references.append(parse_context_reference(raw))
        seen.add(raw)
    return tuple(references)


class ContextReferenceResolver:
    """Authority-aware resolver for dormant Origins/Hunter context references."""

    def __init__(self, hunter: HunterIntelligenceMount) -> None:
        self.hunter = hunter

    def resolve(self, workspace_id: str, reference: ContextReference) -> ResolvedContextReference:
        workspace = self.hunter.transport.get_workspace(workspace_id)
        if workspace.get("workspace_id") != workspace_id:
            raise ContextReferenceError("Origins Workspace identity changed during context resolution")

        if reference.kind == "memory":
            return ResolvedContextReference(
                reference=reference,
                status="unavailable",
                title=f"{reference.project} / {reference.key}",
                payload={
                    "project": reference.project,
                    "key": reference.key,
                    "authority": "hunter.memory.lesson",
                },
                reason="hunter_memory_storage_unwired",
            )

        response = self.hunter.transport.request(
            workspace_id,
            "chat_load",
            {"id": reference.target},
        )
        transport = response.get("transport")
        if not isinstance(transport, dict):
            raise ContextReferenceError("Hunter chat reference response omitted transport receipt")
        status = transport.get("http_status")
        if not isinstance(status, int) or isinstance(status, bool):
            raise ContextReferenceError("Hunter chat reference transport status is invalid")
        if status == 404:
            return ResolvedContextReference(
                reference=reference,
                status="unavailable",
                title=reference.target,
                payload={"session_id": reference.target},
                reason="hunter_chat_not_found",
            )
        if not 200 <= status < 300:
            raise ContextReferenceError(f"Hunter chat reference failed with HTTP {status}")

        body = response.get("body")
        if not isinstance(body, dict):
            raise ContextReferenceError("Hunter chat reference response body is invalid")
        session = body.get("session")
        if not isinstance(session, dict):
            raise ContextReferenceError("Hunter chat reference did not return a session")
        messages = _clean_reference_messages(session.get("messages"))
        return ResolvedContextReference(
            reference=reference,
            status="resolved",
            title=str(session.get("title") or reference.target)[:160],
            payload={
                "session_id": reference.target,
                "messages": messages,
                "createdAt": _safe_integer(session.get("createdAt")),
                "updatedAt": _safe_integer(session.get("updatedAt")),
                "archived": bool(session.get("archived", False)),
                "pinned": bool(session.get("pinned", False)),
            },
        )

    def resolve_text(self, workspace_id: str, text: str) -> tuple[ResolvedContextReference, ...]:
        return tuple(self.resolve(workspace_id, item) for item in extract_context_references(text))


def _clean_reference_messages(value: Any) -> list[dict[str, str]]:
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


def _safe_integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
