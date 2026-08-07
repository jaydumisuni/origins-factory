use crate::store::{Store, StoreError};
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const MAX_DELTA_BYTES: u64 = 256 * 1024;

impl Store {
    pub fn append_retained_output(
        &self,
        session_id: &str,
        stream: &str,
        bytes: &[u8],
    ) -> Result<(), StoreError> {
        if bytes.is_empty() {
            return Ok(());
        }
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let (current, expected_digest): (Vec<u8>, String) = match stream {
            "stdout" => transaction.query_row(
                "SELECT stdout, stdout_retained_sha256 FROM session_outputs WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            ),
            "stderr" => transaction.query_row(
                "SELECT stderr, stderr_retained_sha256 FROM session_outputs WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            ),
            _ => {
                return Err(StoreError::InvalidInput(format!(
                    "unsupported process output stream {stream:?}"
                )))
            }
        }
        .optional()?
        .ok_or_else(|| StoreError::NotFound(format!("session output {session_id}")))?;

        if sha256_bytes(&current) != expected_digest {
            return Err(StoreError::Corrupt(format!(
                "session {session_id} retained {stream} digest mismatch before append"
            )));
        }
        let mut next = current;
        next.extend_from_slice(bytes);
        let next_digest = sha256_bytes(&next);
        match stream {
            "stdout" => transaction.execute(
                "UPDATE session_outputs SET stdout = ?1, stdout_retained_sha256 = ?2
                 WHERE session_id = ?3",
                params![next, next_digest, session_id],
            )?,
            "stderr" => transaction.execute(
                "UPDATE session_outputs SET stderr = ?1, stderr_retained_sha256 = ?2
                 WHERE session_id = ?3",
                params![next, next_digest, session_id],
            )?,
            _ => unreachable!(),
        };
        transaction.commit()?;
        Ok(())
    }

    pub fn read_output_delta(
        &self,
        session_id: &str,
        stdout_after: u64,
        stderr_after: u64,
        limit: u64,
    ) -> Result<Value, StoreError> {
        if !(1..=MAX_DELTA_BYTES).contains(&limit) {
            return Err(StoreError::InvalidInput(format!(
                "output delta limit must be between 1 and {MAX_DELTA_BYTES}"
            )));
        }
        let session = self.get_session(session_id)?;
        let connection = self.connection()?;
        let stored: Option<(Vec<u8>, Vec<u8>, String, String)> = connection
            .query_row(
                "SELECT stdout, stderr, stdout_retained_sha256, stderr_retained_sha256
                 FROM session_outputs WHERE session_id = ?1",
                [session_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()?;
        let (stdout, stderr, stdout_digest, stderr_digest) = stored.ok_or_else(|| {
            StoreError::Corrupt(format!("session {session_id} has no output row"))
        })?;
        if sha256_bytes(&stdout) != stdout_digest {
            return Err(StoreError::Corrupt(format!(
                "session {session_id} retained stdout digest mismatch"
            )));
        }
        if sha256_bytes(&stderr) != stderr_digest {
            return Err(StoreError::Corrupt(format!(
                "session {session_id} retained stderr digest mismatch"
            )));
        }

        let stdout = stream_delta("stdout", &stdout, stdout_after, limit)?;
        let stderr = stream_delta("stderr", &stderr, stderr_after, limit)?;
        Ok(json!({
            "session_id": session_id,
            "state": session["state"],
            "stdout": stdout,
            "stderr": stderr
        }))
    }
}

fn stream_delta(stream: &str, bytes: &[u8], after: u64, limit: u64) -> Result<Value, StoreError> {
    let head = u64::try_from(bytes.len())
        .map_err(|_| StoreError::Corrupt(format!("retained {stream} length overflow")))?;
    if after > head {
        return Err(StoreError::Conflict(format!(
            "{stream}_after cursor {after} is beyond retained head {head}"
        )));
    }
    let start = usize::try_from(after)
        .map_err(|_| StoreError::InvalidInput(format!("{stream}_after is too large")))?;
    let limit = usize::try_from(limit)
        .map_err(|_| StoreError::InvalidInput("output delta limit is too large".to_owned()))?;
    let end = start.saturating_add(limit).min(bytes.len());
    let chunk = &bytes[start..end];
    let next = u64::try_from(end)
        .map_err(|_| StoreError::Corrupt(format!("retained {stream} cursor overflow")))?;
    Ok(json!({
        "after": after,
        "next": next,
        "head": head,
        "bytes": chunk.len(),
        "hex": hex::encode(chunk),
        "text": String::from_utf8(chunk.to_vec()).ok()
    }))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sessions::ProcessSessionStart;
    use std::fs;
    use std::path::PathBuf;
    use uuid::Uuid;

    const EMPTY_SHA256: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

    fn temp_database() -> PathBuf {
        std::env::temp_dir().join(format!("originsd-live-output-{}.sqlite3", Uuid::new_v4()))
    }

    #[test]
    fn byte_cursor_reads_only_new_retained_bytes() {
        let path = temp_database();
        let store = Store::open(&path).unwrap();
        let workspace = store
            .create_workspace("Output proof", vec![], vec![])
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
        let session_id = session["session_id"].as_str().unwrap();
        store
            .append_retained_output(session_id, "stdout", b"abc")
            .unwrap();
        let first = store.read_output_delta(session_id, 0, 0, 2).unwrap();
        assert_eq!(first["stdout"]["text"], "ab");
        assert_eq!(first["stdout"]["next"], 2);
        let second = store.read_output_delta(session_id, 2, 0, 2).unwrap();
        assert_eq!(second["stdout"]["text"], "c");
        assert_eq!(second["stdout"]["next"], 3);
        let _ = fs::remove_file(path);
    }
}
