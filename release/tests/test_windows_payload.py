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


def builder_report(
    project: Path,
    tmp_path: Path,
    *,
    signed: bool = False,
    release_ready: bool = False,
    payload_override: Path | None = None,
) -> Path:
    package = tmp_path / "builder-package"
    payload = package / "Payload" / "Origins Factory"
    package.mkdir(parents=True, exist_ok=True)
    if payload_override is None:
        shutil.copytree(project / "dist", payload)
    else:
        payload = payload_override
    setup = package / "Origins Factory Setup.exe"
    setup.write_bytes(b"MZ" + b"builder-setup" * 100)
    report = {
        "project_path": str(project),
        "app_name": "Origins Factory",
        "package_folder": str(package),
        "payload_folder": str(payload),
        "payload_file_count": len(prove.regular_files(payload)),
        "setup_exe": str(setup),
        "setup_exe_sha256": prove.sha256_file(setup),
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


def test_builder_authority_contract_is_exact(tmp_path: Path):
    project = stage(tmp_path)
    manifest_path = project / "dist" / "origins.windows-payload.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["builder"]["packaging_owner"] = "different owner"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(prove.WindowsProofError, match="authority binding drift"):
        prove.prove_project(project, expected_head=HEAD)


def test_builder_payload_must_be_independent_copy(tmp_path: Path):
    project = stage(tmp_path)
    report = builder_report(project, tmp_path, payload_override=project / "dist")
    with pytest.raises(prove.WindowsProofError, match="independent copy"):
        prove.prove_builder_copy(project, report)


def test_builder_setup_exe_hash_must_match_report(tmp_path: Path):
    project = stage(tmp_path)
    report = builder_report(project, tmp_path)
    data = json.loads(report.read_text(encoding="utf-8"))
    setup = Path(data["setup_exe"])
    setup.write_bytes(setup.read_bytes() + b"tamper")
    with pytest.raises(prove.WindowsProofError, match="Setup EXE hash"):
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
    assert manifest["builder"] == prove.EXPECTED_BUILDER


def test_windows_builder_uses_cmd_shim_for_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "root"
    (root / "rust").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path, timeout: int = 1200) -> str:
        calls.append(list(args))
        if args and args[0] == "cargo":
            target = Path(args[args.index("--target-dir") + 1])
            binary = target / "release" / "originsd.exe"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"MZ")
        elif args and str(args[0]).endswith("vite.cmd"):
            workspace_dist = scratch / "workspace-dist"
            workspace_dist.mkdir(parents=True, exist_ok=True)
            (workspace_dist / "index.html").write_text("<html></html>", encoding="utf-8")
        elif len(args) >= 4 and args[0] == sys.executable and args[1:4] == ["-m", "pip", "wheel"]:
            wheel_dir = Path(args[args.index("--wheel-dir") + 1])
            (wheel_dir / "origins_contracts-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
        return ""

    monkeypatch.setattr(build.sys, "platform", "win32")
    monkeypatch.setattr(build, "run", fake_run)
    monkeypatch.setattr(build, "copy_tracked_subtree", lambda *args, **kwargs: None)
    monkeypatch.setattr(build, "require_clean_git", lambda *args, **kwargs: None)

    build.build_artifacts(root, scratch)

    assert ["npm.cmd", "ci"] in calls
    assert ["npm", "ci"] not in calls


def test_windows_probe_waits_for_gui_process_and_requires_pass_marker():
    workflow = (ROOT / ".github" / "workflows" / "windows-v1-distribution.yml").read_text(encoding="utf-8")
    assert 'Start-Process -FilePath $launcher -ArgumentList "--probe" -Wait -PassThru' in workflow
    assert '$probe.ExitCode -ne 0' in workflow
    assert "ORIGINS_WINDOWS_INSTALLED_PROBE=PASS" in workflow
    assert "Select-String -LiteralPath $stdout" in workflow
    assert "& $launcher --probe" not in workflow
