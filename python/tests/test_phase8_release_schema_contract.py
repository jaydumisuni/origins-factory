from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _schema() -> dict[str, object]:
    return json.loads((ROOT / "release" / "origins-release-v1.schema.json").read_text(encoding="utf-8"))


def test_phase8_schema_is_candidate_only_and_release_shaped() -> None:
    schema = _schema()
    properties = schema["properties"]

    assert properties["status"] == {"const": "candidate"}
    release_pattern = re.compile(properties["release_id"]["pattern"])
    assert release_pattern.fullmatch("origins-factory-0.1.0-linux-x86_64-530327c600a8")
    assert release_pattern.fullmatch("origins-factory-0.1.0-linux-x86_64-not-a-sha") is None
    assert release_pattern.fullmatch("accepted-origins-factory-0.1.0-linux-x86_64-530327c600a8") is None

    comment = str(schema.get("$comment", ""))
    assert "Structural validation is necessary but not sufficient" in comment
    assert "cross-field provenance" in comment


def test_phase8_schema_artifact_set_matches_verifier_boundary() -> None:
    schema = _schema()
    artifacts = schema["properties"]["artifacts"]

    assert artifacts["minItems"] == 3
    assert artifacts["maxItems"] == 3
    item = artifacts["items"]
    assert set(item["properties"]["id"]["enum"]) == {"originsd", "python-plane", "workspace"}

    expected_pairs = {
        ("originsd", "native-binary"),
        ("python-plane", "python-wheel"),
        ("workspace", "static-web-bundle"),
    }
    actual_pairs: set[tuple[str, str]] = set()
    for requirement in artifacts["allOf"]:
        assert requirement["minContains"] == 1
        assert requirement["maxContains"] == 1
        contained = requirement["contains"]
        props = contained["properties"]
        actual_pairs.add((props["id"]["const"], props["kind"]["const"]))
    assert actual_pairs == expected_pairs

    path_pattern = re.compile(item["properties"]["path"]["pattern"])
    for safe in ("bin/originsd", "python/origins_contracts-0.1.0-py3-none-any.whl", "workspace/workspace.tar.gz"):
        assert path_pattern.fullmatch(safe)
    for unsafe in ("/absolute", "../escape", "bin/../escape", ".", "", "bin\\originsd"):
        assert path_pattern.fullmatch(unsafe) is None
