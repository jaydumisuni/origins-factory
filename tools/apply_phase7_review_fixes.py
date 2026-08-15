from __future__ import annotations

from pathlib import Path

EVOLUTION = Path("python/origins_integration/capability_evolution.py")
APPROVALS = Path("python/origins_integration/capability_evolution_approvals.py")
ENGINEERING = Path("python/origins_integration/engineering.py")
SERVER = Path("python/origins_integration/phase7_server.py")
PROOF = Path("tools/prove_phase7_live_owner.py")
STRICT = Path("tools/prove_phase7_live_owner_strict.py")
UI_PROOF = Path("tools/prove_phase7_workspace_ui.py")
CSS = Path("workspace/src/phase7.css")
TEST = Path("python/tests/test_phase7_review_hardening.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_sqlite() -> None:
    for path in (EVOLUTION, APPROVALS):
        text = path.read_text(encoding="utf-8")
        if "from contextlib import closing" not in text:
            text = text.replace("from dataclasses import dataclass\n", "from contextlib import closing\nfrom dataclasses import dataclass\n", 1) if path == EVOLUTION else text.replace("import sqlite3\n", "import sqlite3\nfrom contextlib import closing\n", 1)
        count = text.count("with self._connect() as db:")
        if count < 1:
            raise SystemExit(f"{path}: no SQLite context anchors")
        text = text.replace("with self._connect() as db:", "with closing(self._connect()) as connection, connection as db:")
        path.write_text(text, encoding="utf-8")


def patch_engineering() -> None:
    text = ENGINEERING.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "        limit: int = 512 * 1024,\n",
        "        limit: int = 8 * 1024 * 1024,\n",
        "Phase 7 repository diff bound",
    )
    ENGINEERING.write_text(text, encoding="utf-8")


def patch_server() -> None:
    text = SERVER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        def _authorized(self) -> bool:\n            supplied = self.headers.get("Authorization", "")\n            return hmac.compare_digest(supplied, f"Bearer {token}")\n''',
        '''        def _authorized(self) -> bool:\n            supplied = self.headers.get("Authorization", "").encode("latin-1", "replace")\n            expected = f"Bearer {token}".encode("utf-8")\n            return hmac.compare_digest(supplied, expected)\n''',
        "total bearer comparison",
    )
    text = replace_once(
        text,
        '''            path = urlparse(self.path).path\n            transition_lock.acquire()\n            try:\n                body = self._body()\n                if path == "/v1/evolutions/gap":\n''',
        '''            path = urlparse(self.path).path\n            try:\n                body = self._body()\n            except (Phase7ServerError, ValueError) as exc:\n                self._conflict(exc)\n                return\n            transition_lock.acquire()\n            try:\n                if path == "/v1/evolutions/gap":\n''',
        "body before transition lock",
    )
    SERVER.write_text(text, encoding="utf-8")


def patch_live_proof() -> None:
    text = PROOF.read_text(encoding="utf-8")
    if "import socket\n" not in text:
        text = text.replace("import shutil\n", "import shutil\nimport socket\n", 1)
    old = '''def _wait_health(timeout: float = 12.0) -> None:\n    deadline = time.monotonic() + timeout\n    last = ""\n    while time.monotonic() < deadline:\n        try:\n            with urllib.request.urlopen(f"{PROOF_URL}/v1/health", timeout=0.5) as response:\n                payload = json.loads(response.read().decode("utf-8"))\n                if response.status == 200 and payload.get("ok") is True:\n                    return\n        except Exception as exc:  # proof polling only\n            last = type(exc).__name__\n        time.sleep(0.05)\n    raise ProofError(f"originsd did not become healthy: {last}")\n'''
    new = '''def _ensure_proof_port_free() -> None:\n    host, raw_port = PROOF_BIND.rsplit(":", 1)\n    try:\n        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:\n            sock.bind((host, int(raw_port)))\n    except OSError as exc:\n        raise ProofError(f"Phase 7 proof port is already in use: {PROOF_BIND}") from exc\n\n\ndef _wait_health(process: subprocess.Popen[bytes], token: str, timeout: float = 12.0) -> None:\n    deadline = time.monotonic() + timeout\n    last = ""\n    while time.monotonic() < deadline:\n        exit_code = process.poll()\n        if exit_code is not None:\n            raise ProofError(f"originsd exited before becoming healthy: {exit_code}")\n        try:\n            with urllib.request.urlopen(f"{PROOF_URL}/v1/health", timeout=0.5) as response:\n                payload = json.loads(response.read().decode("utf-8"))\n                if response.status == 200 and payload.get("ok") is True:\n                    auth_request = urllib.request.Request(\n                        f"{PROOF_URL}/v1/capabilities",\n                        headers={"Authorization": f"Bearer {token}"},\n                    )\n                    with urllib.request.urlopen(auth_request, timeout=0.5) as authenticated:\n                        auth_payload = json.loads(authenticated.read().decode("utf-8"))\n                    if authenticated.status == 200 and isinstance(auth_payload.get("capabilities"), list):\n                        if process.poll() is not None:\n                            raise ProofError("originsd exited after health while a foreign listener remained")\n                        return\n        except ProofError:\n            raise\n        except Exception as exc:  # proof polling only\n            last = type(exc).__name__\n        time.sleep(0.05)\n    raise ProofError(f"originsd did not become healthy and authenticated: {last}")\n'''
    text = replace_once(text, old, new, "proof daemon ownership wait")
    text = replace_once(
        text,
        '''    env = os.environ.copy()\n    env.update(\n''',
        '''    _ensure_proof_port_free()\n    env = os.environ.copy()\n    env.update(\n''',
        "proof port preflight",
    )
    text = replace_once(text, "        _wait_health()\n", "        _wait_health(process, token)\n", "proof process wait")
    PROOF.write_text(text, encoding="utf-8")


def patch_strict_proof() -> None:
    text = STRICT.read_text(encoding="utf-8")
    if "import subprocess\n" not in text:
        text = text.replace("import json\n", "import json\nimport subprocess\n", 1)
    text = replace_once(
        text,
        '''def main() -> int:\n    module = _load_base()\n\n''',
        '''def main() -> int:\n    module = _load_base()\n    pytest_probe = subprocess.run(\n        [sys.executable, "-B", "-c", "import pytest"],\n        check=False,\n        stdout=subprocess.DEVNULL,\n        stderr=subprocess.PIPE,\n        text=True,\n        timeout=15,\n    )\n    if pytest_probe.returncode != 0:\n        raise module.ProofError(\n            f"strict canary interpreter cannot import pytest: {sys.executable}: {pytest_probe.stderr[-500:]}"\n        )\n\n''',
        "strict pytest precondition",
    )
    STRICT.write_text(text, encoding="utf-8")


def patch_ui_proof() -> None:
    text = UI_PROOF.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            buttons = cdp.evaluate("[...document.querySelectorAll('.phase7-console button')].map((b)=>b.textContent?.trim()||'')")\n''',
        '''            buttons = cdp.evaluate(\n                "[...document.querySelectorAll('.phase7-switcher button, .phase7-console button')]"\n                ".map((b)=>b.textContent?.trim()||'')"\n            )\n''',
        "Workspace proof switcher buttons",
    )
    UI_PROOF.write_text(text, encoding="utf-8")


def patch_css() -> None:
    text = CSS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        ".phase7-json{max-height:330px;overflow:auto;white-space:pre-wrap;word-break:break-word}",
        ".phase7-json{max-height:330px;overflow:auto;white-space:pre-wrap;overflow-wrap:break-word}",
        "deprecated word-break",
    )
    CSS.write_text(text, encoding="utf-8")


def write_tests() -> None:
    TEST.write_text(
        '''from __future__ import annotations\n\nimport inspect\n\nfrom origins_integration.engineering import OriginsClient\n\n\ndef test_phase7_repository_diff_default_uses_daemon_maximum() -> None:\n    parameter = inspect.signature(OriginsClient.get_repository_diff).parameters["limit"]\n    assert parameter.default == 8 * 1024 * 1024\n''',
        encoding="utf-8",
    )


def main() -> None:
    patch_sqlite()
    patch_engineering()
    patch_server()
    patch_live_proof()
    patch_strict_proof()
    patch_ui_proof()
    patch_css()
    write_tests()


if __name__ == "__main__":
    main()
