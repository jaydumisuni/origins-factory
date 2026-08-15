from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from websockets.sync.client import connect

PROOF_TOKEN = "phase6-render-proof"
WRITE_REASON = "PHASE6_DEVICE_WRITE_NOT_AUTHORIZED"
LINK_REASON = "AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE"
HUAWEI_REVISION = "fd3f7bb1587b65faaa7d37e0057683dcb07975ed"
XRAY_REVISION = "34feb55ab937fa865726cbb22c44b09b52084114"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until(operation: Callable[[], Any], *, timeout: float = 20.0) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = operation()
            if value:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)
    if last_error:
        raise RuntimeError(f"timed out waiting for proof condition: {last_error}") from last_error
    raise RuntimeError("timed out waiting for proof condition")


def encode_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def send_json(self, status: int, value: Any) -> None:
        body = encode_json(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/health":
            return self.send_json(
                200,
                {
                    "ok": True,
                    "service": "origins-phase6-proof-fixture",
                    "api_version": "v1",
                    "device_write_available": False,
                    "huawei_gateway": {"available": True},
                    "xray_bundle": {"configured": True},
                },
            )
        if self.headers.get("Authorization") != f"Bearer {PROOF_TOKEN}":
            return self.send_json(401, {"error": "UNAUTHORIZED"})
        if self.path != "/v1/device":
            return self.send_json(404, {"error": "NOT_FOUND"})
        return self.send_json(200, device_projection())


class FixtureServer:
    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "FixtureServer":
        self.thread.start()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def device_projection() -> dict[str, Any]:
    return {
        "phase": 6,
        "mode": "device_read_only",
        "gateway": {
            "owner": "techguytool-huawei",
            "owner_revision_recovered": HUAWEI_REVISION,
            "available": True,
            "gateway": {
                "health": {"status": "ready", "device_authority": "none", "xray_authority": "read_only"},
                "doctor": {"healthy": True, "recovering_operation_sessions": 1},
                "snapshot": {
                    "physical_sessions": [
                        {
                            "session_id": "phase6-device-session-proof",
                            "fingerprint_sha256": "1" * 64,
                            "state": "active",
                            "recovery_count": 2,
                        }
                    ],
                    "operation_sessions": [
                        {
                            "operation_id": "phase6-gateway-operation-proof",
                            "request_sha256": "2" * 64,
                            "stage": "evidence_collection",
                            "status": "recovering",
                            "recovery_count": 2,
                        }
                    ],
                },
                "journal": {"journal_valid": True},
            },
            "endpoint_observations": [
                {
                    "observation_id": "phase6-endpoint-proof",
                    "transport": "fastboot",
                    "mode": "normal_fastboot",
                    "endpoint_key": "usb:vog",
                    "observed_at": "2026-08-15T06:00:00Z",
                }
            ],
            "contracts": {
                "device_twin": [{"contract": {"payload": {"twin_state": "pre_operation", "verification_status": "certified", "write_allowed": False}}}],
                "device_evidence": [{"contract": {"payload": {"evidence_state": "certified", "write_allowed": False}}}],
                "decision_verdict": [{"contract": {"payload": {"verdict": "ALLOW_READ_ONLY"}}}],
                "mode_lease": [{"contract": {"payload": {"mode": "normal_fastboot", "authority": "verification"}}}],
                "verification_result": [{"contract": {"payload": {"status": "verified", "write_allowed": False}}}],
                "recovery_plan": [{"contract": {"payload": {"state": "in_progress", "current_stage": "evidence_collection", "next_action_code": "VERIFY_EVIDENCE"}}}],
            },
            "write_execution": {"available": False, "reason": WRITE_REASON},
            "agentops_operation_link": {"available": False, "reason": LINK_REASON},
        },
        "xray": {
            "owner": "ttg-device-xray",
            "owner_revision_recovered": XRAY_REVISION,
            "available": True,
            "integrity_verified": True,
            "write_allowed": False,
            "expired": False,
            "manifest": {
                "bundle_schema_version": "2.0",
                "scan_schema_version": "2.0",
                "scan_id": "phase6-ui-proof",
                "write_allowed": False,
            },
            "signature": {
                "status": "UNSIGNED",
                "cryptographically_verified": False,
                "verification_reason": "XRAY_BUNDLE_UNSIGNED",
            },
            "evidence": {
                "certification": {"verdict": "CERTIFIED", "write_allowed": False},
                "profile_match": {"status": "MATCHED", "write_allowed": False},
                "recommended_plan": {"recommendation": "inspect_only", "write_allowed": False},
                "device_identity": {"model": "VOG-L29"},
            },
        },
        "write_execution": {"available": False, "reason": WRITE_REASON},
        "agentops_operation_link": {"available": False, "reason": LINK_REASON},
    }


class Cdp:
    def __init__(self, websocket_url: str):
        self.socket = connect(websocket_url, open_timeout=5, close_timeout=3, max_size=16 * 1024 * 1024)
        self.next_id = 1

    def close(self) -> None:
        self.socket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.socket.recv(timeout=10))
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            result = message.get("result")
            return result if isinstance(result, dict) else {}

    def evaluate(self, expression: str) -> Any:
        response = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        return result.get("value")


def http_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def chrome_target(port: int, page_url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
            targets = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    for target in targets:
        if target.get("type") == "page" and str(target.get("url") or "").startswith(page_url):
            return str(target.get("webSocketDebuggerUrl") or "") or None
    return None


def body_text(cdp: Cdp) -> str:
    return str(cdp.evaluate("document.body ? document.body.innerText : ''") or "")


def click_button(cdp: Cdp, label: str) -> None:
    target = json.dumps(label)
    clicked = cdp.evaluate(
        f"(()=>{{const t={target};const b=[...document.querySelectorAll('button')].find((x)=>x.textContent?.trim()===t);if(!b)return false;b.click();return true;}})()"
    )
    if clicked is not True:
        raise RuntimeError(f"button not found: {label}")


def set_phase6_token(cdp: Cdp) -> None:
    token = json.dumps(PROOF_TOKEN)
    result = cdp.evaluate(
        f"(()=>{{const i=document.querySelector('.phase6-connect input[type=password]');if(!i)return null;const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(i,{token});i.dispatchEvent(new Event('input',{{bubbles:true}}));i.dispatchEvent(new Event('change',{{bubbles:true}}));return i.value;}})()"
    )
    if result != PROOF_TOKEN:
        raise RuntimeError("Phase 6 proof token input did not update")


def screenshot(cdp: Cdp, destination: Path) -> dict[str, Any]:
    response = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = base64.b64decode(str(response.get("data") or ""))
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Chrome screenshot was not PNG")
    destination.write_bytes(data)
    return {"path": str(destination), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def assert_contains(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise RuntimeError(f"rendered XRAY text is missing: {missing}")


def stop_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Phase 6 XRAY surface in isolated real Chrome")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--output-dir", default="/tmp/origins-phase6-workspace-ui-proof")
    args = parser.parse_args()

    repository = Path.cwd().resolve()
    workspace = (repository / args.workspace).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if not Path(args.chrome).is_file():
        raise RuntimeError(f"Chrome executable not found: {args.chrome}")

    profile = Path(tempfile.mkdtemp(prefix="origins-phase6-chrome-"))
    vite: subprocess.Popen[Any] | None = None
    chrome: subprocess.Popen[Any] | None = None
    cdp: Cdp | None = None
    with FixtureServer() as fixture:
        try:
            vite_port = free_port()
            chrome_port = free_port()
            ui_origin = f"http://127.0.0.1:{vite_port}"
            env = os.environ.copy()
            env["VITE_ORIGINS_PHASE6_PROXY_TARGET"] = fixture.origin
            vite = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)],
                cwd=workspace,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            wait_until(lambda: http_ready(ui_origin))
            chrome = subprocess.Popen(
                [
                    args.chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--remote-allow-origins=*",
                    f"--remote-debugging-port={chrome_port}",
                    f"--user-data-dir={profile}",
                    "--window-size=1600,1100",
                    f"{ui_origin}/",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            websocket_url = wait_until(lambda: chrome_target(chrome_port, ui_origin))
            cdp = Cdp(str(websocket_url))
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            wait_until(lambda: "Origins Factory · Phase 6" in body_text(cdp))
            click_button(cdp, "XRAY")
            wait_until(lambda: cdp.evaluate("document.querySelector('.phase6-header h1')?.textContent") == "XRAY")
            set_phase6_token(cdp)
            click_button(cdp, "Connect")
            wait_until(
                lambda: str(cdp.evaluate("document.querySelector('.phase6-status')?.textContent") or "").strip().lower() == "connected"
            )

            rendered = body_text(cdp)
            assert_contains(
                rendered,
                "READ-ONLY AUTHORITY LOCK",
                WRITE_REASON,
                LINK_REASON,
                "phase6-device-session-proof",
                "phase6-gateway-operation-proof",
                "Pre/Post Device Twin",
                "Recovery Plan",
                "SHA-256 VERIFIED",
                "CERTIFIED",
                "VOG-L29",
            )
            if PROOF_TOKEN in rendered:
                raise RuntimeError("fixture bearer leaked into rendered XRAY text")

            buttons = cdp.evaluate("[...document.querySelectorAll('.phase6-console button')].map((b)=>b.textContent?.trim()||'')")
            if not isinstance(buttons, list):
                raise RuntimeError("could not inspect XRAY controls")
            allowed = {"Workspace", "XRAY", "Refresh evidence", "Disconnect"}
            unexpected = sorted({str(value) for value in buttons if str(value) not in allowed})
            if unexpected:
                raise RuntimeError(f"unexpected XRAY action controls: {unexpected}")

            shot = screenshot(cdp, output_dir / "phase6-xray.png")
            proof = {
                "schema_version": "origins.phase6-workspace-ui-proof.v1",
                "proof": "PHASE6_WORKSPACE_UI_OK",
                "source_head": source_head,
                "browser": "system-google-chrome-headless",
                "production_credentials_used": False,
                "fixture_bearer_rendered": False,
                "write_controls_present": False,
                "write_execution_available": False,
                "agentops_gateway_link_available": False,
                "gateway_device_authority": "none",
                "xray_authority": "read_only",
                "xray_integrity_verified": True,
                "screenshot": shot,
            }
            print(json.dumps(proof, sort_keys=True))
        finally:
            if cdp is not None:
                try:
                    cdp.call("Browser.close")
                except Exception:
                    pass
                try:
                    cdp.close()
                except Exception:
                    pass
            stop_process(chrome)
            stop_process(vite)
            shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
