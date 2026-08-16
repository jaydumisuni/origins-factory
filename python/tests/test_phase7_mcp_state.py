from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from origins_integration.phase7_mcp_state import Phase7McpState, Phase7McpStateError

D = "d" * 64


def result() -> dict[str, object]:
    return {
        "operation_id": "ext-phase7-0001",
        "repository_id": "repo-7",
        "review_sha256": "a" * 64,
        "verdict": "PASS",
        "evidence": {"plan_apply_session_id": "session-apply", "review_sha256": "a" * 64},
    }


def test_engineering_result_survives_restart_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "phase7.sqlite"
    first = Phase7McpState(path)
    stored = first.bind_engineering_result(
        "evolution-7",
        operation_id="ext-phase7-0001",
        repository_id="repo-7",
        subject_sha256=D,
        result=result(),
    )
    assert len(str(stored["result_sha256"])) == 64

    second = Phase7McpState(path)
    recovered = second.get_engineering_result("evolution-7")
    assert recovered is not None
    assert recovered["operation_id"] == "ext-phase7-0001"
    assert recovered["subject_sha256"] == D
    assert recovered["result"] == result()

    replay = second.bind_engineering_result(
        "evolution-7",
        operation_id="ext-phase7-0001",
        repository_id="repo-7",
        subject_sha256=D,
        result=result(),
    )
    assert replay["result_sha256"] == recovered["result_sha256"]


def test_engineering_result_cannot_be_replaced_with_different_evidence(tmp_path: Path) -> None:
    state = Phase7McpState(tmp_path / "phase7.sqlite")
    state.bind_engineering_result(
        "evolution-7",
        operation_id="ext-phase7-0001",
        repository_id="repo-7",
        subject_sha256=D,
        result=result(),
    )
    with pytest.raises(Phase7McpStateError, match="cannot be replaced"):
        state.bind_engineering_result(
            "evolution-7",
            operation_id="ext-phase7-0001",
            repository_id="repo-7",
            subject_sha256=D,
            result={**result(), "verdict": "BLOCK"},
        )


def test_engineering_result_digest_tamper_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "phase7.sqlite"
    state = Phase7McpState(path)
    state.bind_engineering_result(
        "evolution-7",
        operation_id="ext-phase7-0001",
        repository_id="repo-7",
        subject_sha256=D,
        result=result(),
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE phase7_engineering_results SET result_json=? WHERE evolution_id=?",
            ('{"verdict":"tampered"}', "evolution-7"),
        )
        db.commit()
    with pytest.raises(Phase7McpStateError, match="digest mismatch"):
        Phase7McpState(path).get_engineering_result("evolution-7")
