from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping

from v1_mission_contract import V1MissionError, file_sha256


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(args: list[str], *, cwd: Path, timeout: float = 120) -> str:
    result = subprocess.run(
        args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise V1MissionError(
            f"command failed ({result.returncode}): {args!r}; "
            f"stdout={result.stdout[-1200:]!r}; stderr={result.stderr[-1200:]!r}"
        )
    return result.stdout.strip()


def _git_head(path: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=path)


def _git_status(path: Path) -> list[str]:
    raw = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=path
    )
    return [line for line in raw.splitlines() if line]


def _assert_clean(label: str, path: Path) -> None:
    status = _git_status(path)
    if not status:
        return
    untracked = [line[3:] for line in status if line.startswith("?? ")]
    if untracked:
        raise V1MissionError(f"{label} checkout contains untracked files: {untracked}")
    raise V1MissionError(f"{label} checkout contains tracked changes: {status}")


def _tracked_file_record(label: str, owner_root: Path, file_path: Path) -> dict[str, object]:
    root = owner_root.resolve()
    path = file_path.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise V1MissionError(f"{label} resolved outside owner root: {path}") from exc
    _run(["git", "ls-files", "--error-unmatch", relative.as_posix()], cwd=root)
    return {
        "label": label,
        "resolved_path": str(path),
        "owner_relative_path": relative.as_posix(),
        "sha256": file_sha256(path),
    }


def _module_authority_record(label: str, owner_root: Path, module: str) -> dict[str, object]:
    spec = importlib.util.find_spec(module)
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        raise V1MissionError(f"{label} module cannot be resolved: {module}")
    record = _tracked_file_record(label, owner_root, Path(spec.origin))
    return {**record, "module": module}


def _write_owner_entrypoint(path: Path, owner_root: Path, module: str) -> dict[str, object]:
    path.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        f"sys.path.insert(0, {str(owner_root)!r})\n"
        f"from {module} import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return {"resolved_path": str(path.resolve()), "module": module, "sha256": file_sha256(path)}


def _session_id(accepted: Mapping[str, object]) -> str:
    session = accepted.get("session")
    if not isinstance(session, Mapping) or not str(session.get("session_id") or ""):
        raise V1MissionError("Origins process acceptance omitted session_id")
    return str(session["session_id"])


def _expect_session(client, session_id: str, expected_exit: int) -> dict[str, object]:
    session = client.wait_session(session_id)
    state = session.get("state")
    if expected_exit == 0 and state != "completed":
        raise V1MissionError(f"unexpected Session state for {session_id}: {state}")
    if expected_exit != 0 and state not in {"failed", "completed"}:
        raise V1MissionError(f"unexpected failed Session state for {session_id}: {state}")
    if session.get("exit_code") != expected_exit:
        raise V1MissionError(
            f"Session {session_id} exit mismatch: expected {expected_exit}, got {session.get('exit_code')}"
        )
    return session


def _route_provider(
    client, *, workspace_id: str, repo: Path, config: Path, provider_id: str, mission_id: str
) -> str:
    accepted = client.submit_process(
        workspace_id=workspace_id,
        workspace_root=str(repo),
        executable="hunter-codeops-switcher",
        args=[
            "--config", str(config), "route", "--task",
            f"Origins v1 Mission {mission_id} provider continuity proof",
            "--client", "terminal", "--mode", "quick_edit", "--provider-id", provider_id,
            "--review", "required",
        ],
        timeout_seconds=60,
        max_output_bytes=256 * 1024,
    )
    sid = _session_id(accepted)
    _expect_session(client, sid, 0)
    payload = json.loads(str(client.get_session_output(sid).get("stdout") or "{}"))
    decision = payload.get("decision") if isinstance(payload, Mapping) else None
    if not isinstance(decision, Mapping) or decision.get("provider_id") != provider_id:
        raise V1MissionError(f"CodeOps route did not preserve requested provider {provider_id}")
    return sid


def _artifact(
    client, *, workspace_id: str, path: Path, owner_ref: str, media_type: str = "application/json"
) -> dict[str, object]:
    return client._json(
        "POST",
        "/v1/artifacts",
        {
            "workspace_id": workspace_id,
            "owner": "origins",
            "owner_ref": owner_ref,
            "path": str(path.resolve()),
            "filename": path.name,
            "media_type": media_type,
        },
        expected_status=201,
    )


def _artifact_projection(result: Mapping[str, object]) -> Mapping[str, object]:
    artifact = result.get("artifact")
    if not isinstance(artifact, Mapping):
        raise V1MissionError("Artifact registration omitted projection")
    return artifact


def _remove_known_transients(run_root: Path, repo: Path) -> list[str]:
    removed: list[str] = []
    for transient in list(repo.rglob("__pycache__")):
        if transient.is_dir():
            shutil.rmtree(transient)
            removed.append(str(transient.relative_to(run_root)))
    for transient in (repo / ".pytest_cache", repo / "upgrade-plan.json"):
        if transient.exists():
            if transient.is_dir():
                shutil.rmtree(transient)
            else:
                transient.unlink()
            removed.append(str(transient.relative_to(run_root)))
    owner_bin = run_root / "owner-bin"
    if owner_bin.exists():
        shutil.rmtree(owner_bin)
        removed.append(str(owner_bin.relative_to(run_root)))
    return sorted(set(removed))


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in "0123456789abcdef" for ch in value)


def _audit_sanitation_scope(
    run_root: Path,
    repo: Path,
    *,
    promoted_files: list[Path] | tuple[Path, ...] = (),
    registered_artifacts: list[Mapping[str, object]] | tuple[Mapping[str, object], ...] = (),
) -> list[str]:
    run_root = run_root.resolve()
    repo = repo.resolve()
    remaining: set[str] = set()

    promoted_root = (run_root / "promoted").resolve()
    allowed_promoted: set[str] = set()
    for item in promoted_files:
        resolved = Path(item).resolve()
        try:
            relative = resolved.relative_to(promoted_root)
        except ValueError as exc:
            raise V1MissionError(f"promoted sanitation allowlist escaped promoted root: {resolved}") from exc
        allowed_promoted.add(relative.as_posix())

    registered_content_digests: set[str] = set()
    for projection in registered_artifacts:
        digest_value = str(projection.get("content_sha256") or "")
        if not _is_lower_hex(digest_value, 64):
            raise V1MissionError(
                f"registered Artifact sanitation projection has invalid content_sha256: {digest_value!r}"
            )
        registered_content_digests.add(digest_value)

    allowed_agentops = {
        "audit.json",
        "evidence.json",
        "lessons.json",
        "approvals.json",
        "operations.json",
        ".audit.json.lock",
        ".evidence.json.lock",
        ".lessons.json.lock",
        ".approvals.json.lock",
        ".operations.json.lock",
    }
    allowed_origins_root = {
        "origins.sqlite3",
        "origins.sqlite3-wal",
        "origins.sqlite3-shm",
    }

    # Any untracked repository path is temporary by definition for this disposable Mission.
    for line in _git_status(repo):
        if line.startswith("?? "):
            remaining.add(str((repo / line[3:]).resolve().relative_to(run_root)))

    for path in run_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(run_root)
        if not relative.parts:
            continue
        if path.is_symlink():
            remaining.add(relative.as_posix())
            continue

        top = relative.parts[0]
        if top == "origins-state":
            state_rel = Path(*relative.parts[1:]).as_posix()
            if state_rel in allowed_origins_root:
                continue
            parts = relative.parts[1:]
            # Canonical immutable Artifact object: artifacts/objects/aa/<64-lower-hex-sha256>.
            if len(parts) == 4 and parts[:2] == ("artifacts", "objects"):
                prefix, digest_value = parts[2], parts[3]
                if (
                    _is_lower_hex(prefix, 2)
                    and _is_lower_hex(digest_value, 64)
                    and digest_value.startswith(prefix)
                    and digest_value in registered_content_digests
                    and file_sha256(path) == digest_value
                ):
                    continue
            remaining.add(relative.as_posix())
            continue

        if top == "agentops-state":
            state_rel = Path(*relative.parts[1:]).as_posix()
            if state_rel not in allowed_agentops:
                remaining.add(relative.as_posix())
            continue

        if top == "promoted":
            promoted_rel = Path(*relative.parts[1:]).as_posix()
            if promoted_rel not in allowed_promoted:
                remaining.add(relative.as_posix())
            continue

        if top != "workspaces":
            remaining.add(relative.as_posix())
            continue

        try:
            repo_relative = path.resolve().relative_to(repo)
        except ValueError:
            remaining.add(relative.as_posix())
            continue
        if repo_relative.parts and repo_relative.parts[0] == ".git":
            continue
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", repo_relative.as_posix()],
            cwd=repo,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            remaining.add(relative.as_posix())
    return sorted(remaining)


@contextmanager
def _running_http_server(server):
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
