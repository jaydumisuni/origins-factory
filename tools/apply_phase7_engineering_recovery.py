from __future__ import annotations

from pathlib import Path

STORE = Path("python/origins_integration/capability_evolution.py")
RUNTIME = Path("python/origins_integration/phase7_runtime.py")
INTELLIGENCE = Path("python/origins_integration/intelligence_runtime.py")
CAP_TEST = Path("python/tests/test_phase7_capability_evolution.py")
PROOF_TEST = Path("python/tests/test_phase7_candidate_proof.py")
UI = Path("workspace/src/Phase7App.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '            "child_operation": None,\n            "candidate": None,\n',
        '            "child_operation": None,\n            "engineering_attempt": None,\n            "candidate": None,\n',
        "engineering_attempt record field",
    )
    anchor = '''    def bind_candidate(self, evolution_id: str, candidate: Mapping[str, object]) -> dict[str, object]:\n'''
    method = '''    def begin_engineering(self, evolution_id: str, attempt: Mapping[str, object]) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "upgrade_operation_ready")
        repository_id = _text(attempt, "repository_id")
        approval_id = _text(attempt, "approval_id")
        subject_sha256 = _digest_value(attempt.get("subject_sha256"), "subject_sha256")
        pre_status = _digest_value(attempt.get("pre_repository_status_sha256"), "pre_repository_status_sha256")
        pre_head = _text(attempt, "pre_repository_head_oid")
        pre_revision = _positive_int(attempt.get("pre_repository_revision"), "pre_repository_revision")
        child = _mapping(record, "child_operation")
        operation_id = _text(attempt, "operation_id")
        if operation_id != str(child.get("operation_id") or ""):
            raise CapabilityEvolutionError("engineering attempt is not bound to the child upgrade Operation")
        record["engineering_attempt"] = {
            "operation_id": operation_id,
            "repository_id": repository_id,
            "approval_id": approval_id,
            "subject_sha256": subject_sha256,
            "pre_repository_status_sha256": pre_status,
            "pre_repository_head_oid": pre_head,
            "pre_repository_revision": pre_revision,
            "started_at": _now(),
        }
        return self._save(record, "engineering_started")

'''
    if method.strip() not in text:
        text = replace_once(text, anchor, method + anchor, "begin engineering method")
    text = replace_once(
        text,
        '        _state(record, "upgrade_operation_ready")\n        required = (\n',
        '        _state(record, "engineering_started")\n        required = (\n',
        "candidate state after engineering start",
    )
    STORE.write_text(text, encoding="utf-8")


def patch_intelligence() -> None:
    text = INTELLIGENCE.read_text(encoding="utf-8")
    text = text.replace("import importlib\n", "import hashlib\nimport importlib\nimport json\n", 1)
    old = '''        metadata: dict[str, object] = {
            "operation_id": operation_id,
            "repository_id": str(subject.get("repository_id", "")).strip(),
            "provider_id": str(subject.get("provider_id", "")),
            "mode": str(subject.get("mode", "quick_edit")),
            "apply_plan": bool(subject.get("apply_plan", False)),
            "status": status,
        }
'''
    new = '''        canonical_subject = _approval_subject("engineering", subject)
        metadata: dict[str, object] = {
            "operation_id": operation_id,
            "repository_id": str(subject.get("repository_id", "")).strip(),
            "provider_id": str(subject.get("provider_id", "")),
            "mode": str(subject.get("mode", "quick_edit")),
            "apply_plan": bool(subject.get("apply_plan", False)),
            "subject_sha256": hashlib.sha256(
                json.dumps(canonical_subject, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "status": status,
        }
'''
    text = replace_once(text, old, new, "engineering evidence subject digest")
    INTELLIGENCE.write_text(text, encoding="utf-8")


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    start = text.index("    def implement_candidate(")
    end = text.index("\n    def record_canary_from_session", start)
    new_method = '''    def implement_candidate(self, evolution_id: str, payload: dict[str, object]) -> dict[str, object]:
        record = self.store.get(evolution_id)
        state = str(record.get("state") or "")
        if state not in {"upgrade_operation_ready", "engineering_started"}:
            raise CapabilityEvolutionError(
                "candidate implementation requires a ready or restart-recoverable child upgrade Operation"
            )
        subject = _engineering_subject(record, payload)
        binding = self.engineering_approvals.require_approved(evolution_id, subject)
        repository_id = str(subject["repository_id"])
        subject_sha256 = sha256_json(subject)
        operation_id = str(subject["operation_id"])
        recovered_result: dict[str, object] | None = None

        if state == "upgrade_operation_ready":
            pre_repository = self.origins_client.refresh_repository(repository_id)
            record = self.store.begin_engineering(
                evolution_id,
                {
                    "operation_id": operation_id,
                    "repository_id": repository_id,
                    "approval_id": binding["approval_id"],
                    "subject_sha256": subject_sha256,
                    "pre_repository_status_sha256": pre_repository["status_sha256"],
                    "pre_repository_head_oid": pre_repository["head_oid"],
                    "pre_repository_revision": pre_repository["revision"],
                },
            )
        else:
            attempt = _mapping(record, "engineering_attempt")
            if attempt.get("operation_id") != operation_id or attempt.get("repository_id") != repository_id:
                raise Phase7RuntimeError("restart engineering request does not match the durable attempt identity")
            if attempt.get("approval_id") != binding["approval_id"]:
                raise Phase7RuntimeError("restart engineering approval does not match the durable attempt")
            if attempt.get("subject_sha256") != subject_sha256:
                raise Phase7RuntimeError("restart engineering subject changed after the durable attempt began")
            pre_repository = {
                "repository_id": repository_id,
                "status_sha256": attempt["pre_repository_status_sha256"],
                "head_oid": attempt["pre_repository_head_oid"],
                "revision": attempt["pre_repository_revision"],
            }
            recovered_result = _recover_completed_engineering_evidence(
                self.intelligence.agentops.snapshot(),
                operation_id=operation_id,
                repository_id=repository_id,
                subject_sha256=subject_sha256,
            )
            current = self.origins_client.refresh_repository(repository_id)
            changed = (
                current.get("status_sha256") != pre_repository.get("status_sha256")
                or current.get("head_oid") != pre_repository.get("head_oid")
            )
            if recovered_result is None and changed:
                raise Phase7RuntimeError(
                    "candidate engineering was interrupted after repository change without completed AgentOps evidence; "
                    "restore the candidate worktree to the durable pre-engineering state before retrying"
                )

        if recovered_result is None:
            command = dict(subject)
            command["approval_id"] = binding["approval_id"]
            result = self.intelligence.engineering_attempt(command)
        else:
            result = recovered_result

        post_repository = self.origins_client.refresh_repository(repository_id)
        repository_diff = self.origins_client.get_repository_diff(repository_id, kind="unstaged")
        change_proof = _candidate_change_proof(pre_repository, post_repository, repository_diff)
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise Phase7RuntimeError("CodeOps engineering result omitted retained evidence")
        agentops_evidence = result.get("agentops_evidence")
        if not isinstance(agentops_evidence, dict):
            raise Phase7RuntimeError("AgentOps engineering evidence is missing")
        evidence_id = agentops_evidence.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise Phase7RuntimeError("AgentOps engineering evidence omitted canonical evidence_id")
        proposal = _mapping(record, "proposal")
        current = self.store.active_generation(str(proposal["capability_id"]))
        base_generation = int(current["generation"]) if current else 0
        base_manifest_sha256 = str(current["manifest_sha256"]) if current else None
        base_evolution_id = str(current["evolution_id"]) if current else None
        generation = base_generation + 1
        manifest = {
            "schema_version": "origins.capability-generation.v1",
            "capability_id": proposal["capability_id"],
            "generation": generation,
            "requested_effects": proposal["requested_effects"],
            "filesystem_read_scope": proposal["filesystem_read_scope"],
            "filesystem_write_scope": proposal["filesystem_write_scope"],
            "network_mode": proposal["network_mode"],
            "network_hosts": proposal["network_hosts"],
            "environment_names": proposal["environment_names"],
            "persistent_lease": proposal["persistent_lease"],
            "delegated_remote_authority": proposal["delegated_remote_authority"],
            "repository_id": repository_id,
            "repository_revision": post_repository["revision"],
            "repository_head_oid": post_repository["head_oid"],
            "repository_status_sha256": post_repository["status_sha256"],
            "repository_diff_sha256": change_proof["diff_sha256"],
            "repository_diff_bytes": change_proof["diff_bytes"],
            "codeops_evidence_sha256": sha256_json(evidence),
        }
        manifest_sha = sha256_json(manifest)
        candidate = {
            "repository_id": repository_id,
            "repository_revision": post_repository["revision"],
            "repository_head_oid": post_repository["head_oid"],
            "repository_status_sha256": post_repository["status_sha256"],
            "repository_diff_sha256": change_proof["diff_sha256"],
            "repository_diff_bytes": change_proof["diff_bytes"],
            "base_generation": base_generation,
            "base_manifest_sha256": base_manifest_sha256,
            "base_evolution_id": base_evolution_id,
            "candidate_generation": generation,
            "manifest": manifest,
            "manifest_sha256": manifest_sha,
            "proof_sha256": sha256_json(
                {"engineering": evidence, "review_sha256": result["review_sha256"], "change_proof": change_proof}
            ),
            "codeops_evidence_ref": f"agentops:evidence:{evidence_id.strip()}",
            "engineering_recovered": recovered_result is not None,
        }
        self.store.bind_candidate(evolution_id, candidate)
        review = {
            "verdict": str(result["verdict"]).replace(" ", "_").upper(),
            "review_sha256": result["review_sha256"],
            "candidate_manifest_sha256": manifest_sha,
            "sergeant_evidence": result["evidence"],
        }
        return self._project(self.store.bind_sergeant_review(evolution_id, review))
'''
    text = text[:start] + new_method + text[end:]

    old_resume = '''    def resume(self, evolution_id: str) -> dict[str, object]:
        record = self.store.resume_mission(evolution_id)
        resume = _mapping(record, "resume")
        stores = self.intelligence.agentops._stores()
        evidence_module = importlib.import_module("agentops.evidence")
        evidence_type = getattr(evidence_module, "EvidenceItem")
        stored = stores.save_evidence(
            evidence_type(
                title="Origins capability evolution Mission resume",
                kind="tool_result",
                summary="Original Mission resume point preserved after controlled capability evolution.",
                source_ref=f"origins.evolution:{evolution_id}",
                metadata={"evolution_id": evolution_id, "resume": dict(resume)},
            )
        )
        return {"evolution": self._project(record), "agentops_evidence": stored}
'''
    new_resume = '''    def resume(self, evolution_id: str) -> dict[str, object]:
        existing = self.store.get(evolution_id)
        record = existing if existing.get("state") == "mission_resumed" else self.store.resume_mission(evolution_id)
        resume = _mapping(record, "resume")
        stores = self.intelligence.agentops._stores()
        stored = _find_resume_evidence(stores.snapshot(), evolution_id, resume)
        if stored is None:
            evidence_module = importlib.import_module("agentops.evidence")
            evidence_type = getattr(evidence_module, "EvidenceItem")
            stored = stores.save_evidence(
                evidence_type(
                    title="Origins capability evolution Mission resume",
                    kind="tool_result",
                    summary="Original Mission resume point preserved after controlled capability evolution.",
                    source_ref=f"origins.evolution:{evolution_id}",
                    metadata={"evolution_id": evolution_id, "resume": dict(resume)},
                )
            )
        return {"evolution": self._project(record), "agentops_evidence": stored}
'''
    text = replace_once(text, old_resume, new_resume, "idempotent resume")

    helper_anchor = '''def _find_pending_owner_approval(service: object, expected_metadata: Mapping[str, object]) -> str | None:\n'''
    helpers = '''def _recover_completed_engineering_evidence(
    snapshot: Mapping[str, object],
    *,
    operation_id: str,
    repository_id: str,
    subject_sha256: str,
) -> dict[str, object] | None:
    raw_items = snapshot.get("evidence")
    if not isinstance(raw_items, list):
        raise Phase7RuntimeError("AgentOps evidence snapshot is malformed")
    matches: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, Mapping) or item.get("source_ref") != f"origins.operation:{operation_id}":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if metadata.get("operation_id") != operation_id or metadata.get("repository_id") != repository_id:
            continue
        if metadata.get("subject_sha256") != subject_sha256 or metadata.get("status") != "completed":
            continue
        if metadata.get("apply_plan") is not True:
            continue
        evidence = metadata.get("origins_attempt_evidence")
        if not isinstance(evidence, Mapping):
            continue
        if evidence.get("operation_id") != operation_id or evidence.get("repository_id") != repository_id:
            continue
        plan_apply_session_id = evidence.get("plan_apply_session_id")
        review_sha256 = evidence.get("review_sha256")
        verdict = str(metadata.get("verdict") or "").replace(" ", "_").upper()
        if not isinstance(plan_apply_session_id, str) or not plan_apply_session_id.strip():
            continue
        if not isinstance(review_sha256, str) or len(review_sha256) != 64:
            continue
        if verdict not in {"PASS", "NEEDS_WORK", "BLOCK"}:
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            continue
        matches.append(
            {
                "verdict": verdict.replace("_", " "),
                "review_sha256": review_sha256,
                "evidence": dict(evidence),
                "agentops_evidence": dict(item),
            }
        )
    if len(matches) > 1:
        raise Phase7RuntimeError("multiple completed AgentOps engineering evidence records match the durable attempt")
    return matches[0] if matches else None


def _find_resume_evidence(
    snapshot: Mapping[str, object], evolution_id: str, resume: Mapping[str, object]
) -> dict[str, object] | None:
    raw_items = snapshot.get("evidence")
    if not isinstance(raw_items, list):
        raise Phase7RuntimeError("AgentOps evidence snapshot is malformed")
    matches: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, Mapping) or item.get("source_ref") != f"origins.evolution:{evolution_id}":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if metadata.get("evolution_id") == evolution_id and metadata.get("resume") == dict(resume):
            matches.append(dict(item))
    if len(matches) > 1:
        raise Phase7RuntimeError("multiple AgentOps Mission-resume evidence records match this evolution")
    return matches[0] if matches else None


'''
    if helpers.strip() not in text:
        text = replace_once(text, helper_anchor, helpers + helper_anchor, "engineering recovery helpers")
    RUNTIME.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = CAP_TEST.read_text(encoding="utf-8")
    helper_anchor = '''def child(evolution_id: str) -> dict[str, object]:\n'''
    helper = '''def engineering_attempt() -> dict[str, object]:
    return {
        "operation_id": "child-7",
        "repository_id": "repo-7",
        "approval_id": "engineering-7",
        "subject_sha256": "9" * 64,
        "pre_repository_status_sha256": "8" * 64,
        "pre_repository_head_oid": "head-before",
        "pre_repository_revision": 1,
    }


'''
    if helper.strip() not in text:
        text = replace_once(text, helper_anchor, helper + helper_anchor, "engineering test helper")
    text = text.replace(
        '''    store.bind_candidate(
        evolution_id,
''',
        '''    store.begin_engineering(evolution_id, engineering_attempt())
    store.bind_candidate(
        evolution_id,
''',
    )
    CAP_TEST.write_text(text, encoding="utf-8")

    proof = PROOF_TEST.read_text(encoding="utf-8")
    proof = proof.replace(
        "from origins_integration.phase7_runtime import Phase7RuntimeError, _candidate_change_proof, _engineering_subject\n",
        "from origins_integration.phase7_runtime import (\n    Phase7RuntimeError,\n    _candidate_change_proof,\n    _engineering_subject,\n    _find_resume_evidence,\n    _recover_completed_engineering_evidence,\n)\n",
        1,
    )
    if "test_completed_engineering_evidence_recovery_is_exact" not in proof:
        proof += '''\n\ndef test_completed_engineering_evidence_recovery_is_exact() -> None:\n    subject_sha = "+" * 64\n    review_sha = "a" * 64\n    item = {\n        "evidence_id": "evidence-7",\n        "source_ref": "origins.operation:child-7",\n        "metadata": {\n            "operation_id": "child-7",\n            "repository_id": "repo-7",\n            "subject_sha256": subject_sha,\n            "status": "completed",\n            "apply_plan": True,\n            "verdict": "PASS",\n            "origins_attempt_evidence": {\n                "operation_id": "child-7",\n                "repository_id": "repo-7",\n                "plan_apply_session_id": "session-apply",\n                "review_sha256": review_sha,\n            },\n        },\n    }\n    recovered = _recover_completed_engineering_evidence(\n        {"evidence": [item]}, operation_id="child-7", repository_id="repo-7", subject_sha256=subject_sha\n    )\n    assert recovered is not None\n    assert recovered["review_sha256"] == review_sha\n    assert recovered["agentops_evidence"]["evidence_id"] == "evidence-7"\n    assert _recover_completed_engineering_evidence(\n        {"evidence": [item]}, operation_id="child-7", repository_id="repo-7", subject_sha256="b" * 64\n    ) is None\n    with pytest.raises(Phase7RuntimeError, match="multiple completed"):\n        _recover_completed_engineering_evidence(\n            {"evidence": [item, {**item, "evidence_id": "evidence-8"}]},\n            operation_id="child-7", repository_id="repo-7", subject_sha256=subject_sha,\n        )\n\n\ndef test_resume_evidence_recovery_is_exact() -> None:\n    resume = {"resume_token": "token-7", "resume_state_sha256": "c" * 64}\n    item = {\n        "evidence_id": "resume-evidence-7",\n        "source_ref": "origins.evolution:evolution-7",\n        "metadata": {"evolution_id": "evolution-7", "resume": resume},\n    }\n    assert _find_resume_evidence({"evidence": [item]}, "evolution-7", resume) == item\n    assert _find_resume_evidence({"evidence": [item]}, "other", resume) is None\n'''
    PROOF_TEST.write_text(proof, encoding="utf-8")


def patch_ui() -> None:
    text = UI.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '  const canImplement = selected?.state === "upgrade_operation_ready" && engApproved;\n',
        '  const canImplement = (selected?.state === "upgrade_operation_ready" || selected?.state === "engineering_started") && engApproved;\n',
        "engineering recovery UI state",
    )
    text = text.replace("Implement candidate", "Implement / recover candidate", 1)
    UI.write_text(text, encoding="utf-8")


def main() -> None:
    patch_store()
    patch_intelligence()
    patch_runtime()
    patch_tests()
    patch_ui()


if __name__ == "__main__":
    main()
