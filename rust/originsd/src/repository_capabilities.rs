use crate::store::{now_rfc3339, Store, StoreError};
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::params;
use serde_json::Value;

const REPOSITORY_CAPABILITIES: &str = include_str!("../../../capabilities/repository.json");

pub fn initialize(store: &Store) -> Result<(), StoreError> {
    let value: Value = serde_json::from_str(REPOSITORY_CAPABILITIES)
        .map_err(|error| StoreError::Contract(format!("repository capabilities JSON: {error}")))?;
    let descriptors = value.as_array().ok_or_else(|| {
        StoreError::Contract("repository capabilities must be an array".to_owned())
    })?;
    let connection = store.connection()?;
    let now = now_rfc3339();
    for descriptor in descriptors {
        validate_contract(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        if descriptor["contract_type"] != "capability_descriptor" {
            return Err(StoreError::Contract(
                "repository capability entry is not capability_descriptor".to_owned(),
            ));
        }
        let canonical =
            canonical_json(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest =
            contract_sha256(descriptor).map_err(|error| StoreError::Contract(error.to_string()))?;
        let capability_id = descriptor["capability_id"].as_str().ok_or_else(|| {
            StoreError::Contract("repository capability_id missing after validation".to_owned())
        })?;
        let version = descriptor["version"].as_str().ok_or_else(|| {
            StoreError::Contract("repository capability version missing after validation".to_owned())
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
