use originsd::store::{Store, StoreError};
use rusqlite::Connection;
use std::fs;
use std::path::{Path, PathBuf};
use uuid::Uuid;

fn temp_database() -> PathBuf {
    std::env::temp_dir().join(format!("originsd-integrity-{}.sqlite3", Uuid::new_v4()))
}

fn cleanup_database(path: &Path) {
    let _ = fs::remove_file(path);
    let _ = fs::remove_file(format!("{}-wal", path.display()));
    let _ = fs::remove_file(format!("{}-shm", path.display()));
}

#[test]
fn journal_chain_tampering_is_detected() {
    let path = temp_database();
    let store = Store::open(&path).expect("store opens");
    store
        .create_workspace("Journal tamper proof", Vec::new(), Vec::new())
        .expect("workspace created");

    let connection = Connection::open(&path).expect("database opens for controlled corruption");
    connection
        .execute(
            "UPDATE journal_entries SET entry_hash = ?1 WHERE sequence = 1",
            ["00".repeat(32)],
        )
        .expect("controlled journal corruption succeeds");
    drop(connection);

    let error = store
        .verify_journal()
        .expect_err("tampered journal must fail verification");
    assert!(matches!(error, StoreError::Corrupt(_)));
    drop(store);
    cleanup_database(&path);
}

#[test]
fn workspace_projection_tampering_is_detected() {
    let path = temp_database();
    let store = Store::open(&path).expect("store opens");
    let workspace = store
        .create_workspace("Workspace tamper proof", Vec::new(), Vec::new())
        .expect("workspace created");
    let workspace_id = workspace["workspace_id"].as_str().unwrap().to_owned();

    let connection = Connection::open(&path).expect("database opens for controlled corruption");
    connection
        .execute(
            "UPDATE workspaces SET projection_sha256 = ?1 WHERE workspace_id = ?2",
            ["00".repeat(32), workspace_id.clone()],
        )
        .expect("controlled workspace corruption succeeds");
    drop(connection);

    let error = store
        .get_workspace(&workspace_id)
        .expect_err("tampered workspace must fail verification");
    assert!(matches!(error, StoreError::Corrupt(_)));
    drop(store);
    cleanup_database(&path);
}
