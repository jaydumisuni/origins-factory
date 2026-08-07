from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum

import pytest

from origins_integration import engineering
from origins_integration.engineering import BridgeError, EngineeringAttemptRequest


def test_bridge_does_not_import_python_subprocess() -> None:
    source = inspect.getsource(engineering)
    assert "import subprocess" not in source
    assert "subprocess." not in source


def test_plan_and_config_paths_are_repository_relative() -> None:
    EngineeringAttemptRequest(operation_id="op-1", repository_id="repo-1", task="task")
    for unsafe in ("../plan.json", "/tmp/plan.json", "C:\\plan.json", "\\\\server\\plan.json"):
        with pytest.raises(BridgeError):
            EngineeringAttemptRequest(
                operation_id="op-1",
                repository_id="repo-1",
                task="task",
                plan=unsafe,
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
