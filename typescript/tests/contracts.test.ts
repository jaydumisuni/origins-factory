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

const fixtures = JSON.parse(
  await readFile(new URL("../../contracts/fixtures.json", import.meta.url), "utf8"),
) as {
  valid: Array<{ name: string; contract: JsonValue }>;
  invalid: Array<{ name: string; expected_error: string; contract: JsonValue }>;
};

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
