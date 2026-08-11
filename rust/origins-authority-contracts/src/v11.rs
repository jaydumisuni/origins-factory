use chrono::{DateTime, Utc};
use origins_contracts::contract_sha256;
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fmt::{Display, Formatter};
use uuid::Uuid;

pub const SCHEMA_VERSION: &str = "1.1.0";
const EFFECTS: &[&str] = &["draft", "execute", "mutate", "observe", "publish", "verify"];
const NETWORK_MODES: &[&str] = &["allowlist", "delegated_remote", "deny"];
const NETWORK_PROTOCOLS: &[&str] = &["http", "https", "tcp", "udp", "ws", "wss"];
const REDIRECT_POLICIES: &[&str] = &["deny_outside_endpoints"];
const AUTHORITY_STATES: &[&str] = &["active", "expired", "revoked", "suspended"];
const HOLDER_KINDS: &[&str] = &["candidate", "operation", "provider", "session"];
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorityError {
    pub code: &'static str,
    pub message: String,
}

impl AuthorityError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self { code, message: message.into() }
    }
}
impl Display for AuthorityError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result { write!(f, "{}: {}", self.code, self.message) }
}
impl std::error::Error for AuthorityError {}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Grant { resource_id: String, prefix: String }
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct Endpoint { protocol: String, host: String, port: u64 }

pub fn authority_sha256(value: &Value) -> Result<String, AuthorityError> {
    validate_authority_contract(value)?;
    contract_sha256(value).map_err(|error| AuthorityError::new("CANONICALIZATION_ERROR", error.to_string()))
}

pub fn validate_authority_contract(value: &Value) -> Result<(), AuthorityError> {
    let object = value.as_object().ok_or_else(|| AuthorityError::new("INVALID_ROOT", "authority contract root must be an object"))?;
    validate_numbers(value, "$")?;
    if string(object, "schema_version")? != SCHEMA_VERSION {
        return Err(AuthorityError::new("UNSUPPORTED_SCHEMA_VERSION", "schema_version must be 1.1.0"));
    }
    match string(object, "contract_type")? {
        "execution_scope" => validate_execution_scope(object),
        "capability_lease" => validate_capability_lease(object),
        other => Err(AuthorityError::new("UNKNOWN_CONTRACT_TYPE", format!("unsupported authority contract_type: {other}"))),
    }
}

pub fn validate_child_scope(child: &Value, parent: &Value) -> Result<(), AuthorityError> {
    validate_authority_contract(parent)?;
    validate_authority_contract(child)?;
    let p = parent.as_object().expect("validated");
    let c = child.as_object().expect("validated");
    require_type(p, "execution_scope", "INVALID_SCOPE_RELATION")?;
    require_type(c, "execution_scope", "INVALID_SCOPE_RELATION")?;
    if string(p, "state")? != "active" || string(c, "state")? != "active" {
        return Err(AuthorityError::new("SCOPE_UNUSABLE", "scope delegation requires active parent and child"));
    }
    if string(c, "workspace_id")? != string(p, "workspace_id")? { return escalation("child scope cannot change workspace"); }
    if string(c, "operation_id")? != string(p, "operation_id")? { return escalation("child scope cannot change operation identity"); }
    if string(c, "parent_scope_id")? != string(p, "scope_id")? { return escalation("child parent_scope_id must reference parent scope"); }
    require_candidate_transition(string(c, "candidate_id")?, string(p, "candidate_id")?)?;
    if !boolean(p, "delegation_allowed")? { return escalation("parent scope forbids delegation"); }
    require_subset(&string_list(c, "effects")?, &string_list(p, "effects")?, "effects")?;
    require_grants_within(&resource_grants(c, "resource_reads")?, &resource_grants(p, "resource_reads")?, "resource_reads")?;
    require_grants_within(&resource_grants(c, "resource_writes")?, &resource_grants(p, "resource_writes")?, "resource_writes")?;
    require_parent_denies(&resource_grants(c, "resource_denies")?, &resource_grants(p, "resource_denies")?)?;
    require_subset(&string_list(c, "environment_names")?, &string_list(p, "environment_names")?, "environment_names")?;
    require_network_narrowing(c, p)?;
    if boolean(c, "process_execution_allowed")? && !boolean(p, "process_execution_allowed")? { return escalation("child cannot enable process execution"); }
    if boolean(c, "persistent_process_allowed")? && !boolean(p, "persistent_process_allowed")? { return escalation("child cannot enable persistent processes"); }
    if boolean(c, "delegated_remote_authority")? && !boolean(p, "delegated_remote_authority")? { return escalation("child cannot enable delegated remote authority"); }
    require_issued_after(string(c, "issued_at")?, string(p, "updated_at")?, "child scope")?;
    require_expiry_not_extended(string(c, "expires_at")?, string(p, "expires_at")?)
}

pub fn validate_lease_within_scope(lease: &Value, scope: &Value) -> Result<(), AuthorityError> {
    validate_authority_contract(scope)?;
    validate_authority_contract(lease)?;
    let s = scope.as_object().expect("validated");
    let l = lease.as_object().expect("validated");
    require_type(s, "execution_scope", "INVALID_LEASE_RELATION")?;
    require_type(l, "capability_lease", "INVALID_LEASE_RELATION")?;
    if string(s, "state")? != "active" || string(l, "state")? != "active" {
        return Err(AuthorityError::new("LEASE_UNUSABLE", "lease issuance/use requires active scope and lease"));
    }
    if string(l, "scope_id")? != string(s, "scope_id")? || string(l, "workspace_id")? != string(s, "workspace_id")? {
        return Err(AuthorityError::new("LEASE_ESCALATION", "lease scope/workspace identity does not match"));
    }
    require_subset(&string_list(l, "effects")?, &string_list(s, "effects")?, "effects")?;
    require_grants_within(&resource_grants(l, "resource_reads")?, &resource_grants(s, "resource_reads")?, "resource_reads")?;
    require_grants_within(&resource_grants(l, "resource_writes")?, &resource_grants(s, "resource_writes")?, "resource_writes")?;
    require_parent_denies(&resource_grants(l, "resource_denies")?, &resource_grants(s, "resource_denies")?)?;
    require_subset(&string_list(l, "environment_names")?, &string_list(s, "environment_names")?, "environment_names")?;
    require_network_narrowing(l, s)?;
    if boolean(l, "persistent_process_allowed")? && !boolean(s, "persistent_process_allowed")? { return lease_escalation("lease cannot enable persistent processes"); }
    if boolean(l, "delegated_remote_authority")? && !boolean(s, "delegated_remote_authority")? { return lease_escalation("lease cannot enable delegated remote authority"); }
    if string_list(l, "effects")?.iter().any(|v| v == "execute") && !boolean(s, "process_execution_allowed")? { return lease_escalation("scope forbids process execution"); }
    require_issued_after(string(l, "issued_at")?, string(s, "updated_at")?, "lease")?;
    require_expiry_not_extended(string(l, "expires_at")?, string(s, "expires_at")?)
}

pub fn validate_scope_current(presented: &Value, current: &Value) -> Result<(), AuthorityError> {
    validate_authority_contract(presented)?;
    validate_authority_contract(current)?;
    let p = presented.as_object().expect("validated");
    let c = current.as_object().expect("validated");
    require_type(p, "execution_scope", "INVALID_SCOPE_RELATION")?;
    require_type(c, "execution_scope", "INVALID_SCOPE_RELATION")?;
    for field in ["scope_id", "workspace_id", "operation_id", "candidate_id"] {
        if string(p, field)? != string(c, field)? { return Err(AuthorityError::new("STALE_SCOPE", format!("presented scope changed {field}"))); }
    }
    if string(c, "state")? != "active" { return Err(AuthorityError::new("SCOPE_UNUSABLE", "current scope is not active")); }
    if integer(p, "revision")? != integer(c, "revision")? || integer(p, "fence")? != integer(c, "fence")? {
        return Err(AuthorityError::new("STALE_SCOPE", "presented scope revision/fence is stale"));
    }
    if authority_sha256(presented)? != authority_sha256(current)? {
        return Err(AuthorityError::new("STALE_SCOPE", "presented scope content differs from current generation"));
    }
    Ok(())
}

pub fn validate_provider_binding(lease: &Value, provider_id: &str, manifest_digest: &str, generation: u64) -> Result<(), AuthorityError> {
    validate_authority_contract(lease)?;
    let l = lease.as_object().expect("validated");
    require_type(l, "capability_lease", "INVALID_LEASE_RELATION")?;
    if string(l, "provider_id")? != provider_id || string(l, "provider_manifest_digest")? != manifest_digest || integer(l, "provider_generation")? != generation {
        return Err(AuthorityError::new("PROVIDER_SUBSTITUTION", "current capability provider does not match lease binding"));
    }
    Ok(())
}

fn validate_execution_scope(o: &Map<String, Value>) -> Result<(), AuthorityError> {
    exact_fields(o, &["contract_type","schema_version","scope_id","workspace_id","operation_id","candidate_id","parent_scope_id","effects","resource_reads","resource_writes","resource_denies","network_mode","network_endpoints","network_redirect_policy","environment_names","process_execution_allowed","persistent_process_allowed","delegation_allowed","delegated_remote_authority","state","fence","issued_at","updated_at","expires_at","revision"])?;
    canonical_uuid(o, "scope_id")?; canonical_uuid(o, "workspace_id")?;
    semantic_id(o, "operation_id", false)?; semantic_id(o, "candidate_id", true)?; optional_uuid(o, "parent_scope_id")?;
    sorted_unique_enum_list(o, "effects", EFFECTS, false)?;
    let reads = resource_grants(o, "resource_reads")?; let writes = resource_grants(o, "resource_writes")?; let denies = resource_grants(o, "resource_denies")?;
    require_grants_within(&writes, &reads, "resource_writes")?; reject_fully_denied(&reads, &denies, "resource_reads")?; reject_fully_denied(&writes, &denies, "resource_writes")?;
    validate_network(o)?; environment_names(o, "environment_names")?;
    let process = boolean(o, "process_execution_allowed")?; let persistent = boolean(o, "persistent_process_allowed")?;
    boolean(o, "delegation_allowed")?; boolean(o, "delegated_remote_authority")?;
    if persistent && !process { return Err(AuthorityError::new("INVALID_SCOPE", "persistent processes require process execution")); }
    validate_network_remote_flag(o)?;
    let state = enum_string(o, "state", AUTHORITY_STATES)?;
    if integer(o, "fence")? < 1 { return Err(AuthorityError::new("INVALID_FENCE", "fence must be at least 1")); }
    validate_chronology(o, state, "scope")?;
    if integer(o, "revision")? < 1 { return Err(AuthorityError::new("INVALID_REVISION", "revision must be at least 1")); }
    Ok(())
}

fn validate_capability_lease(o: &Map<String, Value>) -> Result<(), AuthorityError> {
    exact_fields(o, &["contract_type","schema_version","lease_id","scope_id","workspace_id","capability_id","provider_id","provider_manifest_digest","provider_generation","holder_kind","holder_id","holder_generation","effects","resource_reads","resource_writes","resource_denies","network_mode","network_endpoints","network_redirect_policy","environment_names","persistent_process_allowed","delegated_remote_authority","approval_authority","approval_id","approval_digest","proposal_digest","state","fence","issued_at","updated_at","expires_at","revision"])?;
    canonical_uuid(o, "lease_id")?; canonical_uuid(o, "scope_id")?; canonical_uuid(o, "workspace_id")?; nonempty_string(o, "capability_id")?;
    let provider_id = nonempty_string(o, "provider_id")?; if !valid_provider_id(provider_id) { return Err(AuthorityError::new("INVALID_PROVIDER_ID", "provider_id must be canonical lower-case provider identity")); }
    digest_field(o, "provider_manifest_digest")?; if integer(o, "provider_generation")? < 1 { return Err(AuthorityError::new("INVALID_PROVIDER_GENERATION", "provider_generation must be at least 1")); }
    enum_string(o, "holder_kind", HOLDER_KINDS)?; canonical_uuid(o, "holder_id")?; if integer(o, "holder_generation")? < 1 { return Err(AuthorityError::new("INVALID_HOLDER_GENERATION", "holder_generation must be at least 1")); }
    let effects = sorted_unique_enum_list(o, "effects", EFFECTS, false)?;
    let reads = resource_grants(o, "resource_reads")?; let writes = resource_grants(o, "resource_writes")?; let denies = resource_grants(o, "resource_denies")?;
    require_grants_within(&writes, &reads, "resource_writes")?; reject_fully_denied(&reads, &denies, "resource_reads")?; reject_fully_denied(&writes, &denies, "resource_writes")?;
    validate_network(o)?; environment_names(o, "environment_names")?;
    let persistent = boolean(o, "persistent_process_allowed")?; boolean(o, "delegated_remote_authority")?;
    if persistent && !effects.iter().any(|v| v == "execute") { return Err(AuthorityError::new("INVALID_LEASE", "persistent process lease requires execute effect")); }
    validate_network_remote_flag(o)?;
    nonempty_string(o, "approval_authority")?; nonempty_string(o, "approval_id")?; digest_field(o, "approval_digest")?; digest_field(o, "proposal_digest")?;
    let state = enum_string(o, "state", AUTHORITY_STATES)?;
    if integer(o, "fence")? < 1 { return Err(AuthorityError::new("INVALID_FENCE", "fence must be at least 1")); }
    validate_chronology(o, state, "lease")?;
    if integer(o, "revision")? < 1 { return Err(AuthorityError::new("INVALID_REVISION", "revision must be at least 1")); }
    Ok(())
}

fn validate_chronology(o: &Map<String, Value>, state: &str, kind: &str) -> Result<(), AuthorityError> {
    let issued = timestamp(o, "issued_at")?; let updated = timestamp(o, "updated_at")?;
    if updated < issued { return Err(AuthorityError::new("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede issued_at")); }
    let expires = optional_timestamp(o, "expires_at")?;
    if let Some(exp) = expires.as_ref() { if exp <= &issued { return Err(AuthorityError::new("INVALID_TIMESTAMP_ORDER", "expires_at must be later than issued_at")); } }
    if state == "expired" && expires.is_none() { return Err(AuthorityError::new(if kind == "scope" { "INVALID_SCOPE" } else { "INVALID_LEASE" }, format!("expired {kind} requires expires_at"))); }
    Ok(())
}

fn resource_grants(o: &Map<String, Value>, field: &str) -> Result<Vec<Grant>, AuthorityError> {
    let items = o.get(field).and_then(Value::as_array).ok_or_else(|| AuthorityError::new("INVALID_RESOURCE_GRANTS", format!("{field} must be a list")))?;
    let mut out = Vec::new(); let mut keys = Vec::new();
    for item in items {
        let m = item.as_object().ok_or_else(|| AuthorityError::new("INVALID_RESOURCE_GRANT", format!("{field} entries must be objects")))?;
        exact_fields(m, &["resource_id", "prefix"])?;
        let rid = string(m, "resource_id")?; let prefix = string(m, "prefix")?;
        if !valid_resource_id(rid) { return Err(AuthorityError::new("INVALID_RESOURCE_ID", format!("invalid resource_id in {field}"))); }
        validate_prefix(prefix, field)?;
        keys.push(format!("{rid}\0{prefix}")); out.push(Grant { resource_id: rid.to_owned(), prefix: prefix.to_owned() });
    }
    let mut sorted = keys.clone(); sorted.sort(); sorted.dedup();
    if keys != sorted { return Err(AuthorityError::new("UNSORTED_OR_DUPLICATE_LIST", format!("{field} must be sorted by resource_id/prefix and unique"))); }
    Ok(out)
}

fn network_endpoints(o: &Map<String, Value>) -> Result<Vec<Endpoint>, AuthorityError> {
    let items = o.get("network_endpoints").and_then(Value::as_array).ok_or_else(|| AuthorityError::new("INVALID_NETWORK_ENDPOINTS", "network_endpoints must be a list"))?;
    let mut out = Vec::new();
    for item in items {
        let m = item.as_object().ok_or_else(|| AuthorityError::new("INVALID_NETWORK_ENDPOINT", "network endpoint must be an object"))?;
        exact_fields(m, &["protocol", "host", "port"])?;
        let protocol = string(m, "protocol")?; let host = string(m, "host")?; let port = integer(m, "port")?;
        if !NETWORK_PROTOCOLS.contains(&protocol) { return Err(AuthorityError::new("INVALID_NETWORK_PROTOCOL", "unsupported network endpoint protocol")); }
        if !valid_host(host) { return Err(AuthorityError::new("INVALID_NETWORK_HOST", format!("invalid exact network host: {host}"))); }
        if !(1..=65535).contains(&port) { return Err(AuthorityError::new("INVALID_NETWORK_PORT", "network endpoint port must be 1..65535")); }
        out.push(Endpoint { protocol: protocol.to_owned(), host: host.to_owned(), port });
    }
    let mut sorted = out.clone(); sorted.sort(); sorted.dedup();
    if out != sorted { return Err(AuthorityError::new("UNSORTED_OR_DUPLICATE_LIST", "network_endpoints must be sorted by protocol/host/port and unique")); }
    Ok(out)
}

fn validate_network(o: &Map<String, Value>) -> Result<(), AuthorityError> {
    let mode = enum_string(o, "network_mode", NETWORK_MODES)?; let endpoints = network_endpoints(o)?; enum_string(o, "network_redirect_policy", REDIRECT_POLICIES)?;
    if mode == "deny" && !endpoints.is_empty() { return Err(AuthorityError::new("INVALID_NETWORK_SCOPE", "deny mode cannot include network endpoints")); }
    if mode != "deny" && endpoints.is_empty() { return Err(AuthorityError::new("INVALID_NETWORK_SCOPE", format!("{mode} mode requires exact network endpoints"))); }
    Ok(())
}

fn require_network_narrowing(child: &Map<String, Value>, parent: &Map<String, Value>) -> Result<(), AuthorityError> {
    let cm = string(child, "network_mode")?; let pm = string(parent, "network_mode")?;
    if cm == "deny" { return Ok(()); }
    if cm != pm { return escalation("network authority class cannot change while delegating"); }
    if string(child, "network_redirect_policy")? != string(parent, "network_redirect_policy")? { return escalation("network redirect policy cannot widen while delegating"); }
    let parent_set: BTreeSet<Endpoint> = network_endpoints(parent)?.into_iter().collect();
    if network_endpoints(child)?.iter().any(|e| !parent_set.contains(e)) { return escalation("network_endpoints cannot expand parent authority"); }
    Ok(())
}

fn validate_network_remote_flag(o: &Map<String, Value>) -> Result<(), AuthorityError> {
    let mode = string(o, "network_mode")?; let delegated = boolean(o, "delegated_remote_authority")?;
    if mode == "delegated_remote" && !delegated { return Err(AuthorityError::new("INVALID_NETWORK_SCOPE", "delegated_remote mode must mark delegated remote authority")); }
    if mode != "delegated_remote" && delegated { return Err(AuthorityError::new("INVALID_NETWORK_SCOPE", "delegated remote authority requires delegated_remote mode")); }
    Ok(())
}

fn require_candidate_transition(child: &str, parent: &str) -> Result<(), AuthorityError> {
    if !parent.is_empty() && child != parent { return escalation("candidate identity cannot change or clear once bound"); }
    Ok(())
}
fn require_issued_after(child: &str, parent_updated: &str, label: &str) -> Result<(), AuthorityError> {
    if parse_timestamp(child, "issued_at")? < parse_timestamp(parent_updated, "updated_at")? { return Err(AuthorityError::new("INVALID_ISSUANCE_CHRONOLOGY", format!("{label} cannot predate current parent generation"))); }
    Ok(())
}
fn require_expiry_not_extended(child: &str, parent: &str) -> Result<(), AuthorityError> {
    let c = parse_optional_timestamp(child, "expires_at")?; let p = parse_optional_timestamp(parent, "expires_at")?;
    if let Some(pv) = p { if c.as_ref().map_or(true, |cv| cv > &pv) { return escalation("child/lease expiry cannot extend beyond parent"); } }
    Ok(())
}
fn require_grants_within(children: &[Grant], parents: &[Grant], field: &str) -> Result<(), AuthorityError> { for child in children { if !parents.iter().any(|p| grant_within(child,p)) { return escalation(format!("{field} contains authority outside its parent")); } } Ok(()) }
fn grant_within(c: &Grant, p: &Grant) -> bool { c.resource_id == p.resource_id && (p.prefix.is_empty() || c.prefix == p.prefix || c.prefix.starts_with(&(p.prefix.clone()+"/"))) }
fn require_parent_denies(children: &[Grant], parents: &[Grant]) -> Result<(), AuthorityError> { for p in parents { if !children.contains(p) { return escalation("child/lease cannot drop a parent resource deny"); } } Ok(()) }
fn reject_fully_denied(grants: &[Grant], denies: &[Grant], field: &str) -> Result<(), AuthorityError> { for g in grants { if denies.iter().any(|d| grant_within(g,d)) { return Err(AuthorityError::new("CONTRADICTORY_SCOPE", format!("{field} contains a grant fully covered by a deny"))); } } Ok(()) }
fn require_subset(children: &[String], parents: &[String], field: &str) -> Result<(), AuthorityError> { let p: BTreeSet<&str> = parents.iter().map(String::as_str).collect(); if children.iter().any(|v| !p.contains(v.as_str())) { return escalation(format!("{field} cannot expand parent authority")); } Ok(()) }
fn escalation<T>(message: impl Into<String>) -> Result<T, AuthorityError> { Err(AuthorityError::new("SCOPE_ESCALATION", message)) }
fn lease_escalation<T>(message: impl Into<String>) -> Result<T, AuthorityError> { Err(AuthorityError::new("LEASE_ESCALATION", message)) }

fn exact_fields(o: &Map<String, Value>, expected: &[&str]) -> Result<(), AuthorityError> { let a:BTreeSet<&str>=o.keys().map(String::as_str).collect(); let e:BTreeSet<&str>=expected.iter().copied().collect(); let missing:Vec<&str>=e.difference(&a).copied().collect(); let unknown:Vec<&str>=a.difference(&e).copied().collect(); if !missing.is_empty(){return Err(AuthorityError::new("MISSING_FIELD",format!("missing fields: {}",missing.join(", "))));} if !unknown.is_empty(){return Err(AuthorityError::new("UNKNOWN_FIELD",format!("unknown fields: {}",unknown.join(", "))));} Ok(()) }
fn require_type(o:&Map<String,Value>, expected:&str, code:&'static str)->Result<(),AuthorityError>{if string(o,"contract_type")?!=expected{return Err(AuthorityError::new(code,format!("contract must be {expected}")));}Ok(())}
fn string<'a>(o:&'a Map<String,Value>, field:&str)->Result<&'a str,AuthorityError>{o.get(field).and_then(Value::as_str).ok_or_else(||AuthorityError::new("INVALID_STRING",format!("{field} must be a string")))}
fn nonempty_string<'a>(o:&'a Map<String,Value>,field:&str)->Result<&'a str,AuthorityError>{let v=string(o,field)?;if v.trim().is_empty(){return Err(AuthorityError::new("EMPTY_STRING",format!("{field} cannot be empty")));}Ok(v)}
fn boolean(o:&Map<String,Value>,field:&str)->Result<bool,AuthorityError>{o.get(field).and_then(Value::as_bool).ok_or_else(||AuthorityError::new("INVALID_BOOLEAN",format!("{field} must be boolean")))}
fn canonical_uuid(o:&Map<String,Value>,field:&str)->Result<(),AuthorityError>{let t=nonempty_string(o,field)?;let p=Uuid::parse_str(t).map_err(|_|AuthorityError::new("INVALID_UUID",format!("{field} must be a UUID")))?;if p.hyphenated().to_string()!=t.to_ascii_lowercase(){return Err(AuthorityError::new("INVALID_UUID",format!("{field} must use canonical UUID text")));}Ok(())}
fn optional_uuid(o:&Map<String,Value>,field:&str)->Result<(),AuthorityError>{if string(o,field)?.is_empty(){Ok(())}else{canonical_uuid(o,field)}}
fn enum_string<'a>(o:&'a Map<String,Value>,field:&str,allowed:&[&str])->Result<&'a str,AuthorityError>{let v=nonempty_string(o,field)?;if !allowed.contains(&v){return Err(AuthorityError::new("INVALID_ENUM",format!("{field} must be one of: {}",allowed.join(", "))));}Ok(v)}
fn string_list(o:&Map<String,Value>,field:&str)->Result<Vec<String>,AuthorityError>{let a=o.get(field).and_then(Value::as_array).ok_or_else(||AuthorityError::new("INVALID_LIST",format!("{field} must be a list")))?;a.iter().map(|v|v.as_str().map(str::to_owned).ok_or_else(||AuthorityError::new("INVALID_LIST",format!("{field} must be a list of strings")))).collect()}
fn sorted_unique_string_list(o:&Map<String,Value>,field:&str)->Result<Vec<String>,AuthorityError>{let v=string_list(o,field)?;if v.iter().any(|x|x.is_empty()){return Err(AuthorityError::new("INVALID_LIST",format!("{field} must be a list of non-empty strings")));}let mut s=v.clone();s.sort();s.dedup();if v!=s{return Err(AuthorityError::new("UNSORTED_OR_DUPLICATE_LIST",format!("{field} must be sorted and unique")));}Ok(v)}
fn sorted_unique_enum_list(o:&Map<String,Value>,field:&str,allowed:&[&str],allow_empty:bool)->Result<Vec<String>,AuthorityError>{let v=sorted_unique_string_list(o,field)?;if !allow_empty&&v.is_empty(){return Err(AuthorityError::new("EMPTY_LIST",format!("{field} cannot be empty")));}if v.iter().any(|x|!allowed.contains(&x.as_str())){return Err(AuthorityError::new("INVALID_ENUM",format!("{field} contains unsupported values")));}Ok(v)}
fn integer(o:&Map<String,Value>,field:&str)->Result<u64,AuthorityError>{o.get(field).and_then(Value::as_u64).filter(|v|*v<=MAX_SAFE_INTEGER).ok_or_else(||AuthorityError::new("INVALID_INTEGER",format!("{field} must be a non-negative safe integer")))}
fn timestamp(o:&Map<String,Value>,field:&str)->Result<DateTime<Utc>,AuthorityError>{parse_timestamp(nonempty_string(o,field)?,field)}
fn optional_timestamp(o:&Map<String,Value>,field:&str)->Result<Option<DateTime<Utc>>,AuthorityError>{parse_optional_timestamp(string(o,field)?,field)}
fn parse_optional_timestamp(text:&str,field:&str)->Result<Option<DateTime<Utc>>,AuthorityError>{if text.is_empty(){Ok(None)}else{parse_timestamp(text,field).map(Some)}}
fn parse_timestamp(text:&str,field:&str)->Result<DateTime<Utc>,AuthorityError>{if !text.ends_with('Z'){return Err(AuthorityError::new("INVALID_TIMESTAMP",format!("{field} must be UTC RFC3339 ending in Z")));}DateTime::parse_from_rfc3339(text).map(|v|v.with_timezone(&Utc)).map_err(|_|AuthorityError::new("INVALID_TIMESTAMP",format!("{field} is not valid RFC3339")))}
fn digest_field(o:&Map<String,Value>,field:&str)->Result<(),AuthorityError>{let t=nonempty_string(o,field)?;if t.len()!=64||!t.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){return Err(AuthorityError::new("INVALID_DIGEST",format!("{field} must be lowercase SHA-256")));}Ok(())}
fn environment_names(o:&Map<String,Value>,field:&str)->Result<Vec<String>,AuthorityError>{let n=sorted_unique_string_list(o,field)?;if n.iter().any(|v|!valid_env_name(v)){return Err(AuthorityError::new("INVALID_ENVIRONMENT_NAME",format!("{field} may contain variable names only")));}Ok(n)}
fn semantic_id(o:&Map<String,Value>,field:&str,allow_empty:bool)->Result<(),AuthorityError>{let v=string(o,field)?;if allow_empty&&v.is_empty(){return Ok(());}if !valid_semantic_id(v){return Err(AuthorityError::new("INVALID_SEMANTIC_ID",format!("{field} must use canonical semantic identifier characters")));}Ok(())}
fn validate_prefix(prefix:&str,field:&str)->Result<(),AuthorityError>{if prefix.contains('\0')||prefix.contains('\\')||prefix.starts_with('/')||prefix.contains("//")||prefix.ends_with('/')||(!prefix.is_empty()&&prefix.split('/').any(|p|p.is_empty()||p=="."||p=="..")){return Err(AuthorityError::new("INVALID_RESOURCE_PREFIX",format!("unsafe or non-normalized resource prefix in {field}")));}Ok(())}
fn valid_resource_id(v:&str)->bool{let Some((k,id))=v.split_once(':') else{return false;};!k.is_empty()&&k.len()<=64&&k.bytes().next().map_or(false,|b|b.is_ascii_lowercase())&&k.bytes().all(|b|b.is_ascii_lowercase()||b.is_ascii_digit()||matches!(b,b'_'|b'.'|b'-'))&&!id.is_empty()&&id.len()<=160&&id.bytes().all(|b|b.is_ascii_alphanumeric()||matches!(b,b'_'|b'.'|b':'|b'-'))}
fn valid_semantic_id(v:&str)->bool{!v.is_empty()&&v.len()<=200&&v.bytes().all(|b|b.is_ascii_alphanumeric()||matches!(b,b'_'|b'.'|b':'|b'-'))}
fn valid_provider_id(v:&str)->bool{!v.is_empty()&&v.len()<=160&&v.bytes().next().map_or(false,|b|b.is_ascii_lowercase())&&v.bytes().all(|b|b.is_ascii_lowercase()||b.is_ascii_digit()||matches!(b,b'_'|b'.'|b':'|b'-'))}
fn valid_env_name(v:&str)->bool{let mut b=v.bytes();let Some(f)=b.next()else{return false;};(f.is_ascii_alphabetic()||f==b'_')&&v.len()<=128&&b.all(|x|x.is_ascii_alphanumeric()||x==b'_')}
fn valid_host(v:&str)->bool{!v.is_empty()&&!v.starts_with('.')&&!v.ends_with('.')&&!v.contains("..")&&v.bytes().all(|b|b.is_ascii_lowercase()||b.is_ascii_digit()||matches!(b,b'.'|b'-'))}
fn validate_numbers(value:&Value,path:&str)->Result<(),AuthorityError>{match value{Value::Number(n)=>{if let Some(i)=n.as_i64(){let m=MAX_SAFE_INTEGER as i64;if i < -m || i > m{return Err(AuthorityError::new("INTEGER_OUT_OF_RANGE",format!("integer outside cross-language safe range at {path}")));}Ok(())}else if let Some(u)=n.as_u64(){if u>MAX_SAFE_INTEGER{return Err(AuthorityError::new("INTEGER_OUT_OF_RANGE",format!("integer outside cross-language safe range at {path}")));}Ok(())}else{Err(AuthorityError::new("FLOAT_FORBIDDEN",format!("floating-point value forbidden at {path}")))}}Value::Array(a)=>{for(i,v)in a.iter().enumerate(){validate_numbers(v,&format!("{path}[{i}]"))?;}Ok(())}Value::Object(o)=>{for(k,v)in o{validate_numbers(v,&format!("{path}.{k}"))?;}Ok(())}_=>Ok(())}}
