from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
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

PROOF_TOKEN = "phase5-render-proof"
REMOTE_APPLICATION_REASON = "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until(operation: Callable[[], Any], *, timeout: float = 15.0, interval: float = 0.1) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = operation()
            if value:
                return value
        except Exception as exc:  # proof polling intentionally tolerates startup races
            last_error = exc
        time.sleep(interval)
    if last_error:
        raise RuntimeError(f"timed out waiting for proof condition: {last_error}") from last_error
    raise RuntimeError("timed out waiting for proof condition")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def handler_for(kind: str) -> type[BaseHTTPRequestHandler]:
    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def authorized(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {PROOF_TOKEN}"

        def send_json(self, status: int, value: Any) -> None:
            body = json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def require_auth(self) -> bool:
            if self.authorized():
                return True
            self.send_json(401, {"error": "UNAUTHORIZED"})
            return False

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if kind == "phase5" and path == "/v1/health":
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "service": "origins-phase5-proof-fixture",
                        "api_version": "v1",
                        "oracle": {"available": True},
                        "lumi": {"available": True},
                        "oracle_remote": {"configured": True},
                    },
                )
            if not self.require_auth():
                return
            if kind == "phase5":
                if path == "/v1/browser":
                    return self.send_json(
                        200,
                        {
                            "available": True,
                            "service_available": True,
                            "browser_connected": True,
                            "authority": "observe",
                            "owner": "oracle",
                        },
                    )
                if path == "/v1/oracle/node":
                    return self.send_json(
                        200,
                        {
                            "owner": "oracle",
                            "available": True,
                            "node_id": "kratos-HP-290-G4-Microtower-PC",
                            "remote_application_attachment": {
                                "available": False,
                                "reason": REMOTE_APPLICATION_REASON,
                            },
                        },
                    )
                if path == "/v1/lumi":
                    return self.send_json(
                        200,
                        {"available": True, "owner": "lumi", "queue_depth": 0, "status": "ready"},
                    )
            else:
                if path == "/v1/applications":
                    return self.send_json(
                        200,
                        {
                            "applications": [
                                {
                                    "application_id": "builder",
                                    "name": "THETECHGUY Software Builder",
                                    "launchable": True,
                                    "source": "origins.application-registry.v1",
                                    "executable_name": "builder",
                                }
                            ]
                        },
                    )
                if path == "/v1/artifacts":
                    return self.send_json(
                        200,
                        {
                            "artifacts": [
                                {
                                    "artifact_id": "24c49fe5-4d87-4d07-8a06-5b07d106cf95",
                                    "workspace_id": "11111111-1111-4111-8111-111111111111",
                                    "filename": "verified.bin",
                                    "owner": "oracle",
                                    "size_bytes": 4804,
                                    "content_sha256": "33f70ec221efbf0528be397c916670cbd7bea3d9edfc9ba1d1b514adb6ebb2f9",
                                }
                            ]
                        },
                    )
            return self.send_json(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            if not self.require_auth():
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8"))
            path = self.path.split("?", 1)[0]
            if kind == "phase5" and path == "/v1/browser/handoff":
                return self.send_json(200, {"ok": True, "authority": body.get("authority", "observe")})
            if kind == "phase5" and path == "/v1/browser/human-takeover":
                return self.send_json(200, {"ok": True, "authority": "observe", "human_control": True})
            if kind == "phase5" and path == "/v1/oracle/files/retrieve":
                return self.send_json(
                    201,
                    {
                        "owner": "oracle",
                        "node_id": "kratos-HP-290-G4-Microtower-PC",
                        "remote_path": body.get("remote_path"),
                        "bytes_transferred": 4804,
                        "sha256": "33f70ec221efbf0528be397c916670cbd7bea3d9edfc9ba1d1b514adb6ebb2f9",
                        "artifact_candidate": {
                            "path": "/proof/verified.bin",
                            "filename": "verified.bin",
                        },
                    },
                )
            if kind == "phase5" and path == "/v1/lumi/downloads":
                return self.send_json(201, {"id": "proof-task", "status": "queued"})
            if kind == "phase5" and path == "/v1/lumi/artifact-candidates/proof-task":
                return self.send_json(
                    200,
                    {
                        "owner": "lumi",
                        "owner_task_id": "proof-task",
                        "path": "/proof/lumi.bin",
                        "filename": "lumi.bin",
                        "content_type": "application/octet-stream",
                    },
                )
            if kind == "origins" and path.startswith("/v1/applications/") and path.endswith("/launch"):
                return self.send_json(
                    202,
                    {
                        "accepted": True,
                        "replayed": False,
                        "launch": {
                            "launch_id": body.get("launch_id"),
                            "workspace_id": body.get("workspace_id"),
                            "state": "spawned",
                            "node_id": "local",
                        },
                    },
                )
            if kind == "origins" and path == "/v1/artifacts":
                return self.send_json(201, {"registered": True, "reused": False})
            return self.send_json(404, {"error": "NOT_FOUND"})

    return FixtureHandler


class FixtureServer:
    def __init__(self, kind: str):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(kind))
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
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        remote = result.get("result") if isinstance(result.get("result"), dict) else {}
        if remote.get("exceptionDetails"):
            raise RuntimeError(str(remote["exceptionDetails"]))
        return remote.get("value")


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
    expression = json.dumps(label)
    clicked = cdp.evaluate(
        f"(()=>{{const label={expression};const button=[...document.querySelectorAll('button')].find((item)=>item.textContent?.trim()===label);if(!button)return false;button.click();return true;}})()"
    )
    if clicked is not True:
        raise RuntimeError(f"button not found: {label}")


def set_phase5_token(cdp: Cdp) -> None:
    token = json.dumps(PROOF_TOKEN)
    changed = cdp.evaluate(
        f"(()=>{{const input=document.querySelector('.phase5-connect input[type=password]');if(!input)return false;const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,{token});input.dispatchEvent(new Event('input',{{bubbles:true}}));return true;}})()"
    )
    if changed is not True:
        raise RuntimeError("Phase 5 token input was not found")


def screenshot(cdp: Cdp, destination: Path) -> dict[str, Any]:
    result = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = base64.b64decode(str(result.get("data") or ""))
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Chrome screenshot was not PNG")
    destination.write_bytes(data)
    return {"path": str(destination), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def assert_contains(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise RuntimeError(f"rendered Workspace text is missing: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Phase 5 Workspace surfaces in isolated real Chrome")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--output-dir", default="/tmp/origins-phase5-workspace-ui-proof")
    args = parser.parse_args()

    repository = Path.cwd().resolve()
    workspace = (repository / args.workspace).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if not Path(args.chrome).is_file():
        raise RuntimeError(f"Chrome executable not found: {args.chrome}")

    with FixtureServer("origins") as origins_fixture, FixtureServer("phase5") as phase5_fixture:
        vite_port = free_port()
        chrome_port = free_port()
        ui_origin = f"http://127.0.0.1:{vite_port}"
        env = os.environ.copy()
        env["VITE_ORIGINSD_PROXY_TARGET"] = origins_fixture.origin
        env["VITE_ORIGINS_PHASE5_PROXY_TARGET"] = phase5_fixture.origin
        vite = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)],
            cwd=workspace,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        cdp: Cdp | None = None
        chrome: subprocess.Popen[bytes] | None = None
        try:
            wait_until(lambda: http_ready(ui_origin), timeout=20)
            with tempfile.TemporaryDirectory(prefix="origins-phase5-chrome-") as profile:
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
                        "--window-size=1600,1000",
                        f"{ui_origin}/",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                websocket_url = wait_until(lambda: chrome_target(chrome_port, ui_origin), timeout=20)
                cdp = Cdp(str(websocket_url))
                cdp.call("Page.enable")
                cdp.call("Runtime.enable")
                wait_until(lambda: "Origins Factory · Phase 5" in body_text(cdp), timeout=15)

                core_text = body_text(cdp)
                assert_contains(core_text, "Origins Factory · Phase 5", "Core", "Oracle", "Logistics", "Applications")

                click_button(cdp, "Oracle")
                wait_until(lambda: cdp.evaluate("document.querySelector('.phase5-header h1')?.textContent") == "Oracle")
                set_phase5_token(cdp)
                click_button(cdp, "Connect")
                wait_until(lambda: "connected" in str(cdp.evaluate("document.querySelector('.phase5-status')?.textContent") or "").lower())
                oracle_text = body_text(cdp)
                assert_contains(
                    oracle_text,
                    "Retained browser Session",
                    "Remote Node truth",
                    "Approved remote file retrieval",
                    "Give AI Act",
                    "Human takeover",
                    "I explicitly approve Act authority for this handoff.",
                    "kratos-HP-290-G4-Microtower-PC",
                    REMOTE_APPLICATION_REASON,
                )
                act_disabled = cdp.evaluate(
                    "[...document.querySelectorAll('button')].find((button)=>button.textContent?.trim()==='Give AI Act')?.disabled"
                )
                if act_disabled is not True:
                    raise RuntimeError("Oracle Act control must begin disabled until explicit approval")
                if PROOF_TOKEN in oracle_text:
                    raise RuntimeError("fixture bearer leaked into rendered Oracle text")
                oracle_shot = screenshot(cdp, output_dir / "phase5-oracle.png")

                click_button(cdp, "Logistics")
                wait_until(lambda: cdp.evaluate("document.querySelector('.phase5-header h1')?.textContent") == "Logistics")
                logistics_text = body_text(cdp)
                assert_contains(
                    logistics_text,
                    "Lumi owner state",
                    "Queue acquisition",
                    "Durable Artifacts",
                    "verified.bin",
                    "Lumi owns acquisition, queues, resume and verification.",
                )
                logistics_shot = screenshot(cdp, output_dir / "phase5-logistics.png")

                click_button(cdp, "Applications")
                wait_until(lambda: cdp.evaluate("document.querySelector('.phase5-header h1')?.textContent") == "Applications")
                applications_text = body_text(cdp)
                assert_contains(
                    applications_text,
                    "Workspace Applications",
                    "Executable / argv / cwd",
                    "Server registry owns all three",
                    "Browser-supplied launch args",
                    "Not accepted",
                    "THETECHGUY Software Builder",
                    REMOTE_APPLICATION_REASON,
                )
                applications_shot = screenshot(cdp, output_dir / "phase5-applications.png")

                proof = {
                    "schema_version": "origins.phase5-workspace-ui-proof.v1",
                    "proof": "PHASE5_WORKSPACE_UI_OK",
                    "source_head": source_head,
                    "browser": "system-google-chrome-headless",
                    "production_credentials_used": False,
                    "fixture_bearer_rendered": False,
                    "oracle_act_requires_explicit_approval": True,
                    "remote_application_attachment_available": False,
                    "remote_application_reason": REMOTE_APPLICATION_REASON,
                    "surfaces": ["Core", "Oracle", "Logistics", "Applications"],
                    "screenshots": {
                        "oracle": oracle_shot,
                        "logistics": logistics_shot,
                        "applications": applications_shot,
                    },
                }
                print(json.dumps(proof, sort_keys=True))
                cdp.call("Browser.close")
                cdp.close()
                cdp = None
        finally:
            if cdp is not None:
                try:
                    cdp.call("Browser.close")
                    cdp.close()
                except Exception:
                    pass
            if chrome is not None and chrome.poll() is None:
                chrome.terminate()
                try:
                    chrome.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    chrome.kill()
            if vite.poll() is None:
                os.killpg(vite.pid, 15)
                try:
                    vite.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(vite.pid, 9)
            shutil.rmtree(output_dir / "profile", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
