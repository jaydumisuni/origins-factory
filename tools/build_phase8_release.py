#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA_VERSION = "origins.release.v1"
REPOSITORY = "jaydumisuni/origins-factory"
TARGET_OS = "linux"
TARGET_ARCH = "x86_64"
TARGET_LIBC = "gnu"
DEFAULT_BIND = "127.0.0.1:48700"
PYTHON_REQUIRES = ">=3.10"
PYTHON_DEPENDENCIES = ("websockets==16.1.1",)


class ReleaseError(RuntimeError):
    pass


def run(args: list[str], *, cwd: Path, timeout: int = 900) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"command failed ({result.returncode}): {args!r}\n"
            f"stdout={result.stdout[-4000:]!r}\nstderr={result.stderr[-4000:]!r}"
        )
    return result.stdout.strip()


def git_head(root: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=root)


def require_clean_git(root: Path) -> None:
    for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        result = subprocess.run(args, cwd=root, check=False)
        if result.returncode != 0:
            raise ReleaseError("release source has tracked changes")
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    if untracked:
        raise ReleaseError(f"release source has untracked files: {untracked.splitlines()[:8]!r}")


def require_output_boundary(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    if output == root or output.is_relative_to(root):
        raise ReleaseError("release output must be outside the source checkout")
    if output.exists() and any(output.iterdir()):
        raise ReleaseError("release output directory must be empty")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def component_versions(root: Path) -> dict[str, str]:
    with (root / "rust" / "originsd" / "Cargo.toml").open("rb") as handle:
        rust = tomllib.load(handle)
    with (root / "python" / "pyproject.toml").open("rb") as handle:
        python = tomllib.load(handle)
    workspace = json.loads((root / "workspace" / "package.json").read_text(encoding="utf-8"))
    versions = {
        "originsd": str(rust["package"]["version"]),
        "python": str(python["project"]["version"]),
        "workspace": str(workspace["version"]),
    }
    if len(set(versions.values())) != 1:
        raise ReleaseError(f"component version drift: {versions!r}")
    return versions


def python_runtime_contract(root: Path) -> dict[str, object]:
    with (root / "python" / "pyproject.toml").open("rb") as handle:
        python = tomllib.load(handle)
    project = python.get("project")
    if not isinstance(project, dict):
        raise ReleaseError("Python runtime metadata drift: project metadata is unavailable")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies")
    if (
        not isinstance(requires_python, str)
        or not isinstance(dependencies, list)
        or not all(isinstance(item, str) for item in dependencies)
    ):
        raise ReleaseError("Python runtime metadata drift: requires-python/dependencies are malformed")
    actual = {
        "python_requires": requires_python,
        "python_dependencies": list(dependencies),
    }
    expected = {
        "python_requires": PYTHON_REQUIRES,
        "python_dependencies": list(PYTHON_DEPENDENCIES),
    }
    if actual != expected:
        raise ReleaseError(f"Python runtime metadata drift: expected {expected!r}, got {actual!r}")
    return actual


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ReleaseError(f"required Python build distribution is unavailable: {name}") from exc


def host_glibc_version(root: Path) -> str:
    output = run(["ldd", "--version"], cwd=root)
    first = output.splitlines()[0].strip() if output else ""
    lowered = first.casefold()
    if "glibc" not in lowered and "gnu libc" not in lowered:
        raise ReleaseError(
            f"Phase 8A GNU release requires observable GNU glibc build provenance, got {first!r}"
        )
    match = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)*)\s*$", first)
    if match is None:
        raise ReleaseError(f"could not parse GNU glibc version from ldd output: {first!r}")
    return match.group(1)


def build_environment(root: Path) -> dict[str, str]:
    libc_version = host_glibc_version(root)
    return {
        "rustc": run(["rustc", "--version"], cwd=root),
        "cargo": run(["cargo", "--version"], cwd=root),
        "python": platform.python_version(),
        "pip": f"pip {_distribution_version('pip')}",
        "setuptools": f"setuptools {_distribution_version('setuptools')}",
        "node": run(["node", "--version"], cwd=root),
        "npm": run(["npm", "--version"], cwd=root),
        "glibc": f"glibc {libc_version}",
    }


def require_target() -> None:
    if sys.platform != "linux":
        raise ReleaseError("Phase 8A release candidate currently supports Linux only")
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise ReleaseError(f"Phase 8A release candidate requires x86_64, got {machine!r}")


def require_regular_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ReleaseError(f"release tree is not a regular directory: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReleaseError(f"release tree contains symlink: {path}")
        if not path.is_file() and not path.is_dir():
            raise ReleaseError(f"release tree contains unsupported entry: {path}")


def copy_tracked_subtree(root: Path, prefix: str, destination: Path) -> None:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", prefix],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if listed.returncode != 0:
        raise ReleaseError(f"failed to enumerate tracked {prefix} files: {listed.stderr.decode(errors='replace')}")
    paths = [item.decode("utf-8") for item in listed.stdout.split(b"\0") if item]
    if not paths:
        raise ReleaseError(f"tracked source subtree is empty: {prefix}")
    prefix_path = PurePosixPath(prefix)
    for relative_text in paths:
        relative = PurePosixPath(relative_text)
        try:
            child = relative.relative_to(prefix_path)
        except ValueError as exc:
            raise ReleaseError(f"tracked path escaped {prefix}: {relative_text}") from exc
        source = root.joinpath(*relative.parts)
        if source.is_symlink() or not source.is_file():
            raise ReleaseError(f"tracked release input is not a regular file: {relative_text}")
        target = destination.joinpath(*child.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    if info.isfile():
        executable = bool(info.mode & stat.S_IXUSR)
        info.mode = 0o755 if executable else 0o644
    elif info.isdir():
        info.mode = 0o755
    return info


def deterministic_tar_gz(source_dir: Path, destination: Path, *, arcname: str) -> None:
    require_regular_tree(source_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
                archive.add(source_dir, arcname=arcname, recursive=True, filter=_tar_filter)


def copy_file(source: Path, destination: Path, *, executable: bool = False) -> None:
    if source.is_symlink() or not source.is_file() or source.stat().st_size <= 0:
        raise ReleaseError(f"release artifact missing, symlinked or empty: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o755 if executable else 0o644)


def build_artifacts(root: Path, scratch: Path) -> tuple[Path, Path, Path]:
    rust_target = scratch / "rust-target"
    run(
        ["cargo", "build", "--release", "--locked", "-p", "originsd", "--target-dir", str(rust_target)],
        cwd=root / "rust",
    )
    originsd = rust_target / "release" / "originsd"

    python_source = scratch / "python-source"
    copy_tracked_subtree(root, "python", python_source)
    wheel_dir = scratch / "wheel"
    wheel_dir.mkdir(parents=True)
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=python_source,
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(f"expected exactly one Python wheel, found {[p.name for p in wheels]!r}")

    workspace_source = scratch / "workspace-source"
    copy_tracked_subtree(root, "workspace", workspace_source)
    run(["npm", "ci"], cwd=workspace_source)
    tsc = workspace_source / "node_modules" / ".bin" / "tsc"
    vite = workspace_source / "node_modules" / ".bin" / "vite"
    run([str(tsc), "-b", "--pretty", "false"], cwd=workspace_source)
    workspace_dist = scratch / "workspace-dist"
    run([str(vite), "build", "--outDir", str(workspace_dist), "--emptyOutDir"], cwd=workspace_source)
    if not (workspace_dist / "index.html").is_file():
        raise ReleaseError("Workspace production build did not produce index.html")
    require_regular_tree(workspace_dist)
    require_clean_git(root)
    return originsd, wheels[0], workspace_dist


def artifact_record(release_root: Path, path: Path, *, artifact_id: str, kind: str) -> dict[str, object]:
    relative = path.relative_to(release_root).as_posix()
    normalized = PurePosixPath(relative)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ReleaseError(f"artifact escaped release root: {relative}")
    return {
        "id": artifact_id,
        "kind": kind,
        "path": relative,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def create_manifest(
    *,
    version: str,
    source_commit: str,
    release_id: str,
    build_tools: dict[str, str],
    artifacts: list[dict[str, object]],
    python_runtime: dict[str, object],
) -> dict[str, object]:
    if not isinstance(python_runtime, dict):
        raise ReleaseError("Python runtime contract is malformed")
    python_requires = python_runtime.get("python_requires")
    python_dependencies = python_runtime.get("python_dependencies")
    if (
        set(python_runtime) != {"python_requires", "python_dependencies"}
        or not isinstance(python_requires, str)
        or not isinstance(python_dependencies, list)
        or not all(isinstance(item, str) for item in python_dependencies)
    ):
        raise ReleaseError("Python runtime contract is malformed")
    return {
        "schema_version": SCHEMA_VERSION,
        "product": "origins-factory",
        "product_version": version,
        "release_id": release_id,
        "status": "candidate",
        "source": {"repository": REPOSITORY, "commit": source_commit, "clean": True},
        "target": {"os": TARGET_OS, "arch": TARGET_ARCH, "libc": TARGET_LIBC},
        "build_environment": dict(build_tools),
        "artifacts": artifacts,
        "runtime": {
            "default_bind": DEFAULT_BIND,
            "loopback_only": True,
            "data_dir_external_to_release": True,
            "health": {
                "method": "GET",
                "path": "/v1/health",
                "auth_required": False,
                "expected": {"ok": True, "service": "originsd"},
            },
            "python_requires": python_requires,
            "python_dependencies": list(python_dependencies),
            "activation_owner": "consumer",
            "rollback_owner": "consumer",
        },
        "ownership": {
            "product": "Origins Factory",
            "final_packaging": "THETECHGUY Software Builder",
            "machine_consumer": "Prime OS component/package authority",
            "future_mechanical_substrate": "Ptah Space",
        },
        "claim_boundary": {
            "prime_component_format_claimed": False,
            "prime_installation_claimed": False,
            "builder_final_release_proven": False,
            "ptah_prime_native_proven": False,
            "production_release_accepted": False,
            "runtime_authority_expansion": False,
        },
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def assemble_release(
    *,
    output_dir: Path,
    source_commit: str,
    version: str,
    build_tools: dict[str, str],
    python_runtime: dict[str, object],
    originsd: Path,
    wheel: Path,
    workspace_dist: Path,
) -> tuple[Path, Path, Path]:
    release_id = f"origins-factory-{version}-linux-x86_64-{source_commit[:12]}"
    package_root = output_dir / release_id
    if package_root.exists():
        raise ReleaseError(f"release output already exists: {package_root}")
    package_root.mkdir(parents=True)

    originsd_out = package_root / "bin" / "originsd"
    wheel_out = package_root / "python" / wheel.name
    workspace_out = package_root / "workspace" / "workspace.tar.gz"
    copy_file(originsd, originsd_out, executable=True)
    copy_file(wheel, wheel_out)
    deterministic_tar_gz(workspace_dist, workspace_out, arcname="workspace")

    artifacts = [
        artifact_record(package_root, originsd_out, artifact_id="originsd", kind="native-binary"),
        artifact_record(package_root, wheel_out, artifact_id="python-plane", kind="python-wheel"),
        artifact_record(package_root, workspace_out, artifact_id="workspace", kind="static-web-bundle"),
    ]
    manifest = create_manifest(
        version=version,
        source_commit=source_commit,
        release_id=release_id,
        build_tools=build_tools,
        artifacts=artifacts,
        python_runtime=python_runtime,
    )
    manifest_path = package_root / "RELEASE_MANIFEST.json"
    write_json(manifest_path, manifest)

    archive_path = output_dir / f"{release_id}.tar.gz"
    deterministic_tar_gz(package_root, archive_path, arcname=release_id)
    checksum_path = output_dir / f"{release_id}.sha256"
    checksum_path.write_text(f"{sha256_file(archive_path)}  {archive_path.name}\n", encoding="utf-8")
    return package_root, archive_path, checksum_path


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Phase 8A Origins portable release candidate")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", default="")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    output = args.output.resolve()
    require_target()
    require_output_boundary(root, output)
    require_clean_git(root)
    source_commit = git_head(root)
    if args.expected_head and source_commit != args.expected_head:
        raise ReleaseError(f"source head mismatch: expected {args.expected_head}, got {source_commit}")
    versions = component_versions(root)
    python_runtime = python_runtime_contract(root)
    version = versions["originsd"]
    build_tools = build_environment(root)
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="origins-phase8-release-") as scratch_text:
        scratch = Path(scratch_text)
        originsd, wheel, workspace_dist = build_artifacts(root, scratch)
        package_root, archive_path, checksum_path = assemble_release(
            output_dir=output,
            source_commit=source_commit,
            version=version,
            build_tools=build_tools,
            python_runtime=python_runtime,
            originsd=originsd,
            wheel=wheel,
            workspace_dist=workspace_dist,
        )

    result = {
        "proof": "PHASE8_PORTABLE_RELEASE_CANDIDATE_OK",
        "source_head": source_commit,
        "component_versions": versions,
        "build_environment": build_tools,
        "release_root": str(package_root),
        "archive": str(archive_path),
        "archive_sha256": sha256_file(archive_path),
        "checksum": str(checksum_path),
        "status": "candidate",
        "prime_installation_claimed": False,
        "builder_final_release_proven": False,
        "ptah_prime_native_proven": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseError as exc:
        print(f"phase8 release failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
