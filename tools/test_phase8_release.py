#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("phase8_builder", ROOT / "tools" / "build_phase8_release.py")
proof = load_module("phase8_proof", ROOT / "tools" / "prove_phase8_release.py")


class Phase8ReleaseContractTests(unittest.TestCase):
    def test_output_must_be_outside_source_checkout_and_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            temp = Path(temp_text)
            repo = temp / "repo"
            repo.mkdir()
            with self.assertRaises(builder.ReleaseError):
                builder.require_output_boundary(repo, repo)
            child = repo / "release"
            with self.assertRaises(builder.ReleaseError):
                builder.require_output_boundary(repo, child)
            sibling = temp / "release"
            builder.require_output_boundary(repo, sibling)
            sibling.mkdir()
            (sibling / "occupied").write_text("x", encoding="utf-8")
            with self.assertRaises(builder.ReleaseError):
                builder.require_output_boundary(repo, sibling)

    def test_component_versions_fail_closed_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            (root / "rust" / "originsd").mkdir(parents=True)
            (root / "python").mkdir()
            (root / "workspace").mkdir()
            (root / "rust" / "originsd" / "Cargo.toml").write_text(
                '[package]\nname = "originsd"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            (root / "python" / "pyproject.toml").write_text(
                '[project]\nname = "origins-contracts"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            (root / "workspace" / "package.json").write_text(
                json.dumps({"version": "0.1.0"}), encoding="utf-8"
            )
            self.assertEqual(
                builder.component_versions(root),
                {"originsd": "0.1.0", "python": "0.1.0", "workspace": "0.1.0"},
            )
            (root / "workspace" / "package.json").write_text(
                json.dumps({"version": "0.1.1"}), encoding="utf-8"
            )
            with self.assertRaises(builder.ReleaseError):
                builder.component_versions(root)

    def test_deterministic_tar_gz_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            source = root / "source"
            source.mkdir()
            (source / "b.txt").write_text("bravo\n", encoding="utf-8")
            nested = source / "a"
            nested.mkdir()
            (nested / "x.txt").write_text("xray\n", encoding="utf-8")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            builder.deterministic_tar_gz(source, first, arcname="payload")
            builder.deterministic_tar_gz(source, second, arcname="payload")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlink support unavailable")
    def test_release_tree_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            tree = root / "tree"
            tree.mkdir()
            target = tree / "target.txt"
            target.write_text("target", encoding="utf-8")
            link = tree / "link.txt"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(builder.ReleaseError):
                builder.require_regular_tree(tree)

    def test_candidate_manifest_preserves_owner_and_nonclaim_boundaries(self) -> None:
        manifest = builder.create_manifest(
            version="0.1.0",
            source_commit="a" * 40,
            release_id="origins-factory-0.1.0-linux-x86_64-aaaaaaaaaaaa",
            build_tools={
                "rustc": "rustc 1.75.0",
                "cargo": "cargo 1.75.0",
                "python": "3.12.0",
                "node": "v24.0.0",
                "npm": "11.0.0",
            },
            artifacts=[],
        )
        self.assertEqual(manifest["status"], "candidate")
        self.assertTrue(manifest["runtime"]["data_dir_external_to_release"])
        self.assertEqual(manifest["ownership"]["final_packaging"], "THETECHGUY Software Builder")
        self.assertEqual(manifest["ownership"]["machine_consumer"], "Prime OS component/package authority")
        self.assertEqual(manifest["ownership"]["future_mechanical_substrate"], "Ptah Space")
        self.assertTrue(manifest["claim_boundary"])
        self.assertTrue(all(value is False for value in manifest["claim_boundary"].values()))

    def test_archive_verifier_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            archive_path = Path(temp_text) / "bad.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"bad"
                info = tarfile.TarInfo("../escape")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            with tarfile.open(archive_path, "r:gz") as archive:
                with self.assertRaises(proof.ProofError):
                    proof.safe_members(archive)

    def test_checksum_verifier_rejects_wrong_digest_or_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            archive = root / "release.tar.gz"
            archive.write_bytes(b"release")
            sidecar = root / "release.sha256"
            sidecar.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
            with self.assertRaises(proof.ProofError):
                proof.verify_checksum(archive, sidecar)
            sidecar.write_text(f"{proof.sha256_file(archive)}  another.tar.gz\n", encoding="utf-8")
            with self.assertRaises(proof.ProofError):
                proof.verify_checksum(archive, sidecar)

    def test_release_schema_keeps_prime_and_production_claims_false(self) -> None:
        schema = json.loads((ROOT / "release" / "origins-release-v1.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertIn("build_environment", required)
        claims = schema["properties"]["claim_boundary"]["properties"]
        expected = {
            "prime_component_format_claimed",
            "prime_installation_claimed",
            "builder_final_release_proven",
            "ptah_prime_native_proven",
            "production_release_accepted",
            "runtime_authority_expansion",
        }
        self.assertEqual(set(claims), expected)
        self.assertTrue(all(value == {"const": False} for value in claims.values()))


if __name__ == "__main__":
    unittest.main()
