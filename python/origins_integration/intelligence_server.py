from __future__ import annotations

import argparse
import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlsplit

from .intelligence_runtime import IntelligenceMountError, IntelligenceRuntime

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 48710
MAX_BODY_BYTES = 1024 * 1024


class IntelligenceServerError(RuntimeError):
    """Raised when the Phase-4 semantic service cannot start safely."""


class IntelligenceHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        runtime: IntelligenceRuntime,
        local_token: str,
    ) -> None:
        super().__init__(server_address, IntelligenceRequestHandler)
        self.runtime = runtime
        self.local_token = local_token


class IntelligenceRequestHandler(BaseHTTPRequestHandler):
    server: IntelligenceHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        path = urlsplit(self.path).path
        if path == "/v1/health":
            self._json(HTTPStatus.OK, _public_health(self.server.runtime.health()))
            return
        if not self._authorized():
            self._unauthorized()
            return
        routes: dict[str, Callable[[], dict[str, object]]] = {
            "/v1/operations": self.server.runtime.operations,
            "/v1/approvals": self.server.runtime.approvals,
            "/v1/providers": self.server.runtime.providers,
        }
        action = routes.get(path)
        if action is None:
            self._not_found()
            return
        self._invoke(action)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        if not self._authorized():
            self._unauthorized()
            return
        path = urlsplit(self.path).path
        routes: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
            "/v1/operations": self.server.runtime.run_agentops,
            "/v1/approvals": self.server.runtime.create_approval,
            "/v1/approvals/decision": self.server.runtime.decide_approval,
            "/v1/capability-proposals": self.server.runtime.compile_capability,
            "/v1/engineering/attempt": self.server.runtime.engineering_attempt,
        }
        action = routes.get(path)
        if action is None:
            self._not_found()
            return
        payload = self._body_json()
        if payload is None:
            return
        self._invoke(lambda: action(payload))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        safe_request = self.requestline.replace("\r", " ").replace("\n", " ")[:500]
        message = format % args
        print(f"origins-intelligence {self.client_address[0]} {safe_request} {message}")

    def _invoke(self, action: Callable[[], dict[str, object]]) -> None:
        try:
            payload = action()
        except IntelligenceMountError as exc:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error_code": "OWNER_UNAVAILABLE", "error": str(exc)},
            )
        except (TypeError, ValueError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error_code": "INVALID_REQUEST", "error": str(exc)},
            )
        except Exception as exc:  # owner exception classes are external to this package
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "ok": False,
                    "error_code": "OWNER_FAILURE",
                    "error": f"owning runtime rejected or failed request: {type(exc).__name__}",
                },
            )
        else:
            self._json(HTTPStatus.OK, payload)

    def _body_json(self) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error_code": "INVALID_BODY", "error": "invalid Content-Length"},
            )
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {
                    "ok": False,
                    "error_code": "BODY_TOO_LARGE",
                    "error": f"JSON body limit is {MAX_BODY_BYTES} bytes",
                },
            )
            return None
        if length == 0:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error_code": "INVALID_BODY", "error": "JSON object body is required"},
            )
            return None
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error_code": "INVALID_BODY", "error": "body must be UTF-8 JSON"},
            )
            return None
        if not isinstance(value, dict):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error_code": "INVALID_BODY", "error": "JSON body must be an object"},
            )
            return None
        return value

    def _authorized(self) -> bool:
        expected = self.server.local_token
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        token = supplied[len(prefix) :] if supplied.startswith(prefix) else ""
        return bool(expected) and hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))

    def _unauthorized(self) -> None:
        self._json(
            HTTPStatus.UNAUTHORIZED,
            {"ok": False, "error_code": "UNAUTHORIZED", "error": "valid Origins local bearer token required"},
        )

    def _not_found(self) -> None:
        self._json(
            HTTPStatus.NOT_FOUND,
            {"ok": False, "error_code": "NOT_FOUND", "error": "route not found"},
        )

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def serve(
    *,
    host: str = DEFAULT_BIND,
    port: int = DEFAULT_PORT,
    runtime: IntelligenceRuntime | None = None,
    local_token: str | None = None,
) -> IntelligenceHTTPServer:
    if not _is_loopback_literal(host):
        raise IntelligenceServerError("origins-intelligence refuses non-loopback bind addresses")
    token = (local_token if local_token is not None else os.environ.get("ORIGINS_LOCAL_TOKEN", "")).strip()
    if not token:
        raise IntelligenceServerError("ORIGINS_LOCAL_TOKEN is required")
    return IntelligenceHTTPServer((host, port), runtime or IntelligenceRuntime.from_env(), token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Origins Factory Phase-4 intelligence owner plane")
    parser.add_argument("--host", default=os.environ.get("ORIGINS_INTELLIGENCE_HOST", DEFAULT_BIND))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ORIGINS_INTELLIGENCE_PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)
    server = serve(host=args.host, port=args.port)
    host, port = server.server_address[:2]
    print(f"origins-intelligence ready on http://{host}:{port}")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _public_health(payload: dict[str, object]) -> dict[str, object]:
    owners = payload.get("owners")
    public_owners: dict[str, object] = {}
    if isinstance(owners, dict):
        for name, value in owners.items():
            if isinstance(value, dict):
                public_owners[str(name)] = {
                    "configured": bool(value.get("configured", False)),
                    "available": bool(value.get("available", False)),
                }
    return {
        "ok": payload.get("ok") is True,
        "service": str(payload.get("service", "origins-intelligence")),
        "api_version": str(payload.get("api_version", "v1")),
        "owners": public_owners,
        "mechanical_originsd_configured": bool(payload.get("mechanical_originsd_configured", False)),
    }


def _is_loopback_literal(host: str) -> bool:
    value = host.strip().lower()
    return value in {"127.0.0.1", "::1", "localhost"}


if __name__ == "__main__":
    raise SystemExit(main())
