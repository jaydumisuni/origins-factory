from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class Phase5Error(RuntimeError):
    pass


def _loopback_url(value: str, *, default: str) -> str:
    raw = str(value or default).strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise Phase5Error("owner endpoint must use http/https")
    if parsed.username or parsed.password:
        raise Phase5Error("owner endpoint must not embed credentials")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise Phase5Error("Phase 5 owner endpoints must remain loopback-local")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise Phase5Error("owner endpoint must be an origin, not a path/query URL")
    return raw


@dataclass(frozen=True, slots=True)
class OwnerResponse:
    status: int
    value: dict[str, Any]


class JsonOwnerClient:
    def __init__(
        self,
        base_url: str,
        *,
        default_headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = _loopback_url(base_url, default=base_url)
        self.default_headers = {
            str(key): str(value)
            for key, value in dict(default_headers or {}).items()
            if str(key).strip() and str(value).strip()
        }
        self.timeout = max(1.0, min(60.0, float(timeout)))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, str | int] | None = None,
    ) -> OwnerResponse:
        if not path.startswith("/") or path.startswith("//"):
            raise Phase5Error("owner API path must be absolute and local to the configured origin")
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", **self.default_headers}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise Phase5Error("owner response exceeds 4 MiB projection limit")
                value = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(value, dict):
                    raise Phase5Error("owner response must be a JSON object")
                return OwnerResponse(int(response.status), value)
        except urllib.error.HTTPError as exc:
            raw = exc.read(512 * 1024)
            try:
                value = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                value = {"error": f"OWNER_HTTP_{exc.code}"}
            if not isinstance(value, dict):
                value = {"error": f"OWNER_HTTP_{exc.code}"}
            return OwnerResponse(int(exc.code), value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise Phase5Error(f"owner request failed: {exc}") from exc


class OracleBrowserMount:
    """Thin client for the existing Oracle retained browser authority."""

    ALLOWED_AUTHORITIES = frozenset({"observe", "assist", "act"})

    def __init__(self, base_url: str = "http://127.0.0.1:8765", *, pairing_token: str = ""):
        token = str(pairing_token or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = JsonOwnerClient(base_url, default_headers=headers)

    @classmethod
    def from_env(cls) -> "OracleBrowserMount":
        return cls(
            os.environ.get("ORIGINS_ORACLE_BROWSER_URL", "http://127.0.0.1:8765"),
            pairing_token=os.environ.get("ORACLE_PAIRING_TOKEN", ""),
        )

    def snapshot(self) -> dict[str, Any]:
        health = self.client.request("GET", "/health")
        capabilities = self.client.request("GET", "/capabilities")
        latest = self.client.request("GET", "/latest")
        service_available = health.status == 200 and bool(health.value.get("ok"))
        browser_connected = service_available and bool(health.value.get("browserConnected"))
        return {
            "owner": "oracle",
            "available": browser_connected,
            "service_available": service_available,
            "browser_connected": browser_connected,
            "health": health.value,
            "capabilities": capabilities.value if capabilities.status == 200 else {},
            "latest_observation": latest.value if latest.status == 200 else None,
        }

    def set_authority(self, authority: str, *, approved: bool = False) -> dict[str, Any]:
        authority = str(authority or "").strip().lower()
        if authority not in self.ALLOWED_AUTHORITIES:
            raise Phase5Error(f"unsupported Oracle browser authority: {authority}")
        if authority == "act" and not approved:
            raise Phase5Error("act authority requires an explicit approved handoff")
        return self._command({"type": "setAuthority", "authority": authority}, approved=approved)

    def human_takeover(self) -> dict[str, Any]:
        return self._command({"type": "humanTakeover"}, approved=False)

    def command(self, command: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
        command = dict(command or {})
        if not str(command.get("type") or "").strip():
            raise Phase5Error("browser command type is required")
        if command.get("type") in {"setAuthority", "humanTakeover"}:
            raise Phase5Error("authority transitions must use dedicated Phase 5 handoff methods")
        return self._command(command, approved=approved)

    def _command(self, command: dict[str, Any], *, approved: bool) -> dict[str, Any]:
        response = self.client.request(
            "POST",
            "/command",
            payload={"command": command, "approved": bool(approved)},
        )
        if response.status != 200:
            raise Phase5Error(str(response.value.get("error") or f"Oracle HTTP {response.status}"))
        return response.value


class LumiMount:
    """Thin projection over Lumi's existing persistent queue/download owner."""

    def __init__(self, base_url: str = "http://127.0.0.1:7000"):
        self.client = JsonOwnerClient(base_url)

    @classmethod
    def from_env(cls) -> "LumiMount":
        return cls(os.environ.get("ORIGINS_LUMI_URL", "http://127.0.0.1:7000"))

    def snapshot(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(500, int(limit)))
        capabilities = self.client.request("GET", "/api/capabilities")
        downloads = self.client.request("GET", "/api/downloads", query={"limit": limit})
        queues = self.client.request("GET", "/api/queues")
        available = capabilities.status == 200 and downloads.status == 200 and queues.status == 200
        return {
            "owner": "lumi",
            "available": available,
            "capabilities": capabilities.value if capabilities.status == 200 else {},
            "downloads": downloads.value.get("downloads", []) if downloads.status == 200 else [],
            "queues": queues.value.get("queues", []) if queues.status == 200 else [],
        }

    def queue_download(
        self,
        url: str,
        *,
        filename: str = "",
        queue_id: str = "default",
        priority: int = 0,
        start_paused: bool = False,
    ) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https", "ftp"} or not parsed.netloc:
            raise Phase5Error("Lumi handoff URL must be an absolute http/https/ftp URL")
        if parsed.username or parsed.password:
            raise Phase5Error("credentials must not be embedded in a Lumi handoff URL")
        response = self.client.request(
            "POST",
            "/api/downloads/start",
            payload={
                "url": parsed.geturl(),
                "filename": str(filename or "").strip(),
                "queue_id": str(queue_id or "default"),
                "priority": int(priority),
                "start_paused": bool(start_paused),
            },
        )
        if response.status != 200:
            raise Phase5Error(str(response.value.get("error") or f"Lumi HTTP {response.status}"))
        return response.value

    def task(self, task_id: str) -> dict[str, Any]:
        task_id = str(task_id or "").strip()
        if not task_id or "/" in task_id or ".." in task_id:
            raise Phase5Error("invalid Lumi task ID")
        response = self.client.request("GET", f"/api/downloads/{urllib.parse.quote(task_id, safe='')}")
        if response.status != 200:
            raise Phase5Error(str(response.value.get("error") or f"Lumi HTTP {response.status}"))
        return response.value

    def artifact_candidate(self, task_id: str) -> dict[str, Any]:
        task = self.task(task_id)
        if task.get("status") != "completed":
            raise Phase5Error("only completed Lumi tasks can be handed to Artifact registration")
        path = str(task.get("path") or task.get("final_path") or "").strip()
        if not path:
            raise Phase5Error("completed Lumi task has no owner path")
        return {
            "schema_version": "origins.lumi-artifact-candidate.v1",
            "owner": "lumi",
            "owner_task_id": str(task.get("id") or task_id),
            "path": path,
            "filename": str(task.get("filename") or ""),
            "total_bytes": int(task.get("total_bytes") or task.get("downloaded_bytes") or 0),
            "content_type": str(task.get("content_type") or ""),
            "etag": str(task.get("etag") or ""),
            "last_modified": str(task.get("last_modified") or ""),
            "finished_at": str(task.get("finished_at") or ""),
        }
