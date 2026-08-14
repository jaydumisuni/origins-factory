export type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };

export const SCHEMA_VERSION = "1.0.0";
export const MAX_SAFE_INTEGER = 9_007_199_254_740_991;

const EFFECTS = ["draft", "execute", "mutate", "observe", "publish", "verify"] as const;
const NODE_OS = ["any", "linux", "macos", "windows"] as const;
const MATURITY = ["experimental", "frozen", "planned", "proven"] as const;
const MODEL_DEPENDENCY = ["none", "optional", "required"] as const;
const SESSION_KINDS = ["process"] as const;
const SESSION_STATES = [
  "completed",
  "failed",
  "interrupted",
  "running",
  "starting",
  "timed_out",
] as const;
const SEMVER_RE = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const OID_RE = /^[0-9a-f]{40}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PID_RE = /^[0-9]+$/;
const RFC3339_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const encoder = new TextEncoder();

export class ContractError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ContractError";
    this.code = code;
  }
}

export function canonicalJson(value: JsonValue): string {
  validateNumbers(value, "$");
  return serializeCanonical(value);
}

export function canonicalBytes(value: JsonValue): Uint8Array {
  return encoder.encode(canonicalJson(value));
}

export async function contractSha256(value: JsonValue): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", canonicalBytes(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function validateContract(value: JsonValue): JsonObject {
  const object = asObject(value, "INVALID_ROOT", "contract root must be an object");
  validateNumbers(object, "$");

  const contractType = nonemptyString(object, "contract_type");
  if (stringField(object, "schema_version") !== SCHEMA_VERSION) {
    throw new ContractError("UNSUPPORTED_SCHEMA_VERSION", "schema_version must be 1.0.0");
  }

  switch (contractType) {
    case "authority_ref":
      validateAuthorityRef(object);
      break;
    case "workspace_projection":
      validateWorkspaceProjection(object);
      break;
    case "capability_descriptor":
      validateCapabilityDescriptor(object);
      break;
    case "command_envelope":
      validateCommandEnvelope(object);
      break;
    case "event_envelope":
      validateEventEnvelope(object);
      break;
    case "session_projection":
      validateSessionProjection(object);
      break;
    case "repository_projection":
      validateRepositoryProjection(object);
      break;
    case "artifact_projection":
      validateArtifactProjection(object);
      break;
    default:
      throw new ContractError("UNKNOWN_CONTRACT_TYPE", `unsupported contract_type: ${contractType}`);
  }
  return object;
}

function validateAuthorityRef(value: JsonObject): void {
  exactFields(value, [
    "contract_type",
    "schema_version",
    "authority",
    "kind",
    "id",
    "revision",
    "uri",
    "digest",
    "observed_at",
  ]);
  nonemptyString(value, "authority");
  nonemptyString(value, "kind");
  nonemptyString(value, "id");
  stringField(value, "revision");
  stringField(value, "uri");
  digestField(value, "digest", true);
  timestamp(value, "observed_at");
}

function validateWorkspaceProjection(value: JsonObject): void {
  exactFields(value, [
    "contract_type",
    "schema_version",
    "workspace_id",
    "name",
    "revision",
    "authority_refs",
    "session_refs",
    "created_at",
    "updated_at",
  ]);
  canonicalUuid(value, "workspace_id");
  nonemptyString(value, "name");
  nonnegativeInteger(value, "revision", "INVALID_REVISION");
  authorityRefList(value, "authority_refs");
  authorityRefList(value, "session_refs");
  const created = timestamp(value, "created_at");
  const updated = timestamp(value, "updated_at");
  if (updated < created) {
    throw new ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede created_at");
  }
}

function validateCapabilityDescriptor(value: JsonObject): void {
  exactFields(value, [
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
  ]);
  nonemptyString(value, "capability_id");
  const version = nonemptyString(value, "version");
  if (!SEMVER_RE.test(version)) {
    throw new ContractError("INVALID_SEMVER", "version must be ASCII semantic version X.Y.Z");
  }
  nonemptyString(value, "owner");
  sortedUniqueEnumList(value, "effects", EFFECTS, false);
  sortedUniqueStringList(value, "permissions");
  sortedUniqueEnumList(value, "node_os", NODE_OS, false);
  enumField(value, "maturity", MATURITY);
  enumField(value, "model_dependency", MODEL_DEPENDENCY);
  booleanField(value, "review_required");
  if (booleanField(value, "self_promotable")) {
    throw new ContractError("SELF_PROMOTION_FORBIDDEN", "capabilities cannot self-promote");
  }
}

function validateCommandEnvelope(value: JsonObject): void {
  exactFields(value, [
    "contract_type",
    "schema_version",
    "command_id",
    "workspace_id",
    "capability_id",
    "effect",
    "payload",
    "created_at",
  ]);
  canonicalUuid(value, "command_id");
  canonicalUuid(value, "workspace_id");
  nonemptyString(value, "capability_id");
  enumField(value, "effect", EFFECTS);
  asObject(value.payload, "INVALID_PAYLOAD", "payload must be an object");
  timestamp(value, "created_at");
}

function validateEventEnvelope(value: JsonObject): void {
  exactFields(value, [
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
  ]);
  canonicalUuid(value, "event_id");
  canonicalUuid(value, "workspace_id");
  nonemptyString(value, "producer");
  nonemptyString(value, "kind");
  nonnegativeInteger(value, "sequence", "INVALID_SEQUENCE");
  asObject(value.payload, "INVALID_PAYLOAD", "payload must be an object");
  authorityRefList(value, "evidence_refs");
  timestamp(value, "created_at");
}

function validateSessionProjection(value: JsonObject): void {
  exactFields(value, [
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
  ]);
  canonicalUuid(value, "session_id");
  canonicalUuid(value, "workspace_id");
  canonicalUuid(value, "command_id");
  nonemptyString(value, "capability_id");
  enumField(value, "kind", SESSION_KINDS);
  nonemptyString(value, "workspace_root");
  const state = enumField(value, "state", SESSION_STATES);
  const pid = stringField(value, "pid");
  if (pid !== "" && !PID_RE.test(pid)) {
    throw new ContractError("INVALID_PID", "pid must be empty or ASCII decimal digits");
  }
  const started = timestamp(value, "started_at");
  const updated = timestamp(value, "updated_at");
  if (updated < started) {
    throw new ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede started_at");
  }
  const ended = optionalTimestamp(value, "ended_at");
  if (ended !== null && ended < started) {
    throw new ContractError("INVALID_TIMESTAMP_ORDER", "ended_at cannot precede started_at");
  }
  const exitCode = optionalInteger(value, "exit_code", "INVALID_EXIT_CODE");
  const timedOut = booleanField(value, "timed_out");
  nonnegativeInteger(value, "stdout_bytes", "INVALID_BYTE_COUNT");
  nonnegativeInteger(value, "stderr_bytes", "INVALID_BYTE_COUNT");
  digestField(value, "stdout_sha256", false);
  digestField(value, "stderr_sha256", false);
  booleanField(value, "output_truncated");

  const active = state === "starting" || state === "running";
  if (active && ended !== null) {
    throw new ContractError("INVALID_SESSION_STATE", "active session cannot have ended_at");
  }
  if (active && exitCode !== null) {
    throw new ContractError("INVALID_SESSION_STATE", "active session cannot have exit_code");
  }
  if (!active && ended === null) {
    throw new ContractError("INVALID_SESSION_STATE", "terminal session state requires ended_at");
  }
  if (timedOut !== (state === "timed_out")) {
    throw new ContractError("INVALID_SESSION_STATE", "timed_out flag must match timed_out state");
  }
  if (state === "completed" && exitCode !== 0) {
    throw new ContractError("INVALID_SESSION_STATE", "completed session requires exit_code 0");
  }
  if (state === "failed" && (exitCode === null || exitCode === 0)) {
    throw new ContractError(
      "INVALID_SESSION_STATE",
      "failed session requires a non-zero exit_code",
    );
  }
  if ((state === "timed_out" || state === "interrupted") && exitCode !== null) {
    throw new ContractError(
      "INVALID_SESSION_STATE",
      `${state} session must not claim exit_code`,
    );
  }
}

function validateRepositoryProjection(value: JsonObject): void {
  exactFields(value, [
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
  ]);
  canonicalUuid(value, "repository_id");
  canonicalUuid(value, "workspace_id");
  const revision = nonnegativeInteger(value, "revision", "INVALID_REVISION");
  if (revision < 1) {
    throw new ContractError("INVALID_REVISION", "repository revision must be at least 1");
  }
  nonemptyString(value, "worktree_root");
  nonemptyString(value, "git_dir");
  nonemptyString(value, "common_dir");
  const headOid = stringField(value, "head_oid");
  if (headOid !== "" && !OID_RE.test(headOid)) {
    throw new ContractError(
      "INVALID_GIT_OID",
      "head_oid must be empty or lowercase 40-hex Git OID",
    );
  }
  const headRef = stringField(value, "head_ref");
  const branch = stringField(value, "branch");
  const detached = booleanField(value, "detached");
  const unborn = booleanField(value, "unborn");
  nonnegativeInteger(value, "staged_count", "INVALID_STATUS_COUNT");
  nonnegativeInteger(value, "unstaged_count", "INVALID_STATUS_COUNT");
  nonnegativeInteger(value, "untracked_count", "INVALID_STATUS_COUNT");
  digestField(value, "status_sha256", false);
  timestamp(value, "observed_at");

  if (unborn) {
    if (headOid !== "" || detached || headRef === "" || branch === "") {
      throw new ContractError(
        "INVALID_REPOSITORY_STATE",
        "unborn repository requires symbolic branch and no OID",
      );
    }
  } else if (detached) {
    if (headOid === "" || headRef !== "" || branch !== "") {
      throw new ContractError(
        "INVALID_REPOSITORY_STATE",
        "detached repository requires OID and no symbolic branch",
      );
    }
  } else if (headOid === "" || headRef === "" || branch === "") {
    throw new ContractError(
      "INVALID_REPOSITORY_STATE",
      "attached repository requires OID and symbolic branch",
    );
  }
  if (headRef !== "" && branch !== "" && headRef !== `refs/heads/${branch}`) {
    throw new ContractError("INVALID_REPOSITORY_STATE", "head_ref and branch disagree");
  }
}

function validateArtifactProjection(value: JsonObject): void {
  exactFields(value, [
    "contract_type",
    "schema_version",
    "artifact_id",
    "workspace_id",
    "revision",
    "content_sha256",
    "size_bytes",
    "filename",
    "media_type",
    "storage_class",
    "source_count",
    "created_at",
    "updated_at",
  ]);
  canonicalUuid(value, "artifact_id");
  canonicalUuid(value, "workspace_id");
  const revision = nonnegativeInteger(value, "revision", "INVALID_REVISION");
  if (revision < 1) {
    throw new ContractError("INVALID_REVISION", "artifact revision must be at least 1");
  }
  digestField(value, "content_sha256", false);
  nonnegativeInteger(value, "size_bytes", "INVALID_BYTE_COUNT");
  nonemptyString(value, "filename");
  stringField(value, "media_type");
  if (stringField(value, "storage_class") !== "local_immutable") {
    throw new ContractError("INVALID_STORAGE_CLASS", "storage_class must be local_immutable");
  }
  const sourceCount = nonnegativeInteger(value, "source_count", "INVALID_SOURCE_COUNT");
  if (sourceCount < 1) {
    throw new ContractError("INVALID_SOURCE_COUNT", "source_count must be at least 1");
  }
  const created = timestamp(value, "created_at");
  const updated = timestamp(value, "updated_at");
  if (updated < created) {
    throw new ContractError("INVALID_TIMESTAMP_ORDER", "updated_at cannot precede created_at");
  }
}

function validateNumbers(value: JsonValue, path: string): void {
  if (typeof value === "number") {
    if (!Number.isFinite(value) || !Number.isInteger(value)) {
      throw new ContractError("FLOAT_FORBIDDEN", `floating-point value forbidden at ${path}`);
    }
    if (!Number.isSafeInteger(value)) {
      throw new ContractError(
        "INTEGER_OUT_OF_RANGE",
        `integer outside cross-language safe range at ${path}`,
      );
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => validateNumbers(child, `${path}[${index}]`));
    return;
  }
  if (isObject(value)) {
    for (const [key, child] of Object.entries(value)) {
      validateNumbers(child, `${path}.${key}`);
    }
  }
}

function serializeCanonical(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Object.is(value, -0) ? "0" : String(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(serializeCanonical).join(",")}]`;

  const keys = Object.keys(value).sort(compareUtf8);
  return `{${keys
    .map((key) => `${JSON.stringify(key)}:${serializeCanonical(value[key])}`)
    .join(",")}}`;
}

function compareUtf8(left: string, right: string): number {
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  const length = Math.min(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
}

function exactFields(value: JsonObject, expectedFields: readonly string[]): void {
  const expected = new Set(expectedFields);
  const actual = new Set(Object.keys(value));
  const missing = [...expected].filter((field) => !actual.has(field)).sort(compareUtf8);
  const unknown = [...actual].filter((field) => !expected.has(field)).sort(compareUtf8);
  if (missing.length > 0) {
    throw new ContractError("MISSING_FIELD", `missing fields: ${missing.join(", ")}`);
  }
  if (unknown.length > 0) {
    throw new ContractError("UNKNOWN_FIELD", `unknown fields: ${unknown.join(", ")}`);
  }
}

function stringField(value: JsonObject, field: string): string {
  const item = value[field];
  if (typeof item !== "string") {
    throw new ContractError("INVALID_STRING", `${field} must be a string`);
  }
  return item;
}

function nonemptyString(value: JsonObject, field: string): string {
  const item = stringField(value, field);
  if (item.trim() === "") {
    throw new ContractError("EMPTY_STRING", `${field} cannot be empty`);
  }
  return item;
}

function booleanField(value: JsonObject, field: string): boolean {
  const item = value[field];
  if (typeof item !== "boolean") {
    throw new ContractError("INVALID_BOOLEAN", `${field} must be boolean`);
  }
  return item;
}

function canonicalUuid(value: JsonObject, field: string): string {
  const item = nonemptyString(value, field);
  if (!UUID_RE.test(item)) {
    throw new ContractError("INVALID_UUID", `${field} must be a UUID`);
  }
  return item;
}

function timestamp(value: JsonObject, field: string): number {
  const item = nonemptyString(value, field);
  if (!RFC3339_UTC_RE.test(item)) {
    throw new ContractError("INVALID_TIMESTAMP", `${field} must be UTC RFC3339 ending in Z`);
  }
  const parsed = Date.parse(item);
  if (Number.isNaN(parsed)) {
    throw new ContractError("INVALID_TIMESTAMP", `${field} is not valid RFC3339`);
  }
  return parsed;
}

function optionalTimestamp(value: JsonObject, field: string): number | null {
  const item = stringField(value, field);
  return item === "" ? null : timestamp(value, field);
}

function enumField<T extends string>(
  value: JsonObject,
  field: string,
  allowed: readonly T[],
): T {
  const item = nonemptyString(value, field);
  if (!allowed.includes(item as T)) {
    throw new ContractError("INVALID_ENUM", `${field} must be one of: ${allowed.join(", ")}`);
  }
  return item as T;
}

function nonnegativeInteger(value: JsonObject, field: string, code: string): number {
  const item = value[field];
  if (typeof item !== "number" || !Number.isSafeInteger(item) || item < 0) {
    throw new ContractError(code, `${field} must be a non-negative integer`);
  }
  return item;
}

function optionalInteger(value: JsonObject, field: string, code: string): number | null {
  const item = value[field];
  if (item === null) return null;
  if (typeof item !== "number" || !Number.isSafeInteger(item)) {
    throw new ContractError(code, `${field} must be null or an integer`);
  }
  return item;
}

function digestField(value: JsonObject, field: string, allowEmpty: boolean): string {
  const item = stringField(value, field);
  if (item === "" && allowEmpty) return item;
  if (!SHA256_RE.test(item)) {
    throw new ContractError("INVALID_DIGEST", `${field} must be lowercase SHA-256`);
  }
  return item;
}

function sortedUniqueStringList(value: JsonObject, field: string): string[] {
  const items = value[field];
  if (!Array.isArray(items) || items.some((item) => typeof item !== "string" || item === "")) {
    throw new ContractError("INVALID_LIST", `${field} must be a list of non-empty strings`);
  }
  const strings = items as string[];
  const sorted = [...new Set(strings)].sort(compareUtf8);
  if (strings.length !== sorted.length || strings.some((item, index) => item !== sorted[index])) {
    throw new ContractError("UNSORTED_OR_DUPLICATE_LIST", `${field} must be sorted and unique`);
  }
  return strings;
}

function sortedUniqueEnumList<T extends string>(
  value: JsonObject,
  field: string,
  allowed: readonly T[],
  allowEmpty: boolean,
): string[] {
  const items = sortedUniqueStringList(value, field);
  if (!allowEmpty && items.length === 0) {
    throw new ContractError("EMPTY_LIST", `${field} cannot be empty`);
  }
  const invalid = items.filter((item) => !allowed.includes(item as T));
  if (invalid.length > 0) {
    throw new ContractError(
      "INVALID_ENUM",
      `${field} contains unsupported values: ${invalid.join(", ")}`,
    );
  }
  return items;
}

function authorityRefList(value: JsonObject, field: string): JsonObject[] {
  const items = value[field];
  if (!Array.isArray(items)) {
    throw new ContractError("INVALID_LIST", `${field} must be a list`);
  }
  const seen = new Set<string>();
  const result: JsonObject[] = [];
  for (const item of items) {
    const reference = validateContract(item as JsonValue);
    if (reference.contract_type !== "authority_ref") {
      throw new ContractError("INVALID_REFERENCE", `${field} may contain authority_ref contracts only`);
    }
    const identity = `${reference.authority}\u0000${reference.kind}\u0000${reference.id}`;
    if (seen.has(identity)) {
      throw new ContractError("DUPLICATE_REFERENCE", `duplicate authority reference in ${field}`);
    }
    seen.add(identity);
    result.push(reference);
  }
  return result;
}

function asObject(value: JsonValue | undefined, code: string, message: string): JsonObject {
  if (!isObject(value)) throw new ContractError(code, message);
  return value;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
