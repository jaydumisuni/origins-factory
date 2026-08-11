import {
  canonicalJson,
  ContractError,
  contractSha256,
  type JsonObject,
  type JsonValue,
} from "./contracts.ts";

export const SCHEMA_VERSION = "1.1.0";
const EFFECTS = ["draft", "execute", "mutate", "observe", "publish", "verify"] as const;
const NETWORK_MODES = ["allowlist", "delegated_remote", "deny"] as const;
const NETWORK_PROTOCOLS = ["http", "https", "tcp", "udp", "ws", "wss"] as const;
const REDIRECT_POLICIES = ["deny_outside_endpoints"] as const;
const AUTHORITY_STATES = ["active", "expired", "revoked", "suspended"] as const;
const HOLDER_KINDS = ["candidate", "operation", "provider", "session"] as const;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHA256_RE = /^[0-9a-f]{64}$/;
const ENV_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;
const RESOURCE_ID_RE = /^[a-z][a-z0-9_.-]{0,63}:[A-Za-z0-9_.:-]{1,160}$/;
const SEMANTIC_ID_RE = /^[A-Za-z0-9_.:-]{1,200}$/;
const PROVIDER_ID_RE = /^[a-z][a-z0-9_.:-]{0,159}$/;
const HOST_RE = /^[a-z0-9.-]+$/;
const RFC3339_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const encoder = new TextEncoder();

type Grant = { resource_id: string; prefix: string };
type Endpoint = { protocol: string; host: string; port: number };

export function validateAuthorityContract(value: JsonValue): JsonObject {
  const object = asObject(value, "INVALID_ROOT", "authority contract root must be an object");
  if (stringField(object, "schema_version") !== SCHEMA_VERSION) {
    throw new ContractError("UNSUPPORTED_SCHEMA_VERSION", "schema_version must be 1.1.0");
  }
  const type = stringField(object, "contract_type");
  if (type === "execution_scope") validateExecutionScope(object);
  else if (type === "capability_lease") validateCapabilityLease(object);
  else throw new ContractError("UNKNOWN_CONTRACT_TYPE", `unsupported authority contract_type: ${type}`);
  canonicalJson(object);
  return object;
}

export async function authoritySha256(value: JsonValue): Promise<string> {
  validateAuthorityContract(value);
  return contractSha256(value);
}

export function validateChildScope(childValue: JsonValue, parentValue: JsonValue): void {
  const parent = validateAuthorityContract(parentValue);
  const child = validateAuthorityContract(childValue);
  requireTypes(parent, child, "execution_scope", "INVALID_SCOPE_RELATION");
  if (parent.state !== "active" || child.state !== "active") {
    throw new ContractError("SCOPE_UNUSABLE", "scope delegation requires active parent and child");
  }
  if (child.workspace_id !== parent.workspace_id) throw new ContractError("SCOPE_ESCALATION", "child scope cannot change workspace");
  if (child.operation_id !== parent.operation_id) throw new ContractError("SCOPE_ESCALATION", "child scope cannot change operation identity");
  if (child.parent_scope_id !== parent.scope_id) throw new ContractError("SCOPE_ESCALATION", "child parent_scope_id must reference parent scope");
  requireCandidateTransition(stringField(child, "candidate_id"), stringField(parent, "candidate_id"));
  if (parent.delegation_allowed !== true) throw new ContractError("SCOPE_ESCALATION", "parent scope forbids delegation");
  requireSubset(strings(child.effects), strings(parent.effects), "effects");
  requireGrantsWithin(grants(child.resource_reads), grants(parent.resource_reads), "resource_reads");
  requireGrantsWithin(grants(child.resource_writes), grants(parent.resource_writes), "resource_writes");
  requireParentDenies(grants(child.resource_denies), grants(parent.resource_denies));
  requireSubset(strings(child.environment_names), strings(parent.environment_names), "environment_names");
  requireNetworkNarrowing(child, parent);
  if (child.process_execution_allowed === true && parent.process_execution_allowed !== true) throw new ContractError("SCOPE_ESCALATION", "child cannot enable process execution");
  if (child.persistent_process_allowed === true && parent.persistent_process_allowed !== true) throw new ContractError("SCOPE_ESCALATION", "child cannot enable persistent processes");
  if (child.delegated_remote_authority === true && parent.delegated_remote_authority !== true) throw new ContractError("SCOPE_ESCALATION", "child cannot enable delegated remote authority");
  requireIssuedAfter(stringField(child, "issued_at"), stringField(parent, "updated_at"), "child scope");
  requireExpiryNotExtended(stringField(child, "expires_at"), stringField(parent, "expires_at"));
}

export function validateLeaseWithinScope(leaseValue: JsonValue, scopeValue: JsonValue): void {
  const scope = validateAuthorityContract(scopeValue);
  const lease = validateAuthorityContract(leaseValue);
  if (scope.contract_type !== "execution_scope" || lease.contract_type !== "capability_lease") {
    throw new ContractError("INVALID_LEASE_RELATION", "lease must be checked against execution_scope");
  }
  if (scope.state !== "active" || lease.state !== "active") throw new ContractError("LEASE_UNUSABLE", "lease issuance/use requires active scope and lease");
  if (lease.scope_id !== scope.scope_id || lease.workspace_id !== scope.workspace_id) throw new ContractError("LEASE_ESCALATION", "lease scope/workspace identity does not match");
  requireSubset(strings(lease.effects), strings(scope.effects), "effects");
  requireGrantsWithin(grants(lease.resource_reads), grants(scope.resource_reads), "resource_reads");
  requireGrantsWithin(grants(lease.resource_writes), grants(scope.resource_writes), "resource_writes");
  requireParentDenies(grants(lease.resource_denies), grants(scope.resource_denies));
  requireSubset(strings(lease.environment_names), strings(scope.environment_names), "environment_names");
  requireNetworkNarrowing(lease, scope);
  if (lease.persistent_process_allowed === true && scope.persistent_process_allowed !== true) throw new ContractError("LEASE_ESCALATION", "lease cannot enable persistent processes");
  if (lease.delegated_remote_authority === true && scope.delegated_remote_authority !== true) throw new ContractError("LEASE_ESCALATION", "lease cannot enable delegated remote authority");
  if (strings(lease.effects).includes("execute") && scope.process_execution_allowed !== true) throw new ContractError("LEASE_ESCALATION", "scope forbids process execution");
  requireIssuedAfter(stringField(lease, "issued_at"), stringField(scope, "updated_at"), "lease");
  requireExpiryNotExtended(stringField(lease, "expires_at"), stringField(scope, "expires_at"));
}

export async function validateScopeCurrent(presentedValue: JsonValue, currentValue: JsonValue): Promise<void> {
  const presented = validateAuthorityContract(presentedValue);
  const current = validateAuthorityContract(currentValue);
  requireTypes(presented, current, "execution_scope", "INVALID_SCOPE_RELATION");
  for (const field of ["scope_id", "workspace_id", "operation_id", "candidate_id"] as const) {
    if (presented[field] !== current[field]) throw new ContractError("STALE_SCOPE", `presented scope changed ${field}`);
  }
  if (current.state !== "active") throw new ContractError("SCOPE_UNUSABLE", "current scope is not active");
  if (presented.revision !== current.revision || presented.fence !== current.fence) throw new ContractError("STALE_SCOPE", "presented scope revision/fence is stale");
  if ((await contractSha256(presented)) !== (await contractSha256(current))) throw new ContractError("STALE_SCOPE", "presented scope content differs from current generation");
}

export function validateProviderBinding(
  leaseValue: JsonValue,
  providerId: string,
  providerManifestDigest: string,
  providerGeneration: number,
): void {
  const lease = validateAuthorityContract(leaseValue);
  if (lease.contract_type !== "capability_lease") throw new ContractError("INVALID_LEASE_RELATION", "provider binding requires capability_lease");
  if (lease.provider_id !== providerId || lease.provider_manifest_digest !== providerManifestDigest || lease.provider_generation !== providerGeneration) {
    throw new ContractError("PROVIDER_SUBSTITUTION", "current capability provider does not match lease binding");
  }
}

function validateExecutionScope(value: JsonObject): void {
  exactFields(value, [
    "contract_type", "schema_version", "scope_id", "workspace_id", "operation_id", "candidate_id", "parent_scope_id",
    "effects", "resource_reads", "resource_writes", "resource_denies", "network_mode", "network_endpoints",
    "network_redirect_policy", "environment_names", "process_execution_allowed", "persistent_process_allowed",
    "delegation_allowed", "delegated_remote_authority", "state", "fence", "issued_at", "updated_at", "expires_at", "revision",
  ]);
  uuidField(value, "scope_id");
  uuidField(value, "workspace_id");
  semanticId(value, "operation_id", false);
  semanticId(value, "candidate_id", true);
  optionalUuid(value, "parent_scope_id");
  sortedUniqueEnumList(value, "effects", EFFECTS, false);
  const reads = resourceGrants(value, "resource_reads");
  const writes = resourceGrants(value, "resource_writes");
  const denies = resourceGrants(value, "resource_denies");
  requireGrantsWithin(writes, reads, "resource_writes");
  rejectFullyDeniedGrants(reads, denies, "resource_reads");
  rejectFullyDeniedGrants(writes, denies, "resource_writes");
  validateNetwork(value);
  environmentNames(value, "environment_names");
  const processAllowed = booleanField(value, "process_execution_allowed");
  const persistent = booleanField(value, "persistent_process_allowed");
  booleanField(value, "delegation_allowed");
  booleanField(value, "delegated_remote_authority");
  if (persistent && !processAllowed) throw new ContractError("INVALID_SCOPE", "persistent processes require process execution");
  validateNetworkRemoteFlag(value);
  const state = enumField(value, "state", AUTHORITY_STATES);
  if (nonnegativeInteger(value, "fence", "INVALID_FENCE") < 1) throw new ContractError("INVALID_FENCE", "fence must be at least 1");
  validateChronology(value, state, "scope");
  if (nonnegativeInteger(value, "revision", "INVALID_REVISION") < 1) throw new ContractError("INVALID_REVISION", "revision must be at least 1");
}

function validateCapabilityLease(value: JsonObject): void {
  exactFields(value, [
    "contract_type", "schema_version", "lease_id", "scope_id", "workspace_id", "capability_id", "provider_id",
    "provider_manifest_digest", "provider_generation", "holder_kind", "holder_id", "holder_generation", "effects",
    "resource_reads", "resource_writes", "resource_denies", "network_mode", "network_endpoints", "network_redirect_policy",
    "environment_names", "persistent_process_allowed", "delegated_remote_authority", "approval_authority", "approval_id",
    "approval_digest", "proposal_digest", "state", "fence", "issued_at", "updated_at", "expires_at", "revision",
  ]);
  uuidField(value, "lease_id");
  uuidField(value, "scope_id");
  uuidField(value, "workspace_id");
  nonemptyString(value, "capability_id");
  const providerId = nonemptyString(value, "provider_id");
  if (!PROVIDER_ID_RE.test(providerId)) throw new ContractError("INVALID_PROVIDER_ID", "provider_id must be canonical lower-case provider identity");
  digestField(value, "provider_manifest_digest");
  if (nonnegativeInteger(value, "provider_generation", "INVALID_PROVIDER_GENERATION") < 1) throw new ContractError("INVALID_PROVIDER_GENERATION", "provider_generation must be at least 1");
  enumField(value, "holder_kind", HOLDER_KINDS);
  uuidField(value, "holder_id");
  if (nonnegativeInteger(value, "holder_generation", "INVALID_HOLDER_GENERATION") < 1) throw new ContractError("INVALID_HOLDER_GENERATION", "holder_generation must be at least 1");
  const effects = sortedUniqueEnumList(value, "effects", EFFECTS, false);
  const reads = resourceGrants(value, "resource_reads");
  const writes = resourceGrants(value, "resource_writes");
  const denies = resourceGrants(value, "resource_denies");
  requireGrantsWithin(writes, reads, "resource_writes");
  rejectFullyDeniedGrants(reads, denies, "resource_reads");
  rejectFullyDeniedGrants(writes, denies, "resource_writes");
  validateNetwork(value);
  environmentNames(value, "environment_names");
  const persistent = booleanField(value, "persistent_process_allowed");
  booleanField(value, "delegated_remote_authority");
  if (persistent && !effects.includes("execute")) throw new ContractError("INVALID_LEASE", "persistent process lease requires execute effect");
  validateNetworkRemoteFlag(value);
  nonemptyString(value, "approval_authority");
  nonemptyString(value, "approval_id");
  digestField(value, "approval_digest");
  digestField(value, "proposal_digest");
  const state = enumField(value, "state", AUTHORITY_STATES);
  if (nonnegativeInteger(value, "fence", "INVALID_FENCE") < 1) throw new ContractError("INVALID_FENCE", "fence must be at least 1");
  validateChronology(value, state, "lease");
  if (nonnegativeInteger(value, "revision", "INVALID_REVISION") < 1) throw new ContractError("INVALID_REVISION", "revision must be at least 1");
}

function validateChronology(value: JsonObject, state: string, kind: string): void {
  const issued = timestamp(value, "issued_at");
  const updated = timestamp(value, "updated_at");
  if (updated < issued) throw new ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede issued_at");
  const expires = optionalTimestamp(value, "expires_at");
  if (expires !== null && expires <= issued) throw new ContractError("INVALID_TIMESTAMP_ORDER", "expires_at must be later than issued_at");
  if (state === "expired" && expires === null) throw new ContractError(kind === "scope" ? "INVALID_SCOPE" : "INVALID_LEASE", `expired ${kind} requires expires_at`);
}

function resourceGrants(value: JsonObject, field: string): Grant[] {
  const items = value[field];
  if (!Array.isArray(items)) throw new ContractError("INVALID_RESOURCE_GRANTS", `${field} must be a list`);
  const result: Grant[] = [];
  for (const item of items) {
    const object = asObject(item as JsonValue, "INVALID_RESOURCE_GRANT", `${field} entries must be objects`);
    exactFields(object, ["resource_id", "prefix"]);
    const resourceId = stringField(object, "resource_id");
    const prefix = stringField(object, "prefix");
    if (!RESOURCE_ID_RE.test(resourceId)) throw new ContractError("INVALID_RESOURCE_ID", `invalid resource_id in ${field}`);
    validatePrefix(prefix, field);
    result.push({ resource_id: resourceId, prefix });
  }
  const keys = result.map((item) => `${item.resource_id}\u0000${item.prefix}`);
  const sorted = [...new Set(keys)].sort(compareUtf8);
  if (keys.length !== sorted.length || keys.some((item, index) => item !== sorted[index])) throw new ContractError("UNSORTED_OR_DUPLICATE_LIST", `${field} must be sorted by resource_id/prefix and unique`);
  return result;
}

function networkEndpoints(value: JsonObject, field: string): Endpoint[] {
  const items = value[field];
  if (!Array.isArray(items)) throw new ContractError("INVALID_NETWORK_ENDPOINTS", `${field} must be a list`);
  const result: Endpoint[] = [];
  for (const item of items) {
    const object = asObject(item as JsonValue, "INVALID_NETWORK_ENDPOINT", "network endpoint must be an object");
    exactFields(object, ["protocol", "host", "port"]);
    const protocol = stringField(object, "protocol");
    const host = stringField(object, "host");
    const port = object.port;
    if (!NETWORK_PROTOCOLS.includes(protocol as typeof NETWORK_PROTOCOLS[number])) throw new ContractError("INVALID_NETWORK_PROTOCOL", "unsupported network endpoint protocol");
    if (!HOST_RE.test(host) || host.startsWith(".") || host.endsWith(".") || host.includes("..")) throw new ContractError("INVALID_NETWORK_HOST", `invalid exact network host: ${host}`);
    if (typeof port !== "number" || !Number.isSafeInteger(port) || port < 1 || port > 65535) throw new ContractError("INVALID_NETWORK_PORT", "network endpoint port must be 1..65535");
    result.push({ protocol, host, port });
  }
  const keys = result.map((item) => `${item.protocol}\u0000${item.host}\u0000${String(item.port).padStart(5, "0")}`);
  const sorted = [...new Set(keys)].sort(compareUtf8);
  if (keys.length !== sorted.length || keys.some((item, index) => item !== sorted[index])) throw new ContractError("UNSORTED_OR_DUPLICATE_LIST", `${field} must be sorted by protocol/host/port and unique`);
  return result;
}

function validateNetwork(value: JsonObject): void {
  const mode = enumField(value, "network_mode", NETWORK_MODES);
  const endpoints = networkEndpoints(value, "network_endpoints");
  enumField(value, "network_redirect_policy", REDIRECT_POLICIES);
  if (mode === "deny" && endpoints.length > 0) throw new ContractError("INVALID_NETWORK_SCOPE", "deny mode cannot include network endpoints");
  if (mode !== "deny" && endpoints.length === 0) throw new ContractError("INVALID_NETWORK_SCOPE", `${mode} mode requires exact network endpoints`);
}

function requireNetworkNarrowing(child: JsonObject, parent: JsonObject): void {
  const childMode = stringField(child, "network_mode");
  const parentMode = stringField(parent, "network_mode");
  if (childMode === "deny") return;
  if (childMode !== parentMode) throw new ContractError("SCOPE_ESCALATION", "network authority class cannot change while delegating");
  if (child.network_redirect_policy !== parent.network_redirect_policy) throw new ContractError("SCOPE_ESCALATION", "network redirect policy cannot widen while delegating");
  const parentSet = new Set(networkEndpoints(parent, "network_endpoints").map(endpointKey));
  if (networkEndpoints(child, "network_endpoints").some((item) => !parentSet.has(endpointKey(item)))) throw new ContractError("SCOPE_ESCALATION", "network_endpoints cannot expand parent authority");
}

function endpointKey(item: Endpoint): string { return `${item.protocol}\u0000${item.host}\u0000${item.port}`; }

function validateNetworkRemoteFlag(value: JsonObject): void {
  const mode = stringField(value, "network_mode");
  const delegated = booleanField(value, "delegated_remote_authority");
  if (mode === "delegated_remote" && !delegated) throw new ContractError("INVALID_NETWORK_SCOPE", "delegated_remote mode must mark delegated remote authority");
  if (mode !== "delegated_remote" && delegated) throw new ContractError("INVALID_NETWORK_SCOPE", "delegated remote authority requires delegated_remote mode");
}

function requireCandidateTransition(child: string, parent: string): void {
  if (parent !== "" && child !== parent) throw new ContractError("SCOPE_ESCALATION", "candidate identity cannot change or clear once bound");
}

function validatePrefix(prefix: string, field: string): void {
  if (prefix.includes("\u0000") || prefix.includes("\\") || prefix.startsWith("/") || prefix.includes("//") || prefix.endsWith("/")) throw new ContractError("INVALID_RESOURCE_PREFIX", `unsafe resource prefix in ${field}`);
  if (prefix !== "" && prefix.split("/").some((part) => part === "" || part === "." || part === "..")) throw new ContractError("INVALID_RESOURCE_PREFIX", `resource prefix in ${field} must be normalized`);
}

function grantWithin(child: Grant, parent: Grant): boolean {
  if (child.resource_id !== parent.resource_id) return false;
  return parent.prefix === "" || child.prefix === parent.prefix || child.prefix.startsWith(`${parent.prefix}/`);
}
function requireGrantsWithin(children: Grant[], parents: Grant[], field: string): void { for (const child of children) if (!parents.some((parent) => grantWithin(child, parent))) throw new ContractError("SCOPE_ESCALATION", `${field} contains authority outside its parent`); }
function requireParentDenies(children: Grant[], parents: Grant[]): void { const keys = new Set(children.map((item) => `${item.resource_id}\u0000${item.prefix}`)); for (const parent of parents) if (!keys.has(`${parent.resource_id}\u0000${parent.prefix}`)) throw new ContractError("SCOPE_ESCALATION", "child/lease cannot drop a parent resource deny"); }
function rejectFullyDeniedGrants(items: Grant[], denies: Grant[], field: string): void { for (const item of items) if (denies.some((deny) => grantWithin(item, deny))) throw new ContractError("CONTRADICTORY_SCOPE", `${field} contains a grant fully covered by a deny`); }
function requireSubset(children: string[], parents: string[], field: string): void { const parent = new Set(parents); if (children.some((item) => !parent.has(item))) throw new ContractError("SCOPE_ESCALATION", `${field} cannot expand parent authority`); }
function requireIssuedAfter(childText: string, parentUpdatedText: string, label: string): void { if (parseTimestamp(childText, "issued_at") < parseTimestamp(parentUpdatedText, "updated_at")) throw new ContractError("INVALID_ISSUANCE_CHRONOLOGY", `${label} cannot predate current parent generation`); }
function requireExpiryNotExtended(childText: string, parentText: string): void { const child = parseOptionalTimestamp(childText, "expires_at"); const parent = parseOptionalTimestamp(parentText, "expires_at"); if (parent !== null && (child === null || child > parent)) throw new ContractError("SCOPE_ESCALATION", "child/lease expiry cannot extend beyond parent"); }

function environmentNames(value: JsonObject, field: string): string[] { const names = sortedUniqueStringList(value, field); for (const name of names) if (!ENV_NAME_RE.test(name)) throw new ContractError("INVALID_ENVIRONMENT_NAME", `${field} may contain variable names only`); return names; }
function semanticId(value: JsonObject, field: string, allowEmpty: boolean): string { const item = stringField(value, field); if (allowEmpty && item === "") return item; if (!SEMANTIC_ID_RE.test(item)) throw new ContractError("INVALID_SEMANTIC_ID", `${field} must use canonical semantic identifier characters`); return item; }
function requireTypes(left: JsonObject, right: JsonObject, type: string, code: string): void { if (left.contract_type !== type || right.contract_type !== type) throw new ContractError(code, `both contracts must be ${type}`); }
function exactFields(value: JsonObject, expectedFields: readonly string[]): void { const expected = new Set(expectedFields); const actual = new Set(Object.keys(value)); const missing = [...expected].filter((field) => !actual.has(field)).sort(compareUtf8); const unknown = [...actual].filter((field) => !expected.has(field)).sort(compareUtf8); if (missing.length) throw new ContractError("MISSING_FIELD", `missing fields: ${missing.join(", ")}`); if (unknown.length) throw new ContractError("UNKNOWN_FIELD", `unknown fields: ${unknown.join(", ")}`); }
function stringField(value: JsonObject, field: string): string { const item = value[field]; if (typeof item !== "string") throw new ContractError("INVALID_STRING", `${field} must be a string`); return item; }
function nonemptyString(value: JsonObject, field: string): string { const item = stringField(value, field); if (item.trim() === "") throw new ContractError("EMPTY_STRING", `${field} cannot be empty`); return item; }
function booleanField(value: JsonObject, field: string): boolean { const item = value[field]; if (typeof item !== "boolean") throw new ContractError("INVALID_BOOLEAN", `${field} must be boolean`); return item; }
function uuidField(value: JsonObject, field: string): string { const item = nonemptyString(value, field); if (!UUID_RE.test(item)) throw new ContractError("INVALID_UUID", `${field} must be a UUID`); return item; }
function optionalUuid(value: JsonObject, field: string): string { const item = stringField(value, field); if (item !== "" && !UUID_RE.test(item)) throw new ContractError("INVALID_UUID", `${field} must be empty or a UUID`); return item; }
function enumField<T extends string>(value: JsonObject, field: string, allowed: readonly T[]): T { const item = nonemptyString(value, field); if (!allowed.includes(item as T)) throw new ContractError("INVALID_ENUM", `${field} must be one of: ${allowed.join(", ")}`); return item as T; }
function sortedUniqueStringList(value: JsonObject, field: string): string[] { const items = strings(value[field], field, true); const sorted = [...new Set(items)].sort(compareUtf8); if (items.length !== sorted.length || items.some((item, index) => item !== sorted[index])) throw new ContractError("UNSORTED_OR_DUPLICATE_LIST", `${field} must be sorted and unique`); return items; }
function strings(value: JsonValue | undefined, field = "value", requireNonempty = false): string[] { if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || (requireNonempty && item === ""))) throw new ContractError("INVALID_LIST", `${field} must be a list of ${requireNonempty ? "non-empty " : ""}strings`); return value as string[]; }
function sortedUniqueEnumList<T extends string>(value: JsonObject, field: string, allowed: readonly T[], allowEmpty: boolean): string[] { const items = sortedUniqueStringList(value, field); if (!allowEmpty && items.length === 0) throw new ContractError("EMPTY_LIST", `${field} cannot be empty`); const invalid = items.filter((item) => !allowed.includes(item as T)); if (invalid.length) throw new ContractError("INVALID_ENUM", `${field} contains unsupported values: ${invalid.join(", ")}`); return items; }
function nonnegativeInteger(value: JsonObject, field: string, code: string): number { const item = value[field]; if (typeof item !== "number" || !Number.isSafeInteger(item) || item < 0) throw new ContractError(code, `${field} must be a non-negative integer`); return item; }
function digestField(value: JsonObject, field: string): string { const item = nonemptyString(value, field); if (!SHA256_RE.test(item)) throw new ContractError("INVALID_DIGEST", `${field} must be lowercase SHA-256`); return item; }
function timestamp(value: JsonObject, field: string): number { return parseTimestamp(nonemptyString(value, field), field); }
function optionalTimestamp(value: JsonObject, field: string): number | null { return parseOptionalTimestamp(stringField(value, field), field); }
function parseOptionalTimestamp(text: string, field: string): number | null { return text === "" ? null : parseTimestamp(text, field); }
function parseTimestamp(text: string, field: string): number { if (!RFC3339_UTC_RE.test(text)) throw new ContractError("INVALID_TIMESTAMP", `${field} must be UTC RFC3339 ending in Z`); const parsed = Date.parse(text); if (Number.isNaN(parsed)) throw new ContractError("INVALID_TIMESTAMP", `${field} is not valid RFC3339`); return parsed; }
function asObject(value: JsonValue | undefined, code: string, message: string): JsonObject { if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ContractError(code, message); return value as JsonObject; }
function grants(value: JsonValue | undefined): Grant[] { if (!Array.isArray(value)) throw new ContractError("INVALID_RESOURCE_GRANTS", "resource grants must be a list"); return value.map((item) => { const object = asObject(item as JsonValue, "INVALID_RESOURCE_GRANT", "resource grant must be an object"); return { resource_id: stringField(object, "resource_id"), prefix: stringField(object, "prefix") }; }); }
function compareUtf8(left: string, right: string): number { const a = encoder.encode(left); const b = encoder.encode(right); const length = Math.min(a.length, b.length); for (let index = 0; index < length; index += 1) if (a[index] !== b[index]) return a[index] - b[index]; return a.length - b.length; }
