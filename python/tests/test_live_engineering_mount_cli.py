from __future__ import annotations

from pathlib import Path


def test_live_engineering_mount_cli_compiles_and_uses_production_constructor() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "tools" / "run_live_engineering_mount.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "LiveEngineeringMount.production(client)" in source
    assert "subprocess" not in source
    assert '"--repository-id"' in source
    assert '"--config"' in source
