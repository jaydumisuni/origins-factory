from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol


class CapabilityEvolutionError(ValueError):
    """Raised when a capability-evolution transition is unsafe or inconsistent."""


class AgentOpsEvolutionPort(Protocol):
    def assert_capability_approved(self, proposal: dict[str, object], approval_id: str) -> dict[str, object]: ...
    def create_capability_upgrade_operation(
        self,
        *,
        parent_operation_id: str,
        evolution_id: str,
        proposal: dict[str, object],
        approval_id: str,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class GapEvidence:
    mission_id: str
    parent_operation_id: str
    workspace_id: str
    attempt_id: str
    resume_token: str
    resume_state_sha256: str
    capability_id: str
    expected_effects: tuple[str, ...]
    actual_effects: tuple[str, ...]
    actual_manifest_sha256: str
    refusal_code: str
    evidence_refs: tuple[str, ...]
    summary: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "GapEvidence":
        item = cls(
            mission_id=_text(payload, "mission_id"),
            parent_operation_id=_text(payload, "parent_operation_id"),
            workspace_id=_text(payload, "workspace_id"),
            attempt_id=_text(payload, "attempt_id"),
            resume_token=_text(payload, "resume_token"),
            resume_state_sha256=_digest(payload, "resume_state_sha256"),
            capability_id=_text(payload, "capability_id", 160),
            expected_effects=_strings(payload.get("expected_effects"), "expected_effects"),
            actual_effects=_strings(payload.get("actual_effects", []), "actual_effects", allow_empty=True),
            actual_manifest_sha256=_digest(payload, "actual_manifest_sha256"),
            refusal_code=_text(payload, "refusal_code", 120),
            evidence_refs=_strings(payload.get("evidence_refs"), "evidence_refs"),
            summary=_text(payload, "summary", 1200),
        )
        missing = sorted(set(item.expected_effects) - set(item.actual_effects))
        if not missing:
            raise CapabilityEvolutionError(
                "gap evidence must prove at least one expected effect is absent from the current manifest"
            )
        if len(set(item.evidence_refs)) < 2:
            raise CapabilityEvolutionError("gap confirmation requires at least two distinct evidence references")
        if item.refusal_code in {"", "UNKNOWN", "UNSPECIFIED"}:
            raise CapabilityEvolutionError("gap evidence requires a bounded refusal code")
        return item

    def as_dict(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "parent_operation_id": self.parent_operation_id,
            "workspace_id": self.workspace_id,
            "attempt_id": self.attempt_id,
            "resume_token": self.resume_token,
            "resume_state_sha256": self.resume_state_sha256,
            "capability_id": self.capability_id,
            "expected_effects": list(self.expected_effects),
            "actual_effects": list(self.actual_effects),
            "actual_manifest_sha256": self.actual_manifest_sha256,
            "refusal_code": self.refusal_code,
            "evidence_refs": list(self.evidence_refs),
            "summary": self.summary,
        }


class CapabilityEvolutionStore:
    """Durable Origins coordination state; owner systems retain their own canonical records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evolutions (
                    evolution_id TEXT PRIMARY KEY,
                    capability_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evolutions_capability
                    ON evolutions(capability_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS active_generations (
                    capability_id TEXT PRIMARY KEY,
                    generation INTEGER NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    evolution_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def create_gap(self, payload: Mapping[str, object]) -> dict[str, object]:
        gap = GapEvidence.from_payload(payload)
        now = _now()
        evolution_id = str(uuid.uuid4())
        record: dict[str, object] = {
            "schema_version": "origins.capability-evolution.v1",
            "evolution_id": evolution_id,
            "state": "gap_confirmed",
            "gap": gap.as_dict(),
            "proposal": None,
            "approval": None,
            "child_operation": None,
            "candidate": None,
            "sergeant_review": None,
            "canary": None,
            "promotion": None,
            "resume": None,
            "created_at": now,
            "updated_at": now,
            "revision": 1,
        }
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO evolutions(evolution_id, capability_id, state, record_json, revision, updated_at) VALUES(?,?,?,?,?,?)",
                (evolution_id, gap.capability_id, "gap_confirmed", _json(record), 1, now),
            )
            db.commit()
        return record

    def get(self, evolution_id: str) -> dict[str, object]:
        with self._connect() as db:
            row = db.execute(
                "SELECT record_json FROM evolutions WHERE evolution_id=?", (evolution_id,)
            ).fetchone()
        if row is None:
            raise CapabilityEvolutionError(f"unknown evolution {evolution_id}")
        value = json.loads(str(row["record_json"]))
        if not isinstance(value, dict):
            raise CapabilityEvolutionError("evolution record is corrupt")
        return value

    def list(self) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute("SELECT record_json FROM evolutions ORDER BY updated_at DESC").fetchall()
        return [json.loads(str(row["record_json"])) for row in rows]

    def active_generation(self, capability_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT capability_id, generation, manifest_sha256, evolution_id, updated_at FROM active_generations WHERE capability_id=?",
                (capability_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def bind_proposal(self, evolution_id: str, proposal: Mapping[str, object]) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "gap_confirmed")
        gap = _mapping(record, "gap")
        if proposal.get("capability_id") != gap.get("capability_id"):
            raise CapabilityEvolutionError("proposal capability does not match confirmed gap")
        if proposal.get("workspace_id") != gap.get("workspace_id"):
            raise CapabilityEvolutionError("proposal workspace does not match original Mission")
        if proposal.get("approval_required") is not True or proposal.get("self_approvable") is not False:
            raise CapabilityEvolutionError("capability proposal must require external approval")
        expected = set(_list_of_strings(gap.get("expected_effects"), "gap.expected_effects"))
        requested = set(_list_of_strings(proposal.get("requested_effects"), "proposal.requested_effects"))
        if not expected.issubset(requested):
            raise CapabilityEvolutionError("proposal does not cover the confirmed missing effects")
        record["proposal"] = dict(proposal)
        return self._save(record, "proposal_ready")

    def bind_child_operation(
        self,
        evolution_id: str,
        *,
        approval: Mapping[str, object],
        child_operation: Mapping[str, object],
    ) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "proposal_ready")
        if approval.get("status") != "approved":
            raise CapabilityEvolutionError("owner approval is not approved")
        operation = child_operation.get("operation")
        if not isinstance(operation, Mapping):
            raise CapabilityEvolutionError("AgentOps child operation is malformed")
        if child_operation.get("accepted") is not True or child_operation.get("execution_dispatched") is not False:
            raise CapabilityEvolutionError("AgentOps child operation must be accepted but undispatched")
        gap = _mapping(record, "gap")
        refs = _list_of_strings(_mapping(operation, "evidence").get("evidence_refs"), "operation.evidence_refs")
        if f"origins:parent-operation:{gap['parent_operation_id']}" not in refs:
            raise CapabilityEvolutionError("child operation is not bound to the parent Mission operation")
        if f"origins:evolution:{evolution_id}" not in refs:
            raise CapabilityEvolutionError("child operation is not bound to this evolution")
        record["approval"] = dict(approval)
        record["child_operation"] = dict(child_operation)
        return self._save(record, "upgrade_operation_ready")

    def bind_candidate(self, evolution_id: str, candidate: Mapping[str, object]) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "upgrade_operation_ready")
        required = (
            "repository_id",
            "repository_revision",
            "candidate_generation",
            "manifest_sha256",
            "proof_sha256",
            "codeops_evidence_ref",
        )
        for field in required:
            if field not in candidate:
                raise CapabilityEvolutionError(f"candidate missing {field}")
        generation = _positive_int(candidate.get("candidate_generation"), "candidate_generation")
        manifest_sha = _digest_value(candidate.get("manifest_sha256"), "manifest_sha256")
        proof_sha = _digest_value(candidate.get("proof_sha256"), "proof_sha256")
        capability_id = str(_mapping(record, "gap")["capability_id"])
        current = self.active_generation(capability_id)
        if current is not None and generation <= int(current["generation"]):
            raise CapabilityEvolutionError("candidate generation must advance the active generation")
        clean = dict(candidate)
        clean["candidate_generation"] = generation
        clean["manifest_sha256"] = manifest_sha
        clean["proof_sha256"] = proof_sha
        record["candidate"] = clean
        return self._save(record, "candidate_proven")

    def bind_sergeant_review(self, evolution_id: str, review: Mapping[str, object]) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "candidate_proven")
        verdict = str(review.get("verdict") or "").strip().upper()
        if verdict not in {"PASS", "NEEDS_WORK", "BLOCK"}:
            raise CapabilityEvolutionError("unsupported Sergeant verdict")
        review_sha = _digest_value(review.get("review_sha256"), "review_sha256")
        candidate = _mapping(record, "candidate")
        if review.get("candidate_manifest_sha256") != candidate.get("manifest_sha256"):
            raise CapabilityEvolutionError("Sergeant review is not bound to the candidate manifest")
        clean = dict(review)
        clean["verdict"] = verdict
        clean["review_sha256"] = review_sha
        record["sergeant_review"] = clean
        return self._save(record, "reviewed_pass" if verdict == "PASS" else "reviewed_rejected")

    def record_canary(self, evolution_id: str, canary: Mapping[str, object]) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "reviewed_pass")
        gap = _mapping(record, "gap")
        candidate = _mapping(record, "candidate")
        if canary.get("mission_id") != gap.get("mission_id") or canary.get("attempt_id") != gap.get("attempt_id"):
            raise CapabilityEvolutionError("canary must run against the Mission/Attempt that exposed the gap")
        if canary.get("manifest_sha256") != candidate.get("manifest_sha256"):
            raise CapabilityEvolutionError("canary is not bound to the reviewed candidate manifest")
        if canary.get("authority_expanded") is not False:
            raise CapabilityEvolutionError("canary must not expand authority beyond the accepted manifest")
        if str(canary.get("outcome") or "").lower() != "passed":
            raise CapabilityEvolutionError("only a passed canary may enter promotion review")
        clean = dict(canary)
        clean["proof_sha256"] = _digest_value(canary.get("proof_sha256"), "proof_sha256")
        record["canary"] = clean
        return self._save(record, "canary_passed")

    def decide(self, evolution_id: str, *, decision: str, decided_by: str) -> dict[str, object]:
        record = self.get(evolution_id)
        _state(record, "canary_passed")
        decision = decision.strip().lower()
        if decision not in {"promote", "rollback"}:
            raise CapabilityEvolutionError("decision must be promote or rollback")
        if not decided_by.strip():
            raise CapabilityEvolutionError("decided_by is required")
        candidate = _mapping(record, "candidate")
        capability_id = str(_mapping(record, "gap")["capability_id"])
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT generation, manifest_sha256, evolution_id FROM active_generations WHERE capability_id=?",
                (capability_id,),
            ).fetchone()
            previous = dict(row) if row is not None else None
            promotion: dict[str, object] = {
                "decision": decision,
                "decided_by": decided_by.strip(),
                "decided_at": now,
                "previous_generation": previous,
            }
            if decision == "promote":
                generation = _positive_int(candidate.get("candidate_generation"), "candidate_generation")
                manifest_sha = _digest_value(candidate.get("manifest_sha256"), "manifest_sha256")
                db.execute(
                    "INSERT INTO active_generations(capability_id,generation,manifest_sha256,evolution_id,updated_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(capability_id) DO UPDATE SET generation=excluded.generation, manifest_sha256=excluded.manifest_sha256, evolution_id=excluded.evolution_id, updated_at=excluded.updated_at",
                    (capability_id, generation, manifest_sha, evolution_id, now),
                )
                promotion["active_generation"] = {
                    "capability_id": capability_id,
                    "generation": generation,
                    "manifest_sha256": manifest_sha,
                    "evolution_id": evolution_id,
                }
                next_state = "promoted"
            else:
                promotion["active_generation"] = previous
                next_state = "rolled_back"
            record["promotion"] = promotion
            self._save_in_transaction(db, record, next_state, now)
            db.commit()
        return self.get(evolution_id)

    def resume_mission(self, evolution_id: str) -> dict[str, object]:
        record = self.get(evolution_id)
        if record.get("state") not in {"promoted", "rolled_back"}:
            raise CapabilityEvolutionError("original Mission may resume only after explicit promote/rollback decision")
        gap = _mapping(record, "gap")
        record["resume"] = {
            "mission_id": gap["mission_id"],
            "parent_operation_id": gap["parent_operation_id"],
            "attempt_id": gap["attempt_id"],
            "resume_token": gap["resume_token"],
            "resume_state_sha256": gap["resume_state_sha256"],
            "resumed_at": _now(),
            "exact_pre_upgrade_state_preserved": True,
        }
        return self._save(record, "mission_resumed")

    def _save(self, record: dict[str, object], state: str) -> dict[str, object]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._save_in_transaction(db, record, state, _now())
            db.commit()
        return self.get(str(record["evolution_id"]))

    def _save_in_transaction(
        self, db: sqlite3.Connection, record: dict[str, object], state: str, now: str
    ) -> None:
        evolution_id = str(record["evolution_id"])
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


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(payload: Mapping[str, object], field: str, limit: int = 500) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityEvolutionError(f"{field} is required")
    clean = value.strip()
    if len(clean) > limit:
        raise CapabilityEvolutionError(f"{field} exceeds {limit} characters")
    return clean


def _digest(payload: Mapping[str, object], field: str) -> str:
    return _digest_value(payload.get(field), field)


def _digest_value(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise CapabilityEvolutionError(f"{field} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise CapabilityEvolutionError(f"{field} must be a SHA-256 digest") from exc
    return value.lower()


def _strings(value: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise CapabilityEvolutionError(f"{field} must be a list of strings")
    clean = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
    if not clean and not allow_empty:
        raise CapabilityEvolutionError(f"{field} cannot be empty")
    return clean


def _list_of_strings(value: object, field: str) -> list[str]:
    return list(_strings(value, field))


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CapabilityEvolutionError(f"{field} must be a positive integer")
    return value


def _mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise CapabilityEvolutionError(f"{field} is missing or malformed")
    return value


def _state(record: Mapping[str, object], expected: str) -> None:
    if record.get("state") != expected:
        raise CapabilityEvolutionError(f"evolution must be in {expected}, not {record.get('state')}")


def sha256_json(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
