from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = load("build_windows_payload", ROOT / "tools" / "build_windows_payload.py")
prove = load("prove_windows_payload", ROOT / "tools" / "prove_windows_payload.py")
SCHEMA = json.loads((ROOT / "release" / "origins.windows-payload.schema.json").read_text(encoding="utf-8"))
HEAD = "a" * 40


def fake_inputs(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    binary = tmp_path / "originsd.exe"
    binary.write_bytes(b"MZ" + b"origins-dual-entrypoint" * 50)
    workspace = tmp_path / "workspace"
    (workspace / "assets").mkdir(parents=True)
    (workspace / "index.html").write_text("<html><body>Origins</body></html>", encoding="utf-8")
    (workspace / "assets" / "app.js").write_text("console.log('origins')", encoding="utf-8")
    wheel = tmp_path / "origins_contracts-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    return binary, workspace, wheel


def stage(tmp_path: Path, name: str = "project") -> Path:
    binary, workspace, wheel = fake_inputs(tmp_path / f"inputs-{name}")
    project = tmp_path / name
    build.stage_project(output=project, version="0.1.0", source_commit=HEAD, originsd=binary, workspace_dist=workspace, wheel=wheel)
    return project


def test_candidate_schema_and_independent_proof(tmp_path: Path):
    project = stage(tmp_path)
    manifest = json.loads((project / "dist" / "origins.windows-payload.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(SCHEMA).validate(manifest)
    result = prove.prove_project(project, expected_head=HEAD)
    assert result["ok"] is True
    assert manifest["runtime"]["token_exposed_to_browser"] is False
    assert manifest["claim_boundary"]["code_signed"] is False


def test_staging_is_deterministic(tmp_path: Path):
    first = stage(tmp_path, "a")
    second = stage(tmp_path, "b")
    first_files = {p.relative_to(first).as_posix(): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    second_files = {p.relative_to(second).as_posix(): p.read_bytes() for p in second.rglob("*") if p.is_file()}
    assert first_files == second_files


def test_tampered_payload_is_rejected(tmp_path: Path):
    project = stage(tmp_path)
    (project / "dist" / "workspace" / "index.html").write_text("tampered", encoding="utf-8")
    with pytest.raises(prove.WindowsProofError, match="integrity mismatch"):
        prove.prove_project(project, expected_head=HEAD)


def test_symlink_payload_is_rejected(tmp_path: Path):
    project = stage(tmp_path)
    target = project / "dist" / "workspace" / "index.html"
    link = project / "dist" / "workspace" / "escape-link"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(prove.WindowsProofError, match="symlink refused"):
        prove.prove_project(project, expected_head=HEAD)


def builder_report(project: Path, tmp_path: Path, *, signed: bool = False, release_ready: bool = False) -> Path:
    payload = tmp_path / "builder-package" / "Payload" / "Origins Factory"
    shutil.copytree(project / "dist", payload)
    report = {
        "app_name": "Origins Factory",
        "payload_folder": str(payload),
        "setup_exe": str(tmp_path / "builder-package" / "Origins Factory Setup.exe"),
        "signed": signed,
        "release_ready": release_ready,
    }
    path = tmp_path / "builder-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_builder_copy_must_be_byte_exact(tmp_path: Path):
    project = stage(tmp_path)
    report = builder_report(project, tmp_path)
    assert prove.prove_builder_copy(project, report)["ok"] is True
    copied = tmp_path / "builder-package" / "Payload" / "Origins Factory" / "originsd.exe"
    copied.write_bytes(copied.read_bytes() + b"tamper")
    with pytest.raises(prove.WindowsProofError, match="changed bytes"):
        prove.prove_builder_copy(project, report)


def test_builder_cannot_invent_release_or_signing_claim(tmp_path: Path):
    project = stage(tmp_path)
    report = builder_report(project, tmp_path, signed=True, release_ready=True)
    with pytest.raises(prove.WindowsProofError, match="invented signing/release readiness"):
        prove.prove_builder_copy(project, report)


def test_dual_entrypoint_bytes_must_match(tmp_path: Path):
    project = stage(tmp_path)
    launcher = project / "dist" / "Origins Factory.exe"
    launcher.write_bytes(launcher.read_bytes() + b"different")
    manifest_path = project / "dist" / "origins.windows-payload.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest["files"]:
        if record["path"] == "Origins Factory.exe":
            record["sha256"] = prove.sha256_file(launcher)
            record["size_bytes"] = launcher.stat().st_size
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(prove.WindowsProofError, match="same dual-entrypoint binary"):
        prove.prove_project(project, expected_head=HEAD)


def test_external_state_contract_is_not_install_tree(tmp_path: Path):
    project = stage(tmp_path)
    manifest = json.loads((project / "dist" / "origins.windows-payload.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["data_root"].startswith("%LOCALAPPDATA%")
    assert "Program Files" not in manifest["runtime"]["data_root"]
    assert manifest["builder"]["packaging_owner"] == "THETECHGUY Software Builder"


def test_installed_bootstrap_requires_explicit_proxy_marker():
    bootstrap = (ROOT / "workspace" / "src" / "installedBootstrap.ts").read_text(encoding="utf-8")
    main = (ROOT / "workspace" / "src" / "main.tsx").read_text(encoding="utf-8")
    installed = (ROOT / "workspace" / "src" / "InstalledApp.tsx").read_text(encoding="utf-8")
    assert 'record.installed_proxy !== true' in bootstrap
    assert 'authenticated: responseOk && record.authenticated === true' in bootstrap
    assert 'session.installedProxy ? <InstalledApp sessionReady={session.authenticated} /> : <Phase7App />' in main
    assert 'Installed Origins is running, but this browser session is not authorized.' in installed


def test_installed_runtime_fails_closed_on_state_and_child_lifecycle():
    source = (ROOT / "rust" / "originsd" / "src" / "installed.rs").read_text(encoding="utf-8")
    assert '.env_remove("ORIGINS_INSTALLED_LAUNCHER")' in source
    assert '.kill_on_drop(true)' in source
    assert 'if let Err(error) = wait_for_health' in source
    assert 'if !daemon_matches_data_root(client, daemon_addr, &token).await' in source
    assert 'fs::canonicalize(data_dir)' in source
    assert 'data directory resolves inside the application payload' in source
