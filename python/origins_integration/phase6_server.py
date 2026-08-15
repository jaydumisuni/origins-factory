from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .device_readonly import (
    DeviceReadOnlyError,
    HuaweiGatewayReadOnlyMount,
    XRayBundleReadOnlyMount,
)


DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 48730


def _require_loopback(host: str) -> str:
    value = str(host or "").strip()
    if value not in {"127.0.0.1", "localhost", "::1"}:
        raise DeviceReadOnlyError("Phase 6 service refuses non-loopback bind addresses")
    return value


def _local_token() -> str:
    token = str(os.environ.get("ORIGINS_LOCAL_TOKEN") or "").strip()
    if not token:
        raise DeviceReadOnlyError("ORIGINS_LOCAL_TOKEN is required")
    return token


class Phase6Service:
    def __init__(
        self,
        *,
        gateway: HuaweiGatewayReadOnlyMount,
        xray: XRayBundleReadOnlyMount | None,
    ) -> None:
        self.gateway = gateway
        self.xray = xray

    @classmethod
    def from_env(cls) -> "Phase6Service":
        return cls(
            gateway=HuaweiGatewayReadOnlyMount.from_env(),
            xray=XRayBundleReadOnlyMount.from_env(),
        )

    def health(self) -> dict[str, Any]:
        gateway_available = False
        try:
            health = self.gateway.health()
            gateway_available = (
                health.get("status") == "ready"
                and health.get("device_authority") == "none"
                and health.get("xray_authority") == "read_only"
            )
        except DeviceReadOnlyError:
            gateway_available = False
        return {
            "ok": True,
            "service": "origins-phase6",
            "api_version": "v1",
            "device_write_available": False,
            "huawei_gateway": {"available": gateway_available},
            "xray_bundle": {"configured": self.xray is not None},
        }

    def gateway_projection(self) -> dict[str, Any]:
        return self.gateway.projection()

    def xray_projection(self) -> dict[str, Any]:
        if self.xray is None:
            return {
                "owner": "ttg-device-xray",
                "available": False,
                "reason": "XRAY_BUNDLE_NOT_CONFIGURED",
                "write_allowed": False,
            }
        return self.xray.projection()

    def device_projection(self) -> dict[str, Any]:
        gateway = self.gateway_projection()
        xray = self.xray_projection()
        return {
            "phase": 6,
            "mode": "device_read_only",
            "gateway": gateway,
            "xray": xray,
            "write_execution": {
                "available": False,
                "reason": "PHASE6_DEVICE_WRITE_NOT_AUTHORIZED",
            },
            "agentops_operation_link": gateway.get(
                "agentops_operation_link",
                {
                    "available": False,
                    "reason": "AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE",
                },
            ),
        }


class Phase6Handler(BaseHTTPRequestHandler):
    server_version = "OriginsPhase6/1"

    @property
    def phase6(self) -> Phase6Service:
        return self.server.phase6  # type: ignore[attr-defined]

    @property
    def local_token(self) -> str:
        return self.server.local_token  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/health":
            return self._send(200, self.phase6.health())
        if not self._authorized():
            return self._send(401, {"error": "UNAUTHORIZED"})
        try:
            if parsed.path == "/v1/device":
                return self._send(200, self.phase6.device_projection())
            if parsed.path == "/v1/huawei/gateway":
                return self._send(200, self.phase6.gateway_projection())
            if parsed.path == "/v1/xray/bundle":
                return self._send(200, self.phase6.xray_projection())
            return self._send(404, {"error": "NOT_FOUND"})
        except DeviceReadOnlyError as exc:
            return self._send(409, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        return self._send(
            405,
            {
                "error": "PHASE6_READ_ONLY",
                "message": "Phase 6 exposes no device-mutating HTTP method",
            },
        )

    def do_PUT(self) -> None:  # noqa: N802
        return self.do_POST()

    def do_PATCH(self) -> None:  # noqa: N802
        return self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        return self.do_POST()

    def _authorized(self) -> bool:
        header = str(self.headers.get("Authorization") or "")
        expected = f"Bearer {self.local_token}"
        return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))

    def _send(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def serve(*, host: str = DEFAULT_BIND, port: int = DEFAULT_PORT) -> None:
    host = _require_loopback(host)
    token = _local_token()
    server = ThreadingHTTPServer((host, int(port)), Phase6Handler)
    server.phase6 = Phase6Service.from_env()  # type: ignore[attr-defined]
    server.local_token = token  # type: ignore[attr-defined]
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Origins Phase 6 device read-only owner mount")
    parser.add_argument("--host", default=os.environ.get("ORIGINS_PHASE6_BIND", DEFAULT_BIND))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ORIGINS_PHASE6_PORT", str(DEFAULT_PORT))),
    )
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
