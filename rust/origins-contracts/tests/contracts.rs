use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;

fn fixtures() -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/fixtures.json");
    let text = fs::read_to_string(path).expect("fixtures must be readable");
    serde_json::from_str(&text).expect("fixtures must be valid JSON")
}

#[test]
fn valid_contract_corpus() {
    let fixtures = fixtures();
    for case in fixtures["valid"]
        .as_array()
        .expect("valid fixtures must be an array")
    {
        let name = case["name"].as_str().expect("fixture name");
        let contract = &case["contract"];
        validate_contract(contract).unwrap_or_else(|error| panic!("{name}: {error}"));
        let canonical = canonical_json(contract).expect("canonical JSON");
        assert!(
            !canonical.contains(": "),
            "{name}: canonical JSON contains whitespace"
        );
        let reparsed: Value = serde_json::from_str(&canonical).expect("canonical JSON reparses");
        assert_eq!(
            contract_sha256(contract).expect("digest"),
            contract_sha256(&reparsed).expect("reparsed digest"),
            "{name}: digest changed after canonical round trip"
        );
    }
}

#[test]
fn invalid_contract_corpus() {
    let fixtures = fixtures();
    for case in fixtures["invalid"]
        .as_array()
        .expect("invalid fixtures must be an array")
    {
        let name = case["name"].as_str().expect("fixture name");
        let expected = case["expected_error"].as_str().expect("expected error");
        let error = validate_contract(&case["contract"]).expect_err(name);
        assert_eq!(error.code, expected, "{name}: wrong error code");
    }
}

#[test]
fn unicode_is_not_ascii_escaped() {
    let value: Value = serde_json::from_str(r#"{"z":"Zambia","a":"Origins — 工厂"}"#).unwrap();
    assert_eq!(
        canonical_json(&value).unwrap(),
        r#"{"a":"Origins — 工厂","z":"Zambia"}"#
    );
}
