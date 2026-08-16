from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Mapping, Protocol

MCP_PROTOCOL_VERSION = "2026-07-28"
DEFAULT_APPROVAL_URL = "http://127.0.0.1:8792/mcp"
DEFAULT_EXTERNAL_OPERATION_URL = "http://127.0.0.1:8791/mcp"
MIN_TOKEN_LENGTH = 32
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AgentOpsMcpError(RuntimeError):
    """Raised when an AgentOps MCP owner boundary is unavailable or rejects a request."""


class AgentOpsMcpPort(Protocol):
    def request_approval(self, arguments: Mapping[str, object]) -> dict[str, object]: ...
    def get_approval(self, approval_id: str) -> dict[str, object]: ...
    def list_pending_approvals(self) -> dict[str, object]: ...
    def start_external_operation(self, arguments: Mapping[str, object]) -> dict[str, object]: ...
    def get_external_operation(self, operation_id: str) -> dict[str, object]: ...
    def finalize_external_operation(self, arguments: Mapping[str, object]) -> dict[str, object]: ...


@dataclass(frozen=True)
class AgentOpsMcpEndpoints:
    approval: str
    external_operation: str

    @classmethod
    def from_env(cls) -> "AgentOpsMcpEndpoints":
        return cls(
            approval=os.environ.get("ORIGINS_AGENTOPS_APPROVAL_MCP_URL", DEFAULT_APPROVAL_URL).strip(),
            external_operation=os.environ.get(
                "ORIGINS_AGENTOPS_EXTERNAL_OPERATION_MCP_URL", DEFAULT_EXTERNAL_OPERATION_URL
            ).strip(),
        )


class AgentOpsMcpClient:
    """Small authenticated JSON-RPC client for AgentOps-owned loopback MCP services.

    The bearer credential authenticates this local service caller only. It is never
    interpreted as owner approval authority by Origins.
    """

    def __init__(
        self,
        *,
        endpoints: AgentOpsMcpEndpoints,
        token: str,
        timeout: float = 8.0,
    ) -> None:
        self.endpoints = AgentOpsMcpEndpoints(
            approval=_loopback_mcp_url(endpoints.approval, "approval"),
            external_operation=_loopback_mcp_url(endpoints.external_operation, "external operation"),
        )
        normalized = token.strip()
        if len(normalized) < MIN_TOKEN_LENGTH:
            raise AgentOpsMcpError(f"AGENTOPS_MCP_AUTH_TOKEN must be at least {MIN_TOKEN_LENGTH} characters")
        self._token = normalized
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "AgentOpsMcpClient":
        return cls(
            endpoints=AgentOpsMcpEndpoints.from_env(),
            token=os.environ.get("AGENTOPS_MCP_AUTH_TOKEN", ""),
        )

    def request_approval(self, arguments: Mapping[str, object]) -> dict[str, object]:
        return self._call(self.endpoints.approval, "agentops.approval.request", arguments)

    def get_approval(self, approval_id: str) -> dict[str, object]:
        if not approval_id.strip():
            raise AgentOpsMcpError("approval_id is required")
        return self._call(self.endpoints.approval, "agentops.approval.get", {"approval_id": approval_id.strip()})

    def list_pending_approvals(self) -> dict[str, object]:
        return self._call(self.endpoints.approval, "agentops.approval.list_pending", {})

    def start_external_operation(self, arguments: Mapping[str, object]) -> dict[str, object]:
        return self._call(self.endpoints.external_operation, "agentops.external_operation.start", arguments)

    def get_external_operation(self, operation_id: str) -> dict[str, object]:
        if not operation_id.strip():
            raise AgentOpsMcpError("operation_id is required")
        return self._call(
            self.endpoints.external_operation,
            "agentops.external_operation.get",
            {"operation_id": operation_id.strip()},
        )

    def finalize_external_operation(self, arguments: Mapping[str, object]) -> dict[str, object]:
        return self._call(self.endpoints.external_operation, "agentops.external_operation.finalize", arguments)

    def public_status(self) -> dict[str, object]:
        return {
            "owner": "Hunter-AgentOps",
            "transport": "mcp/rpc",
            "protocol": MCP_PROTOCOL_VERSION,
            "approval_endpoint": self.endpoints.approval,
            "external_operation_endpoint": self.endpoints.external_operation,
            "service_credential_is_owner_authorization": False,
        }

    def _call(self, endpoint: str, tool: str, arguments: Mapping[str, object]) -> dict[str, object]:
        rpc_id = str(uuid.uuid4())
        body = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": dict(arguments),
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "origins-phase7",
                        "version": "1",
                    },
                },
            },
        }
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=raw,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                "Mcp-Method": "tools/call",
                "Mcp-Name": tool,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload_raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1600:]
            raise AgentOpsMcpError(f"AgentOps MCP {tool} failed HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AgentOpsMcpError(f"AgentOps MCP {tool} unavailable: {exc.reason}") from exc
        if status != 200:
            raise AgentOpsMcpError(f"AgentOps MCP {tool} returned HTTP {status}")
        try:
            payload = json.loads(payload_raw or "{}")
        except json.JSONDecodeError as exc:
            raise AgentOpsMcpError(f"AgentOps MCP {tool} returned non-JSON") from exc
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != rpc_id:
            raise AgentOpsMcpError(f"AgentOps MCP {tool} returned an invalid JSON-RPC envelope")
        error = payload.get("error")
        if isinstance(error, Mapping):
            raise AgentOpsMcpError(f"AgentOps MCP {tool} rejected request: {error.get('message') or error}")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise AgentOpsMcpError(f"AgentOps MCP {tool} omitted result")
        structured = result.get("structuredContent")
        if not isinstance(structured, Mapping):
            raise AgentOpsMcpError(f"AgentOps MCP {tool} omitted structuredContent")
        if result.get("isError") is True or structured.get("ok") is not True:
            raise AgentOpsMcpError(str(structured.get("error") or f"AgentOps MCP {tool} returned an error"))
        return dict(structured)


def _loopback_mcp_url(value: str, label: str) -> str:
    raw = value.strip()
    if not raw:
        raise AgentOpsMcpError(f"AgentOps {label} MCP URL is required")
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError as exc:
        raise AgentOpsMcpError(f"AgentOps {label} MCP URL is invalid") from exc
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise AgentOpsMcpError(f"AgentOps {label} MCP URL must use loopback HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/mcp":
        raise AgentOpsMcpError(f"AgentOps {label} MCP URL must be a plain loopback /mcp endpoint")
    if parsed.port is None:
        raise AgentOpsMcpError(f"AgentOps {label} MCP URL must include an explicit port")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
