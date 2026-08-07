use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use serde_json::{json, Value};
use std::env;
use std::fs;
use std::process::ExitCode;

fn main() -> ExitCode {
    let path = match env::args().nth(1) {
        Some(path) => path,
        None => {
            eprintln!("usage: origins-contracts <contract.json>");
            return ExitCode::from(2);
        }
    };

    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(error) => {
            print_json(json!({"ok": false, "error_code": "READ_ERROR", "error": error.to_string()}));
            return ExitCode::from(2);
        }
    };

    let value: Value = match serde_json::from_str(&text) {
        Ok(value) => value,
        Err(error) => {
            print_json(json!({"ok": false, "error_code": "MALFORMED_JSON", "error": error.to_string()}));
            return ExitCode::from(1);
        }
    };

    if let Err(error) = validate_contract(&value) {
        print_json(json!({"ok": false, "error_code": error.code, "error": error.message}));
        return ExitCode::from(1);
    }

    let canonical = match canonical_json(&value) {
        Ok(value) => value,
        Err(error) => {
            print_json(json!({"ok": false, "error_code": error.code, "error": error.message}));
            return ExitCode::from(1);
        }
    };
    let digest = match contract_sha256(&value) {
        Ok(value) => value,
        Err(error) => {
            print_json(json!({"ok": false, "error_code": error.code, "error": error.message}));
            return ExitCode::from(1);
        }
    };

    print_json(json!({"ok": true, "canonical_json": canonical, "sha256": digest}));
    ExitCode::SUCCESS
}

fn print_json(value: Value) {
    println!("{}", serde_json::to_string(&value).expect("result JSON must serialize"));
}
