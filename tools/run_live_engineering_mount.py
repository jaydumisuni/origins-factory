from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from origins_integration.engineering import BridgeError, OriginsClient  # noqa: E402
from origins_integration.live_mount import LiveEngineeringMount  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only Origins live engineering owner-stack smoke."
    )
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--files", default="")
    parser.add_argument("--review-mode", default="pull_request")
    args = parser.parse_args()

    files = tuple(item.strip() for item in args.files.split(",") if item.strip())
    try:
        client = OriginsClient.from_env()
        mount = LiveEngineeringMount.production(client)
        receipt = mount.run(
            args.repository_id,
            config=args.config,
            files=files,
            review_mode=args.review_mode,
        )
    except BridgeError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "live_engineering_proven": False,
                },
                separators=(",", ":"),
            )
        )
        return 2

    print(
        json.dumps(
            {"ok": True, "receipt": receipt.as_dict()},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if receipt.live_engineering_proven else 3


if __name__ == "__main__":
    raise SystemExit(main())
