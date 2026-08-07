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
const SESSION_KINDS: &[&str] = &["process"];
const SESSION_STATES: &[&str] = &[
    "completed",
    "failed",
    "interrupted",
    "running",
    "starting",
    "timed_out",
];

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
        "session_projection" => validate_session_projection(object),
        "repository_projection" => validate_repository_projection(object),
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
    digest_field(object, "digest", true)?;
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

fn validate_session_projection(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "session_id",
            "workspace_id",
            "command_id",
            "capability_id",
            "kind",
            "workspace_root",
            "state",
            "pid",
            "started_at",
            "updated_at",
            "ended_at",
            "exit_code",
            "timed_out",
            "stdout_bytes",
            "stderr_bytes",
            "stdout_sha256",
            "stderr_sha256",
            "output_truncated",
        ],
    )?;
    canonical_uuid(object, "session_id")?;
    canonical_uuid(object, "workspace_id")?;
    canonical_uuid(object, "command_id")?;
    nonempty_string(object, "capability_id")?;
    enum_string(object, "kind", SESSION_KINDS)?;
    nonempty_string(object, "workspace_root")?;
    let state = enum_string(object, "state", SESSION_STATES)?;
    let pid = string(object, "pid")?;
    if !pid.is_empty() && !pid.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ContractError::new(
            "INVALID_PID",
            "pid must be empty or ASCII decimal digits",
        ));
    }
    let started = timestamp(object, "started_at")?;
    let updated = timestamp(object, "updated_at")?;
    if updated < started {
        return Err(ContractError::new(
            "INVALID_TIMESTAMP_ORDER",
            "updated_at cannot precede started_at",
        ));
    }
    let ended = optional_timestamp(object, "ended_at")?;
    if let Some(ended_at) = ended.as_ref() {
        if ended_at < &started {
            return Err(ContractError::new(
                "INVALID_TIMESTAMP_ORDER",
                "ended_at cannot precede started_at",
            ));
        }
    }
    let exit_code = optional_integer(object, "exit_code", "INVALID_EXIT_CODE")?;
    let timed_out = boolean(object, "timed_out")?;
    nonnegative_integer(object, "stdout_bytes", "INVALID_BYTE_COUNT")?;
    nonnegative_integer(object, "stderr_bytes", "INVALID_BYTE_COUNT")?;
    digest_field(object, "stdout_sha256", false)?;
    digest_field(object, "stderr_sha256", false)?;
    boolean(object, "output_truncated")?;

    let active = matches!(state, "starting" | "running");
    if active && ended.is_some() {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "active session cannot have ended_at",
        ));
    }
    if active && exit_code.is_some() {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "active session cannot have exit_code",
        ));
    }
    if !active && ended.is_none() {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "terminal session state requires ended_at",
        ));
    }
    if timed_out != (state == "timed_out") {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "timed_out flag must match timed_out state",
        ));
    }
    if state == "completed" && exit_code != Some(0) {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "completed session requires exit_code 0",
        ));
    }
    if state == "failed" && (exit_code.is_none() || exit_code == Some(0)) {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            "failed session requires a non-zero exit_code",
        ));
    }
    if matches!(state, "timed_out" | "interrupted") && exit_code.is_some() {
        return Err(ContractError::new(
            "INVALID_SESSION_STATE",
            format!("{state} session must not claim exit_code"),
        ));
    }
    Ok(())
}

fn validate_repository_projection(object: &Map<String, Value>) -> Result<(), ContractError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "repository_id",
            "workspace_id",
            "revision",
            "worktree_root",
            "git_dir",
            "common_dir",
            "head_oid",
            "head_ref",
            "branch",
            "detached",
            "unborn",
            "staged_count",
            "unstaged_count",
            "untracked_count",
            "status_sha256",
            "observed_at",
        ],
    )?;
    canonical_uuid(object, "repository_id")?;
    canonical_uuid(object, "workspace_id")?;
    if nonnegative_integer(object, "revision", "INVALID_REVISION")? < 1 {
        return Err(ContractError::new(
            "INVALID_REVISION",
            "repository revision must be at least 1",
        ));
    }
    nonempty_string(object, "worktree_root")?;
    nonempty_string(object, "git_dir")?;
    nonempty_string(object, "common_dir")?;
    let head_oid = string(object, "head_oid")?;
    if !head_oid.is_empty() && !is_git_oid(head_oid) {
        return Err(ContractError::new(
            "INVALID_GIT_OID",
            "head_oid must be empty or lowercase 40-hex Git OID",
        ));
    }
    let head_ref = string(object, "head_ref")?;
    let branch = string(object, "branch")?;
    let detached = boolean(object, "detached")?;
    let unborn = boolean(object, "unborn")?;
    nonnegative_integer(object, "staged_count", "INVALID_STATUS_COUNT")?;
    nonnegative_integer(object, "unstaged_count", "INVALID_STATUS_COUNT")?;
    nonnegative_integer(object, "untracked_count", "INVALID_STATUS_COUNT")?;
    digest_field(object, "status_sha256", false)?;
    timestamp(object, "observed_at")?;

    if unborn {
        if !head_oid.is_empty() || detached || head_ref.is_empty() || branch.is_empty() {
            return Err(ContractError::new(
                "INVALID_REPOSITORY_STATE",
                "unborn repository requires symbolic branch and no OID",
            ));
        }
    } else if detached {
        if head_oid.is_empty() || !head_ref.is_empty() || !branch.is_empty() {
            return Err(ContractError::new(
                "INVALID_REPOSITORY_STATE",
                "detached repository requires OID and no symbolic branch",
            ));
        }
    } else if head_oid.is_empty() || head_ref.is_empty() || branch.is_empty() {
        return Err(ContractError::new(
            "INVALID_REPOSITORY_STATE",
            "attached repository requires OID and symbolic branch",
        ));
    }
    if !head_ref.is_empty()
        && !branch.is_empty()
        && head_ref != format!("refs/heads/{branch}")
    {
        return Err(ContractError::new(
            "INVALID_REPOSITORY_STATE",
            "head_ref and branch disagree",
        ));
    }
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

fn optional_timestamp(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Option<DateTime<Utc>>, ContractError> {
    let text = string(object, field)?;
    if text.is_empty() {
        return Ok(None);
    }
    timestamp(object, field).map(Some)
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

fn optional_integer(
    object: &Map<String, Value>,
    field: &str,
    code: &'static str,
) -> Result<Option<i64>, ContractError> {
    match object.get(field) {
        Some(Value::Null) => Ok(None),
        Some(value) => value
            .as_i64()
            .map(Some)
            .ok_or_else(|| ContractError::new(code, format!("{field} must be null or an integer"))),
        None => Err(ContractError::new(
            "MISSING_FIELD",
            format!("missing field: {field}"),
        )),
    }
}

fn digest_field(
    object: &Map<String, Value>,
    field: &str,
    allow_empty: bool,
) -> Result<(), ContractError> {
    let digest = string(object, field)?;
    if digest.is_empty() && allow_empty {
        return Ok(());
    }
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(ContractError::new(
            "INVALID_DIGEST",
            format!("{field} must be lowercase SHA-256"),
        ));
    }
    Ok(())
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

fn is_git_oid(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
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
