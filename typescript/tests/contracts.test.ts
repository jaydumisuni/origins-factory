import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  canonicalJson,
  ContractError,
  contractSha256,
  type JsonValue,
  validateContract,
} from "../contracts.ts";
import {
  authoritySha256,
  validateAuthorityContract,
  validateChildScope,
  validateLeaseWithinScope,
} from "../authority.ts";

const fixtures = JSON.parse(
  await readFile(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"),
) as {
  valid: Array<{ name: string; contract: JsonValue }>;
  invalid: Array<{ name: string; expected_error: string; contract: JsonValue }>;
};
const authorityFixtures = JSON.parse(
  await readFile(new URL("../../contracts/authority-fixtures.json", import.meta.url), "utf8"),
) as {
  valid: Array<{ name: string; contract: JsonValue }>;
  invalid: Array<{ name: string; expected_error: string; contract: JsonValue }>;
};
const adversarialFixtures = JSON.parse(
  await readFile(new URL("../../contracts/authority-adversarial-fixtures.json", import.meta.url), "utf8"),
) as {
  invalid_contracts: Array<{
    name: string;
    base: "scope" | "lease";
    set: Record<string, JsonValue>;
    expected_error: string;
  }>;
  relations: Array<{
    name: string;
    relation: "child_scope" | "lease_scope";
    parent_set?: Record<string, JsonValue>;
    child_set?: Record<string, JsonValue>;
    scope_set?: Record<string, JsonValue>;
    lease_set?: Record<string, JsonValue>;
    expected_error: string;
  }>;
};
const authorityHashes: Record<string, string> = {
  workspace_candidate_scope: "69acd382b43d3aaee19c57e735ae735bc9c7c770cd4003cae6aec198ab647d9d",
  bounded_process_lease: "c44ba1680fb24b92b1391260daa59adf02a799cbdb3e54c0f30c5a0fb24e1fe0",
};

const workspaceId = "11111111-1111-4111-8111-111111111111";
const scopeId = "22222222-2222-4222-8222-222222222222";
const childScopeId = "33333333-3333-4333-8333-333333333333";
const leaseId = "44444444-4444-4444-8444-444444444444";
const resourceId = `worktree:${childScopeId}`;

const grant = (prefix = "") => ({ resource_id: resourceId, prefix });
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function scope(): JsonValue {
  return {
    contract_type: "execution_scope",
    schema_version: "1.0.0",
    scope_id: scopeId,
    workspace_id: workspaceId,
    operation_id: "agentops:op-42",
    candidate_id: "candidate-a",
    parent_scope_id: "",
    effects: ["execute", "mutate", "observe", "verify"],
    resource_reads: [grant()],
    resource_writes: [grant("src")],
    resource_denies: [grant(".origins")],
    network_mode: "allowlist",
    network_hosts: ["api.example.com", "support.example.com"],
    environment_names: ["LANG", "PATH"],
    process_execution_allowed: true,
    persistent_process_allowed: false,
    delegation_allowed: true,
    delegated_remote_authority: false,
    issued_at: "2026-08-09T12:00:00Z",
    updated_at: "2026-08-09T12:00:00Z",
    expires_at: "2026-08-09T14:00:00Z",
    revision: 1,
  };
}

function childScope(): JsonValue {
  return {
    ...(scope() as Record<string, JsonValue>),
    scope_id: childScopeId,
    candidate_id: "candidate-b",
    parent_scope_id: scopeId,
    effects: ["execute", "observe"],
    resource_reads: [grant("src")],
    resource_writes: [],
    resource_denies: [grant(".origins")],
    network_hosts: ["support.example.com"],
    environment_names: ["LANG"],
    delegation_allowed: false,
    expires_at: "2026-08-09T13:30:00Z",
  };
}

function lease(): JsonValue {
  return {
    contract_type: "capability_lease",
    schema_version: "1.0.0",
    lease_id: leaseId,
    scope_id: scopeId,
    workspace_id: workspaceId,
    parent_lease_id: "",
    capability_id: "origins.process.run",
    holder_kind: "session",
    holder_id: "candidate-a-build",
    effects: ["execute", "observe"],
    resource_reads: [grant("src")],
    resource_writes: [],
    resource_denies: [grant(".origins")],
    network_mode: "deny",
    network_hosts: [],
    environment_names: ["LANG"],
    persistent_process_allowed: false,
    delegated_remote_authority: false,
    approval_authority: "jaydumisuni/Hunter-AgentOps",
    approval_id: "approval-42",
    approval_digest: "0".repeat(64),
    proposal_digest: "1".repeat(64),
    state: "active",
    fence: 1,
    issued_at: "2026-08-09T12:05:00Z",
    updated_at: "2026-08-09T12:05:00Z",
    expires_at: "2026-08-09T13:00:00Z",
    revision: 1,
  };
}

test("valid contract corpus", async () => {
  for (const item of fixtures.valid) {
    assert.equal(validateContract(item.contract), item.contract, item.name);
    const canonical = canonicalJson(item.contract);
    assert.equal(canonical.includes(": "), false, item.name);
    assert.equal(canonical.includes(", "), false, item.name);
    const reparsed = JSON.parse(canonical) as JsonValue;
    assert.equal(await contractSha256(item.contract), await contractSha256(reparsed), item.name);
  }
});

test("invalid contract corpus", () => {
  for (const item of fixtures.invalid) {
    assert.throws(
      () => validateContract(item.contract),
      (error: unknown) => error instanceof ContractError && error.code === item.expected_error,
      item.name,
    );
  }
});

test("unicode canonicalization preserves text", () => {
  assert.equal(
    canonicalJson({ z: "Zambia", a: "Origins — 工厂" }),
    '{"a":"Origins — 工厂","z":"Zambia"}',
  );
});

test("candidate authority scope and lease validate and hash", async () => {
  assert.equal(validateAuthorityContract(scope()).contract_type, "execution_scope");
  assert.equal(validateAuthorityContract(lease()).contract_type, "capability_lease");
  validateLeaseWithinScope(lease(), scope());
  assert.equal(await authoritySha256(scope()), authorityHashes.workspace_candidate_scope);
  assert.equal(await authoritySha256(lease()), authorityHashes.bounded_process_lease);
});

test("shared authority fixture corpus", async () => {
  for (const item of authorityFixtures.valid) {
    validateAuthorityContract(item.contract);
    assert.equal(await authoritySha256(item.contract), authorityHashes[item.name], item.name);
  }
  for (const item of authorityFixtures.invalid) {
    assert.throws(
      () => validateAuthorityContract(item.contract),
      (error: unknown) => error instanceof ContractError && error.code === item.expected_error,
      item.name,
    );
  }
});

test("shared authority invalid-contract attack corpus", () => {
  for (const attack of adversarialFixtures.invalid_contracts) {
    const value = clone(attack.base === "scope" ? scope() : lease()) as Record<string, JsonValue>;
    Object.assign(value, clone(attack.set));
    assert.throws(
      () => validateAuthorityContract(value),
      (error: unknown) => error instanceof ContractError && error.code === attack.expected_error,
      attack.name,
    );
  }
});

test("shared authority relation attack corpus", () => {
  for (const attack of adversarialFixtures.relations) {
    if (attack.relation === "child_scope") {
      const parent = clone(scope()) as Record<string, JsonValue>;
      const child = clone(childScope()) as Record<string, JsonValue>;
      Object.assign(parent, clone(attack.parent_set ?? {}));
      Object.assign(child, clone(attack.child_set ?? {}));
      assert.throws(
        () => validateChildScope(child, parent),
        (error: unknown) => error instanceof ContractError && error.code === attack.expected_error,
        attack.name,
      );
    } else {
      const parentScope = clone(scope()) as Record<string, JsonValue>;
      const candidateLease = clone(lease()) as Record<string, JsonValue>;
      Object.assign(parentScope, clone(attack.scope_set ?? {}));
      Object.assign(candidateLease, clone(attack.lease_set ?? {}));
      assert.throws(
        () => validateLeaseWithinScope(candidateLease, parentScope),
        (error: unknown) => error instanceof ContractError && error.code === attack.expected_error,
        attack.name,
      );
    }
  }
});

test("child authority can narrow but cannot drop a parent deny", () => {
  validateChildScope(childScope(), scope());
  const child = childScope() as Record<string, JsonValue>;
  child.resource_denies = [];
  assert.throws(
    () => validateChildScope(child, scope()),
    (error: unknown) => error instanceof ContractError && error.code === "SCOPE_ESCALATION",
  );
});

test("authority lists must remain sorted and unique", () => {
  const value = scope() as Record<string, JsonValue>;
  value.network_hosts = ["support.example.com", "api.example.com"];
  assert.throws(
    () => validateAuthorityContract(value),
    (error: unknown) => error instanceof ContractError && error.code === "UNSORTED_OR_DUPLICATE_LIST",
  );
});

test("lease cannot switch network authority class", () => {
  const value = lease() as Record<string, JsonValue>;
  value.network_mode = "delegated_remote";
  value.network_hosts = ["support.example.com"];
  value.delegated_remote_authority = true;
  assert.throws(
    () => validateLeaseWithinScope(value, scope()),
    (error: unknown) => error instanceof ContractError && error.code === "SCOPE_ESCALATION",
  );
});
