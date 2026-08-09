use crate::store::{now_rfc3339, Store, StoreError};
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::params;
use serde_json::Value;

const HUNTER_CAPABILITIES: &str = include_str!("../../../capabilities/hunter.json");
const HUNTER_CAPABILITY_ID: &str = "origins.hunter.transport";

pub fn synchronize(store: &Store, configured: bool) -> Result<(), StoreError> {
    if !configured {
        let connection = store.connection()?;
        connection.execute(
            "DELETE FROM capabilities WHERE capability_id = ?1",
            [HUNTER_CAPABILITY_ID],
        )?;
        return Ok(());
    }

    let value: Value = serde_json::from_str(HUNTER_CAPABILITIES)
        .map_err(|error| StoreError::Contract(format!("Hunter capabilities JSON: {error}")))?;
    let descriptors = value
        .as_array()
        .ok_or_else(|| StoreError::Contract("Hunter capabilities must be an array".to_owned()))?;
    let connection = store.connection()?;
    let now = now_rfc3339();
    for descriptor in descriptors {
        validate_contract(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        if descriptor["contract_type"] != "capability_descriptor" {
            return Err(StoreError::Contract(
                "Hunter capability entry is not capability_descriptor".to_owned(),
            ));
        }
        let canonical =
            canonical_json(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest =
            contract_sha256(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let capability_id = descriptor["capability_id"].as_str().ok_or_else(|| {
            StoreError::Contract("Hunter capability_id missing after validation".to_owned())
        })?;
        if capability_id != HUNTER_CAPABILITY_ID {
            return Err(StoreError::Contract(format!(
                "unexpected Hunter capability id {capability_id}"
            )));
        }
        let version = descriptor["version"].as_str().ok_or_else(|| {
            StoreError::Contract("Hunter capability version missing after validation".to_owned())
        })?;
        connection.execute(
            "DELETE FROM capabilities WHERE capability_id = ?1 AND version <> ?2",
            params![capability_id, version],
        )?;
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use uuid::Uuid;

    #[test]
    fn hunter_capability_is_removed_when_transport_becomes_disabled() {
        let root = std::env::temp_dir().join(format!(
            "origins-hunter-capability-test-{}",
            Uuid::new_v4().hyphenated()
        ));
        fs::create_dir_all(&root).unwrap();
        let store = Store::open(root.join("origins.sqlite3")).unwrap();

        synchronize(&store, true).unwrap();
        let configured = store.list_capabilities().unwrap();
        assert!(configured
            .iter()
            .any(|item| { item["capability_id"].as_str() == Some(HUNTER_CAPABILITY_ID) }));

        synchronize(&store, false).unwrap();
        let disabled = store.list_capabilities().unwrap();
        assert!(!disabled
            .iter()
            .any(|item| { item["capability_id"].as_str() == Some(HUNTER_CAPABILITY_ID) }));

        fs::remove_dir_all(root).unwrap();
    }
}
