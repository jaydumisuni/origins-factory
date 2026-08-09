use origins_authority_contracts::{
    validate_authority_contract, validate_child_scope, validate_lease_within_scope,
};
use serde_json::Value;

fn fixtures() -> Value {
    serde_json::from_str(include_str!("../../../contracts/authority-fixtures.json")).unwrap()
}

fn attacks() -> Value {
    serde_json::from_str(include_str!("../../../contracts/authority-adversarial-fixtures.json")).unwrap()
}

fn base(name: &str) -> Value {
    let fixtures = fixtures();
    let index = match name {
        "scope" => 0,
        "lease" => 1,
        other => panic!("unknown base {other}"),
    };
    fixtures["valid"][index]["contract"].clone()
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
    object.insert(
        "scope_id".into(),
        Value::String("33333333-3333-4333-8333-333333333333".into()),
    );
    object.insert("candidate_id".into(), Value::String("candidate-b".into()));
    object.insert(
        "parent_scope_id".into(),
        Value::String("22222222-2222-4222-8222-222222222222".into()),
    );
    object.insert(
        "effects".into(),
        serde_json::json!(["execute", "observe"]),
    );
    object.insert(
        "resource_reads".into(),
        serde_json::json!([{
            "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
            "prefix": "src"
        }]),
    );
    object.insert("resource_writes".into(), serde_json::json!([]));
    object.insert(
        "resource_denies".into(),
        serde_json::json!([{
            "resource_id": "worktree:33333333-3333-4333-8333-333333333333",
            "prefix": ".origins"
        }]),
    );
    object.insert(
        "network_hosts".into(),
        serde_json::json!(["support.example.com"]),
    );
    object.insert("environment_names".into(), serde_json::json!(["LANG"]));
    object.insert("delegation_allowed".into(), Value::Bool(false));
    object.insert(
        "expires_at".into(),
        Value::String("2026-08-09T13:30:00Z".into()),
    );
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
        match attack["relation"].as_str().unwrap() {
            "child_scope" => {
                let mut parent = base("scope");
                let mut child = child_scope();
                if let Some(patch) = attack.get("parent_set") {
                    apply_set(&mut parent, patch);
                }
                if let Some(patch) = attack.get("child_set") {
                    apply_set(&mut child, patch);
                }
                let error = validate_child_scope(&child, &parent).unwrap_err();
                assert_eq!(error.code, expected, "{name}");
            }
            "lease_scope" => {
                let mut scope = base("scope");
                let mut lease = base("lease");
                if let Some(patch) = attack.get("scope_set") {
                    apply_set(&mut scope, patch);
                }
                if let Some(patch) = attack.get("lease_set") {
                    apply_set(&mut lease, patch);
                }
                let error = validate_lease_within_scope(&lease, &scope).unwrap_err();
                assert_eq!(error.code, expected, "{name}");
            }
            other => panic!("unknown relation {other}"),
        }
    }
}
