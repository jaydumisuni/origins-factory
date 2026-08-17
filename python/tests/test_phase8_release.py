from __future__ import annotations

import importlib.util
import json
import os
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "build_phase8_release.py"
SPEC = importlib.util.spec_from_file_location("build_phase8_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def _build_tools() -> dict[str, str]:
    return {
        "rustc": "rustc 1.75.0",
        "cargo": "cargo 1.75.0",
        "python": "3.12.0",
        "node": "v24.0.0",
        "npm": "11.0.0",
    }


def _dummy_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    originsd = tmp_path / "inputs" / "originsd"
    originsd.parent.mkdir(parents=True)
    originsd.write_bytes(b"originsd-candidate")
    originsd.chmod(0o755)

    wheel = tmp_path / "inputs" / "origins_contracts-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel-candidate")

    workspace = tmp_path / "workspace-dist"
    (workspace / "assets").mkdir(parents=True)
    (workspace / "index.html").write_text("<div id='root'></div>\n", encoding="utf-8")
    (workspace / "assets" / "app.js").write_text("console.log('origins')\n", encoding="utf-8")
    return originsd, wheel, workspace


def test_component_versions_are_release_aligned() -> None:
    versions = release.component_versions(ROOT)
    assert versions == {"originsd": "0.1.0", "python": "0.1.0", "workspace": "0.1.0"}


def test_component_version_drift_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "rust" / "originsd").mkdir(parents=True)
    (tmp_path / "python").mkdir()
    (tmp_path / "workspace").mkdir()
    (tmp_path / "rust" / "originsd" / "Cargo.toml").write_text(
        "[package]\nname='originsd'\nversion='0.1.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "python" / "pyproject.toml").write_text(
        "[project]\nname='origins-contracts'\nversion='0.1.1'\n",
        encoding="utf-8",
    )
    (tmp_path / "workspace" / "package.json").write_text(
        json.dumps({"version": "0.1.0"}),
        encoding="utf-8",
    )
    with pytest.raises(release.ReleaseError, match="component version drift"):
        release.component_versions(tmp_path)


def test_release_output_must_be_external_and_empty(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(release.ReleaseError, match="outside the source checkout"):
        release.require_output_boundary(source, source / "release")

    external = tmp_path / "release"
    external.mkdir()
    (external / "occupied").write_text("x", encoding="utf-8")
    with pytest.raises(release.ReleaseError, match="must be empty"):
        release.require_output_boundary(source, external)

    empty = tmp_path / "empty-release"
    release.require_output_boundary(source, empty)


def test_release_tree_rejects_symlinks(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "target"
    target.write_text("data", encoding="utf-8")
    link = tree / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(release.ReleaseError, match="contains symlink"):
        release.require_regular_tree(tree)


def test_manifest_keeps_prime_builder_ptah_nonclaims() -> None:
    manifest = release.create_manifest(
        version="0.1.0",
        source_commit="a" * 40,
        release_id="origins-factory-0.1.0-linux-x86_64-aaaaaaaaaaaa",
        build_tools=_build_tools(),
        artifacts=[
            {"id": "originsd", "kind": "native-binary", "path": "bin/originsd", "sha256": "1" * 64, "size_bytes": 1},
            {"id": "python-plane", "kind": "python-wheel", "path": "python/a.whl", "sha256": "2" * 64, "size_bytes": 1},
            {"id": "workspace", "kind": "static-web-bundle", "path": "workspace/workspace.tar.gz", "sha256": "3" * 64, "size_bytes": 1},
        ],
    )
    assert manifest["schema_version"] == "origins.release.v1"
    assert manifest["source"] == {"repository": "jaydumisuni/origins-factory", "commit": "a" * 40, "clean": True}
    assert manifest["target"] == {"os": "linux", "arch": "x86_64", "libc": "gnu"}
    assert manifest["build_environment"] == _build_tools()
    assert manifest["runtime"]["health"]["path"] == "/v1/health"
    assert manifest["runtime"]["data_dir_external_to_release"] is True
    assert set(manifest["claim_boundary"].values()) == {False}


def test_schema_pins_candidate_claim_boundary() -> None:
    schema = json.loads((ROOT / "release" / "origins-release-v1.schema.json").read_text(encoding="utf-8"))
    assert "build_environment" in schema["required"]
    assert schema["properties"]["target"]["properties"]["os"]["const"] == "linux"
    claims = schema["properties"]["claim_boundary"]["properties"]
    assert claims
    assert all(item.get("const") is False for item in claims.values())


def test_assembled_release_is_digest_bound_and_deterministic(tmp_path: Path) -> None:
    originsd, wheel, workspace = _dummy_inputs(tmp_path)
    first = tmp_path / "out-a"
    second = tmp_path / "out-b"
    first.mkdir()
    second.mkdir()
    kwargs = {
        "source_commit": "b" * 40,
        "version": "0.1.0",
        "build_tools": _build_tools(),
        "originsd": originsd,
        "wheel": wheel,
        "workspace_dist": workspace,
    }
    root_a, archive_a, checksum_a = release.assemble_release(output_dir=first, **kwargs)
    root_b, archive_b, checksum_b = release.assemble_release(output_dir=second, **kwargs)

    assert release.sha256_file(archive_a) == release.sha256_file(archive_b)
    assert checksum_a.read_text(encoding="utf-8").split()[0] == release.sha256_file(archive_a)
    assert checksum_b.read_text(encoding="utf-8").split()[0] == release.sha256_file(archive_b)

    manifest = json.loads((root_a / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in manifest["artifacts"]}
    assert set(by_id) == {"originsd", "python-plane", "workspace"}
    for item in manifest["artifacts"]:
        artifact = root_a / item["path"]
        assert artifact.is_file()
        assert item["sha256"] == release.sha256_file(artifact)
        assert item["size_bytes"] == artifact.stat().st_size

    with tarfile.open(archive_a, "r:gz") as bundle:
        names = bundle.getnames()
    release_id = manifest["release_id"]
    assert f"{release_id}/bin/originsd" in names
    assert f"{release_id}/RELEASE_MANIFEST.json" in names


def test_assemble_refuses_existing_release_identity(tmp_path: Path) -> None:
    originsd, wheel, workspace = _dummy_inputs(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    kwargs = {
        "output_dir": output,
        "source_commit": "c" * 40,
        "version": "0.1.0",
        "build_tools": _build_tools(),
        "originsd": originsd,
        "wheel": wheel,
        "workspace_dist": workspace,
    }
    release.assemble_release(**kwargs)
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.assemble_release(**kwargs)
