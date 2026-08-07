import { readFile } from "node:fs/promises";
import { canonicalJson, ContractError, contractSha256, type JsonValue, validateContract } from "./contracts.ts";

const path = process.argv[2];
if (!path) {
  console.error("usage: node contracts-cli.ts <contract.json>");
  process.exit(2);
}

try {
  const text = await readFile(path, "utf8");
  let value: JsonValue;
  try {
    value = JSON.parse(text) as JsonValue;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.log(JSON.stringify({ ok: false, error_code: "MALFORMED_JSON", error: message }));
    process.exit(1);
  }

  validateContract(value);
  console.log(
    JSON.stringify({
      ok: true,
      canonical_json: canonicalJson(value),
      sha256: await contractSha256(value),
    }),
  );
} catch (error) {
  if (error instanceof ContractError) {
    console.log(JSON.stringify({ ok: false, error_code: error.code, error: error.message }));
    process.exit(1);
  }
  const message = error instanceof Error ? error.message : String(error);
  console.log(JSON.stringify({ ok: false, error_code: "READ_ERROR", error: message }));
  process.exit(2);
}
