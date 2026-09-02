from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_module("build_phase8_release", ROOT / "tools" / "build_phase8_release.py")
proof = _load_module("prove_phase8_release", ROOT / "tools" / "prove_phase8_release.py")


def _build_tools() -> dict[str, str]:
    return {
        "rustc": "rustc 1.75.0",
        "cargo": "cargo 1.75.0",
        "python": "3.12.0",
        "pip": "pip 26.0.1",
        "setuptools": "setuptools 82.0.0",
        "node": "v24.0.0",
        "npm": "11.0.0",
        "glibc": "glibc 2.39",
    }


def _python_runtime() -> dict[str, object]:
    return {
        "python_requires": ">=3.10",
        "python_dependencies": ["websockets==16.1.1"],
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
        python_runtime=_python_runtime(),
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
                "path": "python/a.whl",
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
    assert manifest["schema_version"] == "origins.release.v1"
    assert manifest["source"] == {
        "repository": "jaydumisuni/origins-factory",
        "commit": "a" * 40,
        "clean": True,
    }
    assert manifest["target"] == {"os": "linux", "arch": "x86_64", "libc": "gnu"}
    assert manifest["build_environment"] == _build_tools()
    assert manifest["runtime"]["health"]["path"] == "/v1/health"
    assert manifest["runtime"]["data_dir_external_to_release"] is True
    assert set(manifest["claim_boundary"].values()) == {False}


def test_schema_pins_candidate_claim_boundary_and_full_build_provenance() -> None:
    schema = json.loads((ROOT / "release" / "origins-release-v1.schema.json").read_text(encoding="utf-8"))
    assert "build_environment" in schema["required"]
    assert schema["properties"]["target"]["properties"]["os"]["const"] == "linux"
    build = schema["properties"]["build_environment"]
    assert set(build["required"]) == set(_build_tools())
    assert build["additionalProperties"] is False
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
        "python_runtime": _python_runtime(),
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
        "python_runtime": _python_runtime(),
        "originsd": originsd,
        "wheel": wheel,
        "workspace_dist": workspace,
    }
    release.assemble_release(**kwargs)
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.assemble_release(**kwargs)


def test_archive_verifier_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"bad"
        info = tarfile.TarInfo("../escape")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(proof.ProofError, match="unsafe path"):
            proof.safe_members(archive)


def test_archive_verifier_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for payload in (b"first", b"second"):
            info = tarfile.TarInfo("release/file")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(proof.ProofError, match="duplicate path"):
            proof.safe_members(archive)


def test_checksum_verifier_rejects_wrong_digest_and_name(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"release")
    sidecar = tmp_path / "release.sha256"
    sidecar.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    with pytest.raises(proof.ProofError, match="does not match"):
        proof.verify_checksum(archive, sidecar)

    sidecar.write_text(
        f"{proof.sha256_file(archive)}  another.tar.gz\n",
        encoding="utf-8",
    )
    with pytest.raises(proof.ProofError, match="malformed or names another"):
        proof.verify_checksum(archive, sidecar)


def test_tree_digest_changes_on_byte_or_mode_mutation(tmp_path: Path) -> None:
    root = tmp_path / "release"
    root.mkdir()
    binary = root / "originsd"
    binary.write_bytes(b"one")
    binary.chmod(0o755)
    original = proof.tree_digest(root)
    binary.write_bytes(b"two")
    assert proof.tree_digest(root) != original
    binary.write_bytes(b"one")
    binary.chmod(0o644)
    assert proof.tree_digest(root) != original


def test_host_glibc_provenance_uses_gnu_loader(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        release,
        "run",
        lambda args, cwd: "ldd (Ubuntu GLIBC 2.39-0ubuntu8.7) 2.39\nCopyright",
    )
    assert release.host_glibc_version(tmp_path) == "2.39"

    monkeypatch.setattr(release, "run", lambda args, cwd: "musl libc (x86_64)\nVersion 1.2.5")
    with pytest.raises(release.ReleaseError, match="GNU glibc build provenance"):
        release.host_glibc_version(tmp_path)


def test_runtime_smoke_redirects_child_output_to_files(monkeypatch, tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir()
    binary = release_root / "originsd"
    binary.write_bytes(b"candidate")
    binary.chmod(0o755)
    consumer_root = tmp_path / "consumer"
    captured: list[dict[str, object]] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None

        def poll(self):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def kill(self) -> None:
            self.returncode = -9

    def fake_popen(*args, **kwargs):
        captured.append(kwargs)
        return FakeProcess()

    def fake_wait_health(port, process, *, timeout=12.0):
        data_dir = consumer_root / "data"
        (data_dir / "origins.sqlite3").write_bytes(b"db")
        (data_dir / "local-token.txt").write_text("token", encoding="utf-8")
        return {"journal": {"ok": True}}

    monkeypatch.setattr(proof.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(proof, "wait_health", fake_wait_health)

    result = proof.runtime_smoke(binary, release_root, consumer_root)
    assert result["restart_health"] is True
    assert len(captured) == 2
    for invocation in captured:
        assert invocation["stdout"] is not proof.subprocess.PIPE
        assert invocation["stderr"] is not proof.subprocess.PIPE
        assert hasattr(invocation["stdout"], "write")
        assert hasattr(invocation["stderr"], "write")


def test_python_runtime_contract_is_derived_from_pyproject_and_fails_on_drift(tmp_path: Path) -> None:
    python_root = tmp_path / "python"
    python_root.mkdir()
    pyproject = python_root / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        "name='origins-contracts'\n"
        "version='0.1.0'\n"
        "requires-python='>=3.10'\n"
        "dependencies=['websockets==16.1.1']\n",
        encoding="utf-8",
    )
    runtime = release.python_runtime_contract(tmp_path)
    assert runtime == {
        "python_requires": ">=3.10",
        "python_dependencies": ["websockets==16.1.1"],
    }
    manifest = release.create_manifest(
        version="0.1.0",
        source_commit="d" * 40,
        release_id="origins-factory-0.1.0-linux-x86_64-dddddddddddd",
        build_tools=_build_tools(),
        artifacts=[],
        python_runtime=runtime,
    )
    assert manifest["runtime"]["python_requires"] == runtime["python_requires"]
    assert manifest["runtime"]["python_dependencies"] == runtime["python_dependencies"]

    pyproject.write_text(
        "[project]\n"
        "name='origins-contracts'\n"
        "version='0.1.0'\n"
        "requires-python='>=3.10'\n"
        "dependencies=['websockets==16.1.2']\n",
        encoding="utf-8",
    )
    with pytest.raises(release.ReleaseError, match="Python runtime metadata drift"):
        release.python_runtime_contract(tmp_path)


def test_manifest_rejects_malformed_python_runtime_contract() -> None:
    with pytest.raises(release.ReleaseError, match="Python runtime contract is malformed"):
        release.create_manifest(
            version="0.1.0",
            source_commit="e" * 40,
            release_id="origins-factory-0.1.0-linux-x86_64-eeeeeeeeeeee",
            build_tools=_build_tools(),
            artifacts=[],
            python_runtime={
                "python_requires": ">=3.10",
                "python_dependencies": "websockets==16.1.1",
            },
        )
    with pytest.raises(release.ReleaseError, match="Python runtime contract is malformed"):
        release.create_manifest(
            version="0.1.0",
            source_commit="f" * 40,
            release_id="origins-factory-0.1.0-linux-x86_64-ffffffffffff",
            build_tools=_build_tools(),
            artifacts=[],
            python_runtime=None,  # type: ignore[arg-type]
        )


def test_python_wheel_runtime_metadata_must_match_release_manifest(tmp_path: Path) -> None:
    wheel = tmp_path / "origins_contracts-0.1.0-py3-none-any.whl"
    metadata_name = "origins_contracts-0.1.0.dist-info/METADATA"

    with zipfile.ZipFile(wheel, "w") as package:
        package.writestr(
            metadata_name,
            "Metadata-Version: 2.1\n"
            "Name: origins-contracts\n"
            "Version: 0.1.0\n"
            "Requires-Python: >=3.10\n"
            "Requires-Dist: websockets==16.1.1\n",
        )
    proof.verify_python_wheel(
        wheel,
        version="0.1.0",
        python_requires=">=3.10",
        python_dependencies=["websockets==16.1.1"],
    )

    with zipfile.ZipFile(wheel, "w") as package:
        package.writestr(
            metadata_name,
            "Metadata-Version: 2.1\n"
            "Name: origins-contracts\n"
            "Version: 0.1.0\n"
            "Requires-Python: >=3.10\n"
            "Requires-Dist: websockets==16.1.2\n",
        )
    with pytest.raises(proof.ProofError, match="runtime metadata does not match release manifest"):
        proof.verify_python_wheel(
            wheel,
            version="0.1.0",
            python_requires=">=3.10",
            python_dependencies=["websockets==16.1.1"],
        )
