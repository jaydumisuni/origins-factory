use crate::store::{append_event, verify_stored_contract, Store, StoreError};
use rusqlite::{OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};

impl Store {
    pub fn record_process_cancel_requested(&self, session_id: &str) -> Result<Value, StoreError> {
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
        let projection = verify_stored_contract("session", session_id, &canonical, &digest)?;
        let observed_state = projection["state"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session state is invalid".to_owned()))?;
        if !matches!(observed_state, "starting" | "running") {
            return Err(StoreError::Conflict(format!(
                "session {session_id} is already terminal with state {observed_state}"
            )));
        }
        let workspace_id = projection["workspace_id"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session workspace_id is invalid".to_owned()))?;
        let command_id = projection["command_id"]
            .as_str()
            .ok_or_else(|| StoreError::Corrupt("session command_id is invalid".to_owned()))?;
        let event = append_event(
            &transaction,
            workspace_id,
            "process.session.cancel_requested",
            json!({
                "session_id": session_id,
                "command_id": command_id,
                "observed_state": observed_state
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(event)
    }
}
