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
  validateProviderBinding,
  validateScopeCurrent,
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
  valid: Array<{ name: string; sha256: string; contract: JsonValue }>;
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
  relations: Array<Record<string, JsonValue> & { name: string; relation: string; expected_error: string }>;
};

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const baseScope = (): Record<string, JsonValue> => clone(authorityFixtures.valid[0].contract) as Record<string, JsonValue>;
const baseLease = (): Record<string, JsonValue> => clone(authorityFixtures.valid[1].contract) as Record<string, JsonValue>;

function childScope(): Record<string, JsonValue> {
  const parent = baseScope();
  return {
    ...parent,
    scope_id: "66666666-6666-4666-8666-666666666666",
    candidate_id: "candidate-a",
    parent_scope_id: parent.scope_id,
    effects: ["execute", "observe"],
    resource_reads: [
      { resource_id: "worktree:33333333-3333-4333-8333-333333333333", prefix: "src" },
    ],
    resource_writes: [],
    network_endpoints: [{ protocol: "https", host: "support.example.com", port: 443 }],
    environment_names: ["LANG"],
    delegation_allowed: false,
    issued_at: "2026-08-09T12:10:00Z",
    updated_at: "2026-08-09T12:10:00Z",
    expires_at: "2026-08-09T13:30:00Z",
  };
}

function expectCode(fn: () => unknown, code: string, name?: string): void {
  assert.throws(
    fn,
    (error: unknown) => error instanceof ContractError && error.code === code,
    name,
  );
}

async function expectAsyncCode(fn: () => Promise<unknown>, code: string, name?: string): Promise<void> {
  await assert.rejects(
    fn,
    (error: unknown) => error instanceof ContractError && error.code === code,
    name,
  );
}

test("valid contract corpus", async () => {
  for (const item of fixtures.valid) {
    assert.equal(validateContract(item.contract), item.contract, item.name);
    const canonical = canonicalJson(item.contract);
    assert.equal(canonical.includes(": "), false, item.name);
    assert.equal(canonical.includes(", "), false, item.name);
    assert.equal(await contractSha256(item.contract), await contractSha256(JSON.parse(canonical) as JsonValue), item.name);
  }
});

test("invalid contract corpus", () => {
  for (const item of fixtures.invalid) expectCode(() => validateContract(item.contract), item.expected_error, item.name);
});

test("unicode canonicalization preserves text", () => {
  assert.equal(canonicalJson({ z: "Zambia", a: "Origins — 工厂" }), '{"a":"Origins — 工厂","z":"Zambia"}');
});

test("authority v1.1 shared valid corpus and canonical hashes", async () => {
  for (const item of authorityFixtures.valid) {
    validateAuthorityContract(item.contract);
    assert.equal(await authoritySha256(item.contract), item.sha256, item.name);
  }
  validateLeaseWithinScope(baseLease(), baseScope());
});

test("authority v1.1 shared invalid corpus", () => {
  for (const item of authorityFixtures.invalid) {
    expectCode(() => validateAuthorityContract(item.contract), item.expected_error, item.name);
  }
});

test("shared authority invalid-contract attack corpus", () => {
  for (const attack of adversarialFixtures.invalid_contracts) {
    const value = attack.base === "scope" ? baseScope() : baseLease();
    Object.assign(value, clone(attack.set));
    expectCode(() => validateAuthorityContract(value), attack.expected_error, attack.name);
  }
});

test("shared authority relation attack corpus", async () => {
  for (const attack of adversarialFixtures.relations) {
    if (attack.relation === "child_scope") {
      const parent = baseScope();
      const child = childScope();
      Object.assign(parent, clone((attack.parent_set ?? {}) as Record<string, JsonValue>));
      Object.assign(child, clone((attack.child_set ?? {}) as Record<string, JsonValue>));
      expectCode(() => validateChildScope(child, parent), attack.expected_error, attack.name);
    } else if (attack.relation === "lease_scope") {
      const scope = baseScope();
      const lease = baseLease();
      Object.assign(scope, clone((attack.scope_set ?? {}) as Record<string, JsonValue>));
      Object.assign(lease, clone((attack.lease_set ?? {}) as Record<string, JsonValue>));
      expectCode(() => validateLeaseWithinScope(lease, scope), attack.expected_error, attack.name);
    } else if (attack.relation === "scope_current") {
      const presented = baseScope();
      const current = baseScope();
      Object.assign(presented, clone((attack.presented_set ?? {}) as Record<string, JsonValue>));
      Object.assign(current, clone((attack.current_set ?? {}) as Record<string, JsonValue>));
      await expectAsyncCode(() => validateScopeCurrent(presented, current), attack.expected_error, attack.name);
    } else if (attack.relation === "provider_binding") {
      expectCode(
        () => validateProviderBinding(
          baseLease(),
          String(attack.provider_id),
          String(attack.provider_manifest_digest),
          Number(attack.provider_generation),
        ),
        attack.expected_error,
        attack.name,
      );
    } else {
      assert.fail(`unknown relation ${String(attack.relation)}`);
    }
  }
});

test("SEC-002 root candidate may bind once", () => {
  const root = baseScope();
  const child = childScope();
  validateChildScope(child, root);

  const boundParent = childScope();
  boundParent.delegation_allowed = true;
  const grandchild = clone(boundParent);
  grandchild.scope_id = "77777777-7777-4777-8777-777777777777";
  grandchild.parent_scope_id = boundParent.scope_id;
  grandchild.issued_at = "2026-08-09T12:20:00Z";
  grandchild.updated_at = "2026-08-09T12:20:00Z";
  validateChildScope(grandchild, boundParent);

  grandchild.candidate_id = "candidate-b";
  expectCode(() => validateChildScope(grandchild, boundParent), "SCOPE_ESCALATION");
});

test("SEC-003 exact provider binding succeeds only for approved provider generation", () => {
  validateProviderBinding(baseLease(), "origins.process.local", "2".repeat(64), 1);
  expectCode(
    () => validateProviderBinding(baseLease(), "origins.process.local", "2".repeat(64), 2),
    "PROVIDER_SUBSTITUTION",
  );
});

test("SEC-004 current scope generation is exact", async () => {
  const current = baseScope();
  await validateScopeCurrent(current, current);
  const stale = clone(current);
  current.fence = 2;
  current.revision = 2;
  current.updated_at = "2026-08-09T12:01:00Z";
  await expectAsyncCode(() => validateScopeCurrent(stale, current), "STALE_SCOPE");
});

test("SEC-005 protocol and port are part of endpoint authority", () => {
  const child = childScope();
  child.network_endpoints = [{ protocol: "http", host: "support.example.com", port: 443 }];
  expectCode(() => validateChildScope(child, baseScope()), "SCOPE_ESCALATION");

  const bad = baseScope();
  bad.network_endpoints = [{ protocol: "https", host: "support.example.com", port: 0 }];
  expectCode(() => validateAuthorityContract(bad), "INVALID_NETWORK_PORT");
});
