#!/usr/bin/env python3
from __future__ import annotations

import os

from prove_phase7_live_owner_mcp import main


if __name__ == "__main__":
    os.environ["ORIGINS_PHASE7_STRICT"] = "1"
    raise SystemExit(main())
