from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_exact(
    "tools/build_phase8_release.py",
    "import platform\nimport shutil\n",
    "import platform\nimport re\nimport shutil\n",
)

replace_exact(
    "tools/build_phase8_release.py",
    '''def build_environment(root: Path) -> dict[str, str]:
    libc_name, libc_version = platform.libc_ver()
    if libc_name.lower() != "glibc" or not libc_version:
        raise ReleaseError(
            f"Phase 8A GNU release requires observable glibc build provenance, got {libc_name!r} {libc_version!r}"
        )
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
''',
    '''def host_glibc_version(root: Path) -> str:
    output = run(["ldd", "--version"], cwd=root)
    first = output.splitlines()[0].strip() if output else ""
    lowered = first.casefold()
    if "glibc" not in lowered and "gnu libc" not in lowered:
        raise ReleaseError(
            f"Phase 8A GNU release requires observable GNU glibc build provenance, got {first!r}"
        )
    match = re.search(r"([0-9]+\\.[0-9]+(?:\\.[0-9]+)*)\\s*$", first)
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
''',
)

replace_exact(
    "tools/prove_phase8_release.py",
    '''def runtime_smoke(binary: Path, release_root: Path, consumer_root: Path) -> dict[str, object]:
    data_dir = consumer_root / "data"
    workspace_root = consumer_root / "workspaces"
    artifact_root = consumer_root / "artifact-inputs"
    for path in (data_dir, workspace_root, artifact_root):
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
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait(timeout=5)
                    raise ProofError("released originsd did not shut down cleanly") from exc
        if process.returncode != 0:
            raise ProofError(f"released originsd shutdown returned {process.returncode}")
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
''',
    '''def file_tail(path: Path, *, max_bytes: int = 2000) -> str:
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
''',
)

workflow = Path(".github/workflows/phase8-portable-release.yml")
workflow_text = workflow.read_text(encoding="utf-8")
cache_block = '''      - name: Set up Node 24.19.0
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "24.19.0"
          cache: npm
          cache-dependency-path: workspace/package-lock.json
'''
no_cache_block = '''      - name: Set up Node 24.19.0
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "24.19.0"
'''
if workflow_text.count(cache_block) != 1:
    raise RuntimeError("phase8 workflow: expected exactly one npm cache block")
workflow_text = workflow_text.replace(cache_block, no_cache_block)
workflow_text = workflow_text.replace("permissions:\n  contents: write\n", "permissions:\n  contents: read\n", 1)
start_marker = "  # PHASE8_REVIEW_FIX_ONCE_START\n"
end_marker = "  # PHASE8_REVIEW_FIX_ONCE_END\n"
start = workflow_text.find(start_marker)
end = workflow_text.find(end_marker)
if start < 0 or end < 0 or end < start:
    raise RuntimeError("phase8 workflow: self-removal markers missing")
end += len(end_marker)
workflow.write_text(workflow_text[:start] + workflow_text[end:], encoding="utf-8")

tests = Path("python/tests/test_phase8_release.py")
current = tests.read_text(encoding="utf-8")
if "def test_host_glibc_provenance_uses_gnu_loader" in current:
    raise RuntimeError("review regression tests already present")
addition = r'''


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
'''
tests.write_text(current.rstrip() + addition + "\n", encoding="utf-8")

Path(__file__).unlink()
