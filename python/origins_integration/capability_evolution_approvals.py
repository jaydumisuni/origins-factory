from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .capability_evolution import CapabilityEvolutionError


class EvolutionApprovalBindings:
    """Durable relationship between an Origins evolution and AgentOps capability approval."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_approval_bindings (
                    evolution_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.path)

    def get(self, evolution_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT evolution_id, approval_id, status, request_digest, evidence_json, updated_at "
                "FROM evolution_approval_bindings WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
        if row is None:
            return None
        evidence = _decode_evidence(row["evidence_json"])
        return {
            "evolution_id": str(row["evolution_id"]),
            "approval_id": str(row["approval_id"]),
            "status": str(row["status"]),
            "request_digest": str(row["request_digest"]),
            "evidence": evidence,
            "updated_at": str(row["updated_at"]),
        }

    def bind(self, evolution_id: str, evidence: Mapping[str, object]) -> dict[str, object]:
        approval_id = _required(evidence, "approval_id")
        status = _status(evidence)
        request_digest = _digest(evidence, "request_digest")
        now = _now()
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
                "INSERT INTO evolution_approval_bindings(evolution_id,approval_id,status,request_digest,evidence_json,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(evolution_id) DO UPDATE SET "
                "approval_id=excluded.approval_id,status=excluded.status,request_digest=excluded.request_digest,"
                "evidence_json=excluded.evidence_json,updated_at=excluded.updated_at",
                (evolution_id, approval_id, status, request_digest, _json(evidence), now),
            )
            db.commit()
        binding = self.get(evolution_id)
        assert binding is not None
        return binding

    def require_approved(self, evolution_id: str, approval_id: str) -> dict[str, object]:
        binding = self.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps capability approval binding")
        if binding["approval_id"] != approval_id:
            raise CapabilityEvolutionError("AgentOps capability approval ID does not match the durable evolution binding")
        if binding["status"] != "approved":
            raise CapabilityEvolutionError("AgentOps capability approval binding is not approved")
        return binding


class EvolutionEngineeringApprovalBindings:
    """Durable AgentOps approval binding for the exact CodeOps engineering subject."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_engineering_approvals (
                    evolution_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    subject_sha256 TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.path)

    def get(self, evolution_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT evolution_id, approval_id, status, subject_sha256, request_digest, evidence_json, updated_at "
                "FROM evolution_engineering_approvals WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "evolution_id": str(row["evolution_id"]),
            "approval_id": str(row["approval_id"]),
            "status": str(row["status"]),
            "subject_sha256": str(row["subject_sha256"]),
            "request_digest": str(row["request_digest"]),
            "evidence": _decode_evidence(row["evidence_json"]),
            "updated_at": str(row["updated_at"]),
        }

    def bind(
        self,
        evolution_id: str,
        *,
        subject: Mapping[str, object],
        evidence: Mapping[str, object],
    ) -> dict[str, object]:
        approval_id = _required(evidence, "approval_id")
        status = _status(evidence)
        request_digest = _digest(evidence, "request_digest")
        subject_sha256 = _sha256_json(subject)
        now = _now()
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
                "INSERT INTO evolution_engineering_approvals(evolution_id,approval_id,status,subject_sha256,request_digest,evidence_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(evolution_id) DO UPDATE SET "
                "approval_id=excluded.approval_id,status=excluded.status,subject_sha256=excluded.subject_sha256,"
                "request_digest=excluded.request_digest,evidence_json=excluded.evidence_json,updated_at=excluded.updated_at",
                (evolution_id, approval_id, status, subject_sha256, request_digest, _json(evidence), now),
            )
            db.commit()
        binding = self.get(evolution_id)
        assert binding is not None
        return binding

    def require_approved(self, evolution_id: str, subject: Mapping[str, object]) -> dict[str, object]:
        binding = self.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps engineering approval binding")
        if binding["subject_sha256"] != _sha256_json(subject):
            raise CapabilityEvolutionError("engineering request changed after AgentOps approval")
        if binding["status"] != "approved":
            raise CapabilityEvolutionError("AgentOps engineering approval binding is not approved")
        return binding


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def _decode_evidence(value: object) -> dict[str, object]:
    decoded = json.loads(str(value))
    if not isinstance(decoded, dict):
        raise CapabilityEvolutionError("stored AgentOps approval evidence is corrupt")
    return decoded


def _validate_replacement(previous: dict[str, object] | None, approval_id: str, status: str) -> None:
    if previous is None:
        return
    previous_id = str(previous["approval_id"])
    previous_status = str(previous["status"])
    if previous_id != approval_id and previous_status in {"pending", "approved"}:
        raise CapabilityEvolutionError("cannot replace a pending or approved AgentOps approval binding")
    if previous_id == approval_id and previous_status == "approved" and status != "approved":
        raise CapabilityEvolutionError("approved AgentOps approval binding cannot regress")


def _required(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise CapabilityEvolutionError(f"AgentOps approval evidence missing {field}")
    return item.strip()


def _status(value: Mapping[str, object]) -> str:
    status = _required(value, "status")
    if status not in {"pending", "approved", "rejected"}:
        raise CapabilityEvolutionError(f"unsupported AgentOps approval status {status!r}")
    return status


def _digest(value: Mapping[str, object], field: str) -> str:
    digest = _required(value, field)
    if len(digest) != 64:
        raise CapabilityEvolutionError(f"AgentOps approval {field} must be SHA-256")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise CapabilityEvolutionError(f"AgentOps approval {field} must be SHA-256") from exc
    return digest.lower()


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
