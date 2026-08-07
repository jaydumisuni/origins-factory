from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from origins_contracts import ContractError, canonical_json, contract_sha256, validate_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rust-bin", required=True, type=Path)
    parser.add_argument("--typescript-cli", type=Path)
    args = parser.parse_args()

    fixtures = json.loads((ROOT / "contracts" / "fixtures.json").read_text(encoding="utf-8"))
    cases = [(True, case) for case in fixtures["valid"]] + [(False, case) for case in fixtures["invalid"]]

    failures: list[str] = []
    for expected_valid, case in cases:
        name = case["name"]
        contract = case["contract"]
        python_result = evaluate_python(contract)
        rust_result = evaluate_cli([str(args.rust_bin)], contract, "Rust")
        typescript_result = (
            evaluate_cli(["node", str(args.typescript_cli)], contract, "TypeScript")
            if args.typescript_cli
            else None
        )
        results = [("Python", python_result), ("Rust", rust_result)]
        if typescript_result is not None:
            results.append(("TypeScript", typescript_result))

        invalid_result = False
        for runtime, result in results:
            if result.get("ok") != expected_valid:
                failures.append(f"{name}: {runtime} validity mismatch: {result}")
                invalid_result = True
        if invalid_result:
            continue

        if expected_valid:
            canonical = python_result["canonical_json"]
            digest = python_result["sha256"]
            for runtime, result in results[1:]:
                if canonical != result.get("canonical_json"):
                    failures.append(f"{name}: Python/{runtime} canonical JSON differs")
                if digest != result.get("sha256"):
                    failures.append(f"{name}: Python/{runtime} SHA-256 differs")
        else:
            expected_error = case["expected_error"]
            for runtime, result in results:
                if result.get("error_code") != expected_error:
                    failures.append(
                        f"{name}: {runtime} error {result.get('error_code')} != {expected_error}"
                    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    runtime_count = 3 if args.typescript_cli else 2
    print(f"PASS: {len(cases)} Origins contract cases across {runtime_count} runtimes")
    return 0


def evaluate_python(contract: dict) -> dict:
    try:
        validate_contract(contract)
        return {
            "ok": True,
            "canonical_json": canonical_json(contract),
            "sha256": contract_sha256(contract),
        }
    except ContractError as error:
        return {"ok": False, "error_code": error.code, "error": str(error)}


def evaluate_cli(command: list[str], contract: dict, runtime: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(contract, handle, ensure_ascii=False, separators=(",", ":"))
        path = Path(handle.name)
    try:
        completed = subprocess.run(
            [*command, str(path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            return {
                "ok": False,
                "error_code": f"INVALID_{runtime.upper()}_OUTPUT",
                "error": str(error),
                "stdout": completed.stdout[-1000:],
                "stderr": completed.stderr[-1000:],
            }
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "error_code": f"INVALID_{runtime.upper()}_OUTPUT",
                "error": "CLI output root was not an object",
            }
        return payload
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
