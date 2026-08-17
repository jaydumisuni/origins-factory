#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class ProofLauncherError(RuntimeError):
    pass


def _required_root(name: str, default: str) -> Path:
    root = Path(os.environ.get(name, default)).resolve()
    if not root.is_dir():
        raise ProofLauncherError(f"owner source root is unavailable: {root}")
    return root


def _write_entrypoint(path: Path, *, owner_root: Path, module: str) -> None:
    script = (
        f"#!{sys.executable}\n"
        "from __future__ import annotations\n"
        "import sys\n"
        f"sys.path.insert(0, {str(owner_root)!r})\n"
        f"from {module} import main\n"
        "raise SystemExit(main())\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _prepare_owner_bin(root: Path, *, codeops_root: Path, sergeant_root: Path) -> Path:
    proof_bin = root / "proof-bin"
    proof_bin.mkdir(parents=True, exist_ok=False)
    launchers = {
        "hunter-codeops-switcher": (codeops_root, "hunter_codeops.code_ops_switcher_cli"),
        "sergeant": (sergeant_root, "main_review.cli"),
    }
    for name, (owner_root, module) in launchers.items():
        _write_entrypoint(proof_bin / name, owner_root=owner_root, module=module)
    return proof_bin


def _assert_resolution(name: str, expected: Path, *, path_value: str) -> str:
    resolved = shutil.which(name, path=path_value)
    if not resolved:
        raise ProofLauncherError(f"pinned owner executable did not resolve: {name}")
    actual = Path(resolved).resolve()
    if actual != expected.resolve():
        raise ProofLauncherError(
            f"owner executable provenance mismatch for {name}: expected {expected.resolve()}, got {actual}"
        )
    return str(actual)


def main() -> int:
    source_root = Path(__file__).resolve().parents[1]
    proof_script = source_root / "tools" / "prove_phase7_live_owner_mcp.py"
    if not proof_script.is_file():
        raise ProofLauncherError(f"MCP-native Phase 7 proof is unavailable: {proof_script}")

    codeops_root = _required_root("ORIGINS_PHASE7_CODEOPS_ROOT", "/home/kratos/hunter-codeops")
    sergeant_root = _required_root("ORIGINS_PHASE7_SERGEANT_ROOT", "/home/kratos/Sergeant")

    launcher_root = Path(tempfile.mkdtemp(prefix="origins-phase7-owner-cli-"))
    try:
        proof_bin = _prepare_owner_bin(
            launcher_root,
            codeops_root=codeops_root,
            sergeant_root=sergeant_root,
        )
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(
            [str(proof_bin), str(Path(sys.executable).parent), env.get("PATH", "")]
        )
        resolved = {
            "hunter-codeops-switcher": _assert_resolution(
                "hunter-codeops-switcher",
                proof_bin / "hunter-codeops-switcher",
                path_value=env["PATH"],
            ),
            "sergeant": _assert_resolution(
                "sergeant",
                proof_bin / "sergeant",
                path_value=env["PATH"],
            ),
        }

        completed = subprocess.run(
            [sys.executable, str(proof_script)],
            cwd=source_root,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            sys.stdout.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            return completed.returncode

        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ProofLauncherError("MCP-native Phase 7 proof returned non-JSON output") from exc
        if not isinstance(payload, dict) or payload.get("proof") != "PHASE7_LIVE_OWNER_MCP_OK":
            raise ProofLauncherError("MCP-native Phase 7 proof did not return the expected success contract")

        payload["owner_executable_provenance"] = {
            "pinned": True,
            "codeops_root": str(codeops_root),
            "sergeant_root": str(sergeant_root),
            "resolved": resolved,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(launcher_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
