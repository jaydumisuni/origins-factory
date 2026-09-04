from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from v1_mission_support import _audit_sanitation_scope


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Proof"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "proof@example.invalid"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)


def test_artifact_owner_contract_accepts_origins_without_impersonating_lumi():
    support = (ROOT / "tools" / "v1_mission_support.py").read_text(encoding="utf-8")
    artifacts = (ROOT / "rust" / "originsd" / "src" / "artifacts.rs").read_text(encoding="utf-8")
    assert '"owner": "origins"' in support
    assert '"origins-v1-proof"' not in support
    assert 'matches!(owner.as_str(), "lumi" | "origins")' in artifacts
    assert 'normalize_owner("ORIGINS").unwrap(), "origins"' in artifacts
    assert 'normalize_owner("oracle").is_err()' in artifacts
    assert 'normalize_owner("origins-v1-proof").is_err()' in artifacts


def test_sanitation_audit_rejects_unknown_files_inside_retained_directories(tmp_path: Path):
    run_root = tmp_path / "run"
    repo = run_root / "workspaces" / "repository"
    _init_repo(repo)

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


def test_sanitation_audit_rejects_unregistered_and_tampered_artifact_objects(tmp_path: Path):
    run_root = tmp_path / "run"
    repo = run_root / "workspaces" / "repository"
    _init_repo(repo)

    origins = run_root / "origins-state"
    (origins / "origins.sqlite3").parent.mkdir(parents=True)
    (origins / "origins.sqlite3").write_bytes(b"db")
    (run_root / "agentops-state").mkdir(parents=True)
    (run_root / "promoted").mkdir(parents=True)

    content = b"registered artifact"
    digest = hashlib.sha256(content).hexdigest()
    registered = origins / "artifacts" / "objects" / digest[:2] / digest
    registered.parent.mkdir(parents=True)
    registered.write_bytes(content)
    projections = [{"artifact_id": "artifact-1", "content_sha256": digest}]

    assert _audit_sanitation_scope(
        run_root, repo, registered_artifacts=projections
    ) == []

    injected_content = b"injected object"
    injected_digest = hashlib.sha256(injected_content).hexdigest()
    injected = origins / "artifacts" / "objects" / injected_digest[:2] / injected_digest
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(injected_content)
    remaining = _audit_sanitation_scope(run_root, repo, registered_artifacts=projections)
    assert injected.relative_to(run_root).as_posix() in remaining
    injected.unlink()

    registered.write_bytes(b"tampered")
    remaining = _audit_sanitation_scope(run_root, repo, registered_artifacts=projections)
    assert registered.relative_to(run_root).as_posix() in remaining


def test_recovery_wires_registered_artifact_projections_into_sanitation():
    recovery = (ROOT / "tools" / "v1_mission_recovery.py").read_text(encoding="utf-8")
    assert "registered_artifacts=[candidate_artifact_projection]" in recovery.replace("\n", "").replace(" ", "")
    compact = recovery.replace("\n", "").replace(" ", "")
    assert "registered_artifacts=[candidate_artifact_projection,sanitation_projection,handover_projection,]" in compact
