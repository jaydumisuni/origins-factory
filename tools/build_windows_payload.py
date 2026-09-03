#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "origins.windows-payload.v1"
REPOSITORY = "jaydumisuni/origins-factory"
BUILDER_REPOSITORY = "jaydumisuni/thetechguy-software-builder"
BUILDER_COMMIT = "05586d5163dd0f6fdbf25446a216e076945cfff1"
APP_NAME = "Origins Factory"


class WindowsPayloadError(RuntimeError):
    pass


def run(args: list[str], *, cwd: Path, timeout: int = 1200) -> str:
    result = subprocess.run(args, cwd=cwd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if result.returncode != 0:
        raise WindowsPayloadError(
            f"command failed ({result.returncode}): {args!r}\nstdout={result.stdout[-5000:]!r}\nstderr={result.stderr[-5000:]!r}"
        )
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise WindowsPayloadError(f"payload tree is not a regular directory: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise WindowsPayloadError(f"payload tree contains symlink: {path}")
        if not path.is_file() and not path.is_dir():
            raise WindowsPayloadError(f"payload tree contains unsupported entry: {path}")


def require_output_boundary(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    if output == root or output.is_relative_to(root):
        raise WindowsPayloadError("Windows staging output must be outside the source checkout")
    if output.exists() and any(output.iterdir()):
        raise WindowsPayloadError("Windows staging output directory must be empty")


def require_clean_git(root: Path) -> None:
    for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        if subprocess.run(args, cwd=root, check=False).returncode != 0:
            raise WindowsPayloadError("Windows candidate source has tracked changes")
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    if untracked:
        raise WindowsPayloadError(f"Windows candidate source has untracked files: {untracked.splitlines()[:8]!r}")


def git_head(root: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=root)


def component_version(root: Path) -> str:
    with (root / "rust" / "originsd" / "Cargo.toml").open("rb") as handle:
        rust = tomllib.load(handle)
    with (root / "python" / "pyproject.toml").open("rb") as handle:
        python = tomllib.load(handle)
    workspace = json.loads((root / "workspace" / "package.json").read_text(encoding="utf-8"))
    versions = {str(rust["package"]["version"]), str(python["project"]["version"]), str(workspace["version"])}
    if len(versions) != 1:
        raise WindowsPayloadError(f"component version drift: {sorted(versions)!r}")
    return versions.pop()


def copy_tracked_subtree(root: Path, prefix: str, destination: Path) -> None:
    listed = subprocess.run(["git", "ls-files", "-z", "--", prefix], cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if listed.returncode != 0:
        raise WindowsPayloadError(f"failed to enumerate tracked {prefix} files: {listed.stderr.decode(errors='replace')}")
    paths = [item.decode("utf-8") for item in listed.stdout.split(b"\0") if item]
    if not paths:
        raise WindowsPayloadError(f"tracked source subtree is empty: {prefix}")
    prefix_path = PurePosixPath(prefix)
    for relative_text in paths:
        relative = PurePosixPath(relative_text)
        child = relative.relative_to(prefix_path)
        source = root.joinpath(*relative.parts)
        if source.is_symlink() or not source.is_file():
            raise WindowsPayloadError(f"tracked Windows input is not a regular file: {relative_text}")
        target = destination.joinpath(*child.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def build_artifacts(root: Path, scratch: Path) -> tuple[Path, Path, Path]:
    if sys.platform != "win32":
        raise WindowsPayloadError("Windows v1 payload construction must execute on Windows")
    rust_target = scratch / "rust-target"
    run(["cargo", "build", "--release", "--locked", "-p", "originsd", "--target-dir", str(rust_target)], cwd=root / "rust")
    originsd = rust_target / "release" / "originsd.exe"
    if not originsd.is_file() or originsd.stat().st_size <= 0:
        raise WindowsPayloadError("originsd.exe was not produced")

    workspace_source = scratch / "workspace-source"
    copy_tracked_subtree(root, "workspace", workspace_source)
    run(["npm.cmd", "ci"], cwd=workspace_source)
    run([str(workspace_source / "node_modules" / ".bin" / "tsc.cmd"), "-b", "--pretty", "false"], cwd=workspace_source)
    workspace_dist = scratch / "workspace-dist"
    run([str(workspace_source / "node_modules" / ".bin" / "vite.cmd"), "build", "--outDir", str(workspace_dist), "--emptyOutDir"], cwd=workspace_source)
    if not (workspace_dist / "index.html").is_file():
        raise WindowsPayloadError("Workspace production build did not produce index.html")

    python_source = scratch / "python-source"
    copy_tracked_subtree(root, "python", python_source)
    wheel_dir = scratch / "wheel"
    wheel_dir.mkdir(parents=True)
    run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheel_dir)], cwd=python_source)
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise WindowsPayloadError(f"expected exactly one Python wheel, found {[path.name for path in wheels]!r}")
    require_regular_tree(workspace_dist)
    require_clean_git(root)
    return originsd, workspace_dist, wheels[0]


def copy_regular_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file() or source.stat().st_size <= 0:
        raise WindowsPayloadError(f"candidate input missing, symlinked or empty: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def copy_regular_tree(source: Path, destination: Path) -> None:
    require_regular_tree(source)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_regular_file(path, target)


def file_records(dist: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    manifest_name = "origins.windows-payload.json"
    for path in sorted(item for item in dist.rglob("*") if item.is_file()):
        relative = path.relative_to(dist).as_posix()
        if relative == manifest_name:
            continue
        normalized = PurePosixPath(relative)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise WindowsPayloadError(f"payload path escaped dist: {relative}")
        records.append({"path": relative, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    return records


def manifest(*, version: str, source_commit: str, files: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "product": "origins-factory",
        "product_version": version,
        "status": "candidate",
        "source": {"repository": REPOSITORY, "commit": source_commit, "clean": True},
        "target": {"os": "windows", "arch": "x86_64"},
        "runtime": {
            "launcher": f"{APP_NAME}.exe",
            "daemon": "originsd.exe",
            "workspace": "workspace/index.html",
            "data_root": r"%LOCALAPPDATA%\THETECHGUY\Origins Factory",
            "loopback_only": True,
            "token_exposed_to_browser": False,
            "bootstrap": "one-time-fragment-nonce+httponly-loopback-session",
            "restart_persistence": True,
        },
        "builder": {
            "repository": BUILDER_REPOSITORY,
            "commit": BUILDER_COMMIT,
            "packaging_owner": "THETECHGUY Software Builder",
            "payload_copy_must_match": True,
            "signing_owner": "THETECHGUY Software Builder",
        },
        "files": files,
        "claim_boundary": {
            "builder_final_release_proven": False,
            "code_signed": False,
            "public_distribution_proven": False,
            "prime_installed": False,
            "ptah_integrated": False,
            "runtime_authority_expansion": False,
        },
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def stage_project(*, output: Path, version: str, source_commit: str, originsd: Path, workspace_dist: Path, wheel: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    dist = output / "dist"
    dist.mkdir()
    copy_regular_file(originsd, dist / f"{APP_NAME}.exe")
    copy_regular_file(originsd, dist / "originsd.exe")
    copy_regular_tree(workspace_dist, dist / "workspace")
    copy_regular_file(wheel, dist / "python" / wheel.name)
    records = file_records(dist)
    if len(records) < 4:
        raise WindowsPayloadError("Windows payload is unexpectedly empty")
    write_json(dist / "origins.windows-payload.json", manifest(version=version, source_commit=source_commit, files=records))

    write_json(output / "techguy-build.json", {
        "appName": APP_NAME,
        "appVersion": version,
        "description": "Origins Factory — THETECHGUY Mission Operating Environment",
        "website": "https://thetechguyds.com",
        "installer": {
            "runAsAdmin": True,
            "desktopShortcutChecked": True,
            "startMenuShortcutChecked": True,
            "visitWebsiteChecked": False,
            "runAfterInstallChecked": True,
            "installBase": r"C:\Program Files\THETECHGUY Digital Solutions"
        },
        "dependencies": []
    })
    write_json(output / "thetechguy.project.json", {
        "schema_version": 1,
        "app_name": APP_NAME,
        "app_version": version,
        "publisher": "THETECHGUY DIGITAL SOLUTIONS",
        "installer": {"install_folder_windows": r"C:\Program Files\THETECHGUY Digital Solutions\Origins Factory"}
    })
    return dist / "origins.windows-payload.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    require_output_boundary(root, args.output)
    require_clean_git(root)
    head = git_head(root)
    if head != args.expected_head:
        raise WindowsPayloadError(f"exact-head mismatch: expected {args.expected_head}, got {head}")
    version = component_version(root)
    with tempfile.TemporaryDirectory(prefix="origins-windows-build-") as temporary:
        originsd, workspace_dist, wheel = build_artifacts(root, Path(temporary))
        manifest_path = stage_project(output=args.output, version=version, source_commit=head, originsd=originsd, workspace_dist=workspace_dist, wheel=wheel)
    require_clean_git(root)
    print(json.dumps({"ok": True, "schema_version": SCHEMA_VERSION, "project": str(args.output), "manifest": str(manifest_path), "source_commit": head}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
