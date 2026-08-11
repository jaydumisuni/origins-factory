use origins_authority_contracts::{
    validate_authority_contract, validate_child_scope, validate_lease_within_scope,
    validate_provider_binding, validate_scope_current,
};
use serde_json::{json, Value};

fn fixtures() -> Value {
    serde_json::from_str(include_str!("../../../contracts/authority-fixtures.json")).unwrap()
}
fn attacks() -> Value {
    serde_json::from_str(include_str!("../../../contracts/authority-adversarial-fixtures.json")).unwrap()
}
fn base(name: &str) -> Value {
    let corpus = fixtures();
    let index = match name { "scope" => 0, "lease" => 1, other => panic!("unknown base {other}") };
    corpus["valid"][index]["contract"].clone()
}
fn apply_set(value: &mut Value, patch: &Value) {
    let object = value.as_object_mut().expect("candidate must be object");
    for (key, item) in patch.as_object().expect("patch must be object") {
        object.insert(key.clone(), item.clone());
    }
}
fn child_scope() -> Value {
    let mut child = base("scope");
    let object = child.as_object_mut().unwrap();
    object.insert("scope_id".into(), json!("66666666-6666-4666-8666-666666666666"));
    object.insert("candidate_id".into(), json!("candidate-a"));
    object.insert("parent_scope_id".into(), json!("22222222-2222-4222-8222-222222222222"));
    object.insert("effects".into(), json!(["execute", "observe"]));
    object.insert("resource_reads".into(), json!([{"resource_id":"worktree:33333333-3333-4333-8333-333333333333","prefix":"src"}]));
    object.insert("resource_writes".into(), json!([]));
    object.insert("network_endpoints".into(), json!([{"protocol":"https","host":"support.example.com","port":443}]));
    object.insert("environment_names".into(), json!(["LANG"]));
    object.insert("delegation_allowed".into(), json!(false));
    object.insert("issued_at".into(), json!("2026-08-09T12:10:00Z"));
    object.insert("updated_at".into(), json!("2026-08-09T12:10:00Z"));
    object.insert("expires_at".into(), json!("2026-08-09T13:30:00Z"));
    child
}

#[test]
fn shared_invalid_contract_attack_corpus() {
    let attacks = attacks();
    for attack in attacks["invalid_contracts"].as_array().unwrap() {
        let mut value = base(attack["base"].as_str().unwrap());
        apply_set(&mut value, &attack["set"]);
        let error = validate_authority_contract(&value).unwrap_err();
        assert_eq!(error.code, attack["expected_error"].as_str().unwrap(), "{}", attack["name"]);
    }
}

#[test]
fn shared_relation_attack_corpus() {
    let attacks = attacks();
    for attack in attacks["relations"].as_array().unwrap() {
        let expected = attack["expected_error"].as_str().unwrap();
        let name = attack["name"].as_str().unwrap();
        let error = match attack["relation"].as_str().unwrap() {
            "child_scope" => {
                let mut parent = base("scope");
                let mut child = child_scope();
                if let Some(patch) = attack.get("parent_set") { apply_set(&mut parent, patch); }
                if let Some(patch) = attack.get("child_set") { apply_set(&mut child, patch); }
                validate_child_scope(&child, &parent).unwrap_err()
            }
            "lease_scope" => {
                let mut scope = base("scope");
                let mut lease = base("lease");
                if let Some(patch) = attack.get("scope_set") { apply_set(&mut scope, patch); }
                if let Some(patch) = attack.get("lease_set") { apply_set(&mut lease, patch); }
                validate_lease_within_scope(&lease, &scope).unwrap_err()
            }
            "scope_current" => {
                let mut presented = base("scope");
                let mut current = base("scope");
                if let Some(patch) = attack.get("presented_set") { apply_set(&mut presented, patch); }
                if let Some(patch) = attack.get("current_set") { apply_set(&mut current, patch); }
                validate_scope_current(&presented, &current).unwrap_err()
            }
            "provider_binding" => validate_provider_binding(
                &base("lease"),
                attack["provider_id"].as_str().unwrap(),
                attack["provider_manifest_digest"].as_str().unwrap(),
                attack["provider_generation"].as_u64().unwrap(),
            ).unwrap_err(),
            other => panic!("unknown relation {other}"),
        };
        assert_eq!(error.code, expected, "{name}");
    }
}
