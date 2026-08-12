use chrono::{SecondsFormat, Utc};
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};
use uuid::Uuid;

const DATABASE_SCHEMA_VERSION: i64 = 3;
const JOURNAL_DOMAIN: &[u8] = b"origins-journal-v1\0";
const BUILTIN_CAPABILITIES: &str = include_str!("../../../capabilities/builtin.json");

#[derive(Debug)]
pub enum StoreError {
    Io(String),
    Database(String),
    Contract(String),
    InvalidInput(String),
    NotFound(String),
    Conflict(String),
    Corrupt(String),
}

impl Display for StoreError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(message) => write!(formatter, "I/O error: {message}"),
            Self::Database(message) => write!(formatter, "database error: {message}"),
            Self::Contract(message) => write!(formatter, "contract error: {message}"),
            Self::InvalidInput(message) => write!(formatter, "invalid input: {message}"),
            Self::NotFound(message) => write!(formatter, "not found: {message}"),
            Self::Conflict(message) => write!(formatter, "conflict: {message}"),
            Self::Corrupt(message) => write!(formatter, "corrupt state: {message}"),
        }
    }
}

impl std::error::Error for StoreError {}

impl From<rusqlite::Error> for StoreError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Database(error.to_string())
    }
}

#[derive(Debug, Clone)]
pub struct Store {
    database_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JournalVerification {
    pub ok: bool,
    pub entries: u64,
    pub head_hash: String,
}

impl Store {
    pub fn open(database_path: impl AsRef<Path>) -> Result<Self, StoreError> {
        let database_path = database_path.as_ref().to_path_buf();
        if let Some(parent) = database_path.parent() {
            fs::create_dir_all(parent).map_err(|error| StoreError::Io(error.to_string()))?;
        }

        let store = Self { database_path };
        let connection = store.connection()?;
        migrate(&connection)?;
        seed_capabilities(&connection)?;
        drop(connection);
        store.verify_journal()?;
        crate::sessions::recover_interrupted_sessions(&store)?;
        crate::authority_runtime::verify_authority_state(&store)?;
        store.verify_journal()?;
        Ok(store)
    }

    pub fn database_path(&self) -> &Path {
        &self.database_path
    }

    pub fn schema_version(&self) -> Result<i64, StoreError> {
        let connection = self.connection()?;
        read_schema_version(&connection)
    }

    pub fn create_workspace(
        &self,
        name: &str,
        authority_refs: Vec<Value>,
        session_refs: Vec<Value>,
    ) -> Result<Value, StoreError> {
        let name = name.trim();
        if name.is_empty() {
            return Err(StoreError::InvalidInput(
                "workspace name cannot be empty".to_owned(),
            ));
        }
        if name.chars().count() > 200 {
            return Err(StoreError::InvalidInput(
                "workspace name cannot exceed 200 characters".to_owned(),
            ));
        }
        validate_authority_refs(&authority_refs)?;
        validate_authority_refs(&session_refs)?;

        let workspace_id = Uuid::new_v4().hyphenated().to_string();
        let now = now_rfc3339();
        let projection = json!({
            "contract_type": "workspace_projection",
            "schema_version": "1.0.0",
            "workspace_id": workspace_id,
            "name": name,
            "revision": 1,
            "authority_refs": authority_refs,
            "session_refs": session_refs,
            "created_at": now,
            "updated_at": now,
        });
        validate_contract(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let canonical =
            canonical_json(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest = contract_sha256(&projection)
            .map_err(|error| StoreError::Contract(error.to_string()))?;

        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        transaction.execute(
            "INSERT INTO workspaces (
                workspace_id, projection_json, projection_sha256, revision, created_at, updated_at
             ) VALUES (?1, ?2, ?3, 1, ?4, ?4)",
            params![workspace_id, canonical, digest, now],
        )?;
        append_event(
            &transaction,
            projection["workspace_id"]
                .as_str()
                .expect("validated workspace id"),
            "workspace.created",
            json!({"revision": 1}),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(projection)
    }

    pub fn get_workspace(&self, workspace_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String)> = connection
            .query_row(
                "SELECT projection_json, projection_sha256 FROM workspaces WHERE workspace_id = ?1",
                [workspace_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, expected_digest) =
            stored.ok_or_else(|| StoreError::NotFound(format!("workspace {workspace_id}")))?;
        verify_stored_contract("workspace", workspace_id, &canonical, &expected_digest)
    }

    pub fn workspace_exists(&self, workspace_id: &str) -> Result<bool, StoreError> {
        let connection = self.connection()?;
        let exists: i64 = connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM workspaces WHERE workspace_id = ?1)",
            [workspace_id],
            |row| row.get(0),
        )?;
        Ok(exists == 1)
    }

    pub fn list_capabilities(&self) -> Result<Vec<Value>, StoreError> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT capability_id, descriptor_json, descriptor_sha256 FROM capabilities
             ORDER BY capability_id, version",
        )?;
        let rows = statement.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;

        let mut result = Vec::new();
        for row in rows {
            let (capability_id, canonical, expected_digest) = row?;
            result.push(verify_stored_contract(
                "capability",
                &capability_id,
                &canonical,
                &expected_digest,
            )?);
        }
        Ok(result)
    }

    pub fn workspace_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM workspaces", [], |row| row.get(0))?;
        u64::try_from(count).map_err(|_| StoreError::Corrupt("negative workspace count".to_owned()))
    }

    pub fn capability_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM capabilities", [], |row| row.get(0))?;
        u64::try_from(count)
            .map_err(|_| StoreError::Corrupt("negative capability count".to_owned()))
    }

    pub fn verify_journal(&self) -> Result<JournalVerification, StoreError> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT sequence, event_json, event_sha256, prev_hash, entry_hash
             FROM journal_entries ORDER BY sequence",
        )?;
        let rows = statement.query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
            ))
        })?;

        let mut expected_sequence = 1_i64;
        let mut previous_hash = String::new();
        let mut entries = 0_u64;
        for row in rows {
            let (sequence, event_json, expected_event_digest, stored_prev_hash, stored_entry_hash) =
                row?;
            if sequence != expected_sequence {
                return Err(StoreError::Corrupt(format!(
                    "journal sequence gap: expected {expected_sequence}, got {sequence}"
                )));
            }
            if stored_prev_hash != previous_hash {
                return Err(StoreError::Corrupt(format!(
                    "journal previous hash mismatch at sequence {sequence}"
                )));
            }

            let event: Value = serde_json::from_str(&event_json)
                .map_err(|error| StoreError::Corrupt(format!("journal JSON: {error}")))?;
            validate_contract(&event)
                .map_err(|error| StoreError::Corrupt(format!("journal contract: {error}")))?;
            if event["contract_type"] != "event_envelope" {
                return Err(StoreError::Corrupt(format!(
                    "journal sequence {sequence} is not an event_envelope"
                )));
            }
            if event["sequence"].as_i64() != Some(sequence) {
                return Err(StoreError::Corrupt(format!(
                    "journal sequence {sequence} disagrees with event envelope"
                )));
            }
            let actual_event_digest = contract_sha256(&event)
                .map_err(|error| StoreError::Corrupt(format!("journal digest: {error}")))?;
            if actual_event_digest != expected_event_digest {
                return Err(StoreError::Corrupt(format!(
                    "journal event digest mismatch at sequence {sequence}"
                )));
            }
            let actual_entry_hash = journal_hash(&previous_hash, &actual_event_digest);
            if actual_entry_hash != stored_entry_hash {
                return Err(StoreError::Corrupt(format!(
                    "journal chain hash mismatch at sequence {sequence}"
                )));
            }

            previous_hash = stored_entry_hash;
            expected_sequence += 1;
            entries += 1;
        }

        Ok(JournalVerification {
            ok: true,
            entries,
            head_hash: previous_hash,
        })
    }

    pub(crate) fn connection(&self) -> Result<Connection, StoreError> {
        let connection = Connection::open(&self.database_path)?;
        connection.busy_timeout(std::time::Duration::from_secs(5))?;
        connection.execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")?;
        Ok(connection)
    }
}

fn migrate(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
         );",
    )?;

    let current: Option<String> = connection
        .query_row(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )
        .optional()?;

    let version = match current {
        Some(value) => value
            .parse::<i64>()
            .map_err(|_| StoreError::Corrupt("invalid database schema version".to_owned()))?,
        None => 0,
    };
    if version > DATABASE_SCHEMA_VERSION {
        return Err(StoreError::Corrupt(format!(
            "unsupported newer database schema version {version}; current is {DATABASE_SCHEMA_VERSION}"
        )));
    }

    create_core_tables(connection)?;
    crate::sessions::create_session_tables(connection)?;
    crate::authority_runtime::create_authority_tables(connection)?;

    if version != DATABASE_SCHEMA_VERSION {
        connection.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [DATABASE_SCHEMA_VERSION.to_string()],
        )?;
    }
    Ok(())
}

fn create_core_tables(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY NOT NULL,
            projection_json TEXT NOT NULL,
            projection_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS capabilities (
            capability_id TEXT NOT NULL,
            version TEXT NOT NULL,
            descriptor_json TEXT NOT NULL,
            descriptor_sha256 TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (capability_id, version)
         );
         CREATE TABLE IF NOT EXISTS journal_entries (
            sequence INTEGER PRIMARY KEY NOT NULL,
            event_id TEXT UNIQUE NOT NULL,
            workspace_id TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_sha256 TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
         );",
    )?;
    Ok(())
}

fn read_schema_version(connection: &Connection) -> Result<i64, StoreError> {
    let value: String = connection.query_row(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'",
        [],
        |row| row.get(0),
    )?;
    value
        .parse()
        .map_err(|_| StoreError::Corrupt("invalid database schema version".to_owned()))
}

fn seed_capabilities(connection: &Connection) -> Result<(), StoreError> {
    let value: Value = serde_json::from_str(BUILTIN_CAPABILITIES)
        .map_err(|error| StoreError::Contract(format!("builtin capabilities JSON: {error}")))?;
    let descriptors = value
        .as_array()
        .ok_or_else(|| StoreError::Contract("builtin capabilities must be an array".to_owned()))?;
    let now = now_rfc3339();

    for descriptor in descriptors {
        validate_contract(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        if descriptor["contract_type"] != "capability_descriptor" {
            return Err(StoreError::Contract(
                "builtin capability entry is not capability_descriptor".to_owned(),
            ));
        }
        let canonical =
            canonical_json(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest =
            contract_sha256(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let capability_id = descriptor["capability_id"].as_str().ok_or_else(|| {
            StoreError::Contract("capability_id missing after validation".to_owned())
        })?;
        let version = descriptor["version"].as_str().ok_or_else(|| {
            StoreError::Contract("capability version missing after validation".to_owned())
        })?;
        connection.execute(
            "INSERT INTO capabilities (
                capability_id, version, descriptor_json, descriptor_sha256, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(capability_id, version) DO UPDATE SET
                descriptor_json = excluded.descriptor_json,
                descriptor_sha256 = excluded.descriptor_sha256,
                updated_at = excluded.updated_at",
            params![capability_id, version, canonical, digest, now],
        )?;
    }
    Ok(())
}

pub(crate) fn validate_authority_refs(references: &[Value]) -> Result<(), StoreError> {
    for reference in references {
        validate_contract(reference).map_err(|error| StoreError::Contract(error.to_string()))?;
        if reference["contract_type"] != "authority_ref" {
            return Err(StoreError::InvalidInput(
                "workspace references must be authority_ref contracts".to_owned(),
            ));
        }
    }
    Ok(())
}

pub(crate) fn append_event(
    transaction: &Transaction<'_>,
    workspace_id: &str,
    kind: &str,
    payload: Value,
    evidence_refs: Vec<Value>,
) -> Result<Value, StoreError> {
    validate_authority_refs(&evidence_refs)?;
    let previous: Option<(i64, String)> = transaction
        .query_row(
            "SELECT sequence, entry_hash FROM journal_entries ORDER BY sequence DESC LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let (sequence, previous_hash) = match previous {
        Some((sequence, hash)) => (sequence + 1, hash),
        None => (1, String::new()),
    };
    let now = now_rfc3339();
    let event = json!({
        "contract_type": "event_envelope",
        "schema_version": "1.0.0",
        "event_id": Uuid::new_v4().hyphenated().to_string(),
        "workspace_id": workspace_id,
        "producer": "originsd",
        "kind": kind,
        "sequence": sequence,
        "payload": payload,
        "evidence_refs": evidence_refs,
        "created_at": now,
    });
    validate_contract(&event).map_err(|error| StoreError::Contract(error.to_string()))?;
    let canonical =
        canonical_json(&event).map_err(|error| StoreError::Contract(error.to_string()))?;
    let event_digest =
        contract_sha256(&event).map_err(|error| StoreError::Contract(error.to_string()))?;
    let entry_hash = journal_hash(&previous_hash, &event_digest);
    transaction.execute(
        "INSERT INTO journal_entries (
            sequence, event_id, workspace_id, event_json, event_sha256, prev_hash, entry_hash, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            sequence,
            event["event_id"].as_str().expect("validated event id"),
            workspace_id,
            canonical,
            event_digest,
            previous_hash,
            entry_hash,
            now,
        ],
    )?;
    Ok(event)
}

fn journal_hash(previous_hash: &str, event_digest: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(JOURNAL_DOMAIN);
    hasher.update(previous_hash.as_bytes());
    hasher.update(b"\0");
    hasher.update(event_digest.as_bytes());
    hex::encode(hasher.finalize())
}

pub(crate) fn now_rfc3339() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

pub(crate) fn verify_stored_contract(
    kind: &str,
    id: &str,
    canonical: &str,
    expected_digest: &str,
) -> Result<Value, StoreError> {
    let value: Value = serde_json::from_str(canonical)
        .map_err(|error| StoreError::Corrupt(format!("{kind} JSON: {error}")))?;
    validate_contract(&value)
        .map_err(|error| StoreError::Corrupt(format!("{kind} contract: {error}")))?;
    let actual_digest = contract_sha256(&value)
        .map_err(|error| StoreError::Corrupt(format!("{kind} digest: {error}")))?;
    if actual_digest != expected_digest {
        return Err(StoreError::Corrupt(format!("{kind} {id} digest mismatch")));
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_database() -> PathBuf {
        std::env::temp_dir().join(format!("originsd-test-{}.sqlite3", Uuid::new_v4()))
    }

    #[test]
    fn workspace_survives_store_reopen_and_journal_verifies() {
        let path = temp_database();
        let store = Store::open(&path).expect("store opens");
        let workspace = store
            .create_workspace("Persistence proof", Vec::new(), Vec::new())
            .expect("workspace created");
        let workspace_id = workspace["workspace_id"].as_str().unwrap().to_owned();
        assert_eq!(store.workspace_count().unwrap(), 1);
        assert_eq!(store.verify_journal().unwrap().entries, 1);
        drop(store);

        let reopened = Store::open(&path).expect("store reopens");
        let recovered = reopened
            .get_workspace(&workspace_id)
            .expect("workspace recovers");
        assert_eq!(recovered, workspace);
        let journal = reopened.verify_journal().expect("journal verifies");
        assert_eq!(journal.entries, 1);
        assert!(!journal.head_hash.is_empty());
        assert_eq!(reopened.schema_version().unwrap(), DATABASE_SCHEMA_VERSION);
        assert_eq!(reopened.capability_count().unwrap(), 3);

        let _ = fs::remove_file(path);
    }

    #[test]
    fn empty_workspace_name_is_rejected() {
        let path = temp_database();
        let store = Store::open(&path).expect("store opens");
        let error = store
            .create_workspace("   ", Vec::new(), Vec::new())
            .expect_err("empty name must fail");
        assert!(matches!(error, StoreError::InvalidInput(_)));
        let _ = fs::remove_file(path);
    }
}
