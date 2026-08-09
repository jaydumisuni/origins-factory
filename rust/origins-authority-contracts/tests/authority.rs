use origins_authority_contracts::{
    authority_sha256, validate_authority_contract, validate_child_scope, validate_lease_within_scope,
};
use serde_json::{json, Value};

const WORKSPACE_ID: &str = "11111111-1111-4111-8111-111111111111";
const SCOPE_ID: &str = "22222222-2222-4222-8222-222222222222";
const CHILD_SCOPE_ID: &str = "33333333-3333-4333-8333-333333333333";
const LEASE_ID: &str = "44444444-4444-4444-8444-444444444444";
const SCOPE_SHA256: &str = "69acd382b43d3aaee19c57e735ae735bc9c7c770cd4003cae6aec198ab647d9d";
const LEASE_SHA256: &str = "c44ba1680fb24b92b1391260daa59adf02a799cbdb3e54c0f30c5a0fb24e1fe0";
const AUTHORITY_FIXTURES: &str = include_str!("../../../contracts/authority-fixtures.json");

fn grant(prefix: &str) -> Value {
    json!({"resource_id": format!("worktree:{CHILD_SCOPE_ID}"), "prefix": prefix})
}

fn scope() -> Value {
    json!({
        "contract_type": "execution_scope",
        "schema_version": "1.0.0",
        "scope_id": SCOPE_ID,
        "workspace_id": WORKSPACE_ID,
        "operation_id": "agentops:op-42",
        "candidate_id": "candidate-a",
        "parent_scope_id": "",
        "effects": ["execute", "mutate", "observe", "verify"],
        "resource_reads": [grant("")],
        "resource_writes": [grant("src")],
        "resource_denies": [grant(".origins")],
        "network_mode": "allowlist",
        "network_hosts": ["api.example.com", "support.example.com"],
        "environment_names": ["LANG", "PATH"],
        "process_execution_allowed": true,
        "persistent_process_allowed": false,
        "delegation_allowed": true,
        "delegated_remote_authority": false,
        "issued_at": "2026-08-09T12:00:00Z",
        "updated_at": "2026-08-09T12:00:00Z",
        "expires_at": "2026-08-09T14:00:00Z",
        "revision": 1
    })
}

fn child_scope() -> Value {
    let mut value = scope();
    let object = value.as_object_mut().unwrap();
    object.insert("scope_id".into(), json!(CHILD_SCOPE_ID));
    object.insert("candidate_id".into(), json!("candidate-b"));
    object.insert("parent_scope_id".into(), json!(SCOPE_ID));
    object.insert("effects".into(), json!(["execute", "observe"]));
    object.insert("resource_reads".into(), json!([grant("src")]));
    object.insert("resource_writes".into(), json!([]));
    object.insert("resource_denies".into(), json!([grant(".origins")]));
    object.insert("network_hosts".into(), json!(["support.example.com"]));
    object.insert("environment_names".into(), json!(["LANG"]));
    object.insert("delegation_allowed".into(), json!(false));
    object.insert("expires_at".into(), json!("2026-08-09T13:30:00Z"));
    value
}

fn lease() -> Value {
    json!({
        "contract_type": "capability_lease",
        "schema_version": "1.0.0",
        "lease_id": LEASE_ID,
        "scope_id": SCOPE_ID,
        "workspace_id": WORKSPACE_ID,
        "parent_lease_id": "",
        "capability_id": "origins.process.run",
        "holder_kind": "session",
        "holder_id": "candidate-a-build",
        "effects": ["execute", "observe"],
        "resource_reads": [grant("src")],
        "resource_writes": [],
        "resource_denies": [grant(".origins")],
        "network_mode": "deny",
        "network_hosts": [],
        "environment_names": ["LANG"],
        "persistent_process_allowed": false,
        "delegated_remote_authority": false,
        "approval_authority": "jaydumisuni/Hunter-AgentOps",
        "approval_id": "approval-42",
        "approval_digest": "0".repeat(64),
        "proposal_digest": "1".repeat(64),
        "state": "active",
        "fence": 1,
        "issued_at": "2026-08-09T12:05:00Z",
        "updated_at": "2026-08-09T12:05:00Z",
        "expires_at": "2026-08-09T13:00:00Z",
        "revision": 1
    })
}

#[test]
fn scope_and_lease_validate_and_hash() {
    validate_authority_contract(&scope()).unwrap();
    validate_authority_contract(&lease()).unwrap();
    validate_lease_within_scope(&lease(), &scope()).unwrap();
    assert_eq!(authority_sha256(&scope()).unwrap(), SCOPE_SHA256);
    assert_eq!(authority_sha256(&lease()).unwrap(), LEASE_SHA256);
}

#[test]
fn shared_authority_fixture_corpus() {
    let corpus: Value = serde_json::from_str(AUTHORITY_FIXTURES).unwrap();
    let expected = [("workspace_candidate_scope", SCOPE_SHA256), ("bounded_process_lease", LEASE_SHA256)];
    for item in corpus["valid"].as_array().unwrap() {
        let name = item["name"].as_str().unwrap();
        let contract = &item["contract"];
        validate_authority_contract(contract).unwrap();
        let expected_hash = expected
            .iter()
            .find_map(|(fixture, digest)| (*fixture == name).then_some(*digest))
            .unwrap();
        assert_eq!(authority_sha256(contract).unwrap(), expected_hash, "{name}");
    }
    for item in corpus["invalid"].as_array().unwrap() {
        let name = item["name"].as_str().unwrap();
        let expected_error = item["expected_error"].as_str().unwrap();
        let error = validate_authority_contract(&item["contract"]).unwrap_err();
        assert_eq!(error.code, expected_error, "{name}");
    }
}

#[test]
fn child_can_narrow_but_cannot_drop_parent_deny() {
    validate_child_scope(&child_scope(), &scope()).unwrap();
    let mut child = child_scope();
    child.as_object_mut().unwrap().insert("resource_denies".into(), json!([]));
    let error = validate_child_scope(&child, &scope()).unwrap_err();
    assert_eq!(error.code, "SCOPE_ESCALATION");
}

#[test]
fn unsorted_network_hosts_are_rejected() {
    let mut value = scope();
    value.as_object_mut().unwrap().insert(
        "network_hosts".into(),
        json!(["support.example.com", "api.example.com"]),
    );
    let error = validate_authority_contract(&value).unwrap_err();
    assert_eq!(error.code, "UNSORTED_OR_DUPLICATE_LIST");
}

#[test]
fn lease_cannot_switch_network_authority_class() {
    let mut value = lease();
    let object = value.as_object_mut().unwrap();
    object.insert("network_mode".into(), json!("delegated_remote"));
    object.insert("network_hosts".into(), json!(["support.example.com"]));
    object.insert("delegated_remote_authority".into(), json!(true));
    let error = validate_lease_within_scope(&value, &scope()).unwrap_err();
    assert_eq!(error.code, "SCOPE_ESCALATION");
}

#[test]
fn relative_resource_prefixes_fail_closed() {
    for prefix in ["/etc", "../escape", "src/../secret", "src\\secret", "src//secret", "src/"] {
        let mut value = scope();
        let object = value.as_object_mut().unwrap();
        object.insert("resource_reads".into(), json!([grant(prefix)]));
        object.insert("resource_writes".into(), json!([]));
        assert!(validate_authority_contract(&value).is_err(), "{prefix}");
    }
}

#[test]
fn approval_and_proposal_digests_are_required() {
    let mut value = lease();
    value.as_object_mut().unwrap().insert("approval_digest".into(), json!(""));
    assert_eq!(validate_authority_contract(&value).unwrap_err().code, "EMPTY_STRING");

    let mut value = lease();
    value.as_object_mut().unwrap().insert("proposal_digest".into(), json!("abc"));
    assert_eq!(validate_authority_contract(&value).unwrap_err().code, "INVALID_DIGEST");
}
