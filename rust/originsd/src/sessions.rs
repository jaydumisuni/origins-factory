use crate::store::{append_event, now_rfc3339, verify_stored_contract, Store, StoreError};
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
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

pub(crate) struct ProcessSessionStart<'a> {
    pub workspace_id: &'a str,
    pub command_id: &'a str,
    pub command_sha256: &'a str,
    pub workspace_root: &'a str,
    pub executable: &'a str,
    pub cwd: &'a str,
    pub args_sha256: &'a str,
}

struct SessionTransition<'a> {
    next_state: &'a str,
    pid: Option<String>,
    exit_code: Option<i32>,
    timed_out: bool,
    output: Option<SessionOutputRecord>,
    event_kind: &'a str,
    event_extra: Value,
}

pub(crate) fn create_session_tables(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            command_id TEXT UNIQUE NOT NULL,
            command_sha256 TEXT NOT NULL,
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
            stdout_retained_sha256 TEXT NOT NULL,
            stderr_retained_sha256 TEXT NOT NULL,
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
    pub(crate) fn create_process_session(
        &self,
        start: ProcessSessionStart<'_>,
    ) -> Result<Value, StoreError> {
        if !self.workspace_exists(start.workspace_id)? {
            return Err(StoreError::NotFound(format!(
                "workspace {}",
                start.workspace_id
            )));
        }

        let session_id = Uuid::new_v4().hyphenated().to_string();
        let now = now_rfc3339();
        let projection = json!({
            "contract_type": "session_projection",
            "schema_version": "1.0.0",
            "session_id": session_id,
            "workspace_id": start.workspace_id,
            "command_id": start.command_id,
            "capability_id": "origins.process.run",
            "kind": "process",
            "workspace_root": start.workspace_root,
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
        let existing: Option<String> = transaction
            .query_row(
                "SELECT command_sha256 FROM sessions WHERE command_id = ?1",
                [start.command_id],
                |row| row.get(0),
            )
            .optional()?;
        if let Some(existing_sha256) = existing {
            let detail = if existing_sha256 == start.command_sha256 {
                "already has a process session"
            } else {
                "is already bound to a different command envelope"
            };
            return Err(StoreError::Conflict(format!(
                "command {} {detail}",
                start.command_id
            )));
        }

        attach_session_reference(&transaction, start.workspace_id, &session_id, &now)?;
        transaction.execute(
            "INSERT INTO sessions (
                session_id, workspace_id, command_id, command_sha256,
                projection_json, projection_sha256, state, created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'starting', ?7, ?7)",
            params![
                session_id,
                start.workspace_id,
                start.command_id,
                start.command_sha256,
                canonical,
                digest,
                now
            ],
        )?;
        transaction.execute(
            "INSERT INTO session_outputs (
                session_id, stdout, stderr, stdout_retained_sha256, stderr_retained_sha256
             ) VALUES (?1, ?2, ?3, ?4, ?4)",
            params![session_id, Vec::<u8>::new(), Vec::<u8>::new(), EMPTY_SHA256],
        )?;
        append_event(
            &transaction,
            start.workspace_id,
            "process.session.starting",
            json!({
                "session_id": session_id,
                "command_id": start.command_id,
                "command_sha256": start.command_sha256,
                "capability_id": "origins.process.run",
                "executable": start.executable,
                "cwd": start.cwd,
                "args_sha256": start.args_sha256
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(projection)
    }

    pub fn get_session_for_command(
        &self,
        command_id: &str,
        command_sha256: &str,
    ) -> Result<Option<Value>, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String, String, String)> = connection
            .query_row(
                "SELECT session_id, command_sha256, projection_json, projection_sha256
                 FROM sessions WHERE command_id = ?1",
                [command_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()?;
        stored
            .map(|(session_id, stored_command_sha256, canonical, digest)| {
                if stored_command_sha256 != command_sha256 {
                    return Err(StoreError::Conflict(format!(
                        "command {command_id} is already bound to a different command envelope"
                    )));
                }
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

    pub fn session_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM sessions", [], |row| row.get(0))?;
        u64::try_from(count).map_err(|_| StoreError::Corrupt("negative session count".to_owned()))
    }

    pub fn get_session_output(&self, session_id: &str) -> Result<SessionOutputRecord, StoreError> {
        let projection = self.get_session(session_id)?;
        let connection = self.connection()?;
        let stored: Option<(Vec<u8>, Vec<u8>, String, String)> = connection
            .query_row(
                "SELECT stdout, stderr, stdout_retained_sha256, stderr_retained_sha256
                 FROM session_outputs WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()?;
        let (stdout, stderr, stdout_retained_sha256, stderr_retained_sha256) =
            stored.ok_or_else(|| {
                StoreError::Corrupt(format!("session {session_id} has no output row"))
            })?;
        if sha256_bytes(&stdout) != stdout_retained_sha256 {
            return Err(StoreError::Corrupt(format!(
                "session {session_id} retained stdout digest mismatch"
            )));
        }
        if sha256_bytes(&stderr) != stderr_retained_sha256 {
            return Err(StoreError::Corrupt(format!(
                "session {session_id} retained stderr digest mismatch"
            )));
        }
        Ok(SessionOutputRecord {
            stdout,
            stderr,
            stdout_bytes: required_u64(&projection, "stdout_bytes")?,
            stderr_bytes: required_u64(&projection, "stderr_bytes")?,
            stdout_sha256: required_string(&projection, "stdout_sha256")?.to_owned(),
            stderr_sha256: required_string(&projection, "stderr_sha256")?.to_owned(),
            output_truncated: projection["output_truncated"].as_bool().ok_or_else(|| {
                StoreError::Corrupt("session output_truncated is invalid".to_owned())
            })?,
        })
    }

    pub fn mark_process_running(&self, session_id: &str, pid: u32) -> Result<Value, StoreError> {
        self.transition_process_session(
            session_id,
            SessionTransition {
                next_state: "running",
                pid: Some(pid.to_string()),
                exit_code: None,
                timed_out: false,
                output: None,
                event_kind: "process.session.running",
                event_extra: json!({"pid": pid.to_string()}),
            },
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
        if !matches!(state, "completed" | "failed" | "timed_out" | "interrupted") {
            return Err(StoreError::InvalidInput(format!(
                "unsupported terminal process state {state}"
            )));
        }
        let event_kind = match state {
            "completed" => "process.session.completed",
            "failed" => "process.session.failed",
            "timed_out" => "process.session.timed_out",
            "interrupted" => "process.session.interrupted",
            _ => unreachable!(),
        };
        self.transition_process_session(
            session_id,
            SessionTransition {
                next_state: state,
                pid: None,
                exit_code,
                timed_out,
                output: Some(output),
                event_kind,
                event_extra: json!({"reason": reason}),
            },
        )
    }

    pub fn interrupt_process_session(&self, session_id: &str) -> Result<Value, StoreError> {
        self.transition_process_session(
            session_id,
            SessionTransition {
                next_state: "interrupted",
                pid: None,
                exit_code: None,
                timed_out: false,
                output: None,
                event_kind: "process.session.interrupted",
                event_extra: json!({"reason": "daemon_restart_without_reattach"}),
            },
        )
    }

    fn transition_process_session(
        &self,
        session_id: &str,
        transition: SessionTransition<'_>,
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
        let current_state = projection["state"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session state is invalid".to_owned()))?;
        validate_transition(current_state, transition.next_state)?;

        let now = now_rfc3339();
        projection["state"] = Value::String(transition.next_state.to_owned());
        projection["updated_at"] = Value::String(now.clone());
        if let Some(pid) = transition.pid {
            projection["pid"] = Value::String(pid);
        }
        if matches!(
            transition.next_state,
            "completed" | "failed" | "timed_out" | "interrupted"
        ) {
            projection["ended_at"] = Value::String(now.clone());
            projection["exit_code"] = transition.exit_code.map_or(Value::Null, |code| json!(code));
            projection["timed_out"] = Value::Bool(transition.timed_out);
        }
        if let Some(output) = transition.output.as_ref() {
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
            params![
                next_canonical,
                next_digest,
                transition.next_state,
                now,
                session_id
            ],
        )?;
        if let Some(output) = transition.output {
            let stdout_retained_sha256 = sha256_bytes(&output.stdout);
            let stderr_retained_sha256 = sha256_bytes(&output.stderr);
            transaction.execute(
                "UPDATE session_outputs SET stdout = ?1, stderr = ?2,
                 stdout_retained_sha256 = ?3, stderr_retained_sha256 = ?4
                 WHERE session_id = ?5",
                params![
                    output.stdout,
                    output.stderr,
                    stdout_retained_sha256,
                    stderr_retained_sha256,
                    session_id
                ],
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
            "state": transition.next_state
        });
        if let (Some(target), Some(extra)) = (
            event_payload.as_object_mut(),
            transition.event_extra.as_object(),
        ) {
            for (key, value) in extra {
                target.insert(key.clone(), value.clone());
            }
        }
        append_event(
            &transaction,
            workspace_id,
            transition.event_kind,
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
    if !session_refs
        .iter()
        .any(|reference| reference["id"].as_str() == Some(session_id))
    {
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
    let next_revision = revision
        .checked_add(1)
        .ok_or_else(|| StoreError::Corrupt("workspace revision overflow".to_owned()))?;
    workspace["revision"] = json!(next_revision);
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
            next_revision,
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

fn sha256_bytes(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value[field]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| StoreError::Corrupt(format!("session {field} is invalid")))
}

fn required_u64(value: &Value, field: &str) -> Result<u64, StoreError> {
    value[field]
        .as_u64()
        .ok_or_else(|| StoreError::Corrupt(format!("session {field} is invalid")))
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
        let workspace = store
            .create_workspace("Session proof", vec![], vec![])
            .unwrap();
        let workspace_id = workspace["workspace_id"].as_str().unwrap();
        let command_id = Uuid::new_v4().hyphenated().to_string();
        let session = store
            .create_process_session(ProcessSessionStart {
                workspace_id,
                command_id: &command_id,
                command_sha256: EMPTY_SHA256,
                workspace_root: "/tmp",
                executable: "python3",
                cwd: ".",
                args_sha256: EMPTY_SHA256,
            })
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

    #[test]
    fn command_id_cannot_be_rebound_to_different_digest() {
        let path = temp_database();
        let store = Store::open(&path).unwrap();
        let workspace = store
            .create_workspace("Replay proof", vec![], vec![])
            .unwrap();
        let workspace_id = workspace["workspace_id"].as_str().unwrap();
        let command_id = Uuid::new_v4().hyphenated().to_string();
        store
            .create_process_session(ProcessSessionStart {
                workspace_id,
                command_id: &command_id,
                command_sha256: EMPTY_SHA256,
                workspace_root: "/tmp",
                executable: "python3",
                cwd: ".",
                args_sha256: EMPTY_SHA256,
            })
            .unwrap();
        let error = store
            .get_session_for_command(
                &command_id,
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            .expect_err("digest mismatch must fail");
        assert!(matches!(error, StoreError::Conflict(_)));
        let _ = fs::remove_file(path);
    }
}
