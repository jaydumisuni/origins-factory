from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

READ_DENIED = 41
WRITE_DENIED = 42
TCP_DENIED = 43
UDP_DENIED = 44
SANDBOX_SETUP_FAILED = 125


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    args = parser.parse_args()

    sandbox = args.sandbox.resolve()
    probe = args.probe.resolve()
    if not sandbox.is_file() or not probe.is_file():
        raise AssertionError("native sandbox and probe binaries must exist")

    with tempfile.TemporaryDirectory(prefix="origins-native-containment-") as temporary:
        root = Path(temporary).resolve()
        allowed = root / "allowed"
        outside = root / "outside"
        allowed.mkdir()
        outside.mkdir()
        allowed_read = allowed / "allowed.txt"
        outside_read = outside / "outside.txt"
        allowed_read.write_text("ALLOWED_READ", encoding="utf-8")
        outside_read.write_text("OUTSIDE_READ", encoding="utf-8")

        # Positive controls prove the host user can perform the operations that the sandbox must deny.
        direct(probe, "read", str(outside_read), expected=0)
        direct(probe, "write", str(outside / "direct-write.txt"), "DIRECT", expected=0)
        prove_direct_tcp(probe)
        prove_direct_udp(probe)

        spec_base = {
            "executable": str(probe),
            "cwd": str(allowed),
            "environment": safe_environment(allowed),
            "runtime_read_paths": runtime_read_paths(probe),
            "resource_paths": [{"path": str(allowed), "writable": True}],
            "deny_paths": [],
            "network_mode": "deny",
        }

        allowed_result = sandboxed(
            sandbox,
            root,
            spec_base,
            ["read", str(allowed_read)],
        )
        require_exit(allowed_result, 0, "allowed read")
        if allowed_result.stdout != "ALLOWED_READ":
            raise AssertionError(f"allowed read returned unexpected output: {allowed_result.stdout!r}")

        denied_read = sandboxed(
            sandbox,
            root,
            spec_base,
            ["read", str(outside_read)],
        )
        require_exit(denied_read, READ_DENIED, "outside read")

        allowed_write_path = allowed / "sandbox-write.txt"
        allowed_write = sandboxed(
            sandbox,
            root,
            spec_base,
            ["write", str(allowed_write_path), "SANDBOX_WRITE"],
        )
        require_exit(allowed_write, 0, "allowed write")
        if allowed_write_path.read_text(encoding="utf-8") != "SANDBOX_WRITE":
            raise AssertionError("allowed write did not persist expected content")

        denied_write_path = outside / "sandbox-denied.txt"
        denied_write = sandboxed(
            sandbox,
            root,
            spec_base,
            ["write", str(denied_write_path), "DENIED"],
        )
        require_exit(denied_write, WRITE_DENIED, "outside write")
        if denied_write_path.exists():
            raise AssertionError("outside write created a file despite containment")

        with tcp_listener() as tcp:
            address = f"127.0.0.1:{tcp.getsockname()[1]}"
            denied_tcp = sandboxed(sandbox, root, spec_base, ["tcp", address])
            require_exit(denied_tcp, TCP_DENIED, "TCP network")

        with udp_listener() as udp:
            address = f"127.0.0.1:{udp.getsockname()[1]}"
            denied_udp = sandboxed(sandbox, root, spec_base, ["udp", address])
            if denied_udp.returncode not in (0, UDP_DENIED):
                raise AssertionError(
                    "UDP network probe returned an unexpected result: "
                    f"code={denied_udp.returncode} stdout={denied_udp.stdout!r} "
                    f"stderr={denied_udp.stderr!r}"
                )
            udp.settimeout(0.25)
            try:
                data, _ = udp.recvfrom(1024)
            except TimeoutError:
                data = b""
            if data:
                raise AssertionError(f"sandbox emitted UDP payload despite network deny: {data!r}")

        heartbeat = allowed / "heartbeat.txt"
        prove_process_tree_fence(sandbox, probe, root, spec_base, heartbeat)

    print(
        json.dumps(
            {
                "status": "PASS",
                "platform": sys.platform,
                "allowed_read": True,
                "outside_read_denied": True,
                "allowed_write": True,
                "outside_write_denied": True,
                "tcp_denied": True,
                "udp_denied": True,
                "process_tree_fenced": True,
                "network_mode": "deny",
            },
            sort_keys=True,
        )
    )
    return 0


def direct(probe: Path, *args: str, expected: int) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(probe), *args],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    require_exit(completed, expected, f"direct probe {' '.join(args[:1])}")
    return completed


def prove_direct_tcp(probe: Path) -> None:
    with tcp_listener() as listener:
        accepted: list[bytes] = []

        def receive() -> None:
            connection, _ = listener.accept()
            with connection:
                accepted.append(connection.recv(1024))

        thread = threading.Thread(target=receive, daemon=True)
        thread.start()
        address = f"127.0.0.1:{listener.getsockname()[1]}"
        direct(probe, "tcp", address, expected=0)
        thread.join(timeout=5)
        if accepted != [b"origins-tcp-probe"]:
            raise AssertionError(f"direct TCP positive control failed: {accepted!r}")


def prove_direct_udp(probe: Path) -> None:
    with udp_listener() as listener:
        address = f"127.0.0.1:{listener.getsockname()[1]}"
        direct(probe, "udp", address, expected=0)
        listener.settimeout(5)
        data, _ = listener.recvfrom(1024)
        if data != b"origins-udp-probe":
            raise AssertionError(f"direct UDP positive control failed: {data!r}")


def sandboxed(
    sandbox: Path,
    root: Path,
    base: dict,
    command_args: list[str],
) -> subprocess.CompletedProcess[str]:
    spec = dict(base)
    spec["args"] = command_args
    spec_path = root / f"sandbox-{time.time_ns()}.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    completed = subprocess.run(
        [str(sandbox), str(spec_path)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if completed.returncode == SANDBOX_SETUP_FAILED:
        raise AssertionError(
            "native sandbox setup failed rather than enforcing the requested operation: "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )
    return completed


def prove_process_tree_fence(
    sandbox: Path,
    probe: Path,
    root: Path,
    base: dict,
    heartbeat: Path,
) -> None:
    spec = dict(base)
    spec["args"] = ["tree", str(probe), str(heartbeat)]
    spec_path = root / "sandbox-tree.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    process = subprocess.Popen(
        [str(sandbox), str(spec_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_heartbeat(heartbeat, process)
        before = heartbeat.stat().st_size
        time.sleep(0.35)
        grown = heartbeat.stat().st_size
        if grown <= before:
            raise AssertionError("heartbeat child did not remain live before fencing")

        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        fenced_size = heartbeat.stat().st_size
        time.sleep(0.65)
        after = heartbeat.stat().st_size
        if after != fenced_size:
            raise AssertionError(
                f"child process survived process-tree fence: {fenced_size} -> {after}"
            )
    finally:
        if process.poll() is None:
            if os.name == "nt":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=10)


def wait_for_heartbeat(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(
                "sandbox tree exited before heartbeat: "
                f"code={process.returncode} stdout={stdout!r} stderr={stderr!r}"
            )
        if path.exists() and path.stat().st_size >= 4:
            return
        time.sleep(0.1)
    raise AssertionError("sandbox tree did not create heartbeat in time")


def require_exit(
    completed: subprocess.CompletedProcess[str],
    expected: int,
    label: str,
) -> None:
    if completed.returncode != expected:
        raise AssertionError(
            f"{label} expected exit {expected}, got {completed.returncode}; "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )


def safe_environment(allowed: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name in ("LANG", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    environment["TEMP"] = str(allowed)
    environment["TMP"] = str(allowed)
    return environment


def runtime_read_paths(probe: Path) -> list[str]:
    if os.name == "nt":
        return [str(probe.parent)]
    candidates = [
        Path("/lib"),
        Path("/lib64"),
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/etc/ld.so.cache"),
        Path("/etc/ld.so.preload"),
    ]
    return [str(path) for path in candidates if path.exists()]


class tcp_listener:
    def __enter__(self) -> socket.socket:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(4)
        return self.socket

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.socket.close()


class udp_listener:
    def __enter__(self) -> socket.socket:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        return self.socket

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.socket.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
