from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


HUAWEI_OWNER_REPOSITORY = "jaydumisuni/TECHGUYTOOL-Huawei"
HUAWEI_OWNER_REVISION = "fd3f7bb1587b65faaa7d37e0057683dcb07975ed"
XRAY_OWNER_REPOSITORY = "jaydumisuni/TTG-Device-X-Ray"
XRAY_OWNER_REVISION = "34feb55ab937fa865726cbb22c44b09b52084114"
DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 49321
DEFAULT_TIMEOUT = 5.0
MAX_GATEWAY_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_EVENT_COUNT = 10_000
MAX_BUNDLE_JSON_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_FILES = 4096

READ_ONLY_GATEWAY_COMMANDS = frozenset(
    {
        "health",
        "doctor",
        "snapshot",
        "get_physical_session",
        "get_operation",
        "list_events",
        "verify_journal",
    }
)

PROJECTED_CONTRACT_TYPES = frozenset(
    {
        "physical_device_session",
        "endpoint_observation",
        "device_evidence",
        "device_twin",
        "operation_request",
        "recipe_candidate",
        "decision_verdict",
        "mode_lease",
        "execution_lease",
        "executor_result",
        "verification_result",
        "artifact_manifest",
        "recovery_plan",
    }
)

XRAY_PROJECTION_FILES = (
    "mission.json",
    "transport_evidence.json",
    "candidates.json",
    "device_identity.json",
    "firmware_fingerprint.json",
    "storage_summary.json",
    "partition_map.json",
    "challenger_findings.json",
    "certification.json",
    "profile_match.json",
    "recommended_plan.json",
)


class DeviceReadOnlyError(RuntimeError):
    pass


def _require_loopback(host: str) -> str:
    value = str(host or "").strip()
    if value not in {"127.0.0.1", "localhost", "::1"}:
        raise DeviceReadOnlyError("Huawei Gateway mount accepts loopback hosts only")
    return value


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeviceReadOnlyError(f"{name} must be a JSON object")
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise DeviceReadOnlyError(f"{label} is unavailable: {exc}") from exc
    if size > MAX_BUNDLE_JSON_BYTES:
        raise DeviceReadOnlyError(f"{label} exceeds the Phase 6 JSON size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeviceReadOnlyError(f"{label} is invalid JSON: {exc}") from exc
    return _require_object(value, label)


class HuaweiGatewayReadOnlyMount:
    """Read-only client for the owner-defined TTG Device Gateway JSON-lines protocol."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_GATEWAY_HOST,
        port: int = DEFAULT_GATEWAY_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = _require_loopback(host)
        if not 1 <= int(port) <= 65535:
            raise DeviceReadOnlyError("Huawei Gateway port must be between 1 and 65535")
        if timeout <= 0:
            raise DeviceReadOnlyError("Huawei Gateway timeout must be positive")
        self.port = int(port)
        self.timeout = float(timeout)

    @classmethod
    def from_env(cls) -> "HuaweiGatewayReadOnlyMount":
        raw_port = os.environ.get("ORIGINS_HUAWEI_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)).strip()
        raw_timeout = os.environ.get("ORIGINS_HUAWEI_GATEWAY_TIMEOUT", str(DEFAULT_TIMEOUT)).strip()
        try:
            port = int(raw_port)
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise DeviceReadOnlyError("invalid Huawei Gateway port/timeout configuration") from exc
        return cls(
            host=os.environ.get("ORIGINS_HUAWEI_GATEWAY_HOST", DEFAULT_GATEWAY_HOST),
            port=port,
            timeout=timeout,
        )

    def request(self, name: str, params: Mapping[str, Any] | None = None) -> Any:
        if name not in READ_ONLY_GATEWAY_COMMANDS:
            raise DeviceReadOnlyError(f"Phase 6 refuses non-read Huawei Gateway command {name!r}")
        request_id = str(uuid.uuid4())
        command: dict[str, Any] = {"name": name}
        if params is not None:
            command["params"] = dict(params)
        payload = {"request_id": request_id, "command": command}
        encoded = _json_bytes(payload) + b"\n"
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as stream:
                stream.settimeout(self.timeout)
                stream.sendall(encoded)
                response_bytes = self._read_line(stream)
        except (OSError, TimeoutError) as exc:
            raise DeviceReadOnlyError(f"Huawei Gateway is unavailable: {exc}") from exc
        try:
            response = json.loads(response_bytes.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeviceReadOnlyError(f"Huawei Gateway returned invalid UTF-8 JSON: {exc}") from exc
        response = _require_object(response, "Huawei Gateway response")
        if response.get("request_id") != request_id:
            raise DeviceReadOnlyError("Huawei Gateway response request_id does not match")
        if response.get("ok") is not True:
            error = response.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "GATEWAY_ERROR")
                message = str(error.get("message") or "Huawei Gateway request failed")
                raise DeviceReadOnlyError(f"{code}: {message}")
            raise DeviceReadOnlyError("Huawei Gateway returned an invalid error response")
        return response.get("result")

    def _read_line(self, stream: socket.socket) -> bytes:
        data = bytearray()
        while True:
            chunk = stream.recv(4096)
            if not chunk:
                raise DeviceReadOnlyError("Huawei Gateway closed before returning a response")
            data.extend(chunk)
            if len(data) > MAX_GATEWAY_RESPONSE_BYTES:
                raise DeviceReadOnlyError("Huawei Gateway response exceeds Phase 6 limit")
            newline = data.find(b"\n")
            if newline >= 0:
                return bytes(data[:newline])

    def health(self) -> dict[str, Any]:
        return _require_object(self.request("health"), "Huawei Gateway health")

    def doctor(self) -> dict[str, Any]:
        return _require_object(self.request("doctor"), "Huawei Gateway doctor")

    def snapshot(self) -> dict[str, Any]:
        return _require_object(self.request("snapshot"), "Huawei Gateway snapshot")

    def get_physical_session(self, session_id: str) -> dict[str, Any]:
        return _require_object(
            self.request("get_physical_session", {"session_id": str(session_id)}),
            "Huawei physical session",
        )

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        return _require_object(
            self.request("get_operation", {"operation_id": str(operation_id)}),
            "Huawei operation",
        )

    def verify_journal(self) -> dict[str, Any]:
        return _require_object(self.request("verify_journal"), "Huawei journal verification")

    def list_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        after_sequence = 0
        while len(events) < MAX_EVENT_COUNT:
            page = self.request(
                "list_events", {"after_sequence": after_sequence, "limit": 1000}
            )
            if not isinstance(page, list):
                raise DeviceReadOnlyError("Huawei Gateway event result must be an array")
            if not page:
                return events
            for raw in page:
                event = _require_object(raw, "Huawei Gateway event")
                sequence = event.get("sequence")
                if not isinstance(sequence, int) or sequence <= after_sequence:
                    raise DeviceReadOnlyError("Huawei Gateway event sequence is not strictly increasing")
                events.append(event)
                after_sequence = sequence
                if len(events) >= MAX_EVENT_COUNT:
                    break
            if len(page) < 1000:
                return events
        raise DeviceReadOnlyError("Huawei Gateway event history exceeds Phase 6 projection limit")

    def projection(self) -> dict[str, Any]:
        health = self.health()
        doctor = self.doctor()
        snapshot = self.snapshot()
        journal = self.verify_journal()
        self._enforce_owner_authority(health, doctor, snapshot, journal)
        events = self.list_events()
        endpoints: list[dict[str, Any]] = []
        contracts: list[dict[str, Any]] = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            payload = event.get("payload")
            if event_type == "endpoint_observed" and isinstance(payload, dict):
                endpoints.append(dict(payload))
            elif event_type == "contract_accepted" and isinstance(payload, dict):
                contract_type = str(payload.get("contract_type") or "")
                canonical = payload.get("canonical")
                if contract_type not in PROJECTED_CONTRACT_TYPES or not isinstance(canonical, str):
                    continue
                try:
                    contract = json.loads(canonical)
                except json.JSONDecodeError as exc:
                    raise DeviceReadOnlyError("Huawei Gateway accepted-contract journal is corrupt") from exc
                contract = _require_object(contract, "Huawei accepted contract")
                contracts.append(
                    {
                        "contract_type": contract_type,
                        "contract_sha256": payload.get("contract_sha256"),
                        "event_sequence": event.get("sequence"),
                        "physical_session_id": event.get("physical_session_id"),
                        "contract": contract,
                    }
                )
        by_type: dict[str, list[dict[str, Any]]] = {}
        for contract in contracts:
            by_type.setdefault(str(contract["contract_type"]), []).append(contract)
        return {
            "owner": "techguytool-huawei",
            "owner_repository": HUAWEI_OWNER_REPOSITORY,
            "owner_revision_recovered": HUAWEI_OWNER_REVISION,
            "available": True,
            "gateway": {
                "health": health,
                "doctor": doctor,
                "snapshot": snapshot,
                "journal": journal,
            },
            "endpoint_observations": endpoints,
            "contracts": by_type,
            "write_execution": {
                "available": False,
                "reason": "PHASE6_DEVICE_WRITE_NOT_AUTHORIZED",
            },
            "agentops_operation_link": {
                "available": False,
                "reason": "AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE",
            },
        }

    @staticmethod
    def _enforce_owner_authority(
        health: Mapping[str, Any],
        doctor: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        journal: Mapping[str, Any],
    ) -> None:
        for source_name, source in (("health", health), ("doctor", doctor), ("snapshot", snapshot)):
            if source.get("device_authority") != "none":
                raise DeviceReadOnlyError(
                    f"Huawei Gateway {source_name} expanded device_authority beyond Phase 6"
                )
            if source.get("xray_authority") != "read_only":
                raise DeviceReadOnlyError(
                    f"Huawei Gateway {source_name} no longer reports read_only X-Ray authority"
                )
        if doctor.get("journal_valid") is not True or journal.get("journal_valid") is not True:
            raise DeviceReadOnlyError("Huawei Gateway journal is not verified")


class XRayBundleReadOnlyMount:
    """Verifier/projector for one server-configured sealed TTG Device X-Ray bundle."""

    def __init__(self, bundle_dir: str | os.PathLike[str], *, signing_key_file: str = "") -> None:
        raw = str(bundle_dir or "").strip()
        if not raw:
            raise DeviceReadOnlyError("TTG Device X-Ray bundle directory is not configured")
        self.bundle_dir = Path(raw).expanduser().resolve()
        self.signing_key_file = str(signing_key_file or "").strip()

    @classmethod
    def from_env(cls) -> "XRayBundleReadOnlyMount | None":
        bundle_dir = os.environ.get("ORIGINS_XRAY_BUNDLE_DIR", "").strip()
        if not bundle_dir:
            return None
        return cls(
            bundle_dir,
            signing_key_file=os.environ.get("ORIGINS_XRAY_SIGNING_KEY_FILE", ""),
        )

    def projection(self) -> dict[str, Any]:
        if not self.bundle_dir.is_dir():
            raise DeviceReadOnlyError("TTG Device X-Ray bundle directory does not exist")
        manifest = _read_json(self.bundle_dir / "bundle_manifest.json", label="X-Ray manifest")
        signature = _read_json(self.bundle_dir / "bundle_manifest.sig", label="X-Ray signature report")
        self._verify_manifest(manifest)
        signature_projection = self._verify_signature(manifest, signature)
        evidence: dict[str, Any] = {}
        for relative in XRAY_PROJECTION_FILES:
            path = self.bundle_dir / relative
            if path.is_file():
                evidence[relative.removesuffix(".json")] = _read_json(
                    path, label=f"X-Ray {relative}"
                )
        expires_at = str(manifest.get("expires_at") or "")
        expired = self._expired(expires_at)
        return {
            "owner": "ttg-device-xray",
            "owner_repository": XRAY_OWNER_REPOSITORY,
            "owner_revision_recovered": XRAY_OWNER_REVISION,
            "available": True,
            "integrity_verified": True,
            "write_allowed": False,
            "expired": expired,
            "manifest": manifest,
            "signature": signature_projection,
            "evidence": evidence,
        }

    def _verify_manifest(self, manifest: Mapping[str, Any]) -> None:
        if manifest.get("bundle_schema_version") != "2.0":
            raise DeviceReadOnlyError("unsupported TTG Device X-Ray bundle schema")
        if manifest.get("hash_algorithm") != "sha256":
            raise DeviceReadOnlyError("TTG Device X-Ray bundle hash algorithm is unsupported")
        if manifest.get("write_allowed") is not False:
            raise DeviceReadOnlyError("TTG Device X-Ray bundle expanded write authority")
        expected_manifest_sha = str(manifest.get("manifest_sha256") or "")
        unsigned_manifest = dict(manifest)
        unsigned_manifest.pop("manifest_sha256", None)
        actual_manifest_sha = hashlib.sha256(_json_bytes(unsigned_manifest)).hexdigest()
        if not hmac.compare_digest(expected_manifest_sha, actual_manifest_sha):
            raise DeviceReadOnlyError("TTG Device X-Ray manifest SHA-256 mismatch")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > MAX_BUNDLE_FILES:
            raise DeviceReadOnlyError("TTG Device X-Ray manifest file list is invalid")
        seen: set[str] = set()
        for raw in files:
            entry = _require_object(raw, "X-Ray manifest file")
            relative = str(entry.get("path") or "")
            pure = PurePosixPath(relative)
            if not relative or pure.is_absolute() or ".." in pure.parts or relative in seen:
                raise DeviceReadOnlyError("TTG Device X-Ray manifest contains an unsafe path")
            seen.add(relative)
            path = (self.bundle_dir / Path(*pure.parts)).resolve()
            try:
                path.relative_to(self.bundle_dir)
            except ValueError as exc:
                raise DeviceReadOnlyError("TTG Device X-Ray file escaped bundle root") from exc
            if not path.is_file():
                raise DeviceReadOnlyError(f"TTG Device X-Ray evidence file is missing: {relative}")
            expected_size = entry.get("size_bytes")
            if not isinstance(expected_size, int) or expected_size < 0 or path.stat().st_size != expected_size:
                raise DeviceReadOnlyError(f"TTG Device X-Ray evidence size mismatch: {relative}")
            expected_sha = str(entry.get("sha256") or "")
            actual_sha = _sha256_file(path)
            if not hmac.compare_digest(expected_sha, actual_sha):
                raise DeviceReadOnlyError(f"TTG Device X-Ray evidence SHA-256 mismatch: {relative}")

    def _verify_signature(
        self, manifest: Mapping[str, Any], signature: Mapping[str, Any]
    ) -> dict[str, Any]:
        status = str(signature.get("status") or "")
        if status not in {"SIGNED", "UNSIGNED"}:
            raise DeviceReadOnlyError("TTG Device X-Ray signature status is invalid")
        manifest_sha = str(manifest.get("manifest_sha256") or "")
        if signature.get("manifest_sha256") != manifest_sha:
            raise DeviceReadOnlyError("TTG Device X-Ray signature report references another manifest")
        verified = False
        reason = "XRAY_BUNDLE_UNSIGNED" if status == "UNSIGNED" else "XRAY_SIGNING_KEY_NOT_CONFIGURED"
        if status == "SIGNED" and self.signing_key_file:
            key_path = Path(self.signing_key_file).expanduser().resolve()
            try:
                key = key_path.read_bytes().strip()
            except OSError as exc:
                raise DeviceReadOnlyError(f"X-Ray signing key reference is unavailable: {exc}") from exc
            if not key:
                raise DeviceReadOnlyError("X-Ray signing key reference is empty")
            expected = str(signature.get("signature_hex") or "")
            actual = hmac.new(key, _json_bytes(dict(manifest)), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, actual):
                raise DeviceReadOnlyError("TTG Device X-Ray HMAC signature mismatch")
            verified = True
            reason = ""
        return {
            "status": status,
            "algorithm": signature.get("algorithm"),
            "signer_key_id": signature.get("signer_key_id"),
            "manifest_sha256": manifest_sha,
            "cryptographically_verified": verified,
            "verification_reason": reason,
        }

    @staticmethod
    def _expired(value: str) -> bool:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DeviceReadOnlyError("TTG Device X-Ray bundle expiry is invalid") from exc
        if parsed.tzinfo is None:
            raise DeviceReadOnlyError("TTG Device X-Ray bundle expiry must be timezone-aware")
        return parsed.astimezone(timezone.utc) < datetime.now(timezone.utc)
