from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .capability_evolution import CapabilityEvolutionError


class EvolutionApprovalBindings:
    """Durable relationship between an Origins evolution and AgentOps approval authority."""

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
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def get(self, evolution_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT evolution_id, approval_id, status, request_digest, evidence_json, updated_at "
                "FROM evolution_approval_bindings WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
        if row is None:
            return None
        evidence = json.loads(str(row["evidence_json"]))
        if not isinstance(evidence, dict):
            raise CapabilityEvolutionError("stored AgentOps approval evidence is corrupt")
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
        status = _required(evidence, "status")
        if status not in {"pending", "approved", "rejected"}:
            raise CapabilityEvolutionError(f"unsupported AgentOps approval status {status!r}")
        request_digest = _required(evidence, "request_digest")
        if len(request_digest) != 64:
            raise CapabilityEvolutionError("AgentOps approval request_digest must be SHA-256")
        now = _now()
        previous = self.get(evolution_id)
        if previous is not None:
            previous_id = str(previous["approval_id"])
            previous_status = str(previous["status"])
            if previous_id != approval_id and previous_status in {"pending", "approved"}:
                raise CapabilityEvolutionError("cannot replace a pending or approved AgentOps approval binding")
            if previous_id == approval_id and previous_status == "approved" and status != "approved":
                raise CapabilityEvolutionError("approved AgentOps approval binding cannot regress")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO evolution_approval_bindings(evolution_id,approval_id,status,request_digest,evidence_json,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(evolution_id) DO UPDATE SET "
                "approval_id=excluded.approval_id,status=excluded.status,request_digest=excluded.request_digest,"
                "evidence_json=excluded.evidence_json,updated_at=excluded.updated_at",
                (
                    evolution_id,
                    approval_id,
                    status,
                    request_digest,
                    json.dumps(dict(evidence), sort_keys=True, separators=(",", ":")),
                    now,
                ),
            )
            db.commit()
        binding = self.get(evolution_id)
        assert binding is not None
        return binding

    def require_approved(self, evolution_id: str, approval_id: str) -> dict[str, object]:
        binding = self.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps approval binding")
        if binding["approval_id"] != approval_id:
            raise CapabilityEvolutionError("AgentOps approval ID does not match the durable evolution binding")
        if binding["status"] != "approved":
            raise CapabilityEvolutionError("AgentOps approval binding is not approved")
        return binding


def _required(value: Mapping[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise CapabilityEvolutionError(f"AgentOps approval evidence missing {field}")
    return item.strip()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
