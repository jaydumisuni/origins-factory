use origins_authority_contracts::{
    authority_sha256, validate_authority_contract, validate_child_scope,
    validate_lease_within_scope, validate_provider_binding, validate_scope_current,
};
use serde_json::{json, Value};

fn fixtures() -> Value {
    serde_json::from_str(include_str!("../../../contracts/authority-fixtures.json")).unwrap()
}
fn scope() -> Value { fixtures()["valid"][0]["contract"].clone() }
fn lease() -> Value { fixtures()["valid"][1]["contract"].clone() }
fn apply(value: &mut Value, key: &str, item: Value) { value.as_object_mut().unwrap().insert(key.into(), item); }

fn child_scope() -> Value {
    let mut child = scope();
    apply(&mut child, "scope_id", json!("66666666-6666-4666-8666-666666666666"));
    apply(&mut child, "candidate_id", json!("candidate-a"));
    apply(&mut child, "parent_scope_id", json!("22222222-2222-4222-8222-222222222222"));
    apply(&mut child, "effects", json!(["execute", "observe"]));
    apply(&mut child, "resource_reads", json!([{"resource_id":"worktree:33333333-3333-4333-8333-333333333333","prefix":"src"}]));
    apply(&mut child, "resource_writes", json!([]));
    apply(&mut child, "network_endpoints", json!([{"protocol":"https","host":"support.example.com","port":443}]));
    apply(&mut child, "environment_names", json!(["LANG"]));
    apply(&mut child, "delegation_allowed", json!(false));
    apply(&mut child, "issued_at", json!("2026-08-09T12:10:00Z"));
    apply(&mut child, "updated_at", json!("2026-08-09T12:10:00Z"));
    apply(&mut child, "expires_at", json!("2026-08-09T13:30:00Z"));
    child
}

#[test]
fn shared_v11_corpus_and_hashes() {
    let corpus = fixtures();
    for item in corpus["valid"].as_array().unwrap() {
        let contract = &item["contract"];
        validate_authority_contract(contract).unwrap();
        assert_eq!(authority_sha256(contract).unwrap(), item["sha256"].as_str().unwrap());
    }
    validate_lease_within_scope(&lease(), &scope()).unwrap();
    for item in corpus["invalid"].as_array().unwrap() {
        let error = validate_authority_contract(&item["contract"]).unwrap_err();
        assert_eq!(error.code, item["expected_error"].as_str().unwrap(), "{}", item["name"]);
    }
}

#[test]
fn sec002_candidate_binds_once_and_operation_is_immutable() {
    let root = scope();
    let child = child_scope();
    validate_child_scope(&child, &root).unwrap();

    let mut operation_swap = child.clone();
    apply(&mut operation_swap, "operation_id", json!("agentops:other"));
    assert_eq!(validate_child_scope(&operation_swap, &root).unwrap_err().code, "SCOPE_ESCALATION");

    let mut bound_parent = child_scope();
    apply(&mut bound_parent, "delegation_allowed", json!(true));
    let mut switched = bound_parent.clone();
    apply(&mut switched, "scope_id", json!("77777777-7777-4777-8777-777777777777"));
    apply(&mut switched, "parent_scope_id", json!("66666666-6666-4666-8666-666666666666"));
    apply(&mut switched, "candidate_id", json!("candidate-b"));
    apply(&mut switched, "issued_at", json!("2026-08-09T12:20:00Z"));
    apply(&mut switched, "updated_at", json!("2026-08-09T12:20:00Z"));
    assert_eq!(validate_child_scope(&switched, &bound_parent).unwrap_err().code, "SCOPE_ESCALATION");
}

#[test]
fn sec003_provider_binding_is_exact() {
    validate_provider_binding(&lease(), "origins.process.local", &"2".repeat(64), 1).unwrap();
    assert_eq!(
        validate_provider_binding(&lease(), "origins.process.local", &"2".repeat(64), 2)
            .unwrap_err().code,
        "PROVIDER_SUBSTITUTION"
    );
}

#[test]
fn sec004_scope_generation_is_fenced() {
    let mut current = scope();
    validate_scope_current(&current, &current).unwrap();
    let stale = current.clone();
    apply(&mut current, "fence", json!(2));
    apply(&mut current, "revision", json!(2));
    apply(&mut current, "updated_at", json!("2026-08-09T12:01:00Z"));
    assert_eq!(validate_scope_current(&stale, &current).unwrap_err().code, "STALE_SCOPE");

    apply(&mut current, "state", json!("revoked"));
    assert_eq!(validate_scope_current(&current, &current).unwrap_err().code, "SCOPE_UNUSABLE");
}

#[test]
fn sec005_endpoint_protocol_and_port_are_authority() {
    let mut child = child_scope();
    apply(&mut child, "network_endpoints", json!([{"protocol":"http","host":"support.example.com","port":443}]));
    assert_eq!(validate_child_scope(&child, &scope()).unwrap_err().code, "SCOPE_ESCALATION");

    let mut invalid = scope();
    apply(&mut invalid, "network_endpoints", json!([{"protocol":"https","host":"support.example.com","port":0}]));
    assert_eq!(validate_authority_contract(&invalid).unwrap_err().code, "INVALID_NETWORK_PORT");
}

#[test]
fn issuance_chronology_and_holder_generation_fail_closed() {
    let mut item = lease();
    apply(&mut item, "holder_generation", json!(0));
    assert_eq!(validate_authority_contract(&item).unwrap_err().code, "INVALID_HOLDER_GENERATION");

    let mut item = lease();
    apply(&mut item, "issued_at", json!("2026-08-09T11:59:00Z"));
    apply(&mut item, "updated_at", json!("2026-08-09T12:05:00Z"));
    assert_eq!(validate_lease_within_scope(&item, &scope()).unwrap_err().code, "INVALID_ISSUANCE_CHRONOLOGY");
}
