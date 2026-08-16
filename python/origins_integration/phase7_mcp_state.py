from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


class Phase7McpStateError(ValueError):
    pass


class Phase7McpState:
    """Origins-owned durable coordination evidence for MCP-backed Phase 7 work.

    AgentOps remains canonical for approvals and external-operation lifecycle. This
    table stores only the mechanical engineering result required to recover an
    interrupted Origins coordinator after CodeOps/Sergeant have already completed.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS phase7_engineering_results (
                    evolution_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    subject_sha256 TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    result_json TEXT NOT NULL,
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

    def get_engineering_result(self, evolution_id: str) -> dict[str, object] | None:
        with closing(self._connect()) as connection, connection as db:
            row = db.execute(
                "SELECT operation_id,repository_id,subject_sha256,result_sha256,result_json,updated_at "
                "FROM phase7_engineering_results WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
        if row is None:
            return None
        result = json.loads(str(row["result_json"]))
        if not isinstance(result, dict):
            raise Phase7McpStateError("stored Phase 7 engineering result is malformed")
        if _sha(result) != str(row["result_sha256"]):
            raise Phase7McpStateError("stored Phase 7 engineering result digest mismatch")
        return {
            "operation_id": str(row["operation_id"]),
            "repository_id": str(row["repository_id"]),
            "subject_sha256": str(row["subject_sha256"]),
            "result_sha256": str(row["result_sha256"]),
            "result": result,
            "updated_at": str(row["updated_at"]),
        }

    def bind_engineering_result(
        self,
        evolution_id: str,
        *,
        operation_id: str,
        repository_id: str,
        subject_sha256: str,
        result: Mapping[str, object],
    ) -> dict[str, object]:
        if not operation_id.strip() or not repository_id.strip():
            raise Phase7McpStateError("engineering operation/repository identity is required")
        if len(subject_sha256) != 64:
            raise Phase7McpStateError("engineering subject_sha256 must be SHA-256")
        try:
            int(subject_sha256, 16)
        except ValueError as exc:
            raise Phase7McpStateError("engineering subject_sha256 must be SHA-256") from exc
        clean = json.loads(json.dumps(dict(result), sort_keys=True))
        result_sha256 = _sha(clean)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with closing(self._connect()) as connection, connection as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT operation_id,repository_id,subject_sha256,result_sha256 FROM phase7_engineering_results "
                "WHERE evolution_id=?",
                (evolution_id,),
            ).fetchone()
            if row is not None:
                previous = (
                    str(row["operation_id"]),
                    str(row["repository_id"]),
                    str(row["subject_sha256"]),
                    str(row["result_sha256"]),
                )
                current = (operation_id, repository_id, subject_sha256.lower(), result_sha256)
                if previous != current:
                    raise Phase7McpStateError("engineering result cannot be replaced with different durable evidence")
            db.execute(
                "INSERT INTO phase7_engineering_results(evolution_id,operation_id,repository_id,subject_sha256,result_sha256,result_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(evolution_id) DO UPDATE SET updated_at=excluded.updated_at",
                (
                    evolution_id,
                    operation_id,
                    repository_id,
                    subject_sha256.lower(),
                    result_sha256,
                    json.dumps(clean, sort_keys=True, separators=(",", ":")),
                    now,
                ),
            )
            db.commit()
        stored = self.get_engineering_result(evolution_id)
        assert stored is not None
        return stored


def _sha(value: Mapping[str, object]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
