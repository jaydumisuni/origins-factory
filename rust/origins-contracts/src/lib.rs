use chrono::{DateTime, Utc};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashSet};
use std::fmt::{Display, Formatter};
use uuid::Uuid;

pub const SCHEMA_VERSION: &str = "1.0.0";
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;
const EFFECTS: &[&str] = &["draft", "execute", "mutate", "observe", "publish", "verify"];
const NODE_OS: &[&str] = &["any", "linux", "macos", "windows"];
const MATURITY: &[&str] = &["experimental", "frozen", "planned", "proven"];
const MODEL_DEPENDENCY: &[&str] = &["none", "optional", "required"];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractError {
    pub code: &'static str,
    pub message: String,
}

impl ContractError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl Display for ContractError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for ContractError {}

pub fn canonical_json(value: &Value) -> Result<String, ContractError> {
    validate_numbers(value, "$")?;
    serde_json::to_string(value)
        .map_err(|error| ContractError::new("SERIALIZATION_ERROR", error.to_string()))
}

pub fn canonical_bytes(value: &Value) -> Result<Vec<u8>, ContractError> {
    Ok(canonical_json(value)?.into_bytes())
}

pub fn contract_sha256(value: &Value) -> Result<String, ContractError> {
    let digest = Sha256::digest(canonical_bytes(value)?);
    Ok(hex::encode(digest))
}

pub fn validate_contract(value: &Value) -> Result<(), ContractError> {
    let object = value
        .as_object()
        .ok_or_else(|| ContractError::new("INVALID_ROOT", "contract root must be an object"))?;
    validate_numbers(value, "$")?;

    let contract_type = nonempty_string(object, "contract_type")?;
    if string(object, "schema_version")? != SCHEMA_VERSION {
        return Err(ContractError::new(
            "UNSUPPORTED_SCHEMA_VERSION",
            "schema_version must be 1.0.0",
        ));
    }

    match contract_type {
        "authority_ref" => validate_authority_ref(object),
        "workspace_projection" => validate_workspace_projection(object),
        "capability_descriptor" => validate_capability_descriptor(object),
        "command_envelope" => validate_command_envelope(object),
        "event_envelope" => validate_event_envelope(object),
        other => Err(ContractError::new(
            "UNKNOWN_CONTRACT_TYPE",
            format!("unsupported contract_type: {other}"),
        )),
    }
}

fn validate_authority_ref(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "authority",
            "kind",
            "id",
            "revision",
            "uri",
            "digest",
            "observed_at",
        ],
    )?;
    nonempty_string(object, "authority")?;
    nonempty_string(object, "kind")?;
    nonempty_string(object, "id")?;
    string(object, "revision")?;
    string(object, "uri")?;
    let digest = string(object, "digest")?;
    if !digest.is_empty()
        && (digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))
    {
        return Err(ContractError::new(
            "INVALID_DIGEST",
            "digest must be empty or lowercase SHA-256",
        ));
    }
    timestamp(object, "observed_at")?;
    Ok(())
}

fn validate_workspace_projection(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "workspace_id",
            "name",
            "revision",
            "authority_refs",
            "session_refs",
            "created_at",
            "updated_at",
        ],
    )?;
    canonical_uuid(object, "workspace_id")?;
    nonempty_string(object, "name")?;
    nonnegative_integer(object, "revision", "INVALID_REVISION")?;
    authority_ref_list(object, "authority_refs")?;
    authority_ref_list(object, "session_refs")?;
    let created = timestamp(object, "created_at")?;
    let updated = timestamp(object, "updated_at")?;
    if updated < created {
        return Err(ContractError::new(
            "INVALID_TIMESTAMP_ORDER",
            "updated_at cannot precede created_at",
        ));
    }
    Ok(())
}

fn validate_capability_descriptor(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "capability_id",
            "version",
            "owner",
            "effects",
            "permissions",
            "node_os",
            "maturity",
            "model_dependency",
            "review_required",
            "self_promotable",
        ],
    )?;
    nonempty_string(object, "capability_id")?;
    let version = nonempty_string(object, "version")?;
    if !is_simple_semver(version) {
        return Err(ContractError::new(
            "INVALID_SEMVER",
            "version must be ASCII semantic version X.Y.Z",
        ));
    }
    nonempty_string(object, "owner")?;
    sorted_unique_enum_list(object, "effects", EFFECTS, false)?;
    sorted_unique_string_list(object, "permissions")?;
    sorted_unique_enum_list(object, "node_os", NODE_OS, false)?;
    enum_string(object, "maturity", MATURITY)?;
    enum_string(object, "model_dependency", MODEL_DEPENDENCY)?;
    boolean(object, "review_required")?;
    if boolean(object, "self_promotable")? {
        return Err(ContractError::new(
            "SELF_PROMOTION_FORBIDDEN",
            "capabilities cannot self-promote",
        ));
    }
    Ok(())
}

fn validate_command_envelope(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "command_id",
            "workspace_id",
            "capability_id",
            "effect",
            "payload",
            "created_at",
        ],
    )?;
    canonical_uuid(object, "command_id")?;
    canonical_uuid(object, "workspace_id")?;
    nonempty_string(object, "capability_id")?;
    enum_string(object, "effect", EFFECTS)?;
    if !object.get("payload").is_some_and(Value::is_object) {
        return Err(ContractError::new(
            "INVALID_PAYLOAD",
            "payload must be an object",
        ));
    }
    timestamp(object, "created_at")?;
    Ok(())
}

fn validate_event_envelope(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "event_id",
            "workspace_id",
            "producer",
            "kind",
            "sequence",
            "payload",
            "evidence_refs",
            "created_at",
        ],
    )?;
    canonical_uuid(object, "event_id")?;
    canonical_uuid(object, "workspace_id")?;
    nonempty_string(object, "producer")?;
    nonempty_string(object, "kind")?;
    nonnegative_integer(object, "sequence", "INVALID_SEQUENCE")?;
    if !object.get("payload").is_some_and(Value::is_object) {
        return Err(ContractError::new(
            "INVALID_PAYLOAD",
            "payload must be an object",
        ));
    }
    authority_ref_list(object, "evidence_refs")?;
    timestamp(object, "created_at")?;
    Ok(())
}

fn validate_numbers(value: &Value, path: &str) -> Result<(), ContractError> {
    match value {
        Value::Number(number) => {
            if let Some(integer) = number.as_i64() {
                let max = MAX_SAFE_INTEGER as i64;
                if integer < -max || integer > max {
                    return Err(ContractError::new(
                        "INTEGER_OUT_OF_RANGE",
                        format!("integer outside cross-language safe range at {path}"),
                    ));
                }
                Ok(())
            } else if let Some(integer) = number.as_u64() {
                if integer > MAX_SAFE_INTEGER {
                    return Err(ContractError::new(
                        "INTEGER_OUT_OF_RANGE",
                        format!("integer outside cross-language safe range at {path}"),
                    ));
                }
                Ok(())
            } else {
                Err(ContractError::new(
                    "FLOAT_FORBIDDEN",
                    format!("floating-point value forbidden at {path}"),
                ))
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                validate_numbers(child, &format!("{path}[{index}]"))?;
            }
            Ok(())
        }
        Value::Object(object) => {
            for (key, child) in object {
                validate_numbers(child, &format!("{path}.{key}"))?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn exact_fields(object: &Map<String, Value>, expected: &[&str]) -> Result<(), ContractError> {
    let actual: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    let missing: Vec<&str> = expected.difference(&actual).copied().collect();
    let unknown: Vec<&str> = actual.difference(&expected).copied().collect();
    if !missing.is_empty() {
        return Err(ContractError::new(
            "MISSING_FIELD",
            format!("missing fields: {}", missing.join(", ")),
        ));
    }
    if !unknown.is_empty() {
        return Err(ContractError::new(
            "UNKNOWN_FIELD",
            format!("unknown fields: {}", unknown.join(", ")),
        ));
    }
    Ok(())
}

fn string<'a>(object: &'a Map<String, Value>, field: &str) -> Result<&'a str, ContractError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| ContractError::new("INVALID_STRING", format!("{field} must be a string")))
}

fn nonempty_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, ContractError> {
    let value = string(object, field)?;
    if value.trim().is_empty() {
        return Err(ContractError::new(
            "EMPTY_STRING",
            format!("{field} cannot be empty"),
        ));
    }
    Ok(value)
}

fn boolean(object: &Map<String, Value>, field: &str) -> Result<bool, ContractError> {
    object
        .get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| ContractError::new("INVALID_BOOLEAN", format!("{field} must be boolean")))
}

fn canonical_uuid(object: &Map<String, Value>, field: &str) -> Result<(), ContractError> {
    let text = nonempty_string(object, field)?;
    let parsed = Uuid::parse_str(text)
        .map_err(|_| ContractError::new("INVALID_UUID", format!("{field} must be a UUID")))?;
    if parsed.hyphenated().to_string() != text.to_ascii_lowercase() {
        return Err(ContractError::new(
            "INVALID_UUID",
            format!("{field} must use canonical UUID text"),
        ));
    }
    Ok(())
}

fn timestamp(object: &Map<String, Value>, field: &str) -> Result<DateTime<Utc>, ContractError> {
    let text = nonempty_string(object, field)?;
    if !text.ends_with('Z') {
        return Err(ContractError::new(
            "INVALID_TIMESTAMP",
            format!("{field} must be UTC RFC3339 ending in Z"),
        ));
    }
    DateTime::parse_from_rfc3339(text)
        .map(|value| value.with_timezone(&Utc))
        .map_err(|_| {
            ContractError::new("INVALID_TIMESTAMP", format!("{field} is not valid RFC3339"))
        })
}

fn enum_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    allowed: &[&str],
) -> Result<&'a str, ContractError> {
    let value = nonempty_string(object, field)?;
    if !allowed.contains(&value) {
        return Err(ContractError::new(
            "INVALID_ENUM",
            format!("{field} must be one of: {}", allowed.join(", ")),
        ));
    }
    Ok(value)
}

fn nonnegative_integer(
    object: &Map<String, Value>,
    field: &str,
    code: &'static str,
) -> Result<u64, ContractError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| ContractError::new(code, format!("{field} must be a non-negative integer")))
}

fn sorted_unique_string_list<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<Vec<&'a str>, ContractError> {
    let items = object
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| ContractError::new("INVALID_LIST", format!("{field} must be a list")))?;
    let mut values = Vec::with_capacity(items.len());
    for item in items {
        let text = item
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ContractError::new(
                    "INVALID_LIST",
                    format!("{field} must be a list of non-empty strings"),
                )
            })?;
        values.push(text);
    }
    let mut sorted = values.clone();
    sorted.sort_unstable();
    sorted.dedup();
    if values != sorted {
        return Err(ContractError::new(
            "UNSORTED_OR_DUPLICATE_LIST",
            format!("{field} must be sorted and unique"),
        ));
    }
    Ok(values)
}

fn sorted_unique_enum_list<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    allowed: &[&str],
    allow_empty: bool,
) -> Result<Vec<&'a str>, ContractError> {
    let values = sorted_unique_string_list(object, field)?;
    if !allow_empty && values.is_empty() {
        return Err(ContractError::new(
            "EMPTY_LIST",
            format!("{field} cannot be empty"),
        ));
    }
    let invalid: Vec<&str> = values
        .iter()
        .copied()
        .filter(|value| !allowed.contains(value))
        .collect();
    if !invalid.is_empty() {
        return Err(ContractError::new(
            "INVALID_ENUM",
            format!(
                "{field} contains unsupported values: {}",
                invalid.join(", ")
            ),
        ));
    }
    Ok(values)
}

fn authority_ref_list(object: &Map<String, Value>, field: &str) -> Result<(), ContractError> {
    let items = object
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| ContractError::new("INVALID_LIST", format!("{field} must be a list")))?;
    let mut seen = HashSet::new();
    for item in items {
        validate_contract(item)?;
        let child = item.as_object().ok_or_else(|| {
            ContractError::new(
                "INVALID_REFERENCE",
                format!("{field} contains a non-object"),
            )
        })?;
        if string(child, "contract_type")? != "authority_ref" {
            return Err(ContractError::new(
                "INVALID_REFERENCE",
                format!("{field} may contain authority_ref contracts only"),
            ));
        }
        let identity = (
            string(child, "authority")?.to_owned(),
            string(child, "kind")?.to_owned(),
            string(child, "id")?.to_owned(),
        );
        if !seen.insert(identity) {
            return Err(ContractError::new(
                "DUPLICATE_REFERENCE",
                format!("duplicate authority reference in {field}"),
            ));
        }
    }
    Ok(())
}

fn is_simple_semver(value: &str) -> bool {
    let parts: Vec<&str> = value.split('.').collect();
    parts.len() == 3
        && parts.iter().all(|part| {
            !part.is_empty()
                && part.bytes().all(|byte| byte.is_ascii_digit())
                && (part == &"0" || !part.starts_with('0'))
        })
}
