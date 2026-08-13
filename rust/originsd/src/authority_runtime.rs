use crate::store::{append_event, now_rfc3339, Store, StoreError};
use chrono::{DateTime, Utc};
use origins_authority_contracts::{
    authority_sha256, validate_authority_contract, validate_lease_within_scope,
    validate_provider_binding,
};
use origins_contracts::{canonical_json, contract_sha256};
use rusqlite::{params, Connection, OptionalExtension, Transaction, TransactionBehavior};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

pub const APPROVAL_AUTHORITY: &str = "jaydumisuni/Hunter-AgentOps";
pub const ISSUANCE_BINDING_SCHEMA: &str = "origins.lease-issuance-binding.v1";
pub const RUNTIME_AUTHORITY_ACTIVATED: bool = false;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ResourceGrant {
    pub resource_id: String,
    pub prefix: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(deny_unknown_fields)]
pub struct NetworkEndpoint {
    pub protocol: String,
    pub host: String,
    pub port: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProviderObservation {
    pub capability_id: String,
    pub provider_id: String,
    pub provider_manifest_digest: String,
    pub provider_generation: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct HostPolicyObservation {
    pub digest: String,
    pub generation: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(deny_unknown_fields)]
pub struct ResourceObservation {
    pub resource_id: String,
    pub generation: u64,
    pub digest: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CurrentAuthorityObservation {
    pub provider: ProviderObservation,
    pub host_policy: HostPolicyObservation,
    pub resources: Vec<ResourceObservation>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LeaseGrant {
    pub holder_kind: String,
    pub holder_id: String,
    pub holder_generation: u64,
    pub effects: Vec<String>,
    pub resource_reads: Vec<ResourceGrant>,
    pub resource_writes: Vec<ResourceGrant>,
    pub resource_denies: Vec<ResourceGrant>,
    pub network_mode: String,
    pub network_endpoints: Vec<NetworkEndpoint>,
    pub network_redirect_policy: String,
    pub environment_names: Vec<String>,
    pub persistent_process_allowed: bool,
    pub delegated_remote_authority: bool,
    pub expires_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AuthorityHandle {
    pub lease_id: String,
    pub lease_revision: u64,
    pub lease_fence: u64,
    pub scope_id: String,
    pub scope_revision: u64,
    pub scope_fence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ResourceAccess {
    pub resource_id: String,
    pub path: String,
    pub mode: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct InvocationRequest {
    pub handle: AuthorityHandle,
    pub capability_id: String,
    pub effect: String,
    pub holder_id: String,
    pub holder_generation: u64,
    pub provider: ProviderObservation,
    pub host_policy: HostPolicyObservation,
    pub resources: Vec<ResourceObservation>,
    pub resource_accesses: Vec<ResourceAccess>,
    pub network_endpoints: Vec<NetworkEndpoint>,
    pub environment_names: Vec<String>,
    pub persistent_process: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AuthorityDecision {
    pub authorized: bool,
    pub code: String,
    pub lease_id: String,
    pub lease_digest: String,
    pub scope_id: String,
    pub scope_digest: String,
    pub lease_revision: u64,
    pub lease_fence: u64,
    pub scope_revision: u64,
    pub scope_fence: u64,
    pub runtime_authority_activated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RevocationResult {
    pub scope_id: String,
    pub lease_id: String,
    pub revoked_leases: u64,
    pub new_revision: u64,
    pub new_fence: u64,
}

#[derive(Debug, Clone)]
struct PreflightBindings {
    receipt_sha256: String,
    workspace_id: String,
    capability_id: String,
    proposal_digest: String,
    scope_id: String,
    scope_digest: String,
    scope_revision: u64,
    scope_fence: u64,
    approval_id: String,
    approval_record_digest: String,
    issuance_binding_digest: String,
    provider: ProviderObservation,
    host_policy: HostPolicyObservation,
    resources: Vec<ResourceObservation>,
}

pub(crate) fn create_authority_tables(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS execution_scopes (
            scope_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            contract_json TEXT NOT NULL,
            contract_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            revision INTEGER NOT NULL,
            fence INTEGER NOT NULL,
            updated_at TEXT NOT NULL
         );
         CREATE INDEX IF NOT EXISTS idx_execution_scopes_workspace
            ON execution_scopes(workspace_id, updated_at DESC);
         CREATE TABLE IF NOT EXISTS capability_leases (
            lease_id TEXT PRIMARY KEY NOT NULL,
            scope_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            contract_json TEXT NOT NULL,
            contract_sha256 TEXT NOT NULL,
            preflight_json TEXT NOT NULL,
            preflight_sha256 TEXT NOT NULL,
            issuance_binding_digest TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            provider_manifest_digest TEXT NOT NULL,
            provider_generation INTEGER NOT NULL,
            host_policy_digest TEXT NOT NULL,
            host_policy_generation INTEGER NOT NULL,
            state TEXT NOT NULL,
            revision INTEGER NOT NULL,
            fence INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (scope_id) REFERENCES execution_scopes(scope_id)
         );
         CREATE INDEX IF NOT EXISTS idx_capability_leases_scope
            ON capability_leases(scope_id, updated_at DESC);
         CREATE UNIQUE INDEX IF NOT EXISTS idx_capability_leases_preflight_once
            ON capability_leases(preflight_sha256);
         CREATE TABLE IF NOT EXISTS capability_lease_resources (
            lease_id TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            digest TEXT NOT NULL,
            PRIMARY KEY (lease_id, resource_id),
            FOREIGN KEY (lease_id) REFERENCES capability_leases(lease_id) ON DELETE CASCADE
         );",
    )?;
    Ok(())
}

pub(crate) fn verify_authority_state(store: &Store) -> Result<(), StoreError> {
    let connection = store.connection()?;
    let mut scopes = BTreeMap::<String, Value>::new();
    {
        let mut statement = connection.prepare(
            "SELECT scope_id, contract_json, contract_sha256 FROM execution_scopes ORDER BY scope_id",
        )?;
        let rows = statement.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;
        for row in rows {
            let (scope_id, canonical, digest) = row?;
            let scope = verify_stored_authority("scope", &scope_id, &canonical, &digest)?;
            if scope["contract_type"] != "execution_scope" {
                return Err(StoreError::Corrupt(format!(
                    "authority scope {scope_id} is not execution_scope"
                )));
            }
            scopes.insert(scope_id, scope);
        }
    }

    let mut statement = connection.prepare(
        "SELECT lease_id, scope_id, contract_json, contract_sha256, preflight_json,
                preflight_sha256, provider_id, provider_manifest_digest, provider_generation,
                host_policy_digest, host_policy_generation
         FROM capability_leases ORDER BY lease_id",
    )?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, String>(6)?,
            row.get::<_, String>(7)?,
            row.get::<_, i64>(8)?,
            row.get::<_, String>(9)?,
            row.get::<_, i64>(10)?,
        ))
    })?;
    for row in rows {
        let (
            lease_id,
            scope_id,
            canonical,
            digest,
            preflight_json,
            preflight_digest,
            provider_id,
            provider_manifest_digest,
            provider_generation,
            host_policy_digest,
            host_policy_generation,
        ) = row?;
        let lease = verify_stored_authority("lease", &lease_id, &canonical, &digest)?;
        if lease["contract_type"] != "capability_lease" {
            return Err(StoreError::Corrupt(format!(
                "authority lease {lease_id} is not capability_lease"
            )));
        }
        let scope = scopes.get(&scope_id).ok_or_else(|| {
            StoreError::Corrupt(format!(
                "lease {lease_id} references missing scope {scope_id}"
            ))
        })?;
        if lease["state"] == "active" {
            validate_lease_within_scope(&lease, scope)
                .map_err(|error| StoreError::Corrupt(error.to_string()))?;
        }
        if lease["provider_id"] != provider_id
            || lease["provider_manifest_digest"] != provider_manifest_digest
            || lease["provider_generation"].as_i64() != Some(provider_generation)
        {
            return Err(StoreError::Corrupt(format!(
                "lease {lease_id} provider metadata diverges from contract"
            )));
        }
        require_positive_i64(provider_generation, "provider_generation")?;
        require_positive_i64(host_policy_generation, "host_policy_generation")?;
        require_digest(&host_policy_digest, "host_policy_digest")?;
        let preflight: Value = serde_json::from_str(&preflight_json).map_err(|error| {
            StoreError::Corrupt(format!("lease {lease_id} preflight JSON: {error}"))
        })?;
        let verified_preflight = validate_preflight_receipt(&preflight)?;
        if verified_preflight.receipt_sha256 != preflight_digest {
            return Err(StoreError::Corrupt(format!(
                "lease {lease_id} preflight digest mismatch"
            )));
        }
        let resources = load_resources(&connection, &lease_id)?;
        normalize_resources(resources)?;
    }
    Ok(())
}

impl Store {
    pub fn issue_capability_lease(
        &self,
        preflight_receipt: &Value,
        current_scope: &Value,
        grant: &LeaseGrant,
        current: &CurrentAuthorityObservation,
    ) -> Result<Value, StoreError> {
        let now = now_rfc3339();
        self.issue_capability_lease_at(preflight_receipt, current_scope, grant, current, &now)
    }

    pub(crate) fn issue_capability_lease_at(
        &self,
        preflight_receipt: &Value,
        current_scope: &Value,
        grant: &LeaseGrant,
        current: &CurrentAuthorityObservation,
        issued_at: &str,
    ) -> Result<Value, StoreError> {
        let bindings = validate_preflight_receipt(preflight_receipt)?;
        validate_authority_contract(current_scope)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        if current_scope["contract_type"] != "execution_scope" {
            return Err(StoreError::InvalidInput(
                "lease issuer requires execution_scope".to_owned(),
            ));
        }
        if current_scope["state"] != "active" {
            return Err(StoreError::Conflict(
                "lease issuer requires active current scope".to_owned(),
            ));
        }
        validate_timestamp(issued_at, "issued_at")?;
        if is_expired(current_scope, issued_at)? {
            return Err(StoreError::Conflict(
                "cannot issue lease from expired current scope".to_owned(),
            ));
        }

        let scope_digest = authority_sha256(current_scope)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        let scope_id = required_string(current_scope, "scope_id")?;
        let workspace_id = required_string(current_scope, "workspace_id")?;
        let scope_revision = required_u64(current_scope, "revision")?;
        let scope_fence = required_u64(current_scope, "fence")?;
        if bindings.scope_id != scope_id
            || bindings.workspace_id != workspace_id
            || bindings.scope_digest != scope_digest
            || bindings.scope_revision != scope_revision
            || bindings.scope_fence != scope_fence
        {
            return Err(StoreError::Conflict(
                "preflight scope binding is stale or mismatched".to_owned(),
            ));
        }
        if !self.workspace_exists(workspace_id)? {
            return Err(StoreError::NotFound(format!("workspace {workspace_id}")));
        }

        validate_current_observation(&bindings, current)?;
        validate_grant(grant)?;

        let lease_id = Uuid::new_v4().hyphenated().to_string();
        let lease = json!({
            "contract_type": "capability_lease",
            "schema_version": "1.1.0",
            "lease_id": lease_id,
            "scope_id": scope_id,
            "workspace_id": workspace_id,
            "capability_id": bindings.capability_id,
            "provider_id": current.provider.provider_id,
            "provider_manifest_digest": current.provider.provider_manifest_digest,
            "provider_generation": current.provider.provider_generation,
            "holder_kind": grant.holder_kind,
            "holder_id": grant.holder_id,
            "holder_generation": grant.holder_generation,
            "effects": grant.effects,
            "resource_reads": grant.resource_reads,
            "resource_writes": grant.resource_writes,
            "resource_denies": grant.resource_denies,
            "network_mode": grant.network_mode,
            "network_endpoints": grant.network_endpoints,
            "network_redirect_policy": grant.network_redirect_policy,
            "environment_names": grant.environment_names,
            "persistent_process_allowed": grant.persistent_process_allowed,
            "delegated_remote_authority": grant.delegated_remote_authority,
            "approval_authority": APPROVAL_AUTHORITY,
            "approval_id": bindings.approval_id,
            "approval_digest": bindings.approval_record_digest,
            "proposal_digest": bindings.proposal_digest,
            "state": "active",
            "fence": 1,
            "issued_at": issued_at,
            "updated_at": issued_at,
            "expires_at": grant.expires_at,
            "revision": 1
        });
        validate_lease_within_scope(&lease, current_scope)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        validate_provider_binding(
            &lease,
            &current.provider.provider_id,
            &current.provider.provider_manifest_digest,
            current.provider.provider_generation,
        )
        .map_err(|error| StoreError::InvalidInput(error.to_string()))?;

        let scope_canonical = canonical_json(current_scope)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        let lease_canonical =
            canonical_json(&lease).map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        let lease_digest = authority_sha256(&lease)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        let preflight_canonical = canonical_json(preflight_receipt)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        let resources = normalize_resources(current.resources.clone())?;

        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        store_scope_exact(&transaction, current_scope, &scope_canonical, &scope_digest)?;
        transaction.execute(
            "INSERT INTO capability_leases (
                lease_id, scope_id, workspace_id, contract_json, contract_sha256,
                preflight_json, preflight_sha256, issuance_binding_digest,
                provider_id, provider_manifest_digest, provider_generation,
                host_policy_digest, host_policy_generation,
                state, revision, fence, created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13,
                       'active', 1, 1, ?14, ?14)",
            params![
                lease["lease_id"].as_str().expect("validated lease id"),
                scope_id,
                workspace_id,
                lease_canonical,
                lease_digest,
                preflight_canonical,
                bindings.receipt_sha256,
                bindings.issuance_binding_digest,
                current.provider.provider_id,
                current.provider.provider_manifest_digest,
                i64_from_u64(current.provider.provider_generation, "provider_generation")?,
                current.host_policy.digest,
                i64_from_u64(current.host_policy.generation, "host_policy_generation")?,
                issued_at,
            ],
        )?;
        for resource in &resources {
            transaction.execute(
                "INSERT INTO capability_lease_resources (lease_id, resource_id, generation, digest)
                 VALUES (?1, ?2, ?3, ?4)",
                params![
                    lease["lease_id"].as_str().expect("validated lease id"),
                    resource.resource_id,
                    i64_from_u64(resource.generation, "resource generation")?,
                    resource.digest,
                ],
            )?;
        }
        append_event(
            &transaction,
            workspace_id,
            "authority.lease.issued",
            json!({
                "lease_id": lease["lease_id"],
                "lease_sha256": lease_digest,
                "scope_id": scope_id,
                "scope_sha256": scope_digest,
                "scope_revision": scope_revision,
                "scope_fence": scope_fence,
                "preflight_sha256": bindings.receipt_sha256,
                "issuance_binding_digest": bindings.issuance_binding_digest,
                "runtime_authority_activated": false
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(lease)
    }

    pub fn get_execution_scope(&self, scope_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String)> = connection
            .query_row(
                "SELECT contract_json, contract_sha256 FROM execution_scopes WHERE scope_id = ?1",
                [scope_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, digest) =
            stored.ok_or_else(|| StoreError::NotFound(format!("execution scope {scope_id}")))?;
        verify_stored_authority("scope", scope_id, &canonical, &digest)
    }

    pub fn get_capability_lease(&self, lease_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String)> = connection
            .query_row(
                "SELECT contract_json, contract_sha256 FROM capability_leases WHERE lease_id = ?1",
                [lease_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, digest) =
            stored.ok_or_else(|| StoreError::NotFound(format!("capability lease {lease_id}")))?;
        verify_stored_authority("lease", lease_id, &canonical, &digest)
    }

    pub fn authority_handle(&self, lease_id: &str) -> Result<AuthorityHandle, StoreError> {
        let lease = self.get_capability_lease(lease_id)?;
        let scope_id = required_string(&lease, "scope_id")?.to_owned();
        let scope = self.get_execution_scope(&scope_id)?;
        Ok(AuthorityHandle {
            lease_id: lease_id.to_owned(),
            lease_revision: required_u64(&lease, "revision")?,
            lease_fence: required_u64(&lease, "fence")?,
            scope_id,
            scope_revision: required_u64(&scope, "revision")?,
            scope_fence: required_u64(&scope, "fence")?,
        })
    }

    pub fn authorize_invocation(
        &self,
        request: &InvocationRequest,
    ) -> Result<AuthorityDecision, StoreError> {
        let now = now_rfc3339();
        self.authorize_invocation_at(request, &now)
    }

    pub(crate) fn authorize_invocation_at(
        &self,
        request: &InvocationRequest,
        observed_at: &str,
    ) -> Result<AuthorityDecision, StoreError> {
        validate_timestamp(observed_at, "observed_at")?;
        let lease = self.get_capability_lease(&request.handle.lease_id)?;
        let scope_id = required_string(&lease, "scope_id")?.to_owned();
        let scope = self.get_execution_scope(&scope_id)?;
        let lease_digest =
            authority_sha256(&lease).map_err(|error| StoreError::Corrupt(error.to_string()))?;
        let scope_digest =
            authority_sha256(&scope).map_err(|error| StoreError::Corrupt(error.to_string()))?;
        let lease_revision = required_u64(&lease, "revision")?;
        let lease_fence = required_u64(&lease, "fence")?;
        let scope_revision = required_u64(&scope, "revision")?;
        let scope_fence = required_u64(&scope, "fence")?;

        let base = || AuthorityDecision {
            authorized: false,
            code: String::new(),
            lease_id: request.handle.lease_id.clone(),
            lease_digest: lease_digest.clone(),
            scope_id: scope_id.clone(),
            scope_digest: scope_digest.clone(),
            lease_revision,
            lease_fence,
            scope_revision,
            scope_fence,
            runtime_authority_activated: false,
        };
        let deny = |code: &str| {
            let mut decision = base();
            decision.code = code.to_owned();
            decision
        };

        if request.handle.scope_id != scope_id
            || request.handle.lease_revision != lease_revision
            || request.handle.lease_fence != lease_fence
            || request.handle.scope_revision != scope_revision
            || request.handle.scope_fence != scope_fence
        {
            return Ok(deny("STALE_AUTHORITY_HANDLE"));
        }
        if lease["state"] != "active" {
            return Ok(deny("LEASE_NOT_ACTIVE"));
        }
        if scope["state"] != "active" {
            return Ok(deny("SCOPE_NOT_ACTIVE"));
        }
        if is_expired(&lease, observed_at)? {
            return Ok(deny("LEASE_EXPIRED"));
        }
        if is_expired(&scope, observed_at)? {
            return Ok(deny("SCOPE_EXPIRED"));
        }
        if let Err(error) = validate_lease_within_scope(&lease, &scope) {
            return Ok(deny(error.code));
        }
        if required_string(&lease, "capability_id")? != request.capability_id {
            return Ok(deny("CAPABILITY_MISMATCH"));
        }
        if !string_array(&lease, "effects")?
            .iter()
            .any(|effect| effect == &request.effect)
        {
            return Ok(deny("EFFECT_NOT_GRANTED"));
        }
        if required_string(&lease, "holder_id")? != request.holder_id
            || required_u64(&lease, "holder_generation")? != request.holder_generation
        {
            return Ok(deny("HOLDER_MISMATCH"));
        }
        if validate_provider_binding(
            &lease,
            &request.provider.provider_id,
            &request.provider.provider_manifest_digest,
            request.provider.provider_generation,
        )
        .is_err()
            || request.provider.capability_id != request.capability_id
        {
            return Ok(deny("PROVIDER_SUBSTITUTION"));
        }

        let connection = self.connection()?;
        let metadata: Option<(String, i64)> = connection
            .query_row(
                "SELECT host_policy_digest, host_policy_generation
                 FROM capability_leases WHERE lease_id = ?1",
                [&request.handle.lease_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (host_digest, host_generation) = metadata.ok_or_else(|| {
            StoreError::Corrupt(format!(
                "lease {} metadata missing",
                request.handle.lease_id
            ))
        })?;
        if request.host_policy.digest != host_digest
            || i64_from_u64(request.host_policy.generation, "host policy generation")?
                != host_generation
        {
            return Ok(deny("HOST_POLICY_STALE"));
        }
        let expected_resources = load_resources(&connection, &request.handle.lease_id)?;
        let actual_resources = normalize_resources(request.resources.clone())?;
        if expected_resources != actual_resources {
            return Ok(deny("RESOURCE_GENERATION_STALE"));
        }

        for access in &request.resource_accesses {
            if !matches!(access.mode.as_str(), "read" | "write") {
                return Ok(deny("INVALID_RESOURCE_ACCESS"));
            }
            if normalize_relative_path(&access.path).is_err() {
                return Ok(deny("INVALID_RESOURCE_PATH"));
            }
            if !resource_access_allowed(&lease, access)? {
                return Ok(deny("RESOURCE_ACCESS_DENIED"));
            }
        }
        if !network_access_allowed(&lease, &request.network_endpoints)? {
            return Ok(deny("NETWORK_ACCESS_DENIED"));
        }
        let granted_environment = string_array(&lease, "environment_names")?
            .into_iter()
            .collect::<BTreeSet<_>>();
        if request
            .environment_names
            .iter()
            .any(|name| !granted_environment.contains(name))
        {
            return Ok(deny("ENVIRONMENT_ACCESS_DENIED"));
        }
        if request.persistent_process && lease["persistent_process_allowed"].as_bool() != Some(true)
        {
            return Ok(deny("PERSISTENT_PROCESS_DENIED"));
        }

        let mut decision = base();
        decision.authorized = true;
        decision.code = "AUTHORIZED".to_owned();
        Ok(decision)
    }

    pub fn revoke_lease(
        &self,
        lease_id: &str,
        reason: &str,
    ) -> Result<RevocationResult, StoreError> {
        let now = now_rfc3339();
        self.revoke_lease_at(lease_id, reason, &now)
    }

    pub(crate) fn revoke_lease_at(
        &self,
        lease_id: &str,
        reason: &str,
        observed_at: &str,
    ) -> Result<RevocationResult, StoreError> {
        validate_reason(reason)?;
        validate_timestamp(observed_at, "observed_at")?;
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut lease = load_authority_tx(&transaction, "capability_leases", "lease_id", lease_id)?;
        if lease["state"] == "revoked" {
            return Ok(RevocationResult {
                scope_id: required_string(&lease, "scope_id")?.to_owned(),
                lease_id: lease_id.to_owned(),
                revoked_leases: 0,
                new_revision: required_u64(&lease, "revision")?,
                new_fence: required_u64(&lease, "fence")?,
            });
        }
        let workspace_id = required_string(&lease, "workspace_id")?.to_owned();
        let scope_id = required_string(&lease, "scope_id")?.to_owned();
        let previous_revision = required_u64(&lease, "revision")?;
        let previous_fence = required_u64(&lease, "fence")?;
        set_revoked(&mut lease, observed_at)?;
        persist_lease_contract(&transaction, &lease)?;
        append_event(
            &transaction,
            &workspace_id,
            "authority.lease.revoked",
            json!({
                "lease_id": lease_id,
                "scope_id": scope_id,
                "reason": reason,
                "previous_revision": previous_revision,
                "previous_fence": previous_fence,
                "revision": lease["revision"],
                "fence": lease["fence"]
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(RevocationResult {
            scope_id,
            lease_id: lease_id.to_owned(),
            revoked_leases: 1,
            new_revision: previous_revision + 1,
            new_fence: previous_fence + 1,
        })
    }

    pub fn revoke_scope(
        &self,
        scope_id: &str,
        reason: &str,
    ) -> Result<RevocationResult, StoreError> {
        let now = now_rfc3339();
        self.revoke_scope_at(scope_id, reason, &now)
    }

    pub(crate) fn revoke_scope_at(
        &self,
        scope_id: &str,
        reason: &str,
        observed_at: &str,
    ) -> Result<RevocationResult, StoreError> {
        validate_reason(reason)?;
        validate_timestamp(observed_at, "observed_at")?;
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut scope = load_authority_tx(&transaction, "execution_scopes", "scope_id", scope_id)?;
        let workspace_id = required_string(&scope, "workspace_id")?.to_owned();
        let previous_revision = required_u64(&scope, "revision")?;
        let previous_fence = required_u64(&scope, "fence")?;
        if scope["state"] == "revoked" {
            return Ok(RevocationResult {
                scope_id: scope_id.to_owned(),
                lease_id: String::new(),
                revoked_leases: 0,
                new_revision: previous_revision,
                new_fence: previous_fence,
            });
        }
        set_revoked(&mut scope, observed_at)?;
        persist_scope_contract(&transaction, &scope)?;

        let lease_rows = {
            let mut statement = transaction.prepare(
                "SELECT lease_id, contract_json, contract_sha256 FROM capability_leases
                 WHERE scope_id = ?1 ORDER BY lease_id",
            )?;
            let rows = statement.query_map([scope_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })?;
            let mut collected = Vec::new();
            for row in rows {
                collected.push(row?);
            }
            collected
        };
        let mut revoked_leases = 0_u64;
        for (lease_id, canonical, digest) in lease_rows {
            let mut lease = verify_stored_authority("lease", &lease_id, &canonical, &digest)?;
            if lease["state"] == "revoked" {
                continue;
            }
            set_revoked(&mut lease, observed_at)?;
            persist_lease_contract(&transaction, &lease)?;
            revoked_leases += 1;
            append_event(
                &transaction,
                &workspace_id,
                "authority.lease.revoked",
                json!({
                    "lease_id": lease_id,
                    "scope_id": scope_id,
                    "reason": "scope_revoked",
                    "revision": lease["revision"],
                    "fence": lease["fence"]
                }),
                Vec::new(),
            )?;
        }
        append_event(
            &transaction,
            &workspace_id,
            "authority.scope.revoked",
            json!({
                "scope_id": scope_id,
                "reason": reason,
                "previous_revision": previous_revision,
                "previous_fence": previous_fence,
                "revision": scope["revision"],
                "fence": scope["fence"],
                "revoked_leases": revoked_leases
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(RevocationResult {
            scope_id: scope_id.to_owned(),
            lease_id: String::new(),
            revoked_leases,
            new_revision: required_u64(&scope, "revision")?,
            new_fence: required_u64(&scope, "fence")?,
        })
    }
}

fn validate_preflight_receipt(receipt: &Value) -> Result<PreflightBindings, StoreError> {
    let object = receipt.as_object().ok_or_else(|| {
        StoreError::InvalidInput("preflight receipt must be an object".to_owned())
    })?;
    if object.get("eligible").and_then(Value::as_bool) != Some(true) {
        return Err(StoreError::Conflict(
            "preflight receipt is not eligible".to_owned(),
        ));
    }
    if object
        .get("failure_codes")
        .and_then(Value::as_array)
        .map_or(true, |items| !items.is_empty())
    {
        return Err(StoreError::Conflict(
            "eligible preflight must have no failure codes".to_owned(),
        ));
    }
    for field in [
        "issuer_enabled",
        "lease_created",
        "runtime_authority_activated",
    ] {
        if object.get(field).and_then(Value::as_bool) != Some(false) {
            return Err(StoreError::Conflict(format!(
                "preflight field {field} must remain false before issuer transaction"
            )));
        }
    }
    let receipt_sha256 = object
        .get("receipt_sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| StoreError::InvalidInput("receipt_sha256 is required".to_owned()))?
        .to_owned();
    require_digest(&receipt_sha256, "receipt_sha256")?;
    let mut body = receipt.clone();
    body.as_object_mut()
        .expect("receipt object")
        .remove("receipt_sha256");
    let calculated =
        contract_sha256(&body).map_err(|error| StoreError::InvalidInput(error.to_string()))?;
    if calculated != receipt_sha256 {
        return Err(StoreError::Conflict(
            "preflight receipt digest mismatch".to_owned(),
        ));
    }

    let resources = parse_receipt_resources(object.get("resource_bindings"))?;
    let provider = ProviderObservation {
        capability_id: required_object_string(object, "capability_id")?.to_owned(),
        provider_id: required_object_string(object, "provider_id")?.to_owned(),
        provider_manifest_digest: required_object_string(object, "provider_manifest_digest")?
            .to_owned(),
        provider_generation: required_object_u64(object, "provider_generation")?,
    };
    require_digest(
        &provider.provider_manifest_digest,
        "provider_manifest_digest",
    )?;
    let host_policy = HostPolicyObservation {
        digest: required_object_string(object, "host_policy_digest")?.to_owned(),
        generation: required_object_u64(object, "host_policy_generation")?,
    };
    require_digest(&host_policy.digest, "host_policy_digest")?;
    let bindings = PreflightBindings {
        receipt_sha256,
        workspace_id: required_object_string(object, "workspace_id")?.to_owned(),
        capability_id: provider.capability_id.clone(),
        proposal_digest: required_object_string(object, "proposal_digest")?.to_owned(),
        scope_id: required_object_string(object, "scope_id")?.to_owned(),
        scope_digest: required_object_string(object, "scope_digest")?.to_owned(),
        scope_revision: required_object_u64(object, "scope_revision")?,
        scope_fence: required_object_u64(object, "scope_fence")?,
        approval_id: required_object_string(object, "approval_id")?.to_owned(),
        approval_record_digest: required_object_string(object, "approval_record_digest")?
            .to_owned(),
        issuance_binding_digest: required_object_string(object, "issuance_binding_digest")?
            .to_owned(),
        provider,
        host_policy,
        resources,
    };
    for (value, label) in [
        (&bindings.proposal_digest, "proposal_digest"),
        (&bindings.scope_digest, "scope_digest"),
        (&bindings.approval_record_digest, "approval_record_digest"),
        (&bindings.issuance_binding_digest, "issuance_binding_digest"),
    ] {
        require_digest(value, label)?;
    }

    let binding_document = json!({
        "schema": ISSUANCE_BINDING_SCHEMA,
        "workspace_id": bindings.workspace_id,
        "capability_id": bindings.capability_id,
        "proposal_digest": bindings.proposal_digest,
        "approval_id": bindings.approval_id,
        "approval_record_digest": bindings.approval_record_digest,
        "scope_id": bindings.scope_id,
        "scope_digest": bindings.scope_digest,
        "scope_revision": bindings.scope_revision,
        "scope_fence": bindings.scope_fence,
        "provider_id": bindings.provider.provider_id,
        "provider_manifest_digest": bindings.provider.provider_manifest_digest,
        "provider_generation": bindings.provider.provider_generation,
        "host_policy_digest": bindings.host_policy.digest,
        "host_policy_generation": bindings.host_policy.generation,
        "resource_bindings": bindings.resources
    });
    let binding_digest = contract_sha256(&binding_document)
        .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
    if binding_digest != bindings.issuance_binding_digest {
        return Err(StoreError::Conflict(
            "preflight issuance binding digest mismatch".to_owned(),
        ));
    }
    Ok(bindings)
}

fn validate_current_observation(
    bindings: &PreflightBindings,
    current: &CurrentAuthorityObservation,
) -> Result<(), StoreError> {
    if current.provider != bindings.provider {
        return Err(StoreError::Conflict(
            "provider observation changed after preflight".to_owned(),
        ));
    }
    if current.host_policy != bindings.host_policy {
        return Err(StoreError::Conflict(
            "host policy observation changed after preflight".to_owned(),
        ));
    }
    let actual = normalize_resources(current.resources.clone())?;
    if actual != bindings.resources {
        return Err(StoreError::Conflict(
            "resource generations changed after preflight".to_owned(),
        ));
    }
    Ok(())
}

fn validate_grant(grant: &LeaseGrant) -> Result<(), StoreError> {
    if grant.holder_id.is_empty() || grant.holder_generation == 0 {
        return Err(StoreError::InvalidInput(
            "lease holder identity/generation is required".to_owned(),
        ));
    }
    if grant.effects.is_empty() {
        return Err(StoreError::InvalidInput(
            "lease grant must contain at least one effect".to_owned(),
        ));
    }
    validate_timestamp_or_empty(&grant.expires_at, "grant.expires_at")
}

fn store_scope_exact(
    transaction: &Transaction<'_>,
    scope: &Value,
    canonical: &str,
    digest: &str,
) -> Result<(), StoreError> {
    let scope_id = required_string(scope, "scope_id")?;
    let existing: Option<(String, String)> = transaction
        .query_row(
            "SELECT contract_json, contract_sha256 FROM execution_scopes WHERE scope_id = ?1",
            [scope_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    if let Some((existing_json, existing_digest)) = existing {
        let existing_scope =
            verify_stored_authority("scope", scope_id, &existing_json, &existing_digest)?;
        if existing_scope != *scope || existing_digest != digest {
            return Err(StoreError::Conflict(
                "current scope differs from durable Origins scope generation".to_owned(),
            ));
        }
        return Ok(());
    }
    transaction.execute(
        "INSERT INTO execution_scopes (
            scope_id, workspace_id, contract_json, contract_sha256, state, revision, fence, updated_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            scope_id,
            required_string(scope, "workspace_id")?,
            canonical,
            digest,
            required_string(scope, "state")?,
            i64_from_u64(required_u64(scope, "revision")?, "scope revision")?,
            i64_from_u64(required_u64(scope, "fence")?, "scope fence")?,
            required_string(scope, "updated_at")?,
        ],
    )?;
    Ok(())
}

fn persist_scope_contract(transaction: &Transaction<'_>, scope: &Value) -> Result<(), StoreError> {
    validate_authority_contract(scope).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    let canonical =
        canonical_json(scope).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    let digest = authority_sha256(scope).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    transaction.execute(
        "UPDATE execution_scopes SET contract_json = ?2, contract_sha256 = ?3, state = ?4,
             revision = ?5, fence = ?6, updated_at = ?7 WHERE scope_id = ?1",
        params![
            required_string(scope, "scope_id")?,
            canonical,
            digest,
            required_string(scope, "state")?,
            i64_from_u64(required_u64(scope, "revision")?, "scope revision")?,
            i64_from_u64(required_u64(scope, "fence")?, "scope fence")?,
            required_string(scope, "updated_at")?,
        ],
    )?;
    Ok(())
}

fn persist_lease_contract(transaction: &Transaction<'_>, lease: &Value) -> Result<(), StoreError> {
    validate_authority_contract(lease).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    let canonical =
        canonical_json(lease).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    let digest = authority_sha256(lease).map_err(|error| StoreError::Corrupt(error.to_string()))?;
    transaction.execute(
        "UPDATE capability_leases SET contract_json = ?2, contract_sha256 = ?3, state = ?4,
             revision = ?5, fence = ?6, updated_at = ?7 WHERE lease_id = ?1",
        params![
            required_string(lease, "lease_id")?,
            canonical,
            digest,
            required_string(lease, "state")?,
            i64_from_u64(required_u64(lease, "revision")?, "lease revision")?,
            i64_from_u64(required_u64(lease, "fence")?, "lease fence")?,
            required_string(lease, "updated_at")?,
        ],
    )?;
    Ok(())
}

fn set_revoked(value: &mut Value, observed_at: &str) -> Result<(), StoreError> {
    let revision = required_u64(value, "revision")?;
    let fence = required_u64(value, "fence")?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| StoreError::Corrupt("authority contract is not object".to_owned()))?;
    object.insert("state".to_owned(), Value::String("revoked".to_owned()));
    object.insert("revision".to_owned(), json!(revision + 1));
    object.insert("fence".to_owned(), json!(fence + 1));
    object.insert(
        "updated_at".to_owned(),
        Value::String(observed_at.to_owned()),
    );
    Ok(())
}

fn load_authority_tx(
    transaction: &Transaction<'_>,
    table: &str,
    id_column: &str,
    id: &str,
) -> Result<Value, StoreError> {
    let sql = match (table, id_column) {
        ("execution_scopes", "scope_id") => {
            "SELECT contract_json, contract_sha256 FROM execution_scopes WHERE scope_id = ?1"
        }
        ("capability_leases", "lease_id") => {
            "SELECT contract_json, contract_sha256 FROM capability_leases WHERE lease_id = ?1"
        }
        _ => {
            return Err(StoreError::Corrupt(
                "invalid authority table lookup".to_owned(),
            ))
        }
    };
    let stored: Option<(String, String)> = transaction
        .query_row(sql, [id], |row| Ok((row.get(0)?, row.get(1)?)))
        .optional()?;
    let (canonical, digest) = stored.ok_or_else(|| StoreError::NotFound(id.to_owned()))?;
    verify_stored_authority(table, id, &canonical, &digest)
}

fn verify_stored_authority(
    kind: &str,
    id: &str,
    canonical: &str,
    expected_digest: &str,
) -> Result<Value, StoreError> {
    let value: Value = serde_json::from_str(canonical)
        .map_err(|error| StoreError::Corrupt(format!("{kind} {id} JSON: {error}")))?;
    validate_authority_contract(&value)
        .map_err(|error| StoreError::Corrupt(format!("{kind} {id}: {error}")))?;
    let actual = authority_sha256(&value)
        .map_err(|error| StoreError::Corrupt(format!("{kind} {id} digest: {error}")))?;
    if actual != expected_digest {
        return Err(StoreError::Corrupt(format!("{kind} {id} digest mismatch")));
    }
    Ok(value)
}

fn parse_receipt_resources(value: Option<&Value>) -> Result<Vec<ResourceObservation>, StoreError> {
    let items = value
        .and_then(Value::as_array)
        .ok_or_else(|| StoreError::InvalidInput("resource_bindings must be an array".to_owned()))?;
    let parsed = items
        .iter()
        .map(|item| {
            serde_json::from_value::<ResourceObservation>(item.clone()).map_err(|error| {
                StoreError::InvalidInput(format!("invalid resource binding: {error}"))
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    normalize_resources(parsed)
}

fn normalize_resources(
    mut resources: Vec<ResourceObservation>,
) -> Result<Vec<ResourceObservation>, StoreError> {
    resources.sort();
    let mut ids = BTreeSet::new();
    for item in &resources {
        if item.resource_id.is_empty() || item.generation == 0 {
            return Err(StoreError::InvalidInput(
                "resource observation requires id and positive generation".to_owned(),
            ));
        }
        require_digest(&item.digest, "resource digest")?;
        if !ids.insert(item.resource_id.clone()) {
            return Err(StoreError::InvalidInput(format!(
                "duplicate resource observation {}",
                item.resource_id
            )));
        }
    }
    Ok(resources)
}

fn load_resources(
    connection: &Connection,
    lease_id: &str,
) -> Result<Vec<ResourceObservation>, StoreError> {
    let mut statement = connection.prepare(
        "SELECT resource_id, generation, digest FROM capability_lease_resources
         WHERE lease_id = ?1 ORDER BY resource_id",
    )?;
    let rows = statement.query_map([lease_id], |row| {
        Ok(ResourceObservation {
            resource_id: row.get(0)?,
            generation: u64::try_from(row.get::<_, i64>(1)?).unwrap_or(0),
            digest: row.get(2)?,
        })
    })?;
    let mut resources = Vec::new();
    for row in rows {
        resources.push(row?);
    }
    normalize_resources(resources)
}

fn resource_access_allowed(lease: &Value, access: &ResourceAccess) -> Result<bool, StoreError> {
    let path = normalize_relative_path(&access.path)?;
    let denies = grants(lease, "resource_denies")?;
    if denies
        .iter()
        .any(|grant| grant.resource_id == access.resource_id && prefix_covers(&grant.prefix, &path))
    {
        return Ok(false);
    }
    let field = if access.mode == "write" {
        "resource_writes"
    } else {
        "resource_reads"
    };
    Ok(grants(lease, field)?.iter().any(|grant| {
        grant.resource_id == access.resource_id && prefix_covers(&grant.prefix, &path)
    }))
}

fn network_access_allowed(
    lease: &Value,
    requested: &[NetworkEndpoint],
) -> Result<bool, StoreError> {
    let mode = required_string(lease, "network_mode")?;
    if mode == "deny" {
        return Ok(requested.is_empty());
    }
    if mode == "delegated_remote" {
        return Ok(requested.is_empty());
    }
    let granted_value = lease["network_endpoints"]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt("lease network_endpoints invalid".to_owned()))?;
    let granted = granted_value
        .iter()
        .map(|item| {
            serde_json::from_value::<NetworkEndpoint>(item.clone())
                .map_err(|error| StoreError::Corrupt(error.to_string()))
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    Ok(requested.iter().all(|endpoint| granted.contains(endpoint)))
}

fn grants(value: &Value, field: &str) -> Result<Vec<ResourceGrant>, StoreError> {
    value[field]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt(format!("authority {field} invalid")))?
        .iter()
        .map(|item| {
            serde_json::from_value::<ResourceGrant>(item.clone())
                .map_err(|error| StoreError::Corrupt(error.to_string()))
        })
        .collect()
}

fn normalize_relative_path(path: &str) -> Result<String, StoreError> {
    if path.starts_with('/') || path.starts_with('\\') || path.contains('\\') {
        return Err(StoreError::InvalidInput(
            "resource path must use canonical relative slash form".to_owned(),
        ));
    }
    let mut parts = Vec::new();
    for part in path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." || part.contains(':') {
            return Err(StoreError::InvalidInput(
                "resource path traversal/prefix is forbidden".to_owned(),
            ));
        }
        parts.push(part);
    }
    Ok(parts.join("/"))
}

fn prefix_covers(prefix: &str, path: &str) -> bool {
    if prefix.is_empty() {
        return true;
    }
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn is_expired(value: &Value, observed_at: &str) -> Result<bool, StoreError> {
    let expires = required_string(value, "expires_at")?;
    if expires.is_empty() {
        return Ok(false);
    }
    let expiry = parse_timestamp(expires, "expires_at")?;
    let observed = parse_timestamp(observed_at, "observed_at")?;
    Ok(expiry <= observed)
}

fn validate_reason(reason: &str) -> Result<(), StoreError> {
    if reason.trim().is_empty() || reason.chars().count() > 500 {
        return Err(StoreError::InvalidInput(
            "revocation reason must be 1..500 characters".to_owned(),
        ));
    }
    Ok(())
}

fn validate_timestamp(value: &str, label: &str) -> Result<(), StoreError> {
    parse_timestamp(value, label).map(|_| ())
}

fn validate_timestamp_or_empty(value: &str, label: &str) -> Result<(), StoreError> {
    if value.is_empty() {
        Ok(())
    } else {
        validate_timestamp(value, label)
    }
}

fn parse_timestamp(value: &str, label: &str) -> Result<DateTime<Utc>, StoreError> {
    DateTime::parse_from_rfc3339(value)
        .map(|parsed| parsed.with_timezone(&Utc))
        .map_err(|_| StoreError::InvalidInput(format!("{label} must be RFC3339 timestamp")))
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value[field]
        .as_str()
        .ok_or_else(|| StoreError::Corrupt(format!("authority field {field} invalid")))
}

fn required_u64(value: &Value, field: &str) -> Result<u64, StoreError> {
    value[field]
        .as_u64()
        .ok_or_else(|| StoreError::Corrupt(format!("authority field {field} invalid")))
}

fn string_array(value: &Value, field: &str) -> Result<Vec<String>, StoreError> {
    value[field]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt(format!("authority field {field} invalid")))?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_owned)
                .ok_or_else(|| StoreError::Corrupt(format!("authority field {field} invalid")))
        })
        .collect()
}

fn required_object_string<'a>(
    object: &'a serde_json::Map<String, Value>,
    field: &str,
) -> Result<&'a str, StoreError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| StoreError::InvalidInput(format!("preflight field {field} required")))
}

fn required_object_u64(
    object: &serde_json::Map<String, Value>,
    field: &str,
) -> Result<u64, StoreError> {
    let value = object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| StoreError::InvalidInput(format!("preflight field {field} invalid")))?;
    if value == 0 {
        return Err(StoreError::InvalidInput(format!(
            "preflight field {field} must be positive"
        )));
    }
    Ok(value)
}

fn require_digest(value: &str, label: &str) -> Result<(), StoreError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(StoreError::InvalidInput(format!(
            "{label} must be lowercase SHA-256"
        )));
    }
    Ok(())
}

fn require_positive_i64(value: i64, label: &str) -> Result<(), StoreError> {
    if value < 1 {
        return Err(StoreError::Corrupt(format!("{label} must be positive")));
    }
    Ok(())
}

fn i64_from_u64(value: u64, label: &str) -> Result<i64, StoreError> {
    i64::try_from(value).map_err(|_| StoreError::InvalidInput(format!("{label} is too large")))
}
