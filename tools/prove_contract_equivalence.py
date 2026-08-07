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
    args = parser.parse_args()

    fixtures = json.loads((ROOT / "contracts" / "fixtures.json").read_text(encoding="utf-8"))
    cases = [(True, case) for case in fixtures["valid"]] + [(False, case) for case in fixtures["invalid"]]

    failures: list[str] = []
    for expected_valid, case in cases:
        name = case["name"]
        contract = case["contract"]
        python_result = evaluate_python(contract)
        rust_result = evaluate_rust(args.rust_bin, contract)

        if python_result["ok"] != expected_valid:
            failures.append(f"{name}: Python validity mismatch: {python_result}")
            continue
        if rust_result.get("ok") != expected_valid:
            failures.append(f"{name}: Rust validity mismatch: {rust_result}")
            continue

        if expected_valid:
            if python_result["canonical_json"] != rust_result.get("canonical_json"):
                failures.append(f"{name}: canonical JSON differs")
            if python_result["sha256"] != rust_result.get("sha256"):
                failures.append(f"{name}: SHA-256 differs")
        else:
            expected_error = case["expected_error"]
            if python_result.get("error_code") != expected_error:
                failures.append(f"{name}: Python error {python_result.get('error_code')} != {expected_error}")
            if rust_result.get("error_code") != expected_error:
                failures.append(f"{name}: Rust error {rust_result.get('error_code')} != {expected_error}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"PASS: {len(cases)} cross-language Origins contract cases")
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


def evaluate_rust(binary: Path, contract: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(contract, handle, ensure_ascii=False, separators=(",", ":"))
        path = Path(handle.name)
    try:
        completed = subprocess.run(
            [str(binary), str(path)],
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
                "error_code": "INVALID_RUST_OUTPUT",
                "error": str(error),
                "stdout": completed.stdout[-1000:],
                "stderr": completed.stderr[-1000:],
            }
        return payload
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
