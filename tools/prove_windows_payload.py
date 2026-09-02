#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "origins.windows-payload.v1"
BUILDER_COMMIT = "05586d5163dd0f6fdbf25446a216e076945cfff1"


class WindowsProofError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_files(root: Path) -> dict[str, Path]:
    if not root.is_dir() or root.is_symlink():
        raise WindowsProofError(f"not a regular directory: {root}")
    result: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise WindowsProofError(f"symlink refused: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            normalized = PurePosixPath(relative)
            if normalized.is_absolute() or ".." in normalized.parts:
                raise WindowsProofError(f"path escaped payload: {relative}")
            result[relative] = path
        elif not path.is_dir():
            raise WindowsProofError(f"unsupported payload entry: {path}")
    return result


def load_manifest(project: Path) -> dict[str, object]:
    manifest_path = project / "dist" / "origins.windows-payload.json"
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WindowsProofError(f"manifest unavailable: {error}") from error
    if not isinstance(value, dict):
        raise WindowsProofError("manifest must be an object")
    return value


def prove_project(project: Path, *, expected_head: str | None = None) -> dict[str, object]:
    manifest = load_manifest(project)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise WindowsProofError("unexpected Windows payload schema")
    source = manifest.get("source")
    runtime = manifest.get("runtime")
    builder = manifest.get("builder")
    claims = manifest.get("claim_boundary")
    records = manifest.get("files")
    if not isinstance(source, dict) or source.get("repository") != "jaydumisuni/origins-factory" or source.get("clean") is not True:
        raise WindowsProofError("source binding is malformed")
    if expected_head is not None and source.get("commit") != expected_head:
        raise WindowsProofError(f"source commit mismatch: expected {expected_head}, got {source.get('commit')}")
    if not isinstance(runtime, dict) or runtime != {
        "launcher": "Origins Factory.exe",
        "daemon": "originsd.exe",
        "workspace": "workspace/index.html",
        "data_root": r"%LOCALAPPDATA%\THETECHGUY\Origins Factory",
        "loopback_only": True,
        "token_exposed_to_browser": False,
        "bootstrap": "one-time-fragment-nonce+httponly-loopback-session",
        "restart_persistence": True,
    }:
        raise WindowsProofError("installed runtime contract drift")
    if not isinstance(builder, dict) or builder.get("repository") != "jaydumisuni/thetechguy-software-builder" or builder.get("commit") != BUILDER_COMMIT or builder.get("payload_copy_must_match") is not True:
        raise WindowsProofError("Software Builder authority binding drift")
    expected_claims = {
        "builder_final_release_proven": False,
        "code_signed": False,
        "public_distribution_proven": False,
        "prime_installed": False,
        "ptah_integrated": False,
        "runtime_authority_expansion": False,
    }
    if claims != expected_claims:
        raise WindowsProofError("Windows candidate overclaims release/integration authority")
    if not isinstance(records, list) or not records:
        raise WindowsProofError("Windows payload file records missing")

    dist = project / "dist"
    actual = regular_files(dist)
    actual.pop("origins.windows-payload.json", None)
    declared: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise WindowsProofError("file record must be an object")
        path = record.get("path")
        if not isinstance(path, str) or path in declared:
            raise WindowsProofError("file record path missing or duplicated")
        declared[path] = record
    if set(declared) != set(actual):
        raise WindowsProofError(f"payload file-set mismatch: declared_only={sorted(set(declared)-set(actual))[:8]!r}, actual_only={sorted(set(actual)-set(declared))[:8]!r}")
    for relative, path in actual.items():
        record = declared[relative]
        if record.get("sha256") != sha256_file(path) or record.get("size_bytes") != path.stat().st_size:
            raise WindowsProofError(f"payload integrity mismatch: {relative}")

    launcher = actual.get("Origins Factory.exe")
    daemon = actual.get("originsd.exe")
    if launcher is None or daemon is None or launcher.stat().st_size <= 0:
        raise WindowsProofError("launcher/daemon executable pair missing")
    if sha256_file(launcher) != sha256_file(daemon):
        raise WindowsProofError("launcher and daemon must be the exact same dual-entrypoint binary")
    if "workspace/index.html" not in actual:
        raise WindowsProofError("installed Workspace index missing")
    wheels = [name for name in actual if name.startswith("python/") and name.endswith(".whl")]
    if len(wheels) != 1:
        raise WindowsProofError(f"expected exactly one Python wheel, got {wheels!r}")

    tech = json.loads((project / "techguy-build.json").read_text(encoding="utf-8"))
    project_manifest = json.loads((project / "thetechguy.project.json").read_text(encoding="utf-8"))
    if tech.get("appName") != "Origins Factory" or tech.get("appVersion") != manifest.get("product_version"):
        raise WindowsProofError("Builder project identity/version drift")
    if project_manifest.get("app_name") != "Origins Factory" or project_manifest.get("app_version") != manifest.get("product_version"):
        raise WindowsProofError("project manifest identity/version drift")
    return {"ok": True, "files": len(actual), "source_commit": source.get("commit"), "product_version": manifest.get("product_version")}


def prove_builder_copy(project: Path, report_path: Path) -> dict[str, object]:
    prove_project(project)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise WindowsProofError(f"Builder report unavailable: {error}") from error
    if report.get("app_name") != "Origins Factory":
        raise WindowsProofError("Builder packaged the wrong application")
    if report.get("signed") is not False or report.get("release_ready") is not False:
        raise WindowsProofError("Builder report invented signing/release readiness")
    payload = Path(str(report.get("payload_folder", "")))
    if not payload.is_dir():
        raise WindowsProofError(f"Builder payload folder unavailable: {payload}")
    source_files = regular_files(project / "dist")
    copied_files = regular_files(payload)
    if set(source_files) != set(copied_files):
        raise WindowsProofError("Builder payload copy changed the file set")
    for relative in source_files:
        if sha256_file(source_files[relative]) != sha256_file(copied_files[relative]):
            raise WindowsProofError(f"Builder payload copy changed bytes: {relative}")
    return {"ok": True, "payload_files": len(source_files), "setup_exe": report.get("setup_exe"), "signed": False, "release_ready": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--builder-report", type=Path)
    args = parser.parse_args()
    result = prove_project(args.project, expected_head=args.expected_head)
    if args.builder_report:
        result["builder"] = prove_builder_copy(args.project, args.builder_report)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
