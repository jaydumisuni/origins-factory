from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import v1_mission_contract as m
from v1_mission_support import _assert_clean, _audit_sanitation_scope
from v1_mission_candidate_review import assert_frozen_candidate_unchanged


def capabilities():
    return [
        {"capability_id": "origins.workspace.persistence", "version": "1.0.0", "owner": "origins", "effects": ["observe"], "model_dependency": "none"},
        {"capability_id": "origins.journal.verify", "version": "1.0.0", "owner": "origins", "effects": ["verify"], "model_dependency": "none"},
        {"capability_id": "origins.process.run", "version": "1.0.0", "owner": "origins", "effects": ["execute"], "model_dependency": "none"},
    ]


def repository_projection(*, revision: int = 5, status: str = "s" * 64):
    return {
        "repository_id": "repo-1",
        "workspace_id": "ws-1",
        "revision": revision,
        "worktree_root": "/tmp/repo",
        "git_dir": "/tmp/repo/.git",
        "common_dir": "/tmp/repo/.git",
        "head_oid": "a" * 40,
        "head_ref": "refs/heads/main",
        "branch": "main",
        "detached": False,
        "unborn": False,
        "staged_count": 0,
        "unstaged_count": 2,
        "untracked_count": 1,
        "status_sha256": status,
    }


def test_acceptance_surface_is_exact_16_steps_and_ends_with_handover():
    assert len(m.ACCEPTANCE_STEPS) == 16
    assert m.ACCEPTANCE_STEPS[0] == "workspace_recovered"
    assert m.ACCEPTANCE_STEPS[-1] == "sanitation_and_handover_produced"


def test_loadout_requires_standalone_core_and_two_providers():
    result = m.compile_minimal_loadout(capabilities(), ("provider-a", "provider-b"))
    assert result["runtime_authority_expansion"] is False
    assert result["codeops_provider_ids"] == ["provider-a", "provider-b"]
    with pytest.raises(m.V1MissionError, match="required standalone capabilities"):
        m.compile_minimal_loadout(capabilities()[:-1], ("provider-a", "provider-b"))


def test_candidate_freeze_refuses_empty_diff_and_retains_content():
    with pytest.raises(m.V1MissionError, match="non-empty repository diff"):
        m.build_candidate_record(
            mission_id="m", operation_id="o", repository=repository_projection(), diff_text="", sessions=["s"]
        )
    record = m.build_candidate_record(
        mission_id="m",
        operation_id="o",
        repository=repository_projection(),
        diff_text="diff --git a/a b/a\n+x\n",
        sessions=["s"],
    )
    assert record["diff_text"].startswith("diff --git")
    assert record["repository_stable"]["status_sha256"] == "s" * 64


def test_candidate_review_binding_rejects_mutated_diff_or_git_identity():
    record = m.build_candidate_record(
        mission_id="m", operation_id="o", repository=repository_projection(), diff_text="diff-A", sessions=["s"]
    )
    assert_frozen_candidate_unchanged(record, repository_projection(revision=99), "diff-A")
    with pytest.raises(m.V1MissionError, match="diff changed"):
        assert_frozen_candidate_unchanged(record, repository_projection(revision=100), "diff-B")
    with pytest.raises(m.V1MissionError, match="Git identity changed"):
        assert_frozen_candidate_unchanged(record, repository_projection(revision=100, status="x" * 64), "diff-A")


def test_handover_resume_claims_are_evidence_driven():
    handover = m.build_handover(
        mission_id="m",
        operation={"operation_id": "op", "operation_ref": "agentops:op"},
        workspace_id="w",
        repository=repository_projection(),
        hunter={"session_id": "hs"},
        capability_loadout={"sha256": "c" * 64},
        sessions=["s2", "s1"],
        artifact_refs=["a"],
        sanitation_ref="san",
        authority={"origins": "x" * 40},
        recovery={"repository": True, "sessions": False, "workspace": True, "operation": True},
    )
    assert handover["resume"]["exact_repository_identity_recovered"] is True
    assert handover["resume"]["exact_session_identity_recovered"] is False
    assert handover["resume"]["exact_workspace_identity_recovered"] is True
    assert handover["resume"]["exact_operation_identity_recovered"] is True


def test_assert_clean_rejects_untracked_owner_code(tmp_path: Path):
    repo = tmp_path / "owner"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Proof"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "proof@example.invalid"], cwd=repo, check=True)
    (repo / "tracked.py").write_text("VALUE=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    _assert_clean("Owner", repo)
    (repo / "rogue.py").write_text("VALUE=2\n", encoding="utf-8")
    with pytest.raises(m.V1MissionError, match="untracked"):
        _assert_clean("Owner", repo)


def test_sanitation_audit_rejects_unknown_run_root_file(tmp_path: Path):
    run_root = tmp_path / "run"
    repo = run_root / "workspaces" / "repository"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Proof"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "proof@example.invalid"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    for name in ("origins-state", "agentops-state", "promoted"):
        (run_root / name).mkdir(parents=True, exist_ok=True)
    assert _audit_sanitation_scope(run_root, repo) == []
    (run_root / "mystery.tmp").write_text("x", encoding="utf-8")
    assert "mystery.tmp" in _audit_sanitation_scope(run_root, repo)


def test_static_source_locks_freeze_review_recovery_and_hunter_boundary():
    launcher = (ROOT / "tools" / "prove_v1_repository_mission.py").read_text(encoding="utf-8")
    candidate = (ROOT / "tools" / "v1_mission_candidate.py").read_text(encoding="utf-8")
    review = (ROOT / "tools" / "v1_mission_candidate_review.py").read_text(encoding="utf-8")
    recovery = (ROOT / "tools" / "v1_mission_recovery.py").read_text(encoding="utf-8")
    support = (ROOT / "tools" / "v1_mission_support.py").read_text(encoding="utf-8")
    source = "\n".join((launcher, candidate, review, recovery, support))
    assert 'final v1 Mission requires live production Hunter URL/token' in launcher
    assert 'executable="git"' not in source
    assert 'candidate_artifact_ref' in review
    assert 'assert_frozen_candidate_unchanged' in review
    assert 'pre_restart_sessions' in candidate
    assert 'exact_session_identity_recovered' in recovery
    assert 'git status --porcelain' not in support  # subprocess argv form only, never shell
    assert '"--untracked-files=all"' in support
    assert 'os.environ.pop("ORIGINS_HUNTER_URL", None)' in launcher
    assert 'hunter_status.get("configured") is not False' in recovery



def test_provider_selection_requires_two_enabled_distinct_routes():
    assert m.require_two_enabled_providers({"providers": [{"id": "a", "enabled": True}, {"id": "b", "enabled": True}]}) == ("a", "b")
    with pytest.raises(m.V1MissionError, match="at least two enabled"):
        m.require_two_enabled_providers({"providers": [{"id": "a", "enabled": True}, {"id": "b", "enabled": False}]})


def test_live_launcher_binds_exact_binary_and_tracked_owner_modules():
    launcher = (ROOT / "tools" / "prove_v1_repository_mission.py").read_text(encoding="utf-8")
    assert '"ORIGINS_PHASE7_DAEMON": str(daemon_binary)' in launcher
    assert 'if not daemon_binary.is_file()' in launcher
    assert '_module_authority_record(' in launcher
    assert '_tracked_file_record("CodeOps provider config"' in launcher
    assert '"sha256": file_sha256(daemon_binary)' in launcher


def test_artifact_owner_contract_accepts_origins_without_impersonating_lumi():
    support = (ROOT / "tools" / "v1_mission_support.py").read_text(encoding="utf-8")
    artifacts = (ROOT / "rust" / "originsd" / "src" / "artifacts.rs").read_text(encoding="utf-8")
    assert '"owner": "origins"' in support
    assert '"origins-v1-proof"' not in support
    assert 'matches!(owner.as_str(), "lumi" | "origins")' in artifacts
    assert 'normalize_owner("ORIGINS").unwrap(), "origins"' in artifacts
    assert 'normalize_owner("oracle").is_err()' in artifacts


def test_sanitation_audit_rejects_unknown_files_inside_retained_directories(tmp_path: Path):
    run_root = tmp_path / "run"
    repo = run_root / "workspaces" / "repository"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Proof"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "proof@example.invalid"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)

    origins = run_root / "origins-state"
    agentops = run_root / "agentops-state"
    promoted = run_root / "promoted"
    origins.mkdir(parents=True)
    agentops.mkdir(parents=True)
    promoted.mkdir(parents=True)
    (origins / "origins.sqlite3").write_bytes(b"db")
    (origins / "origins.sqlite3-wal").write_bytes(b"wal")
    (origins / "origins.sqlite3-shm").write_bytes(b"shm")
    artifact_bytes = b"artifact"
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    obj = origins / "artifacts" / "objects" / digest[:2] / digest
    obj.parent.mkdir(parents=True)
    obj.write_bytes(artifact_bytes)
    registered_artifacts = [{"content_sha256": digest}]
    (agentops / "operations.json").write_text("[]\n", encoding="utf-8")
    (agentops / ".operations.json.lock").write_bytes(b"")
    candidate = promoted / "candidate-freeze.json"
    candidate.write_text("{}\n", encoding="utf-8")

    assert _audit_sanitation_scope(
        run_root, repo, promoted_files=[candidate], registered_artifacts=registered_artifacts
    ) == []

    probes = [
        origins / "debug.tmp",
        agentops / "debug.tmp",
        promoted / "scratch.txt",
        origins / "artifacts" / "objects" / "tmp" / "leak.partial",
    ]
    for probe in probes:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("x", encoding="utf-8")
        remaining = _audit_sanitation_scope(
            run_root, repo, promoted_files=[candidate], registered_artifacts=registered_artifacts
        )
        assert probe.relative_to(run_root).as_posix() in remaining
        probe.unlink()

def test_nonclaims_remain_outside_standalone_v1():
    handover = m.build_handover(
        mission_id="m", operation={"operation_id": "op"}, workspace_id="w", repository=repository_projection(),
        hunter={}, capability_loadout={"sha256": "c" * 64}, sessions=[], artifact_refs=[], sanitation_ref="san",
        authority={"origins": "x" * 40}, recovery={"repository": True, "sessions": True, "workspace": True, "operation": True},
    )
    assert handover["nonclaims"] == {
        "prime_installed": False,
        "ptah_integrated": False,
        "device_write_execution": False,
        "public_distribution": False,
        "code_signed": False,
    }
