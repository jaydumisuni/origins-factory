from __future__ import annotations

from pathlib import Path

RUNTIME = Path("python/origins_integration/phase7_runtime.py")
STORE = Path("python/origins_integration/capability_evolution.py")
TEST = Path("python/tests/test_phase7_canary_binding.py")
BASE_PROOF = Path("tools/prove_phase7_live_owner.py")
STRICT_PROOF = Path("tools/prove_phase7_live_owner_strict.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    old = '''        repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        session = self.origins_client.wait_session(session_id)
        canary_binding = _validate_canary_binding(gap, candidate, session, repository, repository_diff)
        output = self.origins_client.get_session_output(session_id)
        if session.get("state") != "completed" or session.get("exit_code") != 0 or bool(session.get("output_truncated")):
            raise Phase7RuntimeError("canary Session must complete successfully without truncation")
'''
    new = '''        session = self.origins_client.wait_session(session_id)
        if session.get("state") != "completed" or session.get("exit_code") != 0 or bool(session.get("output_truncated")):
            raise Phase7RuntimeError("canary Session must complete successfully without truncation")
        output = self.origins_client.get_session_output(session_id)
        repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        canary_binding = _validate_canary_binding(gap, candidate, session, repository, repository_diff)
'''
    text = replace_once(text, old, new, "canary post-session revalidation")

    old = '''    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
        return self._project(self.store.decide(evolution_id, decision=decision, decided_by=decided_by))
'''
    new = '''    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
        normalized = decision.strip().lower()
        candidate_revalidation: dict[str, object] | None = None
        if normalized == "promote":
            record = self.store.get(evolution_id)
            gap = _mapping(record, "gap")
            candidate = _mapping(record, "candidate")
            repository_id = str(candidate.get("repository_id") or "")
            if not repository_id:
                raise Phase7RuntimeError("candidate repository_id is missing")
            repository = self.origins_client.refresh_repository(repository_id)
            repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
            candidate_revalidation = _validate_candidate_repository(gap, candidate, repository, repository_diff)
        return self._project(
            self.store.decide(
                evolution_id,
                decision=normalized,
                decided_by=decided_by,
                candidate_revalidation=candidate_revalidation,
            )
        )
'''
    text = replace_once(text, old, new, "promotion revalidation")

    old = '''def _validate_canary_binding(
    gap: Mapping[str, object],
    candidate: Mapping[str, object],
    session: Mapping[str, object],
    repository: Mapping[str, object],
    diff: Mapping[str, object],
) -> dict[str, object]:
    candidate_repository_id = str(candidate.get("repository_id") or "")
    repository_id = str(repository.get("repository_id") or "")
    if not candidate_repository_id or repository_id != candidate_repository_id:
        raise Phase7RuntimeError("canary Repository identity does not match the reviewed candidate")
    workspace_id = str(gap.get("workspace_id") or "")
    if not workspace_id or repository.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("candidate Repository is not owned by the original Mission Workspace")
    if session.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("canary Session is not owned by the original Mission Workspace")
    worktree_root = str(repository.get("worktree_root") or "")
    if not worktree_root or session.get("workspace_root") != worktree_root:
        raise Phase7RuntimeError("canary Session did not execute in the reviewed candidate worktree")
    expected_head = str(candidate.get("repository_head_oid") or "")
    if not expected_head or repository.get("head_oid") != expected_head:
        raise Phase7RuntimeError("candidate Repository HEAD changed after review")
    expected_status = str(candidate.get("repository_status_sha256") or "")
    if len(expected_status) != 64 or repository.get("status_sha256") != expected_status:
        raise Phase7RuntimeError("candidate Repository status changed after review")
    if diff.get("kind") != "unstaged" or bool(diff.get("truncated")):
        raise Phase7RuntimeError("canary requires the complete reviewed unstaged candidate diff")
    expected_diff = str(candidate.get("repository_diff_sha256") or "")
    expected_bytes = candidate.get("repository_diff_bytes")
    if len(expected_diff) != 64 or diff.get("sha256") != expected_diff:
        raise Phase7RuntimeError("candidate Repository diff changed after review")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise Phase7RuntimeError("candidate Repository diff byte count is malformed")
    if diff.get("complete_bytes") != expected_bytes:
        raise Phase7RuntimeError("candidate Repository diff size changed after review")
    return {
        "repository_id": candidate_repository_id,
        "workspace_id": workspace_id,
        "worktree_root": worktree_root,
        "repository_head_oid": expected_head,
        "repository_status_sha256": expected_status,
        "repository_diff_sha256": expected_diff,
        "repository_diff_bytes": expected_bytes,
    }
'''
    new = '''def _validate_candidate_repository(
    gap: Mapping[str, object],
    candidate: Mapping[str, object],
    repository: Mapping[str, object],
    diff: Mapping[str, object],
) -> dict[str, object]:
    candidate_repository_id = str(candidate.get("repository_id") or "")
    repository_id = str(repository.get("repository_id") or "")
    if not candidate_repository_id or repository_id != candidate_repository_id:
        raise Phase7RuntimeError("candidate Repository identity does not match the reviewed candidate")
    workspace_id = str(gap.get("workspace_id") or "")
    if not workspace_id or repository.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("candidate Repository is not owned by the original Mission Workspace")
    worktree_root = str(repository.get("worktree_root") or "")
    if not worktree_root:
        raise Phase7RuntimeError("candidate Repository worktree is missing")
    expected_head = str(candidate.get("repository_head_oid") or "")
    if not expected_head or repository.get("head_oid") != expected_head:
        raise Phase7RuntimeError("candidate Repository HEAD changed after review")
    expected_status = str(candidate.get("repository_status_sha256") or "")
    if len(expected_status) != 64 or repository.get("status_sha256") != expected_status:
        raise Phase7RuntimeError("candidate Repository status changed after review")
    if diff.get("kind") != "unstaged" or bool(diff.get("truncated")):
        raise Phase7RuntimeError("candidate requires the complete reviewed unstaged diff")
    expected_diff = str(candidate.get("repository_diff_sha256") or "")
    expected_bytes = candidate.get("repository_diff_bytes")
    if len(expected_diff) != 64 or diff.get("sha256") != expected_diff:
        raise Phase7RuntimeError("candidate Repository diff changed after review")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise Phase7RuntimeError("candidate Repository diff byte count is malformed")
    if diff.get("complete_bytes") != expected_bytes:
        raise Phase7RuntimeError("candidate Repository diff size changed after review")
    return {
        "repository_id": candidate_repository_id,
        "workspace_id": workspace_id,
        "worktree_root": worktree_root,
        "repository_head_oid": expected_head,
        "repository_status_sha256": expected_status,
        "repository_diff_sha256": expected_diff,
        "repository_diff_bytes": expected_bytes,
    }


def _validate_canary_binding(
    gap: Mapping[str, object],
    candidate: Mapping[str, object],
    session: Mapping[str, object],
    repository: Mapping[str, object],
    diff: Mapping[str, object],
) -> dict[str, object]:
    binding = _validate_candidate_repository(gap, candidate, repository, diff)
    workspace_id = str(binding["workspace_id"])
    if session.get("workspace_id") != workspace_id:
        raise Phase7RuntimeError("canary Session is not owned by the original Mission Workspace")
    if session.get("workspace_root") != binding["worktree_root"]:
        raise Phase7RuntimeError("canary Session did not execute in the reviewed candidate worktree")
    return binding
'''
    text = replace_once(text, old, new, "candidate repository helper")
    RUNTIME.write_text(text, encoding="utf-8")


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    old = '''    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
'''
    new = '''    def decide(
        self,
        evolution_id: str,
        *,
        decision: str,
        decided_by: str,
        candidate_revalidation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
'''
    text = replace_once(text, old, new, "store decision signature")
    old = '''            promotion: dict[str, object] = {
                "decision": decision,
                "decided_by": decided_by.strip(),
                "decided_at": now,
                "previous_generation": previous,
            }
'''
    new = '''            promotion: dict[str, object] = {
                "decision": decision,
                "decided_by": decided_by.strip(),
                "decided_at": now,
                "previous_generation": previous,
                "candidate_revalidation": dict(candidate_revalidation) if candidate_revalidation is not None else None,
            }
'''
    text = replace_once(text, old, new, "durable promotion revalidation")
    STORE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = text.replace(
        "from origins_integration.phase7_runtime import Phase7RuntimeError, _validate_canary_binding\n",
        "from origins_integration.phase7_runtime import (\n    Phase7Runtime,\n    Phase7RuntimeError,\n    _validate_canary_binding,\n    _validate_candidate_repository,\n)\n",
        1,
    )
    if "test_candidate_repository_binding_is_reusable_for_promotion" not in text:
        text += '''\n\ndef test_candidate_repository_binding_is_reusable_for_promotion() -> None:\n    gap, candidate, _session, repository, diff = values()\n    binding = _validate_candidate_repository(gap, candidate, repository, diff)\n    assert binding["repository_id"] == "repo-7"\n    assert binding["repository_status_sha256"] == D\n\n\nclass _Bindings:\n    def get(self, _evolution_id: str) -> None:\n        return None\n\n\nclass _Store:\n    path = Path("/tmp/unused-phase7-test.sqlite")\n\n    def __init__(self, record: dict[str, object]) -> None:\n        self.record = record\n        self.decisions: list[dict[str, object]] = []\n\n    def get(self, _evolution_id: str) -> dict[str, object]:\n        return self.record\n\n    def record_canary(self, _evolution_id: str, canary: dict[str, object]) -> dict[str, object]:\n        value = dict(self.record)\n        value["state"] = "canary_passed"\n        value["canary"] = dict(canary)\n        return value\n\n    def active_generation(self, _capability_id: str) -> None:\n        return None\n\n    def decide(self, _evolution_id: str, **kwargs: object) -> dict[str, object]:\n        self.decisions.append(dict(kwargs))\n        value = dict(self.record)\n        value["state"] = "promoted" if kwargs["decision"] == "promote" else "rolled_back"\n        return value\n\n\nclass _Client:\n    def __init__(self, *, changed: bool = False) -> None:\n        self.calls: list[str] = []\n        self.changed = changed\n\n    def wait_session(self, _session_id: str) -> dict[str, object]:\n        self.calls.append("wait")\n        return {\n            "state": "completed",\n            "exit_code": 0,\n            "output_truncated": False,\n            "workspace_id": "workspace-7",\n            "workspace_root": "/tmp/candidate",\n            "stdout_sha256": D,\n            "stderr_sha256": E,\n        }\n\n    def get_session_output(self, _session_id: str) -> dict[str, object]:\n        self.calls.append("output")\n        return {"stdout": "ok", "stderr": ""}\n\n    def refresh_repository(self, _repository_id: str) -> dict[str, object]:\n        self.calls.append("refresh")\n        return {\n            "repository_id": "repo-7",\n            "workspace_id": "workspace-7",\n            "worktree_root": "/tmp/candidate",\n            "head_oid": "abc123",\n            "status_sha256": ("f" * 64 if self.changed else D),\n        }\n\n    def get_repository_diff(self, _repository_id: str, *, kind: str) -> dict[str, object]:\n        self.calls.append("diff")\n        return {"kind": kind, "truncated": False, "sha256": E, "complete_bytes": 42}\n\n\ndef _runtime(changed: bool = False) -> tuple[Phase7Runtime, _Store, _Client]:\n    gap, candidate, _session, _repository, _diff = values()\n    record: dict[str, object] = {\n        "evolution_id": "evolution-7",\n        "state": "reviewed_pass",\n        "gap": {**gap, "mission_id": "mission-7", "attempt_id": "attempt-7", "capability_id": "capability-7"},\n        "candidate": {**candidate, "manifest_sha256": "a" * 64},\n    }\n    store = _Store(record)\n    client = _Client(changed=changed)\n    runtime = object.__new__(Phase7Runtime)\n    runtime.store = store\n    runtime.origins_client = client\n    runtime.approvals = _Bindings()\n    runtime.engineering_approvals = _Bindings()\n    return runtime, store, client\n\n\ndef test_canary_waits_for_terminal_session_before_repository_revalidation() -> None:\n    runtime, _store, client = _runtime()\n    result = runtime.record_canary_from_session("evolution-7", "session-7")\n    assert result["state"] == "canary_passed"\n    assert client.calls.index("wait") < client.calls.index("refresh")\n\n\ndef test_promote_revalidates_candidate_and_persists_evidence() -> None:\n    runtime, store, client = _runtime()\n    store.record["state"] = "canary_passed"\n    result = runtime.decide("evolution-7", decision="promote", decided_by="owner")\n    assert result["state"] == "promoted"\n    assert client.calls[:2] == ["refresh", "diff"]\n    assert store.decisions[0]["candidate_revalidation"]["repository_status_sha256"] == D\n\n\ndef test_promote_rejects_candidate_changed_after_canary() -> None:\n    runtime, store, _client = _runtime(changed=True)\n    store.record["state"] = "canary_passed"\n    with pytest.raises(Phase7RuntimeError, match="status changed after review"):\n        runtime.decide("evolution-7", decision="promote", decided_by="owner")\n    assert store.decisions == []\n\n\ndef test_rollback_does_not_require_candidate_revalidation() -> None:\n    runtime, store, client = _runtime(changed=True)\n    store.record["state"] = "canary_passed"\n    result = runtime.decide("evolution-7", decision="rollback", decided_by="owner")\n    assert result["state"] == "rolled_back"\n    assert client.calls == []\n    assert store.decisions[0]["candidate_revalidation"] is None\n'''
    if "from pathlib import Path" not in text:
        text = text.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nfrom pathlib import Path\n\n", 1)
    TEST.write_text(text, encoding="utf-8")


def patch_proofs() -> None:
    text = BASE_PROOF.read_text(encoding="utf-8")
    old = '''def _git_head(path: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=path)


def _sha(value: object) -> str:
'''
    new = '''def _git_head(path: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=path)


def _assert_tracked_clean(name: str, path: Path) -> None:
    for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        result = subprocess.run(args, cwd=path, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise ProofError(f"{name} checkout has tracked changes and cannot be used as exact proof")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha(value: object) -> str:
'''
    text = replace_once(text, old, new, "proof provenance helpers")
    old = '''    expected_head = os.environ.get("ORIGINS_PHASE7_EXPECTED_HEAD", "").strip()
    if expected_head and source_head != expected_head:
        raise ProofError(f"source head mismatch: expected {expected_head}, got {source_head}")

    owner_heads = {
'''
    new = '''    expected_head = os.environ.get("ORIGINS_PHASE7_EXPECTED_HEAD", "").strip()
    if not expected_head:
        raise ProofError("ORIGINS_PHASE7_EXPECTED_HEAD is required for exact-host proof")
    if source_head != expected_head:
        raise ProofError(f"source head mismatch: expected {expected_head}, got {source_head}")
    _assert_tracked_clean("origins-factory", source_root)

    owner_heads = {
'''
    text = replace_once(text, old, new, "required proof head")
    old = '''    if owner_heads != expected_owner_heads:
        raise ProofError(f"owner provenance mismatch: {owner_heads!r}")
    if not CODEOPS_CONFIG.is_file():
'''
    new = '''    if owner_heads != expected_owner_heads:
        raise ProofError(f"owner provenance mismatch: {owner_heads!r}")
    for name, path in (("Hunter-AgentOps", AGENTOPS_ROOT), ("hunter-codeops", CODEOPS_ROOT), ("Sergeant", SERGEANT_ROOT)):
        _assert_tracked_clean(name, path)
    if not CODEOPS_CONFIG.is_file():
'''
    text = replace_once(text, old, new, "owner clean provenance")
    old = '''            "source_head": source_head,
            "owner_heads": owner_heads,
'''
    new = '''            "source_head": source_head,
            "owner_heads": owner_heads,
            "originsd_sha256": _file_sha256(Path(os.environ.get("ORIGINS_PHASE7_DAEMON", str(DEFAULT_DAEMON))).resolve()),
'''
    text = replace_once(text, old, new, "daemon proof digest")
    BASE_PROOF.write_text(text, encoding="utf-8")

    strict = STRICT_PROOF.read_text(encoding="utf-8")
    old = '''            process_kwargs["executable"] = "python3"
            process_kwargs["args"] = ["-m", "pytest", "-q"]
'''
    new = '''            process_kwargs["executable"] = "python3"
            process_kwargs["args"] = ["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
'''
    strict = replace_once(strict, old, new, "strict canary no-write pytest")
    STRICT_PROOF.write_text(strict, encoding="utf-8")


def main() -> None:
    patch_runtime()
    patch_store()
    patch_tests()
    patch_proofs()


if __name__ == "__main__":
    main()
