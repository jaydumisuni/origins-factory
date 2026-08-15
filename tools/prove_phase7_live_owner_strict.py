#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REVIEW_FILES = ["capability.py", "tests/test_capability.py"]


def _load_base() -> ModuleType:
    path = Path(__file__).with_name("prove_phase7_live_owner.py")
    spec = importlib.util.spec_from_file_location("origins_phase7_live_owner_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load Phase 7 owner proof: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _strict_init_repo(module: ModuleType, path: Path, *, initial_value: str, replacement_value: str) -> None:
    path.mkdir(parents=True)
    (path / "capability.py").write_text(
        "def capability() -> str:\n" f"    return {initial_value!r}\n",
        encoding="utf-8",
    )

    tests = path / "tests"
    tests.mkdir()
    (tests / "test_capability.py").write_text(
        "from capability import capability\n\n"
        "def test_capability() -> None:\n"
        f"    assert capability() == {initial_value!r}\n",
        encoding="utf-8",
    )

    (path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "origins-phase7-proof"\n'
        'version = "0.0.0"\n'
        'requires-python = ">=3.10"\n',
        encoding="utf-8",
    )
    (path / "README.md").write_text(
        "# Origins Phase 7 disposable capability proof\n\n"
        "This repository exists only for exact-owner capability-evolution proof.\n",
        encoding="utf-8",
    )
    workflow = path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text(
        "name: proof\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.12'\n"
        "      - run: python -m pytest -q\n",
        encoding="utf-8",
    )

    module._run(["git", "init", "-b", "main"], cwd=path)
    module._run(["git", "config", "user.name", "Origins Phase 7 Proof"], cwd=path)
    module._run(["git", "config", "user.email", "origins-phase7-proof@invalid.local"], cwd=path)
    module._run(["git", "add", "."], cwd=path)
    module._run(["git", "commit", "-m", "proof baseline"], cwd=path)

    plan = {
        "operations": [
            {
                "path": "capability.py",
                "action": "replace",
                "old": f"return {initial_value!r}",
                "new": f"return {replacement_value!r}",
                "required": True,
            },
            {
                "path": "tests/test_capability.py",
                "action": "replace",
                "old": f"assert capability() == {initial_value!r}",
                "new": f"assert capability() == {replacement_value!r}",
                "required": True,
            },
        ],
        "reason": "Phase 7 disposable capability proof",
        "require_review": True,
    }
    (path / "upgrade-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scoped(payload: dict[str, object]) -> dict[str, object]:
    scoped = dict(payload)
    scoped["files"] = list(REVIEW_FILES)
    return scoped


def main() -> int:
    module = _load_base()

    def strict_init_repo(path: Path, *, initial_value: str, replacement_value: str) -> None:
        _strict_init_repo(
            module,
            path,
            initial_value=initial_value,
            replacement_value=replacement_value,
        )

    module._init_repo = strict_init_repo

    original_create_engineering_approval = module.Phase7Runtime.create_engineering_approval
    original_implement_candidate = module.Phase7Runtime.implement_candidate

    def create_engineering_approval(
        self: object,
        evolution_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return original_create_engineering_approval(self, evolution_id, _scoped(payload))

    def implement_candidate(
        self: object,
        evolution_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return original_implement_candidate(self, evolution_id, _scoped(payload))

    module.Phase7Runtime.create_engineering_approval = create_engineering_approval
    module.Phase7Runtime.implement_candidate = implement_candidate

    original_run_evolution = module._run_evolution

    def run_evolution(**kwargs: object) -> dict[str, object]:
        # Exercise the changed repository through its actual test suite for the
        # canary rather than using an ad-hoc assertion.
        client = kwargs["client"]
        original_submit_process = client.submit_process

        def submit_process(**process_kwargs: object) -> dict[str, object]:
            process_kwargs["executable"] = "python3"
            process_kwargs["args"] = ["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
            return original_submit_process(**process_kwargs)

        client.submit_process = submit_process
        try:
            return original_run_evolution(**kwargs)
        finally:
            client.submit_process = original_submit_process

    module._run_evolution = run_evolution
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
