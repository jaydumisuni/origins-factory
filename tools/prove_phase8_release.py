#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
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


def safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    if not members:
        raise ProofError("release archive is empty")
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ProofError(f"release archive contains unsafe path: {member.name}")
        if member.issym() or member.islnk():
            raise ProofError(f"release archive contains a link: {member.name}")
        if not member.isfile() and not member.isdir():
            raise ProofError(f"release archive contains unsupported entry: {member.name}")
    return members


def extract_archive(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = safe_members(archive)
        top = {PurePosixPath(member.name).parts[0] for member in members if PurePosixPath(member.name).parts}
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
    if len(parts) != 2 or parts[1] != archive.name:
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
    if manifest.get("schema_version") != "origins.release.v1":
        raise ProofError("release manifest schema changed")
    if manifest.get("product") != "origins-factory" or manifest.get("status") != "candidate":
        raise ProofError("release candidate identity/status changed")
    source = manifest.get("source")
    if source != {"repository": "jaydumisuni/origins-factory", "commit": expected_head, "clean": True}:
        raise ProofError("release source provenance changed")
    if manifest.get("target") != {"os": "linux", "arch": "x86_64", "libc": "gnu"}:
        raise ProofError("release target changed")
    build = manifest.get("build_environment")
    if not isinstance(build, dict) or set(build) != {"rustc", "cargo", "python", "node", "npm"}:
        raise ProofError("release build provenance is incomplete")
    if not all(isinstance(value, str) and value.strip() for value in build.values()):
        raise ProofError("release build provenance contains empty values")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise ProofError("release runtime contract is missing")
    if runtime.get("default_bind") != "127.0.0.1:48700" or runtime.get("loopback_only") is not True:
        raise ProofError("release loopback runtime boundary changed")
    if runtime.get("data_dir_external_to_release") is not True:
        raise ProofError("release no longer requires external persistent data")
    health = runtime.get("health")
    if health != {
        "method": "GET",
        "path": "/v1/health",
        "auth_required": False,
        "expected": {"ok": True, "service": "originsd"},
    }:
        raise ProofError("release health contract changed")
    claims = manifest.get("claim_boundary")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
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
    for item in raw:
        if not isinstance(item, dict):
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
            names = package.namelist()
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ProofError("Python wheel contains unsafe path")
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


def runtime_smoke(binary: Path, release_root: Path, consumer_root: Path) -> dict[str, object]:
    data_dir = consumer_root / "data"
    workspace_root = consumer_root / "workspaces"
    artifact_root = consumer_root / "artifact-inputs"
    for path in (data_dir, workspace_root, artifact_root):
        path.mkdir(parents=True, exist_ok=True)
    if data_dir.is_relative_to(release_root):
        raise ProofError("runtime data directory is inside the immutable release root")

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
        process = subprocess.Popen(
            [str(binary)],
            cwd=consumer_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            health = wait_health(port, process)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if attempt == 0:
            first_health = health
        else:
            second_health = health
    if first_health is None or second_health is None:
        raise ProofError("runtime health proof did not complete twice")
    database = data_dir / "origins.sqlite3"
    token = data_dir / "local-token"
    if not database.is_file() or database.stat().st_size <= 0:
        raise ProofError("released originsd did not persist its external database")
    if not token.is_file() or token.stat().st_size <= 0:
        raise ProofError("released originsd did not persist its external local token")
    if (release_root / ".origins").exists():
        raise ProofError("released originsd wrote mutable state into the release root")
    return {
        "restart_health": True,
        "database_external": True,
        "local_token_external": True,
        "journal_ok": bool(second_health.get("journal", {}).get("ok")) if isinstance(second_health.get("journal"), dict) else False,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independently prove an Origins Phase 8A release candidate")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
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
