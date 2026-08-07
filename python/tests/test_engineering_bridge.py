from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace

import pytest

from origins_integration import engineering
from origins_integration.engineering import BridgeError, EngineeringAttemptRequest, ExternalContracts


def test_bridge_does_not_import_python_subprocess() -> None:
    source = inspect.getsource(engineering)
    assert "import subprocess" not in source
    assert "subprocess." not in source


def test_plan_paths_remain_repository_relative() -> None:
    EngineeringAttemptRequest(operation_id="op-1", repository_id="repo-1", task="task")
    for unsafe in ("../plan.json", "/tmp/plan.json", "C:\\plan.json", "\\\\server\\plan.json"):
        with pytest.raises(BridgeError):
            EngineeringAttemptRequest(
                operation_id="op-1",
                repository_id="repo-1",
                task="task",
                plan=unsafe,
            )


def test_codeops_config_is_an_integration_reference_not_repository_artifact() -> None:
    for config in (
        "config/code_ops_switcher.example.json",
        "/opt/hunter/codeops/config.json",
        "C:\\Hunter\\CodeOps\\config.json",
        "../integration/codeops.json",
    ):
        request = EngineeringAttemptRequest(
            operation_id="op-1",
            repository_id="repo-1",
            task="task",
            config=config,
        )
        assert request.config == config

    for invalid in ("", "   ", "config/unsafe\x00value.json"):
        with pytest.raises(BridgeError):
            EngineeringAttemptRequest(
                operation_id="op-1",
                repository_id="repo-1",
                task="task",
                config=invalid,
            )


def test_review_actions_are_exact_and_non_promoting() -> None:
    assert engineering.REVIEW_ACTIONS == {
        "PASS": "complete_candidate",
        "NEEDS WORK": "correct",
        "BLOCK": "block",
        "UNKNOWN": "unresolved",
    }
    assert "PASS with caveat" not in engineering.REVIEW_ACTIONS
    assert "NEEDS_WORK" not in engineering.REVIEW_ACTIONS


def test_sergeant_command_must_match_codeops_contract() -> None:
    payload = {
        "command": [
            "sergeant",
            "app-review",
            "/repo",
            "--mode",
            "pull_request",
            "--files",
            "src/app.py,tests/test_app.py",
            "--pretty",
        ]
    }
    command = engineering._extract_sergeant_command(
        payload,
        workspace_root="/repo",
        files=("src/app.py", "tests/test_app.py"),
        review_mode="pull_request",
    )
    assert command[0] == "sergeant"

    payload["command"][0] = "bash"
    with pytest.raises(BridgeError):
        engineering._extract_sergeant_command(
            payload,
            workspace_root="/repo",
            files=("src/app.py", "tests/test_app.py"),
            review_mode="pull_request",
        )


def test_production_loader_targets_current_owning_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class ApprovalState:
        def __init__(self, value: str) -> None:
            self.value = value

    class CodeOpsOperationPacket:
        pass

    def ingest(text: str):
        return text

    modules = {
        "hunter_agentops.code_ops_switcher_runner": SimpleNamespace(
            ApprovalState=ApprovalState,
            CodeOpsOperationPacket=CodeOpsOperationPacket,
        ),
        "hunter_codeops.code_ops_sergeant_ingest": SimpleNamespace(
            ingest_sergeant_result_text=ingest,
        ),
    }

    def fake_import(name: str):
        calls.append(name)
        return modules[name]

    monkeypatch.setattr(engineering.importlib, "import_module", fake_import)
    loaded = ExternalContracts.load()
    assert isinstance(loaded, ExternalContracts)
    assert calls == [
        "hunter_agentops.code_ops_switcher_runner",
        "hunter_codeops.code_ops_sergeant_ingest",
    ]


class Verdict(Enum):
    PASS_ = "PASS"
    NEEDS_WORK = "NEEDS WORK"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


@dataclass
class IngestResult:
    verdict: Verdict
    needs_loop: bool
    blocked: bool
    summary: str


def test_external_ingest_shape_can_preserve_canonical_verdict_enum() -> None:
    result = IngestResult(Verdict.NEEDS_WORK, True, False, "correct it")
    assert engineering._enum_value(result.verdict) == "NEEDS WORK"
