from __future__ import annotations

import importlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Protocol

TERMINAL_STATES = {"completed", "failed", "interrupted", "timed_out"}
APPROVAL_STATES = {"not_required", "required", "approved", "denied"}
REVIEW_ACTIONS = {
    "PASS": "complete_candidate",
    "NEEDS WORK": "correct",
    "BLOCK": "block",
    "UNKNOWN": "unresolved",
}
SAFE_RELATIVE_RE = re.compile(r"^[^\x00]+$")


class BridgeError(RuntimeError):
    """Raised when an Origins engineering attempt cannot be safely completed."""


class IntegrationUnavailable(BridgeError):
    """Raised when an owning AgentOps/CodeOps package is unavailable or incompatible."""


@dataclass(frozen=True)
class EngineeringAttemptRequest:
    operation_id: str
    repository_id: str
    task: str
    config: str = "config/code_ops_switcher.example.json"
    files: tuple[str, ...] = field(default_factory=tuple)
    plan: str = ""
    apply_plan: bool = False
    approval_state: str = "not_required"
    client_kind: str = "terminal"
    mode: str = "quick_edit"
    provider_id: str = ""
    required_capability: str = ""
    review: str = "required"
    review_mode: str = "pull_request"

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise BridgeError("operation_id is required")
        if not self.repository_id.strip():
            raise BridgeError("repository_id is required")
        if not self.task.strip():
            raise BridgeError("task is required")
        if self.approval_state not in APPROVAL_STATES:
            raise BridgeError(
                "approval_state must be one of: " + ", ".join(sorted(APPROVAL_STATES))
            )
        _validate_config_reference(self.config, "CodeOps config")
        if self.plan:
            _validate_relative_path(self.plan, "CodeOps plan")
        if not self.review_mode.strip():
            raise BridgeError("review_mode is required")


@dataclass(frozen=True)
class MechanicalResult:
    session_id: str
    session: dict[str, Any]
    output: dict[str, Any]
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class EngineeringAttemptResult:
    operation_id: str
    repository_id: str
    repository_revision: int
    repository_head_oid: str
    route: MechanicalResult
    plan_preview: MechanicalResult | None
    plan_apply: MechanicalResult | None
    sergeant_command: MechanicalResult
    sergeant_review: MechanicalResult
    review_sha256: str
    verdict: str
    needs_loop: bool
    blocked: bool
    summary: str
    recommended_agentops_action: str

    def evidence_record(self) -> dict[str, Any]:
        return {
            "event": "origins.engineering_attempt.result",
            "operation_id": self.operation_id,
            "repository_id": self.repository_id,
            "repository_revision": self.repository_revision,
            "repository_head_oid": self.repository_head_oid,
            "route_session_id": self.route.session_id,
            "plan_preview_session_id": self.plan_preview.session_id if self.plan_preview else "",
            "plan_apply_session_id": self.plan_apply.session_id if self.plan_apply else "",
            "sergeant_command_session_id": self.sergeant_command.session_id,
            "sergeant_review_session_id": self.sergeant_review.session_id,
            "review_sha256": self.review_sha256,
            "verdict": self.verdict,
            "needs_loop": self.needs_loop,
            "blocked": self.blocked,
            "recommended_agentops_action": self.recommended_agentops_action,
        }


class ContractAdapter(Protocol):
    def build_agentops_packet(
        self, request: EngineeringAttemptRequest, *, workspace: str
    ) -> Any: ...

    def ingest_sergeant_result_text(self, text: str) -> Any: ...


class ExternalContracts:
    """Dynamic adapter to the owning AgentOps and CodeOps Python contracts."""

    def __init__(self, approval_state_type: Any, packet_type: Any, ingest: Any) -> None:
        self._approval_state_type = approval_state_type
        self._packet_type = packet_type
        self._ingest = ingest

    @classmethod
    def load(cls) -> "ExternalContracts":
        try:
            agentops = importlib.import_module("hunter_agentops.code_ops_switcher_runner")
            ingest_module = importlib.import_module("hunter_codeops.code_ops_sergeant_ingest")
            approval_state_type = getattr(agentops, "ApprovalState")
            packet_type = getattr(agentops, "CodeOpsOperationPacket")
            ingest = getattr(ingest_module, "ingest_sergeant_result_text")
        except (ImportError, AttributeError) as exc:
            raise IntegrationUnavailable(
                "current Hunter AgentOps and Hunter CodeOps Python contracts are required"
            ) from exc
        return cls(approval_state_type, packet_type, ingest)

    def build_agentops_packet(
        self, request: EngineeringAttemptRequest, *, workspace: str
    ) -> Any:
        try:
            approval_state = self._approval_state_type(request.approval_state)
            return self._packet_type(
                operation_id=request.operation_id,
                task=request.task,
                client_kind=request.client_kind,
                mode=request.mode,
                config=request.config,
                provider_id=request.provider_id,
                required_capability=request.required_capability,
                review=request.review,
                workspace=workspace,
                files=request.files,
                plan=request.plan,
                apply_plan=request.apply_plan,
                approval_state=approval_state,
            )
        except Exception as exc:  # owning contract defines its own validation error type
            raise BridgeError(f"AgentOps operation packet rejected: {exc}") from exc

    def ingest_sergeant_result_text(self, text: str) -> Any:
        try:
            return self._ingest(text)
        except Exception as exc:  # owning CodeOps contract defines its own error type
            raise BridgeError(f"CodeOps Sergeant result ingestion failed: {exc}") from exc


class OriginsClient:
    """Minimal authenticated client for the proven originsd mechanical surface."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0) -> None:
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise BridgeError("Origins engineering bridge requires a loopback originsd URL")
        if not token:
            raise BridgeError("Origins local bearer token is required")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "OriginsClient":
        base_url = os.environ.get("ORIGINS_URL", "http://127.0.0.1:48700")
        token = os.environ.get("ORIGINS_LOCAL_TOKEN", "")
        return cls(base_url, token)

    def get_repository(self, repository_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/repositories/{urllib.parse.quote(repository_id)}")

    def submit_process(
        self,
        *,
        workspace_id: str,
        workspace_root: str,
        executable: str,
        args: list[str],
        timeout_seconds: int = 120,
        max_output_bytes: int = 4 * 1024 * 1024,
    ) -> dict[str, Any]:
        envelope = {
            "contract_type": "command_envelope",
            "schema_version": "1.0.0",
            "command_id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "capability_id": "origins.process.run",
            "effect": "execute",
            "payload": {
                "workspace_root": workspace_root,
                "executable": executable,
                "args": args,
                "cwd": ".",
                "timeout_seconds": timeout_seconds,
                "max_output_bytes": max_output_bytes,
            },
            "created_at": _now(),
        }
        return self._json("POST", "/v1/commands", envelope, expected_status=202)

    def wait_session(self, session_id: str, *, timeout: float = 150.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = self._json("GET", f"/v1/sessions/{urllib.parse.quote(session_id)}")
            if last.get("state") in TERMINAL_STATES:
                return last
            time.sleep(0.05)
        raise BridgeError(f"Origins Session {session_id} did not become terminal: {last}")

    def get_session_output(self, session_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/sessions/{urllib.parse.quote(session_id)}/output")

    def _json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if response.status != expected_status:
                    raise BridgeError(
                        f"originsd {method} {path} returned HTTP {response.status}, expected {expected_status}"
                    )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1200:]
            raise BridgeError(f"originsd {method} {path} failed HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BridgeError(f"originsd {method} {path} unavailable: {exc.reason}") from exc
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise BridgeError(f"originsd {method} {path} returned non-JSON") from exc
        if not isinstance(value, dict):
            raise BridgeError(f"originsd {method} {path} returned a non-object")
        return value


class EngineeringBridge:
    def __init__(self, client: OriginsClient, contracts: ContractAdapter | None = None) -> None:
        self.client = client
        self.contracts = contracts or ExternalContracts.load()

    def run_attempt(self, request: EngineeringAttemptRequest) -> EngineeringAttemptResult:
        repository = self.client.get_repository(request.repository_id)
        workspace_id = _required_string(repository, "workspace_id")
        workspace_root = _required_string(repository, "worktree_root")
        repository_revision = _required_int(repository, "revision")
        repository_head_oid = _required_string(repository, "head_oid", allow_empty=True)

        # The owning AgentOps packet validates operation files and approval before any process is started.
        packet = self.contracts.build_agentops_packet(request, workspace=workspace_root)
        _validate_packet_identity(packet, request, workspace_root)

        route_args = [
            "--config",
            request.config,
            "route",
            "--task",
            request.task,
            "--client",
            request.client_kind,
            "--mode",
            request.mode,
        ]
        if request.provider_id:
            route_args.extend(["--provider-id", request.provider_id])
        if request.required_capability:
            route_args.extend(["--capability", request.required_capability])
        if request.review:
            route_args.extend(["--review", request.review])
        route = self._run_json_process(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            executable="hunter-codeops-switcher",
            args=route_args,
            label="CodeOps route",
        )

        plan_preview: MechanicalResult | None = None
        plan_apply: MechanicalResult | None = None
        if request.plan:
            plan_args = [
                "--config",
                request.config,
                "apply-plan",
                "--root",
                workspace_root,
                "--plan",
                request.plan,
            ]
            plan_preview = self._run_json_process(
                workspace_id=workspace_id,
                workspace_root=workspace_root,
                executable="hunter-codeops-switcher",
                args=plan_args,
                label="CodeOps plan dry-run",
            )
            if request.apply_plan:
                # AgentOps owning packet already rejected non-approved apply intent.
                plan_apply = self._run_json_process(
                    workspace_id=workspace_id,
                    workspace_root=workspace_root,
                    executable="hunter-codeops-switcher",
                    args=[*plan_args, "--apply"],
                    label="CodeOps plan apply",
                )

        sergeant_args = [
            "--config",
            request.config,
            "sergeant-command",
            "--workspace",
            workspace_root,
            "--review-mode",
            request.review_mode,
        ]
        if request.files:
            sergeant_args.extend(["--files", ",".join(request.files)])
        sergeant_command_result = self._run_json_process(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            executable="hunter-codeops-switcher",
            args=sergeant_args,
            label="CodeOps Sergeant command",
        )
        command = _extract_sergeant_command(
            sergeant_command_result.payload,
            workspace_root=workspace_root,
            files=request.files,
            review_mode=request.review_mode,
        )

        sergeant_review = self._run_text_process(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            executable="sergeant",
            args=command[1:],
            label="Sergeant review",
        )
        stdout = _required_output_text(sergeant_review, "Sergeant review")
        ingested = self.contracts.ingest_sergeant_result_text(stdout)
        verdict = _enum_value(getattr(ingested, "verdict", None))
        if verdict not in REVIEW_ACTIONS:
            raise BridgeError(f"CodeOps returned unsupported Sergeant verdict: {verdict!r}")
        needs_loop = bool(getattr(ingested, "needs_loop", verdict != "PASS"))
        blocked = bool(getattr(ingested, "blocked", verdict == "BLOCK"))
        summary = str(getattr(ingested, "summary", "")).strip()[:500]
        review_sha256 = _required_string(sergeant_review.session, "stdout_sha256")

        return EngineeringAttemptResult(
            operation_id=request.operation_id,
            repository_id=request.repository_id,
            repository_revision=repository_revision,
            repository_head_oid=repository_head_oid,
            route=route,
            plan_preview=plan_preview,
            plan_apply=plan_apply,
            sergeant_command=sergeant_command_result,
            sergeant_review=sergeant_review,
            review_sha256=review_sha256,
            verdict=verdict,
            needs_loop=needs_loop,
            blocked=blocked,
            summary=summary,
            recommended_agentops_action=REVIEW_ACTIONS[verdict],
        )

    def _run_json_process(
        self,
        *,
        workspace_id: str,
        workspace_root: str,
        executable: str,
        args: list[str],
        label: str,
    ) -> MechanicalResult:
        result = self._run_text_process(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            executable=executable,
            args=args,
            label=label,
        )
        text = _required_output_text(result, label)
        try:
            payload = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise BridgeError(f"{label} returned non-JSON output") from exc
        if not isinstance(payload, dict):
            raise BridgeError(f"{label} JSON root must be an object")
        if payload.get("ok") is False:
            raise BridgeError(f"{label} reported failure: {payload.get('error', 'unknown error')}")
        return MechanicalResult(result.session_id, result.session, result.output, payload)

    def _run_text_process(
        self,
        *,
        workspace_id: str,
        workspace_root: str,
        executable: str,
        args: list[str],
        label: str,
    ) -> MechanicalResult:
        accepted = self.client.submit_process(
            workspace_id=workspace_id,
            workspace_root=workspace_root,
            executable=executable,
            args=args,
        )
        session = accepted.get("session")
        if not isinstance(session, dict):
            raise BridgeError(f"{label} did not return a Session projection")
        session_id = _required_string(session, "session_id")
        session = self.client.wait_session(session_id)
        output = self.client.get_session_output(session_id)
        if session.get("state") != "completed" or session.get("exit_code") != 0:
            raise BridgeError(
                f"{label} mechanical Session {session_id} ended as {session.get('state')} "
                f"with exit_code={session.get('exit_code')}"
            )
        if bool(session.get("output_truncated")):
            raise BridgeError(f"{label} output was truncated; semantic ingestion is unsafe")
        return MechanicalResult(session_id, session, output, None)


def _extract_sergeant_command(
    payload: dict[str, Any] | None,
    *,
    workspace_root: str,
    files: tuple[str, ...],
    review_mode: str,
) -> list[str]:
    if not isinstance(payload, dict):
        raise BridgeError("CodeOps Sergeant command payload missing")
    command = payload.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise BridgeError("CodeOps Sergeant command must be a non-empty string argv list")
    expected_prefix = ["sergeant", "app-review", workspace_root, "--mode", review_mode]
    if command[: len(expected_prefix)] != expected_prefix:
        raise BridgeError("CodeOps Sergeant command does not match the reviewed app-review contract")
    expected_files = ",".join(files)
    if files:
        try:
            index = command.index("--files")
        except ValueError as exc:
            raise BridgeError("CodeOps Sergeant command omitted requested file scope") from exc
        if index + 1 >= len(command) or command[index + 1] != expected_files:
            raise BridgeError("CodeOps Sergeant command changed requested file scope")
    elif "--files" in command:
        raise BridgeError("CodeOps Sergeant command introduced unexpected file scope")
    allowed_flags = {"--mode", "--files", "--pretty"}
    index = 3
    while index < len(command):
        item = command[index]
        if item not in allowed_flags:
            raise BridgeError(f"CodeOps Sergeant command introduced unsupported argument {item!r}")
        if item in {"--mode", "--files"}:
            index += 2
        else:
            index += 1
    return command


def _validate_packet_identity(packet: Any, request: EngineeringAttemptRequest, workspace: str) -> None:
    expected = {
        "operation_id": request.operation_id,
        "task": request.task,
        "workspace": workspace,
        "files": request.files,
        "plan": request.plan,
        "apply_plan": request.apply_plan,
    }
    for field, expected_value in expected.items():
        actual = getattr(packet, field, None)
        if actual != expected_value:
            raise BridgeError(f"AgentOps packet changed {field}: expected {expected_value!r}, got {actual!r}")


def _validate_config_reference(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise BridgeError(f"{label} must be a non-empty NUL-free path reference")


def _validate_relative_path(value: str, label: str) -> None:
    if not value or not SAFE_RELATIVE_RE.fullmatch(value):
        raise BridgeError(f"{label} must be a non-empty relative path")
    posix = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise BridgeError(f"{label} must stay relative to the Repository worktree")
    if ".." in posix.parts or ".." in windows.parts:
        raise BridgeError(f"{label} cannot escape the Repository worktree")


def _required_output_text(result: MechanicalResult, label: str) -> str:
    text = result.output.get("stdout")
    if not isinstance(text, str):
        raise BridgeError(f"{label} stdout is not UTF-8 text")
    return text


def _required_string(value: dict[str, Any], field: str, *, allow_empty: bool = False) -> str:
    item = value.get(field)
    if not isinstance(item, str) or (not allow_empty and not item):
        raise BridgeError(f"required string field {field} missing")
    return item


def _required_int(value: dict[str, Any], field: str) -> int:
    item = value.get(field)
    if not isinstance(item, int) or isinstance(item, bool):
        raise BridgeError(f"required integer field {field} missing")
    return item


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else ""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
