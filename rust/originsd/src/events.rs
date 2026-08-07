use crate::store::{Store, StoreError};
use origins_contracts::validate_contract;
use rusqlite::params;
use serde_json::Value;

const MAX_EVENT_PAGE: u64 = 1_000;

#[derive(Debug, Clone)]
pub struct EventPage {
    pub events: Vec<Value>,
    pub after_sequence: u64,
    pub next_sequence: u64,
    pub head_sequence: u64,
    pub head_hash: String,
}

impl Store {
    pub fn list_events_after(
        &self,
        after_sequence: u64,
        limit: u64,
    ) -> Result<EventPage, StoreError> {
        if !(1..=MAX_EVENT_PAGE).contains(&limit) {
            return Err(StoreError::InvalidInput(format!(
                "event limit must be between 1 and {MAX_EVENT_PAGE}"
            )));
        }
        let after_i64 = i64::try_from(after_sequence)
            .map_err(|_| StoreError::InvalidInput("after_sequence is too large".to_owned()))?;
        let limit_i64 = i64::try_from(limit)
            .map_err(|_| StoreError::InvalidInput("event limit is too large".to_owned()))?;

        let journal = self.verify_journal()?;
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT sequence, event_json FROM journal_entries
             WHERE sequence > ?1 ORDER BY sequence ASC LIMIT ?2",
        )?;
        let rows = statement.query_map(params![after_i64, limit_i64], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?;
        let mut events = Vec::new();
        let mut next_sequence = after_sequence;
        for row in rows {
            let (sequence, event_json) = row?;
            let event: Value = serde_json::from_str(&event_json)
                .map_err(|error| StoreError::Corrupt(format!("journal JSON: {error}")))?;
            validate_contract(&event)
                .map_err(|error| StoreError::Corrupt(format!("journal contract: {error}")))?;
            if event["contract_type"] != "event_envelope"
                || event["sequence"].as_i64() != Some(sequence)
            {
                return Err(StoreError::Corrupt(format!(
                    "journal sequence {sequence} event projection mismatch"
                )));
            }
            next_sequence = u64::try_from(sequence)
                .map_err(|_| StoreError::Corrupt("negative journal sequence".to_owned()))?;
            events.push(event);
        }

        Ok(EventPage {
            events,
            after_sequence,
            next_sequence,
            head_sequence: journal.entries,
            head_hash: journal.head_hash,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use uuid::Uuid;

    fn temp_database() -> PathBuf {
        std::env::temp_dir().join(format!("originsd-events-{}.sqlite3", Uuid::new_v4()))
    }

    #[test]
    fn event_cursor_returns_only_later_sequences() {
        let path = temp_database();
        let store = Store::open(&path).unwrap();
        store.create_workspace("one", vec![], vec![]).unwrap();
        store.create_workspace("two", vec![], vec![]).unwrap();

        let first = store.list_events_after(0, 1).unwrap();
        assert_eq!(first.events.len(), 1);
        assert_eq!(first.next_sequence, 1);
        assert_eq!(first.head_sequence, 2);

        let second = store.list_events_after(first.next_sequence, 10).unwrap();
        assert_eq!(second.events.len(), 1);
        assert_eq!(second.events[0]["sequence"], 2);
        assert_eq!(second.next_sequence, 2);
        let _ = fs::remove_file(path);
    }
}
