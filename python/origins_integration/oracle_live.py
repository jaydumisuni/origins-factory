from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from websockets.sync.client import connect

SCHEMA = "oracle.live.v1"
MAGIC = b"ORL1"
VERSION = 1
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
DEFAULT_MAX_TRANSFER_BYTES = 1024 * 1024 * 1024
DEFAULT_CHUNK_BYTES = 256 * 1024
DEFAULT_WINDOW_BYTES = 4 * 1024 * 1024
REQUIRED_REMOTE_METHODS = frozenset(
    {
        "filesystem.stat",
        "filesystem.hash",
        "filesystem.download.start",
    }
)


class OracleLiveError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _frame(kind: str, **values: Any) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA,
        "frameId": str(uuid.uuid4()),
        "sentAt": _timestamp(),
        "kind": kind,
        **values,
    }


def _live_ws_url(base_url: str, *, peer_id: str, node_id: str) -> str:
    raw = str(base_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OracleLiveError("ORACLE_LIVE_URL must be an absolute http/https origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OracleLiveError("Oracle Live URL must not embed credentials/query/fragment")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urllib.parse.urlencode({"role": "client", "peerId": peer_id, "nodeId": node_id})
    return urllib.parse.urlunparse((scheme, parsed.netloc, "/live/ws", "", query, ""))


def _safe_remote_path(value: str) -> str:
    path = str(value or "")
    if not path or len(path) > 4096 or "\x00" in path:
        raise OracleLiveError("remote path is invalid")
    return path


def _safe_basename(remote_path: str) -> str:
    text = remote_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "remote-file"
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "remote-file"
    return text[:180]


def _decode_binary(raw: bytes) -> tuple[dict[str, Any], bytes]:
    if len(raw) < 8 or raw[:4] != MAGIC or raw[4] != VERSION or raw[5] != 0:
        raise OracleLiveError("Oracle ORL1 binary frame is invalid")
    header_length = struct.unpack(">H", raw[6:8])[0]
    if header_length <= 0 or len(raw) < 8 + header_length:
        raise OracleLiveError("Oracle ORL1 header length is invalid")
    header_text = raw[8 : 8 + header_length].decode("utf-8")
    header = json.loads(header_text)
    if not isinstance(header, dict):
        raise OracleLiveError("Oracle ORL1 header must be an object")
    payload = raw[8 + header_length :]
    if int(header.get("payloadLength", -1)) != len(payload):
        raise OracleLiveError("Oracle ORL1 payload length mismatch")
    return header, payload


@dataclass(frozen=True, slots=True)
class OracleRemoteFileReceipt:
    node_id: str
    session_id: str
    stream_id: str
    remote_path: str
    local_path: str
    bytes_transferred: int
    sha256: str
    chunks: int

    def projection(self) -> dict[str, Any]:
        return {
            "schema_version": "origins.oracle-remote-file-receipt.v1",
            "owner": "oracle",
            "node_id": self.node_id,
            "session_id": self.session_id,
            "stream_id": self.stream_id,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "bytes_transferred": self.bytes_transferred,
            "sha256": self.sha256,
            "chunks": self.chunks,
            "artifact_candidate": {
                "schema_version": "origins.oracle-artifact-candidate.v1",
                "owner": "oracle",
                "owner_node_id": self.node_id,
                "owner_session_id": self.session_id,
                "path": self.local_path,
                "filename": Path(self.local_path).name,
                "total_bytes": self.bytes_transferred,
                "sha256": self.sha256,
            },
        }


class OracleLiveConnection:
    """Minimal client for the frozen oracle.live.v1 workstation read/transfer surface."""

    def __init__(
        self,
        *,
        base_url: str,
        node_id: str,
        token: str,
        peer_id: str | None = None,
        timeout: float = 15.0,
        connector: Callable[..., Any] = connect,
    ):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.node_id = str(node_id or "").strip()
        self.token = str(token or "").strip()
        self.peer_id = peer_id or f"origins-phase5-{uuid.uuid4()}"
        self.timeout = max(1.0, min(60.0, float(timeout)))
        self.connector = connector
        self.socket: Any | None = None
        self.connection_id = ""

        if not self.node_id or len(self.node_id) > 160:
            raise OracleLiveError("ORIGINS_ORACLE_NODE_ID is required and must be <= 160 characters")
        if not self.token:
            raise OracleLiveError("Oracle Live token is required")

    def __enter__(self) -> "OracleLiveConnection":
        uri = _live_ws_url(self.base_url, peer_id=self.peer_id, node_id=self.node_id)
        self.socket = self.connector(
            uri,
            additional_headers={"Authorization": f"Bearer {self.token}"},
            open_timeout=self.timeout,
            close_timeout=3,
            max_size=None,
        )
        self._send(
            _frame(
                "hello",
                role="client",
                peerId=self.peer_id,
                supportedVersions=[SCHEMA],
                capabilities=[
                    "node.ping",
                    "node.capabilities",
                    "filesystem.stat",
                    "filesystem.hash",
                    "filesystem.download.start",
                ],
            )
        )
        welcome = self._next_control(lambda value: value.get("kind") == "welcome")
        if welcome.get("selectedVersion") != SCHEMA:
            raise OracleLiveError("Oracle Live selected an unsupported protocol version")
        self.connection_id = str(welcome.get("connectionId") or "")
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self.socket is not None:
            try:
                self.socket.close(1000, "Origins Phase 5 client complete")
            except Exception:
                pass
            self.socket = None

    def _send(self, value: dict[str, Any]) -> None:
        if self.socket is None:
            raise OracleLiveError("Oracle Live connection is not open")
        self.socket.send(_canonical_json(value))

    def _recv(self, timeout: float | None = None) -> str | bytes:
        if self.socket is None:
            raise OracleLiveError("Oracle Live connection is not open")
        try:
            value = self.socket.recv(timeout=timeout or self.timeout)
        except Exception as exc:
            raise OracleLiveError(f"Oracle Live receive failed: {exc}") from exc
        if not isinstance(value, (str, bytes)):
            raise OracleLiveError("Oracle Live emitted an unsupported WebSocket message type")
        return value

    def _next_control(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        while True:
            raw = self._recv()
            if isinstance(raw, bytes):
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise OracleLiveError("Oracle Live emitted invalid control JSON") from exc
            if not isinstance(value, dict):
                raise OracleLiveError("Oracle Live control message must be an object")
            if predicate(value):
                return value

    def _send_request(self, session_id: str, method: str, params: dict[str, Any]) -> str:
        request_id = str(uuid.uuid4())
        self._send(
            _frame(
                "request",
                sessionId=session_id,
                requestId=request_id,
                method=method,
                params=params,
            )
        )
        return request_id

    def request(self, session_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._send_request(session_id, method, params)
        response = self._next_control(
            lambda value: value.get("kind") == "response" and value.get("requestId") == request_id
        )
        if not bool(response.get("ok")):
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            code = str(error.get("code") or "ORACLE_LIVE_REQUEST_FAILED")
            message = str(error.get("message") or method)
            raise OracleLiveError(f"{code}: {message}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise OracleLiveError(f"Oracle Live {method} result must be an object")
        return result

    def verify_node(self, session_id: str) -> dict[str, Any]:
        ping = self.request(session_id, "node.ping", {"client": "origins-phase5"})
        if str(ping.get("nodeId") or "") != self.node_id:
            raise OracleLiveError("Oracle Live routed to a different Node identity")
        return ping

    def capabilities(self, session_id: str) -> dict[str, Any]:
        self.verify_node(session_id)
        capabilities = self.request(session_id, "node.capabilities", {})
        methods = capabilities.get("methods")
        if not isinstance(methods, list):
            raise OracleLiveError("Oracle Node capability response has no method inventory")
        missing = sorted(REQUIRED_REMOTE_METHODS.difference(str(item) for item in methods))
        if missing:
            raise OracleLiveError(f"Oracle Node is missing required file capabilities: {', '.join(missing)}")
        return capabilities

    def download_file(
        self,
        *,
        session_id: str,
        remote_path: str,
        destination_root: Path,
        max_bytes: int,
    ) -> OracleRemoteFileReceipt:
        remote_path = _safe_remote_path(remote_path)
        self.capabilities(session_id)
        stat_value = self.request(session_id, "filesystem.stat", {"path": remote_path})
        if not bool(stat_value.get("isFile")):
            raise OracleLiveError("Oracle remote retrieval requires a regular file")
        size = int(stat_value.get("size") or 0)
        if size < 0 or size > max_bytes:
            raise OracleLiveError("Oracle remote file exceeds the approved transfer limit")
        hash_value = self.request(session_id, "filesystem.hash", {"path": remote_path})
        expected_sha = str(hash_value.get("sha256") or "").lower()
        if not SHA256_RE.fullmatch(expected_sha):
            raise OracleLiveError("Oracle remote file hash is invalid")

        destination_root.mkdir(parents=True, exist_ok=True)
        destination_root = destination_root.resolve()
        transfer_id = str(uuid.uuid4())
        stream_id = f"origins-download-{uuid.uuid4()}"
        final_path = destination_root / f"{transfer_id}-{_safe_basename(remote_path)}"
        partial_path = destination_root / f".{transfer_id}.partial"
        digest = hashlib.sha256()
        received = 0
        next_sequence = 0
        response_value: dict[str, Any] | None = None
        close_value: dict[str, Any] | None = None

        self._send(
            _frame(
                "stream.open",
                sessionId=session_id,
                streamId=stream_id,
                direction="download",
                contentType="application/octet-stream",
                initialWindowBytes=DEFAULT_WINDOW_BYTES,
            )
        )
        request_id = self._send_request(
            session_id,
            "filesystem.download.start",
            {"streamId": stream_id, "path": remote_path, "chunkSize": DEFAULT_CHUNK_BYTES},
        )
        try:
            with partial_path.open("xb") as output:
                while response_value is None or close_value is None:
                    raw = self._recv(timeout=30.0)
                    if isinstance(raw, bytes):
                        header, payload = _decode_binary(raw)
                        if header.get("streamId") != stream_id:
                            continue
                        sequence = int(header.get("sequence", -1))
                        offset = int(header.get("offset", -1))
                        if sequence != next_sequence or offset != received:
                            raise OracleLiveError("Oracle download stream sequence/offset mismatch")
                        if received + len(payload) > max_bytes:
                            raise OracleLiveError("Oracle download stream exceeded the approved transfer limit")
                        output.write(payload)
                        digest.update(payload)
                        received += len(payload)
                        self._send(
                            _frame(
                                "ack",
                                scope="stream",
                                id=stream_id,
                                throughSequence=sequence,
                                windowBytes=DEFAULT_WINDOW_BYTES,
                            )
                        )
                        next_sequence += 1
                        continue

                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise OracleLiveError("Oracle Live control message must be an object")
                    if value.get("kind") == "response" and value.get("requestId") == request_id:
                        if not bool(value.get("ok")):
                            error = value.get("error") if isinstance(value.get("error"), dict) else {}
                            raise OracleLiveError(
                                f"{error.get('code') or 'ORACLE_DOWNLOAD_FAILED'}: "
                                f"{error.get('message') or remote_path}"
                            )
                        response_value = value.get("result") if isinstance(value.get("result"), dict) else {}
                    elif value.get("kind") == "stream.close" and value.get("streamId") == stream_id:
                        close_value = value
                output.flush()
                os.fsync(output.fileno())

            actual_sha = digest.hexdigest()
            response_sha = str((response_value or {}).get("sha256") or "").lower()
            close_sha = str((close_value or {}).get("sha256") or "").lower()
            response_bytes = int((response_value or {}).get("bytes") or received)
            if received != size or response_bytes != received:
                raise OracleLiveError("Oracle download byte count does not match remote stat/result")
            if actual_sha != expected_sha or response_sha != expected_sha or close_sha != expected_sha:
                raise OracleLiveError("Oracle download SHA-256 verification failed")
            os.replace(partial_path, final_path)
            return OracleRemoteFileReceipt(
                node_id=self.node_id,
                session_id=session_id,
                stream_id=stream_id,
                remote_path=remote_path,
                local_path=str(final_path),
                bytes_transferred=received,
                sha256=actual_sha,
                chunks=next_sequence,
            )
        except Exception:
            try:
                partial_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise


class OracleRemoteNodeMount:
    """Read-only Origins mount over Oracle's frozen remote Node/file transfer contract."""

    def __init__(
        self,
        *,
        base_url: str,
        node_id: str,
        token: str,
        transfer_root: Path,
        max_transfer_bytes: int = DEFAULT_MAX_TRANSFER_BYTES,
        connection_factory: Callable[..., OracleLiveConnection] = OracleLiveConnection,
    ):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.node_id = str(node_id or "").strip()
        self.token = str(token or "").strip()
        self.transfer_root = Path(transfer_root)
        self.max_transfer_bytes = max(1, min(int(max_transfer_bytes), 16 * DEFAULT_MAX_TRANSFER_BYTES))
        self.connection_factory = connection_factory
        if not self.base_url or not self.node_id or not self.token:
            raise OracleLiveError("Oracle remote Node mount requires URL, Node ID, and local token reference")

    @classmethod
    def from_env(cls) -> "OracleRemoteNodeMount | None":
        base_url = str(os.environ.get("ORACLE_LIVE_URL") or "").strip()
        node_id = str(os.environ.get("ORIGINS_ORACLE_NODE_ID") or os.environ.get("ORACLE_LIVE_NODE_ID") or "").strip()
        token = str(os.environ.get("ORACLE_LIVE_TOKEN") or "").strip()
        token_file = str(os.environ.get("ORACLE_LIVE_TOKEN_FILE") or "").strip()
        if not token and token_file:
            try:
                token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise OracleLiveError(f"Oracle Live token file is unavailable: {exc}") from exc
        if not base_url and not node_id and not token:
            return None
        transfer_root = Path(os.environ.get("ORIGINS_REMOTE_TRANSFER_ROOT") or ".origins/remote-transfers")
        max_bytes = int(os.environ.get("ORIGINS_ORACLE_MAX_TRANSFER_BYTES") or DEFAULT_MAX_TRANSFER_BYTES)
        return cls(
            base_url=base_url,
            node_id=node_id,
            token=token,
            transfer_root=transfer_root,
            max_transfer_bytes=max_bytes,
        )

    def _connection(self) -> OracleLiveConnection:
        return self.connection_factory(base_url=self.base_url, node_id=self.node_id, token=self.token)

    def snapshot(self) -> dict[str, Any]:
        session_id = f"origins-node-inspect-{uuid.uuid4()}"
        with self._connection() as client:
            capabilities = client.capabilities(session_id)
        methods = [str(item) for item in capabilities.get("methods", [])]
        return {
            "owner": "oracle",
            "available": True,
            "node_id": self.node_id,
            "platform": capabilities.get("platform"),
            "arch": capabilities.get("arch"),
            "hostname": capabilities.get("hostname"),
            "file_retrieval": all(item in methods for item in REQUIRED_REMOTE_METHODS),
            "remote_application_attachment": {
                "available": False,
                "reason": "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE",
            },
        }

    def retrieve_file(self, remote_path: str, *, approved: bool) -> dict[str, Any]:
        if not approved:
            raise OracleLiveError("remote file retrieval requires explicit approval")
        session_id = f"origins-file-{uuid.uuid4()}"
        with self._connection() as client:
            receipt = client.download_file(
                session_id=session_id,
                remote_path=_safe_remote_path(remote_path),
                destination_root=self.transfer_root,
                max_bytes=self.max_transfer_bytes,
            )
        return receipt.projection()
