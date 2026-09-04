from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from v1_mission_contract import V1MissionError, repository_stable_projection


def assert_frozen_candidate_unchanged(
    candidate_record: Mapping[str, object], repository: Mapping[str, object], diff_text: str
) -> None:
    expected_repository = candidate_record.get("repository_stable")
    actual_repository = repository_stable_projection(repository)
    if expected_repository != actual_repository:
        raise V1MissionError(
            f"frozen candidate Git identity changed: expected={expected_repository} actual={actual_repository}"
        )
    actual_diff_sha = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    if actual_diff_sha != candidate_record.get("diff_sha256"):
        raise V1MissionError(
            f"frozen candidate diff changed: expected={candidate_record.get('diff_sha256')} actual={actual_diff_sha}"
        )


def review_frozen_candidate(
    *,
    client,
    bridge_type,
    request_type,
    operation_id: str,
    repository_id: str,
    config: Path,
    candidate_record: Mapping[str, object],
    candidate_artifact_ref: str,
    sessions: list[str],
):
    bridge = bridge_type(client)
    repository_stable = candidate_record.get("repository_stable")
    if not isinstance(repository_stable, Mapping):
        raise V1MissionError("candidate freeze omitted repository identity")
    task = (
        "Review immutable Origins v1 candidate "
        f"artifact={candidate_artifact_ref} freeze_sha256={candidate_record.get('sha256')} "
        f"diff_sha256={candidate_record.get('diff_sha256')} "
        f"repository_id={repository_id} head_oid={repository_stable.get('head_oid')} "
        f"status_sha256={repository_stable.get('status_sha256')}"
    )
    attempt = bridge.run_attempt(
        request_type(
            operation_id=operation_id,
            repository_id=repository_id,
            task=task,
            config=str(config),
            files=("capability.py", "tests/test_capability.py"),
            plan="",
            apply_plan=False,
            approval_state="approved",
            review="required",
            review_mode="pull_request",
        )
    )
    sessions.extend(
        [attempt.route.session_id, attempt.sergeant_command.session_id, attempt.sergeant_review.session_id]
    )
    if attempt.repository_id != repository_id:
        raise V1MissionError("Sergeant attempt changed Repository identity")
    if attempt.repository_head_oid != repository_stable.get("head_oid"):
        raise V1MissionError("Sergeant reviewed a different Repository HEAD than the frozen candidate")

    post_repository = client.refresh_repository(repository_id)
    post_diff = client.get_repository_diff(repository_id, kind="unstaged")
    if post_diff.get("truncated") is True:
        raise V1MissionError("post-review candidate diff is truncated")
    post_diff_text = str(post_diff.get("retained_text") or "")
    assert_frozen_candidate_unchanged(candidate_record, post_repository, post_diff_text)

    if attempt.verdict == "BLOCK":
        raise V1MissionError("Sergeant BLOCK verdict prevents v1 acceptance")
    if attempt.verdict == "NEEDS WORK":
        raise V1MissionError(
            "Sergeant returned NEEDS WORK; exact bounded correction is required before v1 acceptance"
        )
    if attempt.verdict != "PASS":
        raise V1MissionError(f"Sergeant returned unsupported final v1 verdict: {attempt.verdict}")
    return attempt, post_repository
