use crate::store::{append_event, now_rfc3339, verify_stored_contract, Store, StoreError};
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde_json::{json, Value};
use std::collections::HashSet;
use uuid::Uuid;

const EMPTY_SHA256: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

#[derive(Debug, Clone)]
pub struct SessionOutputRecord {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub stdout_bytes: u64,
    pub stderr_bytes: u64,
    pub stdout_sha256: String,
    pub stderr_sha256: String,
    pub output_truncated: bool,
}

impl SessionOutputRecord {
    pub fn empty() -> Self {
        Self {
            stdout: Vec::new(),
            stderr: Vec::new(),
            stdout_bytes: 0,
            stderr_bytes: 0,
            stdout_sha256: EMPTY_SHA256.to_owned(),
            stderr_sha256: EMPTY_SHA256.to_owned(),
            output_truncated: false,
        }
    }
}

pub(crate) fn create_session_tables(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            command_id TEXT UNIQUE NOT NULL,
            projection_json TEXT NOT NULL,
            projection_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
         );
         CREATE INDEX IF NOT EXISTS idx_sessions_workspace_updated
            ON sessions(workspace_id, updated_at DESC);
         CREATE TABLE IF NOT EXISTS session_outputs (
            session_id TEXT PRIMARY KEY NOT NULL,
            stdout BLOB NOT NULL,
            stderr BLOB NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
         );",
    )?;
    Ok(())
}

pub(crate) fn recover_interrupted_sessions(store: &Store) -> Result<(), StoreError> {
    let active = {
        let connection = store.connection()?;
        let mut statement = connection.prepare(
            "SELECT session_id FROM sessions
             WHERE state IN ('starting', 'running')
             ORDER BY created_at, session_id",
        )?;
        let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
        let mut ids = Vec::new();
        for row in rows {
            ids.push(row?);
        }
        ids
    };

    for session_id in active {
        store.interrupt_process_session(&session_id)?;
    }
    Ok(())
}

impl Store {
    pub fn create_process_session(
        &self,
        workspace_id: &str,
        command_id: &str,
        workspace_root: &str,
        executable: &str,
        cwd: &str,
        args_sha256: &str,
    ) -> Result<Value, StoreError> {
        if !self.workspace_exists(workspace_id)? {
            return Err(StoreError::NotFound(format!("workspace {workspace_id}")));
        }

        let session_id = Uuid::new_v4().hyphenated().to_string();
        let now = now_rfc3339();
        let projection = json!({
            "contract_type": "session_projection",
            "schema_version": "1.0.0",
            "session_id": session_id,
            "workspace_id": workspace_id,
            "command_id": command_id,
            "capability_id": "origins.process.run",
            "kind": "process",
            "workspace_root": workspace_root,
            "state": "starting",
            "pid": "",
            "started_at": now,
            "updated_at": now,
            "ended_at": "",
            "exit_code": null,
            "timed_out": false,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
            "stdout_sha256": EMPTY_SHA256,
            "stderr_sha256": EMPTY_SHA256,
            "output_truncated": false
        });
        validate_contract(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let canonical =
            canonical_json(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest = contract_sha256(&projection)
            .map_err(|error| StoreError::Contract(error.to_string()))?;

        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let existing: i64 = transaction.query_row(
            "SELECT EXISTS(SELECT 1 FROM sessions WHERE command_id = ?1)",
            [command_id],
            |row| row.get(0),
        )?;
        if existing == 1 {
            return Err(StoreError::Conflict(format!(
                "command {command_id} already has a process session"
            )));
        }

        attach_session_reference(&transaction, workspace_id, &session_id, &now)?;
        transaction.execute(
            "INSERT INTO sessions (
                session_id, workspace_id, command_id, projection_json, projection_sha256,
                state, created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, 'starting', ?6, ?6)",
            params![session_id, workspace_id, command_id, canonical, digest, now],
        )?;
        transaction.execute(
            "INSERT INTO session_outputs (session_id, stdout, stderr) VALUES (?1, ?2, ?3)",
            params![session_id, Vec::<u8>::new(), Vec::<u8>::new()],
        )?;
        append_event(
            &transaction,
            workspace_id,
            "process.session.starting",
            json!({
                "session_id": session_id,
                "command_id": command_id,
                "capability_id": "origins.process.run",
                "executable": executable,
                "cwd": cwd,
                "args_sha256": args_sha256
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(projection)
    }

    pub fn get_session_by_command(&self, command_id: &str) -> Result<Option<Value>, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String, String)> = connection
            .query_row(
                "SELECT session_id, projection_json, projection_sha256
                 FROM sessions WHERE command_id = ?1",
                [command_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .optional()?;
        stored
            .map(|(session_id, canonical, digest)| {
                verify_stored_contract("session", &session_id, &canonical, &digest)
            })
            .transpose()
    }

    pub fn get_session(&self, session_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String)> = connection
            .query_row(
                "SELECT projection_json, projection_sha256 FROM sessions WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, digest) =
            stored.ok_or_else(|| StoreError::NotFound(format!("session {session_id}")))?;
        verify_stored_contract("session", session_id, &canonical, &digest)
    }

    pub fn list_sessions(&self) -> Result<Vec<Value>, StoreError> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT session_id, projection_json, projection_sha256 FROM sessions
             ORDER BY updated_at DESC, session_id",
        )?;
        let rows = statement.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;
        let mut sessions = Vec::new();
        for row in rows {
            let (session_id, canonical, digest) = row?;
            sessions.push(verify_stored_contract(
                "session",
                &session_id,
                &canonical,
                &digest,
            )?);
        }
        Ok(sessions)
    }

    pub fn get_session_output(&self, session_id: &str) -> Result<SessionOutputRecord, StoreError> {
        let projection = self.get_session(session_id)?;
        let connection = self.connection()?;
        let stored: Option<(Vec<u8>, Vec<u8>)> = connection
            .query_row(
                "SELECT stdout, stderr FROM session_outputs WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (stdout, stderr) =
            stored.ok_or_else(|| StoreError::Corrupt(format!("session {session_id} has no output row")))?;
        Ok(SessionOutputRecord {
            stdout,
            stderr,
            stdout_bytes: projection["stdout_bytes"].as_u64().unwrap_or(0),
            stderr_bytes: projection["stderr_bytes"].as_u64().unwrap_or(0),
            stdout_sha256: projection["stdout_sha256"].as_str().unwrap_or(EMPTY_SHA256).to_owned(),
            stderr_sha256: projection["stderr_sha256"].as_str().unwrap_or(EMPTY_SHA256).to_owned(),
            output_truncated: projection["output_truncated"].as_bool().unwrap_or(false),
        })
    }

    pub fn mark_process_running(&self, session_id: &str, pid: u32) -> Result<Value, StoreError> {
        self.transition_process_session(
            session_id,
            "running",
            Some(pid.to_string()),
            None,
            false,
            None,
            "process.session.running",
            json!({"pid": pid.to_string()}),
        )
    }

    pub fn finish_process_session(
        &self,
        session_id: &str,
        state: &str,
        exit_code: Option<i32>,
        timed_out: bool,
        output: SessionOutputRecord,
        reason: &str,
    ) -> Result<Value, StoreError> {
        if !matches!(state, "completed" | "failed" | "timed_out") {
            return Err(StoreError::InvalidInput(format!(
                "unsupported terminal process state {state}"
            )));
        }
        let event_kind = match state {
            "completed" => "process.session.completed",
            "failed" => "process.session.failed",
            "timed_out" => "process.session.timed_out",
            _ => unreachable!(),
        };
        self.transition_process_session(
            session_id,
            state,
            None,
            exit_code,
            timed_out,
            Some(output),
            event_kind,
            json!({"reason": reason}),
        )
    }

    pub fn interrupt_process_session(&self, session_id: &str) -> Result<Value, StoreError> {
        self.transition_process_session(
            session_id,
            "interrupted",
            None,
            None,
            false,
            None,
            "process.session.interrupted",
            json!({"reason": "daemon_restart_without_reattach"}),
        )
    }

    fn transition_process_session(
        &self,
        session_id: &str,
        next_state: &str,
        pid: Option<String>,
        exit_code: Option<i32>,
        timed_out: bool,
        output: Option<SessionOutputRecord>,
        event_kind: &str,
        event_extra: Value,
    ) -> Result<Value, StoreError> {
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let stored: Option<(String, String)> = transaction
            .query_row(
                "SELECT projection_json, projection_sha256 FROM sessions WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, digest) =
            stored.ok_or_else(|| StoreError::NotFound(format!("session {session_id}")))?;
        let mut projection = verify_stored_contract("session", session_id, &canonical, &digest)?;
        let current_state = projection["state"].as_str().unwrap_or("");
        validate_transition(current_state, next_state)?;

        let now = now_rfc3339();
        projection["state"] = Value::String(next_state.to_owned());
        projection["updated_at"] = Value::String(now.clone());
        if let Some(pid) = pid {
            projection["pid"] = Value::String(pid);
        }
        if matches!(next_state, "completed" | "failed" | "timed_out" | "interrupted") {
            projection["ended_at"] = Value::String(now.clone());
            projection["exit_code"] = exit_code.map_or(Value::Null, |code| json!(code));
            projection["timed_out"] = Value::Bool(timed_out);
        }
        if let Some(output) = output.as_ref() {
            projection["stdout_bytes"] = json!(output.stdout_bytes);
            projection["stderr_bytes"] = json!(output.stderr_bytes);
            projection["stdout_sha256"] = Value::String(output.stdout_sha256.clone());
            projection["stderr_sha256"] = Value::String(output.stderr_sha256.clone());
            projection["output_truncated"] = Value::Bool(output.output_truncated);
        }
        validate_contract(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let next_canonical =
            canonical_json(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let next_digest = contract_sha256(&projection)
            .map_err(|error| StoreError::Contract(error.to_string()))?;

        transaction.execute(
            "UPDATE sessions SET projection_json = ?1, projection_sha256 = ?2,
             state = ?3, updated_at = ?4 WHERE session_id = ?5",
            params![next_canonical, next_digest, next_state, now, session_id],
        )?;
        if let Some(output) = output {
            transaction.execute(
                "UPDATE session_outputs SET stdout = ?1, stderr = ?2 WHERE session_id = ?3",
                params![output.stdout, output.stderr, session_id],
            )?;
        }

        let workspace_id = projection["workspace_id"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session workspace_id missing".to_owned()))?;
        let command_id = projection["command_id"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session command_id missing".to_owned()))?;
        let mut event_payload = json!({
            "session_id": session_id,
            "command_id": command_id,
            "state": next_state
        });
        if let (Some(target), Some(extra)) = (event_payload.as_object_mut(), event_extra.as_object()) {
            for (key, value) in extra {
                target.insert(key.clone(), value.clone());
            }
        }
        append_event(
            &transaction,
            workspace_id,
            event_kind,
            event_payload,
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(projection)
    }
}

fn attach_session_reference(
    transaction: &Transaction<'_>,
    workspace_id: &str,
    session_id: &str,
    observed_at: &str,
) -> Result<(), StoreError> {
    let stored: Option<(String, String)> = transaction
        .query_row(
            "SELECT projection_json, projection_sha256 FROM workspaces WHERE workspace_id = ?1",
            [workspace_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let (canonical, digest) =
        stored.ok_or_else(|| StoreError::NotFound(format!("workspace {workspace_id}")))?;
    let mut workspace = verify_stored_contract("workspace", workspace_id, &canonical, &digest)?;

    let session_refs = workspace["session_refs"]
        .as_array_mut()
        .ok_or_else(|| StoreError::Corrupt("workspace session_refs is not an array".to_owned()))?;
    let identities: HashSet<String> = session_refs
        .iter()
        .filter_map(|reference| reference["id"].as_str().map(str::to_owned))
        .collect();
    if !identities.contains(session_id) {
        session_refs.push(json!({
            "contract_type": "authority_ref",
            "schema_version": "1.0.0",
            "authority": "originsd",
            "kind": "session",
            "id": session_id,
            "revision": "",
            "uri": "",
            "digest": "",
            "observed_at": observed_at
        }));
    }
    let revision = workspace["revision"]
        .as_u64()
        .ok_or_else(|| StoreError::Corrupt("workspace revision is invalid".to_owned()))?;
    workspace["revision"] = json!(revision + 1);
    workspace["updated_at"] = Value::String(observed_at.to_owned());
    validate_contract(&workspace).map_err(|error| StoreError::Contract(error.to_string()))?;
    let next_canonical =
        canonical_json(&workspace).map_err(|error| StoreError::Contract(error.to_string()))?;
    let next_digest =
        contract_sha256(&workspace).map_err(|error| StoreError::Contract(error.to_string()))?;
    transaction.execute(
        "UPDATE workspaces SET projection_json = ?1, projection_sha256 = ?2,
         revision = ?3, updated_at = ?4 WHERE workspace_id = ?5",
        params![
            next_canonical,
            next_digest,
            revision + 1,
            observed_at,
            workspace_id
        ],
    )?;
    Ok(())
}

fn validate_transition(current: &str, next: &str) -> Result<(), StoreError> {
    let allowed = matches!(
        (current, next),
        ("starting", "running")
            | ("starting", "failed")
            | ("starting", "interrupted")
            | ("running", "completed")
            | ("running", "failed")
            | ("running", "timed_out")
            | ("running", "interrupted")
    );
    if allowed {
        Ok(())
    } else {
        Err(StoreError::Conflict(format!(
            "invalid session transition {current} -> {next}"
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn temp_database() -> PathBuf {
        std::env::temp_dir().join(format!("originsd-session-{}.sqlite3", Uuid::new_v4()))
    }

    #[test]
    fn active_session_becomes_interrupted_after_reopen() {
        let path = temp_database();
        let store = Store::open(&path).unwrap();
        let workspace = store.create_workspace("Session proof", vec![], vec![]).unwrap();
        let workspace_id = workspace["workspace_id"].as_str().unwrap();
        let command_id = Uuid::new_v4().hyphenated().to_string();
        let session = store
            .create_process_session(
                workspace_id,
                &command_id,
                "/tmp",
                "python3",
                ".",
                EMPTY_SHA256,
            )
            .unwrap();
        let session_id = session["session_id"].as_str().unwrap().to_owned();
        store.mark_process_running(&session_id, 1234).unwrap();
        drop(store);

        let reopened = Store::open(&path).unwrap();
        let recovered = reopened.get_session(&session_id).unwrap();
        assert_eq!(recovered["state"], "interrupted");
        assert_eq!(recovered["exit_code"], Value::Null);
        assert!(!recovered["ended_at"].as_str().unwrap().is_empty());
        let _ = fs::remove_file(path);
    }
}
