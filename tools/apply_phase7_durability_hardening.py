from __future__ import annotations

from pathlib import Path

RUNTIME = Path("python/origins_integration/phase7_runtime.py")
STORE = Path("python/origins_integration/capability_evolution.py")
APPROVALS = Path("python/origins_integration/capability_evolution_approvals.py")
APPROVAL_TEST = Path("python/tests/test_phase7_approval_binding.py")
CAP_TEST = Path("python/tests/test_phase7_capability_evolution.py")
UI = Path("workspace/src/Phase7App.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    text = text.replace("import uuid\n", "", 1)

    old = '''        request = service.create_request(
            task_title=str(proposal["task_title"]),
'''
    new = '''        recovered_id = _find_pending_owner_approval(
            service,
            {
                "origins_approval_kind": "capability",
                "evolution_id": evolution_id,
                "proposal": dict(proposal),
            },
        )
        if recovered_id is not None:
            evidence = service.get_evidence(recovered_id).public_dict()
            binding = self.approvals.bind(evolution_id, evidence)
            return {
                "owner": "Hunter-AgentOps",
                "approval": service.get_state(recovered_id).public_dict(),
                "binding": binding,
                "recovered_pending": True,
            }
        request = service.create_request(
            task_title=str(proposal["task_title"]),
'''
    text = replace_once(text, old, new, "capability pending approval recovery")

    old = '''        operation_id = f"cap-upgrade-{uuid.uuid4()}"
'''
    new = '''        operation_id = f"cap-upgrade-{evolution_id}"
'''
    text = replace_once(text, old, new, "deterministic child operation id")

    old = '''        created = self.intelligence.create_approval(
            {
                "kind": "engineering",
'''
    new = '''        service = self.intelligence.agentops._stores().approval_service()
        recovered_id = _find_pending_owner_approval(
            service,
            {"origins_approval_kind": "engineering", "subject": subject},
        )
        if recovered_id is not None:
            evidence = service.get_evidence(recovered_id).public_dict()
            binding = self.engineering_approvals.bind(evolution_id, subject=subject, evidence=evidence)
            return {
                "owner": "Hunter-AgentOps",
                "approval": service.get_state(recovered_id).public_dict(),
                "binding": binding,
                "engineering_subject": subject,
                "recovered_pending": True,
            }
        created = self.intelligence.create_approval(
            {
                "kind": "engineering",
'''
    text = replace_once(text, old, new, "engineering pending approval recovery")

    anchor = '''def _engineering_subject(record: Mapping[str, object], payload: Mapping[str, object]) -> dict[str, object]:
'''
    helper = '''def _find_pending_owner_approval(service: object, expected_metadata: Mapping[str, object]) -> str | None:
    list_pending = getattr(service, "list_pending", None)
    if not callable(list_pending):
        raise Phase7RuntimeError("AgentOps approval service does not expose durable pending approvals")
    matches: list[str] = []
    for item in list_pending():
        if not isinstance(item, Mapping):
            continue
        request = item.get("request")
        metadata = request.get("metadata") if isinstance(request, Mapping) else None
        if not isinstance(metadata, Mapping):
            continue
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            continue
        approval_id = request.get("approval_id")
        if isinstance(approval_id, str) and approval_id.strip():
            matches.append(approval_id.strip())
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        raise Phase7RuntimeError("multiple pending AgentOps approvals match the same Phase 7 subject")
    return unique[0] if unique else None


'''
    if helper.strip() not in text:
        text = replace_once(text, anchor, helper + anchor, "pending approval helper")
    RUNTIME.write_text(text, encoding="utf-8")


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    old = '''        evolution_id = str(record["evolution_id"])
        row = db.execute("SELECT revision FROM evolutions WHERE evolution_id=?", (evolution_id,)).fetchone()
        if row is None:
            raise CapabilityEvolutionError(f"unknown evolution {evolution_id}")
        revision = int(row["revision"]) + 1
        record["state"] = state
        record["updated_at"] = now
        record["revision"] = revision
        db.execute(
            "UPDATE evolutions SET state=?, record_json=?, revision=?, updated_at=? WHERE evolution_id=?",
            (state, _json(record), revision, now, evolution_id),
        )
'''
    new = '''        evolution_id = str(record["evolution_id"])
        expected_revision = _positive_int(record.get("revision"), "revision")
        row = db.execute("SELECT revision FROM evolutions WHERE evolution_id=?", (evolution_id,)).fetchone()
        if row is None:
            raise CapabilityEvolutionError(f"unknown evolution {evolution_id}")
        current_revision = int(row["revision"])
        if current_revision != expected_revision:
            raise CapabilityEvolutionError(
                f"evolution changed concurrently: expected revision {expected_revision}, current is {current_revision}"
            )
        revision = current_revision + 1
        record["state"] = state
        record["updated_at"] = now
        record["revision"] = revision
        cursor = db.execute(
            "UPDATE evolutions SET state=?, record_json=?, revision=?, updated_at=? WHERE evolution_id=? AND revision=?",
            (state, _json(record), revision, now, evolution_id, expected_revision),
        )
        if cursor.rowcount != 1:
            raise CapabilityEvolutionError("evolution revision changed during durable update")
'''
    text = replace_once(text, old, new, "evolution revision CAS")
    STORE.write_text(text, encoding="utf-8")


def patch_approvals() -> None:
    text = APPROVALS.read_text(encoding="utf-8")
    old = '''        previous = self.get(evolution_id)
        _validate_replacement(previous, approval_id, status)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
'''
    new = '''        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT approval_id, status FROM evolution_approval_bindings WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
            previous = None if row is None else {
                "approval_id": str(row["approval_id"]),
                "status": str(row["status"]),
            }
            _validate_replacement(previous, approval_id, status)
            db.execute(
'''
    text = replace_once(text, old, new, "capability approval transaction")

    old = '''        previous = self.get(evolution_id)
        if previous is not None and previous["subject_sha256"] != subject_sha256:
            if previous["status"] in {"pending", "approved"}:
                raise CapabilityEvolutionError("cannot change an engineering subject with a pending or approved binding")
        _validate_replacement(previous, approval_id, status)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
'''
    new = '''        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT approval_id, status, subject_sha256 FROM evolution_engineering_approvals WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
            previous = None if row is None else {
                "approval_id": str(row["approval_id"]),
                "status": str(row["status"]),
                "subject_sha256": str(row["subject_sha256"]),
            }
            if previous is not None and previous["subject_sha256"] != subject_sha256:
                if previous["status"] in {"pending", "approved"}:
                    raise CapabilityEvolutionError("cannot change an engineering subject with a pending or approved binding")
            _validate_replacement(previous, approval_id, status)
            db.execute(
'''
    text = replace_once(text, old, new, "engineering approval transaction")
    APPROVALS.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = APPROVAL_TEST.read_text(encoding="utf-8")
    if "_find_pending_owner_approval" not in text:
        text = text.replace(
            "from origins_integration.capability_evolution_approvals import (\n",
            "from origins_integration.phase7_runtime import Phase7RuntimeError, _find_pending_owner_approval\nfrom origins_integration.capability_evolution_approvals import (\n",
            1,
        )
    if "test_pending_owner_approval_recovery_is_exact_and_ambiguous_matches_fail" not in text:
        text += '''\n\nclass _PendingService:\n    def __init__(self, items: list[dict[str, object]]) -> None:\n        self.items = items\n\n    def list_pending(self) -> list[dict[str, object]]:\n        return self.items\n\n\ndef _pending(approval_id: str, metadata: dict[str, object]) -> dict[str, object]:\n    return {"request": {"approval_id": approval_id, "metadata": metadata}, "record": None, "approved": False}\n\n\ndef test_pending_owner_approval_recovery_is_exact_and_ambiguous_matches_fail() -> None:\n    expected = {"origins_approval_kind": "capability", "evolution_id": "evolution-7"}\n    service = _PendingService([\n        _pending("other", {"origins_approval_kind": "capability", "evolution_id": "other"}),\n        _pending("match", expected),\n    ])\n    assert _find_pending_owner_approval(service, expected) == "match"\n    duplicate = _PendingService([_pending("a", expected), _pending("b", expected)])\n    with pytest.raises(Phase7RuntimeError, match="multiple pending"):\n        _find_pending_owner_approval(duplicate, expected)\n\n\ndef test_concurrent_first_capability_binding_cannot_replace_pending_binding(tmp_path: Path) -> None:\n    import threading\n\n    path = tmp_path / "phase7.sqlite"\n    barrier = threading.Barrier(2)\n\n    class LegacyRaceProbe(EvolutionApprovalBindings):\n        def get(self, evolution_id: str):\n            value = super().get(evolution_id)\n            barrier.wait(timeout=5)\n            return value\n\n    bindings = LegacyRaceProbe(path)\n    errors: list[Exception] = []\n\n    def bind(approval_id: str) -> None:\n        try:\n            bindings.bind("evolution-7", evidence(approval_id, "pending"))\n        except Exception as exc:  # expected loser\n            errors.append(exc)\n\n    threads = [threading.Thread(target=bind, args=(approval_id,)) for approval_id in ("approval-a", "approval-b")]\n    for thread in threads:\n        thread.start()\n    for thread in threads:\n        thread.join(timeout=5)\n    assert all(not thread.is_alive() for thread in threads)\n    assert len(errors) == 1\n    assert "cannot replace" in str(errors[0])\n    stored = EvolutionApprovalBindings(path).get("evolution-7")\n    assert stored is not None and stored["approval_id"] in {"approval-a", "approval-b"}\n'''
    APPROVAL_TEST.write_text(text, encoding="utf-8")

    cap = CAP_TEST.read_text(encoding="utf-8")
    if "test_stale_evolution_record_cannot_overwrite_newer_revision" not in cap:
        cap += '''\n\ndef test_stale_evolution_record_cannot_overwrite_newer_revision(tmp_path: Path) -> None:\n    store = CapabilityEvolutionStore(tmp_path / "phase7.sqlite")\n    created = store.create_gap(gap_payload())\n    first = store.get(str(created["evolution_id"]))\n    stale = store.get(str(created["evolution_id"]))\n    store._save(first, "gap_confirmed")\n    with pytest.raises(CapabilityEvolutionError, match="changed concurrently"):\n        store._save(stale, "gap_confirmed")\n'''
    CAP_TEST.write_text(cap, encoding="utf-8")


def patch_ui() -> None:
    text = UI.read_text(encoding="utf-8")
    old = '''                <label>Reviewed implementation plan<textarea value={plan} onChange={(e) => setPlan(e.target.value)} /></label>
'''
    new = '''                <label>Reviewed implementation plan path<input value={plan} onChange={(e) => setPlan(e.target.value)} placeholder="relative/path/to/plan.json" /></label>
'''
    text = replace_once(text, old, new, "Workspace plan path field")
    UI.write_text(text, encoding="utf-8")


def main() -> None:
    patch_runtime()
    patch_store()
    patch_approvals()
    patch_tests()
    patch_ui()


if __name__ == "__main__":
    main()
