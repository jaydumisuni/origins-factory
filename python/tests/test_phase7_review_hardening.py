from __future__ import annotations

import inspect

from origins_integration.engineering import OriginsClient


def test_phase7_repository_diff_default_uses_daemon_maximum() -> None:
    parameter = inspect.signature(OriginsClient.get_repository_diff).parameters["limit"]
    assert parameter.default == 8 * 1024 * 1024
