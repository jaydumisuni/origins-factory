from __future__ import annotations

import importlib.util
import io
import json
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FROZEN_SHA = "530327c600a8758c3eba71c63b63efd726d1c85f"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_module("phase8_builder_pass_b", ROOT / "tools" / "build_phase8_release.py")
proof = _load_module("phase8_proof_pass_b", ROOT / "tools" / "prove_phase8_release.py")


def _build_tools() -> dict[str, str]:
    return {
        "rustc": "rustc 1.75.0",
        "cargo": "cargo 1.75.0",
        "python": "3.12.13",
        "pip": "pip 26.2.1",
        "setuptools": "setuptools 84.0.0",
        "node": "v24.19.0",
        "npm": "11.17.0",
        "glibc": "glibc 2.39",
    }


def _manifest() -> dict[str, object]:
    version = "0.1.0"
    return builder.create_manifest(
        version=version,
        source_commit=FROZEN_SHA,
        release_id=f"origins-factory-{version}-linux-x86_64-{FROZEN_SHA[:12]}",
        build_tools=_build_tools(),
        artifacts=[
            {
                "id": "originsd",
                "kind": "native-binary",
                "path": "bin/originsd",
                "sha256": "1" * 64,
                "size_bytes": 1,
            },
            {
                "id": "python-plane",
                "kind": "python-wheel",
                "path": "python/origins_contracts-0.1.0-py3-none-any.whl",
                "sha256": "2" * 64,
                "size_bytes": 1,
            },
            {
                "id": "workspace",
                "kind": "static-web-bundle",
                "path": "workspace/workspace.tar.gz",
                "sha256": "3" * 64,
                "size_bytes": 1,
            },
        ],
    )


def _write_manifest(tmp_path: Path, manifest: dict[str, object], *, root_name: str | None = None) -> Path:
    name = root_name or str(manifest["release_id"])
    release_root = tmp_path / name
    release_root.mkdir()
    (release_root / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return release_root


def test_pass_b_rejects_manifest_self_promotion(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["status"] = "accepted"
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="identity/status changed"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_production_claim_flip(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["claim_boundary"]["production_release_accepted"] = True
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="widened an explicitly false claim"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_prime_install_claim_flip(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["claim_boundary"]["prime_installation_claimed"] = True
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="widened an explicitly false claim"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_source_commit_substitution(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["source"]["commit"] = "f" * 40
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="source provenance changed"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_release_root_identity_substitution(tmp_path: Path) -> None:
    manifest = _manifest()
    release_root = _write_manifest(tmp_path, manifest, root_name="origins-factory-0.1.0-linux-x86_64-wrongwrong12")
    with pytest.raises(proof.ProofError, match="archive root/release_id"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_unexpected_manifest_field(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["self_approved"] = True
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="top-level contract changed"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_runtime_dependency_expansion(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["runtime"]["python_dependencies"].append("requests==2.32.5")
    release_root = _write_manifest(tmp_path, manifest)
    with pytest.raises(proof.ProofError, match="runtime contract changed"):
        proof.verify_manifest(release_root, expected_head=FROZEN_SHA)


def test_pass_b_rejects_extra_artifact_authority(tmp_path: Path) -> None:
    manifest = _manifest()
    release_root = tmp_path / str(manifest["release_id"])
    release_root.mkdir()
    for item, payload in zip(manifest["artifacts"], (b"o", b"p", b"w"), strict=True):
        artifact = release_root / str(item["path"])
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(payload)
        item["sha256"] = proof.sha256_file(artifact)
        item["size_bytes"] = artifact.stat().st_size
    manifest["artifacts"].append(
        {
            "id": "prime-installer",
            "kind": "native-binary",
            "path": "bin/prime-installer",
            "sha256": "4" * 64,
            "size_bytes": 1,
        }
    )
    with pytest.raises(proof.ProofError, match="identity/kind changed"):
        proof.verify_artifacts(release_root, manifest)


def test_pass_b_rejects_tar_hardlink(tmp_path: Path) -> None:
    archive_path = tmp_path / "hardlink.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        data = b"ok"
        regular = tarfile.TarInfo("release/file")
        regular.size = len(data)
        archive.addfile(regular, io.BytesIO(data))
        link = tarfile.TarInfo("release/link")
        link.type = tarfile.LNKTYPE
        link.linkname = "release/file"
        archive.addfile(link)
    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(proof.ProofError, match="contains a link"):
            proof.safe_members(archive)


def test_pass_b_rejects_duplicate_wheel_paths(tmp_path: Path) -> None:
    wheel = tmp_path / "origins_contracts-0.1.0-py3-none-any.whl"
    metadata_name = "origins_contracts-0.1.0.dist-info/METADATA"
    with zipfile.ZipFile(wheel, "w") as package:
        package.writestr(metadata_name, "Name: origins-contracts\nVersion: 0.1.0\n")
        package.writestr(metadata_name, "Name: origins-contracts\nVersion: 9.9.9\n")
    with pytest.raises(proof.ProofError, match="duplicate paths"):
        proof.verify_python_wheel(wheel, version="0.1.0")


def test_pass_b_rejects_wheel_symlink(tmp_path: Path) -> None:
    wheel = tmp_path / "origins_contracts-0.1.0-py3-none-any.whl"
    metadata_name = "origins_contracts-0.1.0.dist-info/METADATA"
    with zipfile.ZipFile(wheel, "w") as package:
        package.writestr(metadata_name, "Name: origins-contracts\nVersion: 0.1.0\n")
        link = zipfile.ZipInfo("origins_contracts/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "target")
    with pytest.raises(proof.ProofError, match="contains a symlink"):
        proof.verify_python_wheel(wheel, version="0.1.0")


def test_pass_b_rejects_workspace_source_leakage(tmp_path: Path) -> None:
    bundle = tmp_path / "workspace.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, payload in (
            ("workspace/index.html", b"<div id='root'></div>"),
            ("workspace/src/app.ts", b"export const leaked = true"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(proof.ProofError, match="contains build/source material"):
        proof.verify_workspace_bundle(bundle, tmp_path / "unpacked")


def test_pass_b_rejects_noncanonical_checksum_case(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"candidate")
    sidecar = tmp_path / "release.sha256"
    sidecar.write_text(f"{'A' * 64}  {archive.name}\n", encoding="utf-8")
    with pytest.raises(proof.ProofError, match="malformed"):
        proof.verify_checksum(archive, sidecar)


def test_pass_b_requires_exact_lowercase_git_sha_before_io(tmp_path: Path) -> None:
    with pytest.raises(proof.ProofError, match="exact 40-character lowercase Git SHA"):
        proof.main(
            [
                "--archive",
                str(tmp_path / "missing.tar.gz"),
                "--checksum",
                str(tmp_path / "missing.sha256"),
                "--expected-head",
                FROZEN_SHA.upper(),
            ]
        )
