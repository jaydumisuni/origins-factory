from __future__ import annotations

import inspect
from enum import Enum
from types import SimpleNamespace

from origins_integration import doctor
from origins_integration.doctor import EngineeringMountDoctor


class ApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"


class Packet:
    def __init__(
        self,
        *,
        operation_id: str,
        task: str,
        workspace: str,
        files=(),
        plan="",
        apply_plan=False,
        approval_state=ApprovalState.NOT_REQUIRED,
        **_kwargs,
    ) -> None:
        self.operation_id = operation_id
        self.task = task
        self.workspace = workspace
        self.files = files
        self.plan = plan
        self.apply_plan = apply_plan
        self.approval_state = approval_state


class Verdict(str, Enum):
    PASS_ = "PASS"
    NEEDS_WORK = "NEEDS WORK"
    BLOCK = "BLOCK"


def ingest(text: str):
    if '"PASS"' in text:
        return SimpleNamespace(verdict=Verdict.PASS_, needs_loop=False, blocked=False)
    if '"NEEDS WORK"' in text:
        return SimpleNamespace(verdict=Verdict.NEEDS_WORK, needs_loop=True, blocked=False)
    if '"BLOCK"' in text:
        return SimpleNamespace(verdict=Verdict.BLOCK, needs_loop=True, blocked=True)
    raise ValueError("unknown")


class FakeClient:
    def __init__(self, outcomes: dict[str, tuple[str, int | None, bool]] | None = None) -> None:
        self.outcomes = outcomes or {
            doctor.CODEOPS_EXECUTABLE: ("completed", 0, False),
            doctor.SERGEANT_EXECUTABLE: ("completed", 0, False),
        }
        self.submitted: list[tuple[str, tuple[str, ...]]] = []
        self.inspections: list[tuple[str, str]] = []

    def get_repository(self, repository_id: str):
        return {
            "repository_id": repository_id,
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "revision": 7,
            "head_oid": "a" * 40,
            "worktree_root": "/repo",
        }

    def inspect_repository(self, workspace_id: str, path: str):
        self.inspections.append((workspace_id, path))
        return {
            "repository_id": "repo-1",
            "workspace_id": workspace_id,
            "revision": 8,
            "head_oid": "b" * 40,
            "worktree_root": path,
        }

    def submit_process(self, *, executable: str, args: list[str], **_kwargs):
        self.submitted.append((executable, tuple(args)))
        return {"session": {"session_id": f"session-{executable}"}}

    def wait_session(self, session_id: str, *, timeout: float):
        executable = session_id.removeprefix("session-")
        state, exit_code, truncated = self.outcomes[executable]
        return {
            "session_id": session_id,
            "state": state,
            "exit_code": exit_code,
            "output_truncated": truncated,
            "stdout_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        }

    def get_session_output(self, session_id: str):
        return {"session_id": session_id, "stdout": "help", "stderr": ""}


def importer(name: str):
    if name == doctor.AGENTOPS_MODULE:
        return SimpleNamespace(ApprovalState=ApprovalState, CodeOpsOperationPacket=Packet)
    if name == doctor.CODEOPS_INGEST_MODULE:
        return SimpleNamespace(ingest_sergeant_result_text=ingest)
    raise ImportError(name)


def versions(name: str) -> str:
    return {
        doctor.AGENTOPS_DISTRIBUTION: "0.3.0",
        doctor.CODEOPS_DISTRIBUTION: "0.3.0",
        doctor.SERGEANT_DISTRIBUTION: "0.4.1",
    }[name]


def test_doctor_has_no_python_subprocess_execution() -> None:
    source = inspect.getsource(doctor)
    assert "import subprocess" not in source
    assert "subprocess." not in source


def test_owner_contract_names_are_exact() -> None:
    assert doctor.AGENTOPS_MODULE == "hunter_agentops.code_ops_switcher_runner"
    assert doctor.AGENTOPS_DISTRIBUTION == "hunter-agentops"
    assert doctor.CODEOPS_INGEST_MODULE == "hunter_codeops.code_ops_sergeant_ingest"
    assert doctor.CODEOPS_DISTRIBUTION == "hunter-codeops"
    assert doctor.SERGEANT_DISTRIBUTION == "sergeant-reviewer"
    assert doctor.CODEOPS_EXECUTABLE == "hunter-codeops-switcher"
    assert doctor.SERGEANT_EXECUTABLE == "sergeant"


def test_all_compatible_never_becomes_proven() -> None:
    client = FakeClient()
    result = EngineeringMountDoctor(client, importer=importer, version_reader=versions).run("repo-1")
    assert result.repository_revision == 8
    assert result.repository_head_oid == "b" * 40
    assert client.inspections == [("11111111-1111-4111-8111-111111111111", "/repo")]
    assert result.overall_status == "compatible"
    assert result.live_engineering_proven is False
    assert result.blockers == ()
    assert [surface.status for surface in result.surfaces] == [
        "compatible",
        "compatible",
        "compatible",
        "compatible",
    ]
    assert client.submitted == [
        ("hunter-codeops-switcher", ("--help",)),
        ("sergeant", ("--help",)),
    ]


def test_missing_python_owner_keeps_overall_missing() -> None:
    def missing_agentops(name: str):
        if name == doctor.AGENTOPS_MODULE:
            raise ImportError("agentops missing")
        return importer(name)

    result = EngineeringMountDoctor(
        FakeClient(), importer=missing_agentops, version_reader=versions
    ).run("repo-1")
    assert result.overall_status == "missing"
    assert result.surfaces[0].status == "missing"
    assert result.blockers


def test_incompatible_agentops_packet_is_available_not_compatible() -> None:
    class BrokenPacket(Packet):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.workspace = "/wrong"

    def broken_importer(name: str):
        if name == doctor.AGENTOPS_MODULE:
            return SimpleNamespace(ApprovalState=ApprovalState, CodeOpsOperationPacket=BrokenPacket)
        return importer(name)

    result = EngineeringMountDoctor(
        FakeClient(), importer=broken_importer, version_reader=versions
    ).run("repo-1")
    assert result.surfaces[0].status == "available"
    assert result.overall_status == "available"


def test_codeops_ingest_semantic_change_is_available() -> None:
    def bad_ingest(_text: str):
        return SimpleNamespace(verdict="PASS", needs_loop=True, blocked=False)

    def bad_importer(name: str):
        if name == doctor.CODEOPS_INGEST_MODULE:
            return SimpleNamespace(ingest_sergeant_result_text=bad_ingest)
        return importer(name)

    result = EngineeringMountDoctor(
        FakeClient(), importer=bad_importer, version_reader=versions
    ).run("repo-1")
    codeops_python = next(surface for surface in result.surfaces if surface.surface == "codeops_python")
    assert codeops_python.status == "available"
    assert result.overall_status == "available"


def test_cli_interruption_is_missing_and_nonzero_is_available() -> None:
    client = FakeClient(
        {
            doctor.CODEOPS_EXECUTABLE: ("interrupted", None, False),
            doctor.SERGEANT_EXECUTABLE: ("failed", 2, False),
        }
    )
    result = EngineeringMountDoctor(client, importer=importer, version_reader=versions).run("repo-1")
    codeops_cli = next(surface for surface in result.surfaces if surface.surface == "codeops_cli")
    sergeant_cli = next(surface for surface in result.surfaces if surface.surface == "sergeant_cli")
    assert codeops_cli.status == "missing"
    assert sergeant_cli.status == "available"
    assert result.overall_status == "missing"


def test_cli_truncated_help_is_not_compatible() -> None:
    client = FakeClient(
        {
            doctor.CODEOPS_EXECUTABLE: ("completed", 0, True),
            doctor.SERGEANT_EXECUTABLE: ("completed", 0, False),
        }
    )
    result = EngineeringMountDoctor(client, importer=importer, version_reader=versions).run("repo-1")
    codeops_cli = next(surface for surface in result.surfaces if surface.surface == "codeops_cli")
    assert codeops_cli.status == "available"
    assert result.overall_status == "available"
