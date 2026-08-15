from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

PROOF_TOKEN = "phase7-render-proof"
EVOLUTION_ID = "evolution-phase7-ui-proof"
MISSION_ID = "mission-phase7-ui-proof"
ATTEMPT_ID = "attempt-phase7-ui-proof"
CAPABILITY_ID = "origins.proof.capability.ui"
MANIFEST_SHA = "a" * 64
DIFF_SHA = "b" * 64
REVIEW_SHA = "c" * 64


def _load_browser_helpers() -> ModuleType:
    path = Path(__file__).with_name("prove_phase6_workspace_ui.py")
    spec = importlib.util.spec_from_file_location("origins_phase7_browser_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load browser proof helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evolution_projection() -> dict[str, Any]:
    return {
        "evolution_id": EVOLUTION_ID,
        "state": "canary_passed",
        "gap": {
            "mission_id": MISSION_ID,
            "parent_operation_id": "parent-operation-phase7-ui-proof",
            "workspace_id": "workspace-phase7-ui-proof",
            "attempt_id": ATTEMPT_ID,
            "resume_token": "resume-phase7-ui-proof",
            "resume_state_sha256": "d" * 64,
            "capability_id": CAPABILITY_ID,
            "expected_effects": ["verify"],
            "actual_effects": ["observe"],
            "actual_manifest_sha256": "e" * 64,
            "refusal_code": "CAPABILITY_EFFECT_MISSING",
            "evidence_refs": ["origins:evidence:expected", "origins:evidence:actual"],
            "summary": "Fixture Mission exposed one bounded missing verification effect.",
        },
        "proposal": {
            "capability_id": CAPABILITY_ID,
            "requested_effects": ["verify"],
            "approval_required": True,
            "self_approvable": False,
            "persistent_lease": False,
            "delegated_remote_authority": False,
        },
        "approval_binding": {
            "status": "approved",
            "approval_id": "approval-capability-phase7-ui-proof",
        },
        "engineering_approval_binding": {
            "status": "approved",
            "approval_id": "approval-engineering-phase7-ui-proof",
        },
        "child_operation": {
            "accepted": True,
            "execution_dispatched": False,
            "operation_id": "child-operation-phase7-ui-proof",
        },
        "candidate": {
            "candidate_generation": 2,
            "base_generation": 1,
            "manifest_sha256": MANIFEST_SHA,
            "repository_diff_sha256": DIFF_SHA,
            "repository_diff_bytes": 128,
        },
        "sergeant_review": {
            "verdict": "PASS",
            "review_sha256": REVIEW_SHA,
            "candidate_manifest_sha256": MANIFEST_SHA,
        },
        "canary": {
            "mission_id": MISSION_ID,
            "attempt_id": ATTEMPT_ID,
            "manifest_sha256": MANIFEST_SHA,
            "outcome": "passed",
            "authority_expanded": False,
        },
        "promotion": None,
        "resume": None,
        "active_generation": {
            "capability_id": CAPABILITY_ID,
            "generation": 1,
            "manifest_sha256": "f" * 64,
            "evolution_id": "evolution-phase7-previous",
        },
        "revision": 10,
    }


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/health":
            return self._json(
                200,
                {
                    "ok": True,
                    "service": "origins-phase7-proof-fixture",
                    "phase": 7,
                    "runtime_authority_expansion": False,
                    "model_self_approval": False,
                    "owners": {
                        "Hunter-AgentOps": {"available": True},
                        "hunter-codeops": {"available": True},
                        "Sergeant": {"available": True},
                    },
                },
            )
        if self.headers.get("Authorization") != f"Bearer {PROOF_TOKEN}":
            return self._json(401, {"error": "UNAUTHORIZED"})
        if self.path == "/v1/evolutions":
            return self._json(200, {"phase": 7, "evolutions": [evolution_projection()]})
        if self.path == f"/v1/evolutions/{EVOLUTION_ID}":
            return self._json(200, evolution_projection())
        return self._json(404, {"error": "NOT_FOUND"})


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


def _set_token(cdp: Any) -> None:
    token = json.dumps(PROOF_TOKEN)
    value = cdp.evaluate(
        f"(()=>{{const i=document.querySelector('.phase7-connect input[type=password]');if(!i)return null;"
        f"const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(i,{token});"
        "i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}));return i.value;}})()"
    )
    if value != PROOF_TOKEN:
        raise RuntimeError("Phase 7 proof token input did not update")


def _assert_contains(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise RuntimeError(f"rendered EVOLUTION text is missing: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Phase 7 EVOLUTION surface in isolated real Chrome")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--output-dir", default="/tmp/origins-phase7-workspace-ui-proof")
    args = parser.parse_args()

    helpers = _load_browser_helpers()
    repository = Path.cwd().resolve()
    workspace = (repository / args.workspace).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    expected_head = os.environ.get("ORIGINS_PHASE7_EXPECTED_HEAD", "").strip()
    if expected_head and source_head != expected_head:
        raise RuntimeError(f"source head mismatch: expected {expected_head}, got {source_head}")
    if not Path(args.chrome).is_file():
        raise RuntimeError(f"Chrome executable not found: {args.chrome}")

    profile = Path(tempfile.mkdtemp(prefix="origins-phase7-chrome-"))
    vite: subprocess.Popen[Any] | None = None
    chrome: subprocess.Popen[Any] | None = None
    cdp: Any = None
    with FixtureServer() as fixture:
        try:
            vite_port = helpers.free_port()
            chrome_port = helpers.free_port()
            ui_origin = f"http://127.0.0.1:{vite_port}"
            env = os.environ.copy()
            env["VITE_ORIGINS_PHASE7_PROXY_TARGET"] = fixture.origin
            vite = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)],
                cwd=workspace,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            helpers.wait_until(lambda: helpers.http_ready(ui_origin))
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
            websocket_url = helpers.wait_until(lambda: helpers.chrome_target(chrome_port, ui_origin))
            cdp = helpers.Cdp(str(websocket_url))
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            helpers.wait_until(lambda: "Origins Factory · Phase 7" in helpers.body_text(cdp))
            helpers.click_button(cdp, "EVOLUTION")
            helpers.wait_until(lambda: cdp.evaluate("document.querySelector('.phase7-header h1')?.textContent") == "EVOLUTION")
            _set_token(cdp)
            helpers.click_button(cdp, "Connect")
            helpers.wait_until(
                lambda: str(cdp.evaluate("document.querySelector('.phase7-status')?.textContent") or "").strip().lower() == "connected"
            )

            rendered = helpers.body_text(cdp)
            _assert_contains(
                rendered,
                "NO SELF-AUTHORITY",
                "Models cannot confirm their own gap",
                CAPABILITY_ID,
                MISSION_ID,
                ATTEMPT_ID,
                "Runtime authority expansion",
                "FALSE",
                "Generation Candidate",
                "Sergeant Review",
                "Canary",
                "Promote Generation",
                "Rollback candidate",
            )
            if PROOF_TOKEN in rendered:
                raise RuntimeError("fixture bearer leaked into rendered EVOLUTION text")
            if "Activate automatically" in rendered or "Self approve" in rendered:
                raise RuntimeError("rendered EVOLUTION surface exposes implicit self-authority")

            buttons = cdp.evaluate("[...document.querySelectorAll('.phase7-console button')].map((b)=>b.textContent?.trim()||'')")
            if not isinstance(buttons, list):
                raise RuntimeError("could not inspect EVOLUTION controls")
            required_buttons = {"Workspace", "EVOLUTION", "Refresh", "Disconnect", "Confirm gap + compile proposal", "Promote Generation", "Rollback candidate"}
            missing_buttons = sorted(required_buttons - {str(value) for value in buttons})
            if missing_buttons:
                raise RuntimeError(f"EVOLUTION controls are missing: {missing_buttons}")

            screenshot = helpers.screenshot(cdp, output_dir / "phase7-evolution.png")
            result = {
                "schema_version": "origins.phase7-workspace-ui-proof.v1",
                "proof": "PHASE7_WORKSPACE_UI_OK",
                "source_head": source_head,
                "browser": "system-google-chrome-headless",
                "runtime_authority_expansion": False,
                "model_self_approval": False,
                "promotion_is_explicit": True,
                "rollback_is_explicit": True,
                "production_credentials_used": False,
                "fixture_bearer_rendered": False,
                "screenshot": screenshot,
            }
            print(json.dumps(result, sort_keys=True))
            return 0
        finally:
            if cdp is not None:
                try:
                    cdp.close()
                except Exception:
                    pass
            helpers.stop_process(chrome)
            helpers.stop_process(vite)
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
