use origins_authority_contracts::authority_sha256;
use origins_contracts::contract_sha256;
use originsd::authority_runtime::{
    AuthorityHandle, CurrentAuthorityObservation, HostPolicyObservation, InvocationRequest,
    LeaseGrant, NetworkEndpoint, ProviderObservation, ResourceAccess, ResourceGrant,
    ResourceObservation, ISSUANCE_BINDING_SCHEMA, RUNTIME_AUTHORITY_ACTIVATED,
};
use originsd::store::{Store, StoreError};
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use uuid::Uuid;

const RESOURCE_ID: &str = "worktree:33333333-3333-4333-8333-333333333333";
const SCOPE_ID: &str = "22222222-2222-4222-8222-222222222222";
const HOLDER_ID: &str = "55555555-5555-4555-8555-555555555555";
const CAPABILITY_ID: &str = "origins.process.run";
const PROVIDER_ID: &str = "origins.process.local";
const PROVIDER_DIGEST: &str =
    "2222222222222222222222222222222222222222222222222222222222222222";
const HOST_POLICY_DIGEST: &str =
    "3333333333333333333333333333333333333333333333333333333333333333";
const RESOURCE_DIGEST: &str =
    "4444444444444444444444444444444444444444444444444444444444444444";

struct Harness {
    root: PathBuf,
    database: PathBuf,
    store: Store,
    workspace_id: String,
    scope: Value,
    current: CurrentAuthorityObservation,
}

impl Harness {
    fn new(label: &str) -> Self {
        let root = std::env::temp_dir().join(format!(
            "origins-stage2-{label}-{}",
            Uuid::new_v4().hyphenated()
        ));
        fs::create_dir_all(&root).unwrap();
        let database = root.join("origins.sqlite3");
        let store = Store::open(&database).unwrap();
        let workspace = store
            .create_workspace("Stage-2 authority proof", Vec::new(), Vec::new())
            .unwrap();
        let workspace_id = workspace["workspace_id"].as_str().unwrap().to_owned();
        let scope = scope_fixture(&workspace_id);
        let current = current_observation();
        Self {
            root,
            database,
            store,
            workspace_id,
            scope,
            current,
        }
    }

    fn issue(&self, nonce: &str) -> Value {
        let receipt = preflight_receipt(&self.scope, &self.current, nonce);
        self.store
            .issue_capability_lease(&receipt, &self.scope, &grant(), &self.current)
            .unwrap()
    }
}

impl Drop for Harness {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn scope_fixture(workspace_id: &str) -> Value {
    json!({
        "contract_type": "execution_scope",
        "schema_version": "1.1.0",
        "scope_id": SCOPE_ID,
        "workspace_id": workspace_id,
        "operation_id": "agentops:stage2-proof",
        "candidate_id": "",
        "parent_scope_id": "",
        "effects": ["execute", "mutate", "observe", "verify"],
        "resource_reads": [{"resource_id": RESOURCE_ID, "prefix": ""}],
        "resource_writes": [{"resource_id": RESOURCE_ID, "prefix": "src"}],
        "resource_denies": [{"resource_id": RESOURCE_ID, "prefix": ".origins"}],
        "network_mode": "allowlist",
        "network_endpoints": [
            {"protocol": "https", "host": "api.example.com", "port": 443},
            {"protocol": "https", "host": "support.example.com", "port": 443}
        ],
        "network_redirect_policy": "deny_outside_endpoints",
        "environment_names": ["LANG", "PATH"],
        "process_execution_allowed": true,
        "persistent_process_allowed": false,
        "delegation_allowed": true,
        "delegated_remote_authority": false,
        "state": "active",
        "fence": 1,
        "issued_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "expires_at": "",
        "revision": 1
    })
}

fn current_observation() -> CurrentAuthorityObservation {
    CurrentAuthorityObservation {
        provider: ProviderObservation {
            capability_id: CAPABILITY_ID.to_owned(),
            provider_id: PROVIDER_ID.to_owned(),
            provider_manifest_digest: PROVIDER_DIGEST.to_owned(),
            provider_generation: 4,
        },
        host_policy: HostPolicyObservation {
            digest: HOST_POLICY_DIGEST.to_owned(),
            generation: 9,
        },
        resources: vec![ResourceObservation {
            resource_id: RESOURCE_ID.to_owned(),
            generation: 7,
            digest: RESOURCE_DIGEST.to_owned(),
        }],
    }
}

fn grant() -> LeaseGrant {
    LeaseGrant {
        holder_kind: "session".to_owned(),
        holder_id: HOLDER_ID.to_owned(),
        holder_generation: 3,
        effects: vec!["execute".to_owned(), "observe".to_owned()],
        resource_reads: vec![ResourceGrant {
            resource_id: RESOURCE_ID.to_owned(),
            prefix: "src".to_owned(),
        }],
        resource_writes: vec![ResourceGrant {
            resource_id: RESOURCE_ID.to_owned(),
            prefix: "src/generated".to_owned(),
        }],
        resource_denies: vec![ResourceGrant {
            resource_id: RESOURCE_ID.to_owned(),
            prefix: ".origins".to_owned(),
        }],
        network_mode: "allowlist".to_owned(),
        network_endpoints: vec![NetworkEndpoint {
            protocol: "https".to_owned(),
            host: "api.example.com".to_owned(),
            port: 443,
        }],
        network_redirect_policy: "deny_outside_endpoints".to_owned(),
        environment_names: vec!["LANG".to_owned()],
        persistent_process_allowed: false,
        delegated_remote_authority: false,
        expires_at: String::new(),
    }
}

fn preflight_receipt(
    scope: &Value,
    current: &CurrentAuthorityObservation,
    nonce: &str,
) -> Value {
    let workspace_id = scope["workspace_id"].as_str().unwrap();
    let scope_digest = authority_sha256(scope).unwrap();
    let proposal_digest = digest_for(&format!("proposal:{nonce}"));
    let approval_id = format!("approval-{nonce}");
    let approval_record_digest = digest_for(&format!("approval-record:{nonce}"));
    let resource_bindings = current
        .resources
        .iter()
        .map(|item| {
            json!({
                "resource_id": item.resource_id,
                "generation": item.generation,
                "digest": item.digest
            })
        })
        .collect::<Vec<_>>();
    let binding = json!({
        "schema": ISSUANCE_BINDING_SCHEMA,
        "workspace_id": workspace_id,
        "capability_id": CAPABILITY_ID,
        "proposal_digest": proposal_digest,
        "approval_id": approval_id,
        "approval_record_digest": approval_record_digest,
        "scope_id": SCOPE_ID,
        "scope_digest": scope_digest,
        "scope_revision": 1,
        "scope_fence": 1,
        "provider_id": current.provider.provider_id,
        "provider_manifest_digest": current.provider.provider_manifest_digest,
        "provider_generation": current.provider.provider_generation,
        "host_policy_digest": current.host_policy.digest,
        "host_policy_generation": current.host_policy.generation,
        "resource_bindings": resource_bindings
    });
    let issuance_binding_digest = contract_sha256(&binding).unwrap();
    let body = json!({
        "eligible": true,
        "failure_codes": [],
        "observed_at": "2026-08-12T00:00:00Z",
        "workspace_id": workspace_id,
        "capability_id": CAPABILITY_ID,
        "proposal_digest": proposal_digest,
        "scope_id": SCOPE_ID,
        "scope_digest": scope_digest,
        "scope_revision": 1,
        "scope_fence": 1,
        "approval_id": approval_id,
        "approval_request_digest": digest_for(&format!("approval-request:{nonce}")),
        "approval_metadata_digest": proposal_digest,
        "approval_record_digest": approval_record_digest,
        "approval_ledger_event_digest": digest_for(&format!("approval-ledger:{nonce}")),
        "auth_actor": "owner-1",
        "auth_method": "totp",
        "auth_proof_id": format!("proof-{nonce}"),
        "issuance_binding_digest": issuance_binding_digest,
        "provider_id": current.provider.provider_id,
        "provider_manifest_digest": current.provider.provider_manifest_digest,
        "provider_generation": current.provider.provider_generation,
        "host_policy_digest": current.host_policy.digest,
        "host_policy_generation": current.host_policy.generation,
        "resource_bindings": resource_bindings,
        "issuer_enabled": false,
        "lease_created": false,
        "runtime_authority_activated": false
    });
    let receipt_sha256 = contract_sha256(&body).unwrap();
    let mut receipt = body;
    receipt
        .as_object_mut()
        .unwrap()
        .insert("receipt_sha256".to_owned(), Value::String(receipt_sha256));
    receipt
}

fn digest_for(label: &str) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(label.as_bytes()))
}

fn invocation(handle: AuthorityHandle, current: &CurrentAuthorityObservation) -> InvocationRequest {
    InvocationRequest {
        handle,
        capability_id: CAPABILITY_ID.to_owned(),
        effect: "execute".to_owned(),
        holder_id: HOLDER_ID.to_owned(),
        holder_generation: 3,
        provider: current.provider.clone(),
        host_policy: current.host_policy.clone(),
        resources: current.resources.clone(),
        resource_accesses: vec![
            ResourceAccess {
                resource_id: RESOURCE_ID.to_owned(),
                path: "src/main.rs".to_owned(),
                mode: "read".to_owned(),
            },
            ResourceAccess {
                resource_id: RESOURCE_ID.to_owned(),
                path: "src/generated/output.json".to_owned(),
                mode: "write".to_owned(),
            },
        ],
        network_endpoints: vec![NetworkEndpoint {
            protocol: "https".to_owned(),
            host: "api.example.com".to_owned(),
            port: 443,
        }],
        environment_names: vec!["LANG".to_owned()],
        persistent_process: false,
    }
}

#[test]
fn issuer_is_durable_single_use_and_restart_safe() {
    let harness = Harness::new("issuer");
    assert!(!RUNTIME_AUTHORITY_ACTIVATED);
    let receipt = preflight_receipt(&harness.scope, &harness.current, "one");
    let lease = harness
        .store
        .issue_capability_lease(&receipt, &harness.scope, &grant(), &harness.current)
        .unwrap();
    let lease_id = lease["lease_id"].as_str().unwrap().to_owned();
    assert_eq!(lease["state"], "active");
    assert_eq!(lease["revision"], 1);
    assert_eq!(lease["fence"], 1);

    let replay = harness
        .store
        .issue_capability_lease(&receipt, &harness.scope, &grant(), &harness.current);
    assert!(replay.is_err(), "one preflight receipt must never mint two leases");

    let reopened = Store::open(&harness.database).unwrap();
    assert_eq!(reopened.get_capability_lease(&lease_id).unwrap(), lease);
    let handle = reopened.authority_handle(&lease_id).unwrap();
    assert_eq!(handle.lease_revision, 1);
    assert_eq!(handle.lease_fence, 1);
}

#[test]
fn runtime_revalidates_every_current_authority_dimension() {
    let harness = Harness::new("runtime");
    let lease = harness.issue("runtime");
    let lease_id = lease["lease_id"].as_str().unwrap();
    let handle = harness.store.authority_handle(lease_id).unwrap();
    let valid = invocation(handle.clone(), &harness.current);
    let decision = harness.store.authorize_invocation(&valid).unwrap();
    assert!(decision.authorized);
    assert_eq!(decision.code, "AUTHORIZED");
    assert!(!decision.runtime_authority_activated);

    let mut changed = valid.clone();
    changed.effect = "mutate".to_owned();
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "EFFECT_NOT_GRANTED"
    );

    let mut changed = valid.clone();
    changed.provider.provider_generation += 1;
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "PROVIDER_SUBSTITUTION"
    );

    let mut changed = valid.clone();
    changed.host_policy.generation += 1;
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "HOST_POLICY_STALE"
    );

    let mut changed = valid.clone();
    changed.resources[0].generation += 1;
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "RESOURCE_GENERATION_STALE"
    );

    let mut changed = valid.clone();
    changed.resource_accesses[1].path = "src/not-granted.txt".to_owned();
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "RESOURCE_ACCESS_DENIED"
    );

    let mut changed = valid.clone();
    changed.network_endpoints[0].host = "support.example.com".to_owned();
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "NETWORK_ACCESS_DENIED"
    );

    let mut changed = valid;
    changed.environment_names.push("PATH".to_owned());
    assert_eq!(
        harness.store.authorize_invocation(&changed).unwrap().code,
        "ENVIRONMENT_ACCESS_DENIED"
    );
}

#[test]
fn lease_revocation_fences_old_handles_across_restart() {
    let harness = Harness::new("lease-revoke");
    let lease = harness.issue("revoke");
    let lease_id = lease["lease_id"].as_str().unwrap().to_owned();
    let handle = harness.store.authority_handle(&lease_id).unwrap();
    assert!(harness
        .store
        .authorize_invocation(&invocation(handle.clone(), &harness.current))
        .unwrap()
        .authorized);

    let revoked = harness.store.revoke_lease(&lease_id, "owner revoked proof lease").unwrap();
    assert_eq!(revoked.new_revision, 2);
    assert_eq!(revoked.new_fence, 2);
    let denied = harness
        .store
        .authorize_invocation(&invocation(handle, &harness.current))
        .unwrap();
    assert!(!denied.authorized);
    assert_eq!(denied.code, "STALE_AUTHORITY_HANDLE");

    let reopened = Store::open(&harness.database).unwrap();
    let recovered = reopened.get_capability_lease(&lease_id).unwrap();
    assert_eq!(recovered["state"], "revoked");
    assert_eq!(recovered["revision"], 2);
    assert_eq!(recovered["fence"], 2);
}

#[test]
fn scope_revocation_cascades_all_leases_and_is_idempotent() {
    let harness = Harness::new("scope-revoke");
    let first = harness.issue("scope-a");
    let second = harness.issue("scope-b");
    let first_id = first["lease_id"].as_str().unwrap().to_owned();
    let second_id = second["lease_id"].as_str().unwrap().to_owned();

    let result = harness
        .store
        .revoke_scope(SCOPE_ID, "owner revoked proof scope")
        .unwrap();
    assert_eq!(result.revoked_leases, 2);
    assert_eq!(result.new_revision, 2);
    assert_eq!(result.new_fence, 2);

    let repeated = harness
        .store
        .revoke_scope(SCOPE_ID, "repeat revocation must be idempotent")
        .unwrap();
    assert_eq!(repeated.revoked_leases, 0);
    assert_eq!(repeated.new_revision, 2);
    assert_eq!(repeated.new_fence, 2);

    let reopened = Store::open(&harness.database).unwrap();
    assert_eq!(reopened.get_execution_scope(SCOPE_ID).unwrap()["state"], "revoked");
    assert_eq!(reopened.get_capability_lease(&first_id).unwrap()["state"], "revoked");
    assert_eq!(reopened.get_capability_lease(&second_id).unwrap()["state"], "revoked");
}

#[test]
fn authority_contract_tamper_is_rejected_on_restart() {
    let harness = Harness::new("tamper");
    let lease = harness.issue("tamper");
    let lease_id = lease["lease_id"].as_str().unwrap().to_owned();
    let database = harness.database.clone();
    drop(harness.store.clone());

    let connection = Connection::open(&database).unwrap();
    connection
        .execute(
            "UPDATE capability_leases SET contract_json = ?2 WHERE lease_id = ?1",
            params![lease_id, "{}"],
        )
        .unwrap();
    drop(connection);

    let reopened = Store::open(&database);
    assert!(matches!(reopened, Err(StoreError::Corrupt(_))));
}
