use chrono::{DateTime, Utc};
use origins_contracts::contract_sha256;
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fmt::{Display, Formatter};
use uuid::Uuid;

const SCHEMA_VERSION: &str = "1.0.0";
const EFFECTS: &[&str] = &["draft", "execute", "mutate", "observe", "publish", "verify"];
const NETWORK_MODES: &[&str] = &["allowlist", "delegated_remote", "deny"];
const LEASE_STATES: &[&str] = &["active", "expired", "revoked", "suspended"];
const HOLDER_KINDS: &[&str] = &["candidate", "operation", "provider", "session"];
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorityError {
    pub code: &'static str,
    pub message: String,
}

impl AuthorityError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl Display for AuthorityError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for AuthorityError {}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Grant {
    resource_id: String,
    prefix: String,
}

pub fn authority_sha256(value: &Value) -> Result<String, AuthorityError> {
    validate_authority_contract(value)?;
    contract_sha256(value)
        .map_err(|error| AuthorityError::new("CANONICALIZATION_ERROR", error.to_string()))
}

pub fn validate_authority_contract(value: &Value) -> Result<(), AuthorityError> {
    let object = value.as_object().ok_or_else(|| {
        AuthorityError::new("INVALID_ROOT", "authority contract root must be an object")
    })?;
    validate_numbers(value, "$")?;
    if string(object, "schema_version")? != SCHEMA_VERSION {
        return Err(AuthorityError::new(
            "UNSUPPORTED_SCHEMA_VERSION",
            "schema_version must be 1.0.0",
        ));
    }
    match string(object, "contract_type")? {
        "execution_scope" => validate_execution_scope(object),
        "capability_lease" => validate_capability_lease(object),
        other => Err(AuthorityError::new(
            "UNKNOWN_CONTRACT_TYPE",
            format!("unsupported authority contract_type: {other}"),
        )),
    }
}

pub fn validate_child_scope(child: &Value, parent: &Value) -> Result<(), AuthorityError> {
    validate_authority_contract(parent)?;
    validate_authority_contract(child)?;
    let parent = parent.as_object().expect("validated object");
    let child = child.as_object().expect("validated object");
    if string(parent, "contract_type")? != "execution_scope"
        || string(child, "contract_type")? != "execution_scope"
    {
        return Err(AuthorityError::new(
            "INVALID_SCOPE_RELATION",
            "child and parent must both be execution_scope",
        ));
    }
    if string(child, "workspace_id")? != string(parent, "workspace_id")? {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "child scope cannot change workspace",
        ));
    }
    if string(child, "parent_scope_id")? != string(parent, "scope_id")? {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "child parent_scope_id must reference parent scope",
        ));
    }
    if !boolean(parent, "delegation_allowed")? {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "parent scope forbids delegation",
        ));
    }
    require_subset(
        &string_list(child, "effects")?,
        &string_list(parent, "effects")?,
        "effects",
    )?;
    require_grants_within(
        &resource_grants(child, "resource_reads")?,
        &resource_grants(parent, "resource_reads")?,
        "resource_reads",
    )?;
    require_grants_within(
        &resource_grants(child, "resource_writes")?,
        &resource_grants(parent, "resource_writes")?,
        "resource_writes",
    )?;
    require_parent_denies(
        &resource_grants(child, "resource_denies")?,
        &resource_grants(parent, "resource_denies")?,
    )?;
    require_subset(
        &string_list(child, "environment_names")?,
        &string_list(parent, "environment_names")?,
        "environment_names",
    )?;
    require_network_narrowing(child, parent)?;
    if boolean(child, "process_execution_allowed")?
        && !boolean(parent, "process_execution_allowed")?
    {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "child cannot enable process execution",
        ));
    }
    if boolean(child, "persistent_process_allowed")?
        && !boolean(parent, "persistent_process_allowed")?
    {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "child cannot enable persistent processes",
        ));
    }
    if boolean(child, "delegated_remote_authority")?
        && !boolean(parent, "delegated_remote_authority")?
    {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "child cannot enable delegated remote authority",
        ));
    }
    require_expiry_not_extended(string(child, "expires_at")?, string(parent, "expires_at")?)
}

pub fn validate_lease_within_scope(lease: &Value, scope: &Value) -> Result<(), AuthorityError> {
    validate_authority_contract(scope)?;
    validate_authority_contract(lease)?;
    let scope = scope.as_object().expect("validated object");
    let lease = lease.as_object().expect("validated object");
    if string(scope, "contract_type")? != "execution_scope"
        || string(lease, "contract_type")? != "capability_lease"
    {
        return Err(AuthorityError::new(
            "INVALID_LEASE_RELATION",
            "lease must be checked against execution_scope",
        ));
    }
    if string(lease, "scope_id")? != string(scope, "scope_id")?
        || string(lease, "workspace_id")? != string(scope, "workspace_id")?
    {
        return Err(AuthorityError::new(
            "LEASE_ESCALATION",
            "lease scope/workspace identity does not match",
        ));
    }
    require_subset(
        &string_list(lease, "effects")?,
        &string_list(scope, "effects")?,
        "effects",
    )?;
    require_grants_within(
        &resource_grants(lease, "resource_reads")?,
        &resource_grants(scope, "resource_reads")?,
        "resource_reads",
    )?;
    require_grants_within(
        &resource_grants(lease, "resource_writes")?,
        &resource_grants(scope, "resource_writes")?,
        "resource_writes",
    )?;
    require_parent_denies(
        &resource_grants(lease, "resource_denies")?,
        &resource_grants(scope, "resource_denies")?,
    )?;
    require_subset(
        &string_list(lease, "environment_names")?,
        &string_list(scope, "environment_names")?,
        "environment_names",
    )?;
    require_network_narrowing(lease, scope)?;
    if boolean(lease, "persistent_process_allowed")?
        && !boolean(scope, "persistent_process_allowed")?
    {
        return Err(AuthorityError::new(
            "LEASE_ESCALATION",
            "lease cannot enable persistent processes",
        ));
    }
    if boolean(lease, "delegated_remote_authority")?
        && !boolean(scope, "delegated_remote_authority")?
    {
        return Err(AuthorityError::new(
            "LEASE_ESCALATION",
            "lease cannot enable delegated remote authority",
        ));
    }
    if string_list(lease, "effects")?
        .iter()
        .any(|effect| effect == "execute")
        && !boolean(scope, "process_execution_allowed")?
    {
        return Err(AuthorityError::new(
            "LEASE_ESCALATION",
            "scope forbids process execution",
        ));
    }
    require_expiry_not_extended(string(lease, "expires_at")?, string(scope, "expires_at")?)
}

fn validate_execution_scope(object: &Map<String, Value>) -> Result<(), AuthorityError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "scope_id",
            "workspace_id",
            "operation_id",
            "candidate_id",
            "parent_scope_id",
            "effects",
            "resource_reads",
            "resource_writes",
            "resource_denies",
            "network_mode",
            "network_hosts",
            "environment_names",
            "process_execution_allowed",
            "persistent_process_allowed",
            "delegation_allowed",
            "delegated_remote_authority",
            "issued_at",
            "updated_at",
            "expires_at",
            "revision",
        ],
    )?;
    canonical_uuid(object, "scope_id")?;
    canonical_uuid(object, "workspace_id")?;
    nonempty_string(object, "operation_id")?;
    string(object, "candidate_id")?;
    optional_uuid(object, "parent_scope_id")?;
    sorted_unique_enum_list(object, "effects", EFFECTS, false)?;
    let reads = resource_grants(object, "resource_reads")?;
    let writes = resource_grants(object, "resource_writes")?;
    let denies = resource_grants(object, "resource_denies")?;
    require_grants_within(&writes, &reads, "resource_writes")?;
    reject_fully_denied_grants(&reads, &denies, "resource_reads")?;
    reject_fully_denied_grants(&writes, &denies, "resource_writes")?;
    validate_network(object)?;
    environment_names(object, "environment_names")?;
    let process_allowed = boolean(object, "process_execution_allowed")?;
    let persistent = boolean(object, "persistent_process_allowed")?;
    boolean(object, "delegation_allowed")?;
    boolean(object, "delegated_remote_authority")?;
    if persistent && !process_allowed {
        return Err(AuthorityError::new(
            "INVALID_SCOPE",
            "persistent processes require process execution",
        ));
    }
    validate_network_remote_flag(object)?;
    let issued = timestamp(object, "issued_at")?;
    let updated = timestamp(object, "updated_at")?;
    if updated < issued {
        return Err(AuthorityError::new(
            "INVALID_TIMESTAMP_ORDER",
            "updated_at cannot precede issued_at",
        ));
    }
    if let Some(expires) = optional_timestamp(object, "expires_at")? {
        if expires <= issued {
            return Err(AuthorityError::new(
                "INVALID_TIMESTAMP_ORDER",
                "expires_at must be later than issued_at",
            ));
        }
    }
    if nonnegative_integer(object, "revision", "INVALID_REVISION")? < 1 {
        return Err(AuthorityError::new(
            "INVALID_REVISION",
            "revision must be at least 1",
        ));
    }
    Ok(())
}

fn validate_capability_lease(object: &Map<String, Value>) -> Result<(), AuthorityError> {
    exact_fields(
        object,
        &[
            "contract_type",
            "schema_version",
            "lease_id",
            "scope_id",
            "workspace_id",
            "parent_lease_id",
            "capability_id",
            "holder_kind",
            "holder_id",
            "effects",
            "resource_reads",
            "resource_writes",
            "resource_denies",
            "network_mode",
            "network_hosts",
            "environment_names",
            "persistent_process_allowed",
            "delegated_remote_authority",
            "approval_authority",
            "approval_id",
            "approval_digest",
            "proposal_digest",
            "state",
            "fence",
            "issued_at",
            "updated_at",
            "expires_at",
            "revision",
        ],
    )?;
    canonical_uuid(object, "lease_id")?;
    canonical_uuid(object, "scope_id")?;
    canonical_uuid(object, "workspace_id")?;
    optional_uuid(object, "parent_lease_id")?;
    nonempty_string(object, "capability_id")?;
    enum_string(object, "holder_kind", HOLDER_KINDS)?;
    nonempty_string(object, "holder_id")?;
    let effects = sorted_unique_enum_list(object, "effects", EFFECTS, false)?;
    let reads = resource_grants(object, "resource_reads")?;
    let writes = resource_grants(object, "resource_writes")?;
    let denies = resource_grants(object, "resource_denies")?;
    require_grants_within(&writes, &reads, "resource_writes")?;
    reject_fully_denied_grants(&reads, &denies, "resource_reads")?;
    reject_fully_denied_grants(&writes, &denies, "resource_writes")?;
    validate_network(object)?;
    environment_names(object, "environment_names")?;
    let persistent = boolean(object, "persistent_process_allowed")?;
    boolean(object, "delegated_remote_authority")?;
    if persistent && !effects.iter().any(|effect| effect == "execute") {
        return Err(AuthorityError::new(
            "INVALID_LEASE",
            "persistent process lease requires execute effect",
        ));
    }
    validate_network_remote_flag(object)?;
    nonempty_string(object, "approval_authority")?;
    nonempty_string(object, "approval_id")?;
    digest_field(object, "approval_digest")?;
    digest_field(object, "proposal_digest")?;
    let state = enum_string(object, "state", LEASE_STATES)?;
    if nonnegative_integer(object, "fence", "INVALID_FENCE")? < 1 {
        return Err(AuthorityError::new(
            "INVALID_FENCE",
            "fence must be at least 1",
        ));
    }
    let issued = timestamp(object, "issued_at")?;
    let updated = timestamp(object, "updated_at")?;
    if updated < issued {
        return Err(AuthorityError::new(
            "INVALID_TIMESTAMP_ORDER",
            "updated_at cannot precede issued_at",
        ));
    }
    let expires = optional_timestamp(object, "expires_at")?;
    if let Some(expires_at) = expires.as_ref() {
        if expires_at <= &issued {
            return Err(AuthorityError::new(
                "INVALID_TIMESTAMP_ORDER",
                "expires_at must be later than issued_at",
            ));
        }
    }
    if state == "expired" && expires.is_none() {
        return Err(AuthorityError::new(
            "INVALID_LEASE",
            "expired lease requires expires_at",
        ));
    }
    if nonnegative_integer(object, "revision", "INVALID_REVISION")? < 1 {
        return Err(AuthorityError::new(
            "INVALID_REVISION",
            "revision must be at least 1",
        ));
    }
    Ok(())
}

fn resource_grants(object: &Map<String, Value>, field: &str) -> Result<Vec<Grant>, AuthorityError> {
    let items = object.get(field).and_then(Value::as_array).ok_or_else(|| {
        AuthorityError::new("INVALID_RESOURCE_GRANTS", format!("{field} must be a list"))
    })?;
    let mut result = Vec::with_capacity(items.len());
    let mut keys = Vec::with_capacity(items.len());
    for item in items {
        let item = item.as_object().ok_or_else(|| {
            AuthorityError::new(
                "INVALID_RESOURCE_GRANT",
                format!("{field} entries must be objects"),
            )
        })?;
        exact_fields(item, &["resource_id", "prefix"])?;
        let resource_id = string(item, "resource_id")?;
        let prefix = string(item, "prefix")?;
        if !valid_resource_id(resource_id) {
            return Err(AuthorityError::new(
                "INVALID_RESOURCE_ID",
                format!("invalid resource_id in {field}"),
            ));
        }
        validate_prefix(prefix, field)?;
        keys.push(format!("{resource_id}\0{prefix}"));
        result.push(Grant {
            resource_id: resource_id.to_owned(),
            prefix: prefix.to_owned(),
        });
    }
    let mut sorted = keys.clone();
    sorted.sort();
    sorted.dedup();
    if keys != sorted {
        return Err(AuthorityError::new(
            "UNSORTED_OR_DUPLICATE_LIST",
            format!("{field} must be sorted by resource_id/prefix and unique"),
        ));
    }
    Ok(result)
}

fn validate_prefix(prefix: &str, field: &str) -> Result<(), AuthorityError> {
    if prefix.contains('\0')
        || prefix.contains('\\')
        || prefix.starts_with('/')
        || prefix.contains("//")
        || prefix.ends_with('/')
    {
        return Err(AuthorityError::new(
            "INVALID_RESOURCE_PREFIX",
            format!("unsafe resource prefix in {field}"),
        ));
    }
    if !prefix.is_empty()
        && prefix
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(AuthorityError::new(
            "INVALID_RESOURCE_PREFIX",
            format!("resource prefix in {field} must be normalized"),
        ));
    }
    Ok(())
}

fn grant_within(child: &Grant, parent: &Grant) -> bool {
    child.resource_id == parent.resource_id
        && (parent.prefix.is_empty()
            || child.prefix == parent.prefix
            || child.prefix.starts_with(&(parent.prefix.clone() + "/")))
}

fn require_grants_within(
    children: &[Grant],
    parents: &[Grant],
    field: &str,
) -> Result<(), AuthorityError> {
    for child in children {
        if !parents.iter().any(|parent| grant_within(child, parent)) {
            return Err(AuthorityError::new(
                "SCOPE_ESCALATION",
                format!("{field} contains authority outside its parent"),
            ));
        }
    }
    Ok(())
}

fn require_parent_denies(children: &[Grant], parents: &[Grant]) -> Result<(), AuthorityError> {
    for parent in parents {
        if !children.iter().any(|child| child == parent) {
            return Err(AuthorityError::new(
                "SCOPE_ESCALATION",
                "child/lease cannot drop a parent resource deny",
            ));
        }
    }
    Ok(())
}

fn reject_fully_denied_grants(
    grants: &[Grant],
    denies: &[Grant],
    field: &str,
) -> Result<(), AuthorityError> {
    for grant in grants {
        if denies.iter().any(|deny| grant_within(grant, deny)) {
            return Err(AuthorityError::new(
                "CONTRADICTORY_SCOPE",
                format!("{field} contains a grant fully covered by a deny"),
            ));
        }
    }
    Ok(())
}

fn validate_network(object: &Map<String, Value>) -> Result<(), AuthorityError> {
    let mode = enum_string(object, "network_mode", NETWORK_MODES)?;
    let hosts = sorted_unique_string_list(object, "network_hosts")?;
    for host in &hosts {
        if !valid_host(host) {
            return Err(AuthorityError::new(
                "INVALID_NETWORK_HOST",
                format!("invalid exact network host: {host}"),
            ));
        }
    }
    if mode == "deny" && !hosts.is_empty() {
        return Err(AuthorityError::new(
            "INVALID_NETWORK_SCOPE",
            "deny mode cannot include network hosts",
        ));
    }
    if mode != "deny" && hosts.is_empty() {
        return Err(AuthorityError::new(
            "INVALID_NETWORK_SCOPE",
            format!("{mode} mode requires exact network hosts"),
        ));
    }
    Ok(())
}

fn validate_network_remote_flag(object: &Map<String, Value>) -> Result<(), AuthorityError> {
    let mode = string(object, "network_mode")?;
    let delegated = boolean(object, "delegated_remote_authority")?;
    if mode == "delegated_remote" && !delegated {
        return Err(AuthorityError::new(
            "INVALID_NETWORK_SCOPE",
            "delegated_remote mode must mark delegated remote authority",
        ));
    }
    if mode != "delegated_remote" && delegated {
        return Err(AuthorityError::new(
            "INVALID_NETWORK_SCOPE",
            "delegated remote authority requires delegated_remote mode",
        ));
    }
    Ok(())
}

fn require_network_narrowing(
    child: &Map<String, Value>,
    parent: &Map<String, Value>,
) -> Result<(), AuthorityError> {
    let child_mode = string(child, "network_mode")?;
    let parent_mode = string(parent, "network_mode")?;
    if child_mode == "deny" {
        return Ok(());
    }
    if child_mode != parent_mode {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            "network authority class cannot change while delegating",
        ));
    }
    require_subset(
        &string_list(child, "network_hosts")?,
        &string_list(parent, "network_hosts")?,
        "network_hosts",
    )
}

fn environment_names(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Vec<String>, AuthorityError> {
    let names = sorted_unique_string_list(object, field)?;
    for name in &names {
        if !valid_env_name(name) {
            return Err(AuthorityError::new(
                "INVALID_ENVIRONMENT_NAME",
                format!("{field} may contain variable names only"),
            ));
        }
    }
    Ok(names)
}

fn require_subset(
    children: &[String],
    parents: &[String],
    field: &str,
) -> Result<(), AuthorityError> {
    let parent: BTreeSet<&str> = parents.iter().map(String::as_str).collect();
    if children.iter().any(|item| !parent.contains(item.as_str())) {
        return Err(AuthorityError::new(
            "SCOPE_ESCALATION",
            format!("{field} cannot expand parent authority"),
        ));
    }
    Ok(())
}

fn require_expiry_not_extended(child: &str, parent: &str) -> Result<(), AuthorityError> {
    let child = parse_optional_timestamp(child, "expires_at")?;
    let parent = parse_optional_timestamp(parent, "expires_at")?;
    if let Some(parent) = parent {
        if child.is_none() || child.as_ref().is_some_and(|value| value > &parent) {
            return Err(AuthorityError::new(
                "SCOPE_ESCALATION",
                "child/lease expiry cannot extend beyond parent",
            ));
        }
    }
    Ok(())
}

fn validate_numbers(value: &Value, path: &str) -> Result<(), AuthorityError> {
    match value {
        Value::Number(number) => {
            if let Some(integer) = number.as_i64() {
                let max = MAX_SAFE_INTEGER as i64;
                if integer < -max || integer > max {
                    return Err(AuthorityError::new(
                        "INTEGER_OUT_OF_RANGE",
                        format!("integer outside cross-language safe range at {path}"),
                    ));
                }
                Ok(())
            } else if let Some(integer) = number.as_u64() {
                if integer > MAX_SAFE_INTEGER {
                    return Err(AuthorityError::new(
                        "INTEGER_OUT_OF_RANGE",
                        format!("integer outside cross-language safe range at {path}"),
                    ));
                }
                Ok(())
            } else {
                Err(AuthorityError::new(
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

fn exact_fields(object: &Map<String, Value>, expected: &[&str]) -> Result<(), AuthorityError> {
    let actual: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    let missing: Vec<&str> = expected.difference(&actual).copied().collect();
    let unknown: Vec<&str> = actual.difference(&expected).copied().collect();
    if !missing.is_empty() {
        return Err(AuthorityError::new(
            "MISSING_FIELD",
            format!("missing fields: {}", missing.join(", ")),
        ));
    }
    if !unknown.is_empty() {
        return Err(AuthorityError::new(
            "UNKNOWN_FIELD",
            format!("unknown fields: {}", unknown.join(", ")),
        ));
    }
    Ok(())
}

fn string<'a>(object: &'a Map<String, Value>, field: &str) -> Result<&'a str, AuthorityError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| AuthorityError::new("INVALID_STRING", format!("{field} must be a string")))
}

fn nonempty_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, AuthorityError> {
    let value = string(object, field)?;
    if value.trim().is_empty() {
        return Err(AuthorityError::new(
            "EMPTY_STRING",
            format!("{field} cannot be empty"),
        ));
    }
    Ok(value)
}

fn boolean(object: &Map<String, Value>, field: &str) -> Result<bool, AuthorityError> {
    object
        .get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| AuthorityError::new("INVALID_BOOLEAN", format!("{field} must be boolean")))
}

fn canonical_uuid(object: &Map<String, Value>, field: &str) -> Result<(), AuthorityError> {
    let text = nonempty_string(object, field)?;
    let parsed = Uuid::parse_str(text)
        .map_err(|_| AuthorityError::new("INVALID_UUID", format!("{field} must be a UUID")))?;
    if parsed.hyphenated().to_string() != text.to_ascii_lowercase() {
        return Err(AuthorityError::new(
            "INVALID_UUID",
            format!("{field} must use canonical UUID text"),
        ));
    }
    Ok(())
}

fn optional_uuid(object: &Map<String, Value>, field: &str) -> Result<(), AuthorityError> {
    let text = string(object, field)?;
    if text.is_empty() {
        return Ok(());
    }
    canonical_uuid(object, field)
}

fn enum_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    allowed: &[&str],
) -> Result<&'a str, AuthorityError> {
    let value = nonempty_string(object, field)?;
    if !allowed.contains(&value) {
        return Err(AuthorityError::new(
            "INVALID_ENUM",
            format!("{field} must be one of: {}", allowed.join(", ")),
        ));
    }
    Ok(value)
}

fn string_list(object: &Map<String, Value>, field: &str) -> Result<Vec<String>, AuthorityError> {
    let items = object
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| AuthorityError::new("INVALID_LIST", format!("{field} must be a list")))?;
    items
        .iter()
        .map(|item| {
            item.as_str().map(str::to_owned).ok_or_else(|| {
                AuthorityError::new("INVALID_LIST", format!("{field} must be a list of strings"))
            })
        })
        .collect()
}

fn sorted_unique_string_list(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Vec<String>, AuthorityError> {
    let values = string_list(object, field)?;
    if values.iter().any(|value| value.is_empty()) {
        return Err(AuthorityError::new(
            "INVALID_LIST",
            format!("{field} must be a list of non-empty strings"),
        ));
    }
    let mut sorted = values.clone();
    sorted.sort();
    sorted.dedup();
    if values != sorted {
        return Err(AuthorityError::new(
            "UNSORTED_OR_DUPLICATE_LIST",
            format!("{field} must be sorted and unique"),
        ));
    }
    Ok(values)
}

fn sorted_unique_enum_list(
    object: &Map<String, Value>,
    field: &str,
    allowed: &[&str],
    allow_empty: bool,
) -> Result<Vec<String>, AuthorityError> {
    let values = sorted_unique_string_list(object, field)?;
    if !allow_empty && values.is_empty() {
        return Err(AuthorityError::new(
            "EMPTY_LIST",
            format!("{field} cannot be empty"),
        ));
    }
    let invalid: Vec<&str> = values
        .iter()
        .map(String::as_str)
        .filter(|value| !allowed.contains(value))
        .collect();
    if !invalid.is_empty() {
        return Err(AuthorityError::new(
            "INVALID_ENUM",
            format!(
                "{field} contains unsupported values: {}",
                invalid.join(", ")
            ),
        ));
    }
    Ok(values)
}

fn nonnegative_integer(
    object: &Map<String, Value>,
    field: &str,
    code: &'static str,
) -> Result<u64, AuthorityError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .filter(|value| *value <= MAX_SAFE_INTEGER)
        .ok_or_else(|| {
            AuthorityError::new(code, format!("{field} must be a non-negative safe integer"))
        })
}

fn timestamp(object: &Map<String, Value>, field: &str) -> Result<DateTime<Utc>, AuthorityError> {
    parse_timestamp(nonempty_string(object, field)?, field)
}

fn optional_timestamp(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Option<DateTime<Utc>>, AuthorityError> {
    parse_optional_timestamp(string(object, field)?, field)
}

fn parse_optional_timestamp(
    text: &str,
    field: &str,
) -> Result<Option<DateTime<Utc>>, AuthorityError> {
    if text.is_empty() {
        Ok(None)
    } else {
        parse_timestamp(text, field).map(Some)
    }
}

fn parse_timestamp(text: &str, field: &str) -> Result<DateTime<Utc>, AuthorityError> {
    if !text.ends_with('Z') {
        return Err(AuthorityError::new(
            "INVALID_TIMESTAMP",
            format!("{field} must be UTC RFC3339 ending in Z"),
        ));
    }
    DateTime::parse_from_rfc3339(text)
        .map(|value| value.with_timezone(&Utc))
        .map_err(|_| {
            AuthorityError::new("INVALID_TIMESTAMP", format!("{field} is not valid RFC3339"))
        })
}

fn digest_field(object: &Map<String, Value>, field: &str) -> Result<(), AuthorityError> {
    let text = nonempty_string(object, field)?;
    if text.len() != 64
        || !text
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(AuthorityError::new(
            "INVALID_DIGEST",
            format!("{field} must be lowercase SHA-256"),
        ));
    }
    Ok(())
}

fn valid_resource_id(value: &str) -> bool {
    let Some((kind, id)) = value.split_once(':') else {
        return false;
    };
    !kind.is_empty()
        && kind.len() <= 64
        && kind
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase())
        && kind.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'.' | b'-')
        })
        && !id.is_empty()
        && id.len() <= 160
        && id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b':' | b'-'))
}

fn valid_env_name(value: &str) -> bool {
    let mut bytes = value.bytes();
    let Some(first) = bytes.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == b'_')
        && value.len() <= 128
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn valid_host(value: &str) -> bool {
    if value.is_empty()
        || value.starts_with('.')
        || value.ends_with('.')
        || value.contains("..")
        || value.contains('/')
        || value.contains('@')
        || value.contains('*')
    {
        return false;
    }
    let (host, port) = match value.rsplit_once(':') {
        Some((host, port))
            if !port.is_empty() && port.bytes().all(|byte| byte.is_ascii_digit()) =>
        {
            (host, Some(port))
        }
        _ => (value, None),
    };
    if host.is_empty()
        || !host.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-')
        })
    {
        return false;
    }
    match port {
        None => true,
        Some(port) => port.parse::<u16>().is_ok_and(|value| value > 0),
    }
}
