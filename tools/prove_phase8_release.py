#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


class ProofError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ProofError(f"release tree is not a regular directory: {root}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            raise ProofError(f"release tree contains symlink: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + f"{mode:o}".encode("ascii") + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + f"{mode:o}".encode("ascii") + b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        else:
            raise ProofError(f"release tree contains unsupported entry: {path}")
    return digest.hexdigest()


def safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    if not members:
        raise ProofError("release archive is empty")
    seen: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        normalized = path.as_posix()
        if not path.parts or normalized in {"", "."}:
            raise ProofError("release archive contains an empty member path")
        if path.is_absolute() or ".." in path.parts:
            raise ProofError(f"release archive contains unsafe path: {member.name}")
        if normalized in seen:
            raise ProofError(f"release archive contains duplicate path: {normalized}")
        seen.add(normalized)
        if member.issym() or member.islnk():
            raise ProofError(f"release archive contains a link: {member.name}")
        if not member.isfile() and not member.isdir():
            raise ProofError(f"release archive contains unsupported entry: {member.name}")
    return members


def extract_archive(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = safe_members(archive)
        top = {PurePosixPath(member.name).parts[0] for member in members}
        if len(top) != 1:
            raise ProofError(f"release archive must contain exactly one top-level release root: {sorted(top)!r}")
        archive.extractall(destination, members=members, filter="data")
    release_root = destination / next(iter(top))
    if not release_root.is_dir():
        raise ProofError("release root was not extracted")
    return release_root


def verify_checksum(archive: Path, checksum: Path) -> str:
    text = checksum.read_text(encoding="utf-8").strip()
    parts = text.split()
    if len(parts) != 2 or parts[1] != archive.name or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
        raise ProofError("release checksum sidecar is malformed or names another archive")
    actual = sha256_file(archive)
    if parts[0] != actual:
        raise ProofError("release archive SHA-256 does not match sidecar")
    return actual


def verify_manifest(release_root: Path, *, expected_head: str) -> dict[str, object]:
    manifest_path = release_root / "RELEASE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProofError("release manifest is unavailable or invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ProofError("release manifest must be an object")
    expected_top = {
        "schema_version",
        "product",
        "product_version",
        "release_id",
        "status",
        "source",
        "target",
        "build_environment",
        "artifacts",
        "runtime",
        "ownership",
        "claim_boundary",
    }
    if set(manifest) != expected_top:
        raise ProofError("release manifest top-level contract changed")
    if manifest.get("schema_version") != "origins.release.v1":
        raise ProofError("release manifest schema changed")
    if manifest.get("product") != "origins-factory" or manifest.get("status") != "candidate":
        raise ProofError("release candidate identity/status changed")
    version = manifest.get("product_version")
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ProofError("release product version is invalid")
    expected_release_id = f"origins-factory-{version}-linux-x86_64-{expected_head[:12]}"
    if manifest.get("release_id") != expected_release_id or release_root.name != expected_release_id:
        raise ProofError("release archive root/release_id is not bound to version and source head")
    source = manifest.get("source")
    if source != {"repository": "jaydumisuni/origins-factory", "commit": expected_head, "clean": True}:
        raise ProofError("release source provenance changed")
    if manifest.get("target") != {"os": "linux", "arch": "x86_64", "libc": "gnu"}:
        raise ProofError("release target changed")
    build = manifest.get("build_environment")
    expected_build_keys = {"rustc", "cargo", "python", "pip", "setuptools", "node", "npm", "glibc"}
    if not isinstance(build, dict) or set(build) != expected_build_keys:
        raise ProofError("release build provenance is incomplete")
    if not all(isinstance(value, str) and value.strip() for value in build.values()):
        raise ProofError("release build provenance contains empty values")
    if not str(build["glibc"]).startswith("glibc "):
        raise ProofError("release GNU libc provenance is malformed")
    runtime = manifest.get("runtime")
    expected_runtime = {
        "default_bind": "127.0.0.1:48700",
        "loopback_only": True,
        "data_dir_external_to_release": True,
        "health": {
            "method": "GET",
            "path": "/v1/health",
            "auth_required": False,
            "expected": {"ok": True, "service": "originsd"},
        },
        "python_requires": ">=3.10",
        "python_dependencies": ["websockets==16.1.1"],
        "activation_owner": "consumer",
        "rollback_owner": "consumer",
    }
    if runtime != expected_runtime:
        raise ProofError("release runtime contract changed")
    expected_claims = {
        "prime_component_format_claimed",
        "prime_installation_claimed",
        "builder_final_release_proven",
        "ptah_prime_native_proven",
        "production_release_accepted",
        "runtime_authority_expansion",
    }
    claims = manifest.get("claim_boundary")
    if (
        not isinstance(claims, dict)
        or set(claims) != expected_claims
        or any(value is not False for value in claims.values())
    ):
        raise ProofError("release candidate widened an explicitly false claim")
    ownership = manifest.get("ownership")
    if ownership != {
        "product": "Origins Factory",
        "final_packaging": "THETECHGUY Software Builder",
        "machine_consumer": "Prime OS component/package authority",
        "future_mechanical_substrate": "Ptah Space",
    }:
        raise ProofError("release ownership boundary changed")
    return manifest


def verify_artifacts(release_root: Path, manifest: dict[str, object]) -> dict[str, Path]:
    raw = manifest.get("artifacts")
    if not isinstance(raw, list):
        raise ProofError("release artifacts are missing")
    artifacts: dict[str, Path] = {}
    expected_kinds = {
        "originsd": "native-binary",
        "python-plane": "python-wheel",
        "workspace": "static-web-bundle",
    }
    expected_fields = {"id", "kind", "path", "sha256", "size_bytes"}
    for item in raw:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise ProofError("release artifact entry is malformed")
        artifact_id = item.get("id")
        relative_text = item.get("path")
        if artifact_id not in expected_kinds or item.get("kind") != expected_kinds[artifact_id]:
            raise ProofError("release artifact identity/kind changed")
        if artifact_id in artifacts or not isinstance(relative_text, str):
            raise ProofError("release artifact is duplicate or pathless")
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ProofError("release artifact path escaped release root")
        artifact = release_root.joinpath(*relative.parts)
        if artifact.is_symlink() or not artifact.is_file():
            raise ProofError(f"release artifact is unavailable: {artifact_id}")
        if item.get("sha256") != sha256_file(artifact) or item.get("size_bytes") != artifact.stat().st_size:
            raise ProofError(f"release artifact digest/size changed: {artifact_id}")
        artifacts[str(artifact_id)] = artifact
    if set(artifacts) != set(expected_kinds):
        raise ProofError("release artifact set is incomplete")
    return artifacts


def verify_python_wheel(wheel: Path, *, version: str) -> None:
    try:
        with zipfile.ZipFile(wheel) as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ProofError("Python wheel contains duplicate paths")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ProofError("Python wheel contains unsafe path")
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ProofError("Python wheel contains a symlink")
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise ProofError("Python wheel has invalid metadata layout")
            metadata = package.read(metadata_names[0]).decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise ProofError("Python artifact is not a valid wheel") from exc
    if "Name: origins-contracts\n" not in metadata or f"Version: {version}\n" not in metadata:
        raise ProofError("Python wheel name/version does not match release manifest")


def verify_workspace_bundle(bundle: Path, destination: Path) -> None:
    with tarfile.open(bundle, "r:gz") as archive:
        members = safe_members(archive)
        top = {PurePosixPath(member.name).parts[0] for member in members}
        if top != {"workspace"}:
            raise ProofError("Workspace bundle has an unexpected top-level layout")
        archive.extractall(destination, members=members, filter="data")
    index = destination / "workspace" / "index.html"
    if not index.is_file():
        raise ProofError("Workspace bundle does not contain production index.html")
    for path in destination.rglob("*"):
        if path.name == "node_modules" or path.suffix in {".tsx", ".ts"}:
            raise ProofError("Workspace bundle contains build/source material")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int, process: subprocess.Popen[bytes], *, timeout: float = 12.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProofError(f"released originsd exited before health: {process.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("ok") is True and payload.get("service") == "originsd":
                return payload
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(0.05)
    raise ProofError(f"released originsd did not become healthy: {last}")


def file_tail(path: Path, *, max_bytes: int = 2000) -> str:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        return handle.read(max_bytes).decode("utf-8", errors="replace")


def runtime_smoke(binary: Path, release_root: Path, consumer_root: Path) -> dict[str, object]:
    data_dir = consumer_root / "data"
    workspace_root = consumer_root / "workspaces"
    artifact_root = consumer_root / "artifact-inputs"
    log_root = consumer_root / "runtime-logs"
    for path in (data_dir, workspace_root, artifact_root, log_root):
        path.mkdir(parents=True, exist_ok=True)
    if data_dir.is_relative_to(release_root):
        raise ProofError("runtime data directory is inside the immutable release root")

    release_before = tree_digest(release_root)
    first_health: dict[str, object] | None = None
    second_health: dict[str, object] | None = None
    for attempt in range(2):
        port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "ORIGINS_BIND": f"127.0.0.1:{port}",
                "ORIGINS_DATA_DIR": str(data_dir),
                "ORIGINS_WORKSPACE_ROOTS": str(workspace_root),
                "ORIGINS_ARTIFACT_ROOTS": str(artifact_root),
            }
        )
        stdout_path = log_root / f"originsd-{attempt + 1}.stdout.log"
        stderr_path = log_root / f"originsd-{attempt + 1}.stderr.log"
        health: dict[str, object] | None = None
        health_error: ProofError | None = None
        shutdown_error: str | None = None
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                [str(binary)],
                cwd=consumer_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            try:
                health = wait_health(port, process)
            except ProofError as exc:
                health_error = exc
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            shutdown_error = "released originsd did not stop after kill"
                        else:
                            shutdown_error = "released originsd did not shut down cleanly"
        stderr_tail = file_tail(stderr_path)
        if health_error is not None:
            raise ProofError(f"{health_error}; stderr_tail={stderr_tail!r}") from health_error
        if shutdown_error is not None:
            raise ProofError(f"{shutdown_error}; stderr_tail={stderr_tail!r}")
        if process.returncode != 0:
            raise ProofError(
                f"released originsd shutdown returned {process.returncode}; stderr_tail={stderr_tail!r}"
            )
        if health is None:
            raise ProofError("runtime health proof returned no payload")
        if attempt == 0:
            first_health = health
        else:
            second_health = health
    if first_health is None or second_health is None:
        raise ProofError("runtime health proof did not complete twice")
    database = data_dir / "origins.sqlite3"
    token = data_dir / "local-token.txt"
    if not database.is_file() or database.stat().st_size <= 0:
        raise ProofError("released originsd did not persist its external database")
    if not token.is_file() or token.stat().st_size <= 0:
        raise ProofError("released originsd did not persist its external local token")
    journal = second_health.get("journal")
    if not isinstance(journal, dict) or journal.get("ok") is not True:
        raise ProofError("released originsd journal is not valid after restart")
    release_after = tree_digest(release_root)
    if release_after != release_before:
        raise ProofError("released originsd mutated immutable release bytes during runtime proof")
    return {
        "restart_health": True,
        "database_external": True,
        "local_token_external": True,
        "journal_ok": True,
        "release_tree_immutable": True,
        "release_tree_sha256": release_before,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independently prove an Origins Phase 8A release candidate")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{40}", args.expected_head) is None:
        raise ProofError("expected head must be an exact 40-character lowercase Git SHA")
    archive = args.archive.resolve()
    checksum = args.checksum.resolve()
    archive_sha = verify_checksum(archive, checksum)
    with tempfile.TemporaryDirectory(prefix="origins-phase8-consumer-") as temp_text:
        temp = Path(temp_text)
        release_root = extract_archive(archive, temp / "release")
        manifest = verify_manifest(release_root, expected_head=args.expected_head)
        artifacts = verify_artifacts(release_root, manifest)
        version = str(manifest["product_version"])
        verify_python_wheel(artifacts["python-plane"], version=version)
        verify_workspace_bundle(artifacts["workspace"], temp / "workspace-unpacked")
        runtime = runtime_smoke(artifacts["originsd"], release_root, temp / "consumer-state")

    result = {
        "proof": "PHASE8_PORTABLE_RELEASE_PROOF_OK",
        "source_head": args.expected_head,
        "archive_sha256": archive_sha,
        "product_version": manifest["product_version"],
        "release_id": manifest["release_id"],
        "runtime": runtime,
        "prime_installation_claimed": False,
        "builder_final_release_proven": False,
        "ptah_prime_native_proven": False,
        "production_release_accepted": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProofError as exc:
        print(f"phase8 release proof failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
