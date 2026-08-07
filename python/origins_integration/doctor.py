from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass
from typing import Any, Callable

from .engineering import BridgeError, OriginsClient

STATUS_ORDER = {"missing": 0, "available": 1, "compatible": 2, "proven": 3}

AGENTOPS_MODULE = "hunter_agentops.code_ops_switcher_runner"
AGENTOPS_DISTRIBUTION = "hunter-agentops"
CODEOPS_INGEST_MODULE = "hunter_codeops.code_ops_sergeant_ingest"
CODEOPS_DISTRIBUTION = "hunter-codeops"
SERGEANT_DISTRIBUTION = "sergeant-reviewer"
CODEOPS_EXECUTABLE = "hunter-codeops-switcher"
SERGEANT_EXECUTABLE = "sergeant"


@dataclass(frozen=True)
class MountSurfaceResult:
    surface: str
    status: str
    version: str
    detail: str
    session_id: str = ""
    evidence_sha256: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUS_ORDER:
            raise ValueError(f"unsupported mount status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "status": self.status,
            "version": self.version,
            "detail": self.detail,
            "session_id": self.session_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class EngineeringMountDoctorResult:
    repository_id: str
    repository_revision: int
    repository_head_oid: str
    surfaces: tuple[MountSurfaceResult, ...]
    overall_status: str
    live_engineering_proven: bool
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "repository_revision": self.repository_revision,
            "repository_head_oid": self.repository_head_oid,
            "surfaces": [surface.as_dict() for surface in self.surfaces],
            "overall_status": self.overall_status,
            "live_engineering_proven": self.live_engineering_proven,
            "blockers": list(self.blockers),
        }


class EngineeringMountDoctor:
    """Read-only compatibility doctor for the current engineering owners."""

    def __init__(
        self,
        client: OriginsClient,
        *,
        importer: Callable[[str], Any] = importlib.import_module,
        version_reader: Callable[[str], str] = importlib.metadata.version,
    ) -> None:
        self.client = client
        self._importer = importer
        self._version_reader = version_reader

    def run(self, repository_id: str) -> EngineeringMountDoctorResult:
        stored_repository = self.client.get_repository(repository_id)
        workspace_id = _required_string(stored_repository, "workspace_id")
        worktree = _required_string(stored_repository, "worktree_root")
        repository = self.client.inspect_repository(workspace_id, worktree)
        if _required_string(repository, "repository_id") != repository_id:
            raise BridgeError("Repository refresh changed Repository identity")
        revision = _required_int(repository, "revision")
        head_oid = _required_string(repository, "head_oid", allow_empty=True)

        surfaces = (
            self._probe_agentops(worktree),
            self._probe_codeops_ingest(),
            self._probe_cli(
                surface="codeops_cli",
                distribution=CODEOPS_DISTRIBUTION,
                executable=CODEOPS_EXECUTABLE,
                workspace_id=workspace_id,
                worktree=worktree,
            ),
            self._probe_cli(
                surface="sergeant_cli",
                distribution=SERGEANT_DISTRIBUTION,
                executable=SERGEANT_EXECUTABLE,
                workspace_id=workspace_id,
                worktree=worktree,
            ),
        )
        overall = min(surfaces, key=lambda surface: STATUS_ORDER[surface.status]).status
        blockers = tuple(
            f"{surface.surface}: {surface.detail}"
            for surface in surfaces
            if STATUS_ORDER[surface.status] < STATUS_ORDER["compatible"]
        )
        return EngineeringMountDoctorResult(
            repository_id=repository_id,
            repository_revision=revision,
            repository_head_oid=head_oid,
            surfaces=surfaces,
            overall_status=overall,
            live_engineering_proven=False,
            blockers=blockers,
        )

    def _probe_agentops(self, worktree: str) -> MountSurfaceResult:
        version = self._version(AGENTOPS_DISTRIBUTION)
        try:
            module = self._importer(AGENTOPS_MODULE)
        except ImportError as exc:
            return MountSurfaceResult(
                "agentops_python",
                "missing",
                version,
                f"cannot import {AGENTOPS_MODULE}: {exc}",
            )
        except Exception as exc:  # imported owner exists but failed during import
            return MountSurfaceResult(
                "agentops_python",
                "available",
                version,
                f"{AGENTOPS_MODULE} import failed compatibility probe: {exc}",
            )

        approval_type = getattr(module, "ApprovalState", None)
        packet_type = getattr(module, "CodeOpsOperationPacket", None)
        if approval_type is None or packet_type is None:
            return MountSurfaceResult(
                "agentops_python",
                "available",
                version,
                "required ApprovalState/CodeOpsOperationPacket symbols are incomplete",
            )
        try:
            approval = approval_type("not_required")
            packet = packet_type(
                operation_id="origins-doctor-probe",
                task="Origins compatibility probe",
                workspace=worktree,
                files=(),
                plan="",
                apply_plan=False,
                approval_state=approval,
            )
            if getattr(packet, "operation_id", None) != "origins-doctor-probe":
                raise ValueError("operation_id was not preserved")
            if getattr(packet, "task", None) != "Origins compatibility probe":
                raise ValueError("task was not preserved")
            if getattr(packet, "workspace", None) != worktree:
                raise ValueError("Repository worktree was not preserved")
            if bool(getattr(packet, "apply_plan", True)):
                raise ValueError("harmless probe unexpectedly requests apply")
        except Exception as exc:
            return MountSurfaceResult(
                "agentops_python",
                "available",
                version,
                f"AgentOps packet behavior is incompatible: {exc}",
            )
        return MountSurfaceResult(
            "agentops_python",
            "compatible",
            version,
            "AgentOps packet/approval contract is compatible",
        )

    def _probe_codeops_ingest(self) -> MountSurfaceResult:
        version = self._version(CODEOPS_DISTRIBUTION)
        try:
            module = self._importer(CODEOPS_INGEST_MODULE)
        except ImportError as exc:
            return MountSurfaceResult(
                "codeops_python",
                "missing",
                version,
                f"cannot import {CODEOPS_INGEST_MODULE}: {exc}",
            )
        except Exception as exc:
            return MountSurfaceResult(
                "codeops_python",
                "available",
                version,
                f"{CODEOPS_INGEST_MODULE} import failed compatibility probe: {exc}",
            )
        ingest = getattr(module, "ingest_sergeant_result_text", None)
        if not callable(ingest):
            return MountSurfaceResult(
                "codeops_python",
                "available",
                version,
                "required ingest_sergeant_result_text callable is missing",
            )
        expected = {
            "PASS": (False, False),
            "NEEDS WORK": (True, False),
            "BLOCK": (True, True),
        }
        try:
            for verdict, (needs_loop, blocked) in expected.items():
                result = ingest(f'{{"verdict":"{verdict}"}}')
                actual_verdict = _enum_value(getattr(result, "verdict", None))
                if actual_verdict != verdict:
                    raise ValueError(f"{verdict} normalized as {actual_verdict!r}")
                if bool(getattr(result, "needs_loop", None)) != needs_loop:
                    raise ValueError(f"{verdict} needs_loop contract changed")
                if bool(getattr(result, "blocked", None)) != blocked:
                    raise ValueError(f"{verdict} blocked contract changed")
        except Exception as exc:
            return MountSurfaceResult(
                "codeops_python",
                "available",
                version,
                f"CodeOps Sergeant ingest behavior is incompatible: {exc}",
            )
        return MountSurfaceResult(
            "codeops_python",
            "compatible",
            version,
            "CodeOps Sergeant ingest contract is compatible",
        )

    def _probe_cli(
        self,
        *,
        surface: str,
        distribution: str,
        executable: str,
        workspace_id: str,
        worktree: str,
    ) -> MountSurfaceResult:
        version = self._version(distribution)
        try:
            accepted = self.client.submit_process(
                workspace_id=workspace_id,
                workspace_root=worktree,
                executable=executable,
                args=["--help"],
                timeout_seconds=20,
                max_output_bytes=256 * 1024,
            )
            session = accepted.get("session")
            if not isinstance(session, dict):
                raise BridgeError("originsd did not return a Session projection")
            session_id = _required_string(session, "session_id")
            session = self.client.wait_session(session_id, timeout=30)
            output = self.client.get_session_output(session_id)
        except BridgeError as exc:
            return MountSurfaceResult(
                surface,
                "missing",
                version,
                f"cannot start {executable} through originsd: {exc}",
            )

        state = str(session.get("state", ""))
        exit_code = session.get("exit_code")
        truncated = bool(session.get("output_truncated"))
        evidence_sha256 = str(session.get("stdout_sha256", ""))
        if state == "completed" and exit_code == 0 and not truncated:
            return MountSurfaceResult(
                surface,
                "compatible",
                version,
                f"{executable} --help completed through originsd",
                session_id=session_id,
                evidence_sha256=evidence_sha256,
            )
        if state == "interrupted" and exit_code is None:
            return MountSurfaceResult(
                surface,
                "missing",
                version,
                f"{executable} could not be started through originsd",
                session_id=session_id,
                evidence_sha256=evidence_sha256,
            )
        detail = f"{executable} is present but probe ended state={state} exit_code={exit_code}"
        if truncated:
            detail += " with truncated output"
        # Retained output stays in its mechanical Session; the doctor records only status/digest.
        del output
        return MountSurfaceResult(
            surface,
            "available",
            version,
            detail,
            session_id=session_id,
            evidence_sha256=evidence_sha256,
        )

    def _version(self, distribution: str) -> str:
        try:
            value = self._version_reader(distribution)
        except importlib.metadata.PackageNotFoundError:
            return ""
        except Exception:
            return ""
        return value if isinstance(value, str) else str(value)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else ""


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
