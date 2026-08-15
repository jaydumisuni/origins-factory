from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from origins_integration.oracle_live import (
    MAGIC,
    SCHEMA,
    VERSION,
    OracleLiveConnection,
    OracleLiveError,
    OracleRemoteNodeMount,
    _canonical_json,
    _decode_binary,
)


def control(kind: str, **values: Any) -> str:
    return _canonical_json(
        {
            "schemaVersion": SCHEMA,
            "frameId": "frame-test",
            "sentAt": "2026-08-15T00:00:00.000Z",
            "kind": kind,
            **values,
        }
    )


def binary(stream_id: str, sequence: int, offset: int, payload: bytes) -> bytes:
    header = {
        "schemaVersion": SCHEMA,
        "kind": "stream.chunk",
        "streamId": stream_id,
        "sequence": sequence,
        "offset": offset,
        "final": False,
        "payloadLength": len(payload),
    }
    encoded = _canonical_json(header).encode("utf-8")
    return MAGIC + bytes([VERSION, 0]) + struct.pack(">H", len(encoded)) + encoded + payload


class FakeOracleSocket:
    def __init__(self, payload: bytes, *, node_id: str, bad_sequence: bool = False):
        self.payload = payload
        self.node_id = node_id
        self.bad_sequence = bad_sequence
        self.sent: list[dict[str, Any]] = []
        self.welcome_sent = False
        self.pending_request: dict[str, Any] | None = None
        self.download_stage = 0
        self.closed = False

    def send(self, value: str | bytes) -> None:
        if isinstance(value, bytes):
            return
        parsed = json.loads(value)
        self.sent.append(parsed)
        if parsed.get("kind") == "request":
            self.pending_request = parsed
            if parsed.get("method") == "filesystem.download.start":
                self.download_stage = 1

    def recv(self, timeout: float | None = None) -> str | bytes:  # noqa: ARG002
        if not self.welcome_sent:
            self.welcome_sent = True
            return control(
                "welcome",
                connectionId="connection-test",
                selectedVersion=SCHEMA,
                heartbeatIntervalMs=10_000,
                maxInFlightRequests=16,
                maxUnackedStreamBytes=4 * 1024 * 1024,
                resumeWindowMs=30_000,
            )

        request = self.pending_request
        if request is None:
            raise TimeoutError("no pending fake Oracle request")
        request_id = request["requestId"]
        method = request["method"]

        if method == "node.ping":
            self.pending_request = None
            return control(
                "response",
                sessionId=request["sessionId"],
                requestId=request_id,
                ok=True,
                result={"nodeId": self.node_id, "echo": request["params"]},
            )
        if method == "node.capabilities":
            self.pending_request = None
            return control(
                "response",
                sessionId=request["sessionId"],
                requestId=request_id,
                ok=True,
                result={
                    "methods": [
                        "filesystem.stat",
                        "filesystem.hash",
                        "filesystem.download.start",
                    ],
                    "platform": "linux",
                    "arch": "x64",
                    "hostname": self.node_id,
                    "roots": ["/home/kratos"],
                },
            )
        if method == "filesystem.stat":
            self.pending_request = None
            return control(
                "response",
                sessionId=request["sessionId"],
                requestId=request_id,
                ok=True,
                result={"size": len(self.payload), "isFile": True, "isDirectory": False},
            )
        if method == "filesystem.hash":
            self.pending_request = None
            return control(
                "response",
                sessionId=request["sessionId"],
                requestId=request_id,
                ok=True,
                result={"sha256": hashlib.sha256(self.payload).hexdigest()},
            )
        if method == "filesystem.download.start":
            stream_id = request["params"]["streamId"]
            if self.download_stage == 1:
                self.download_stage = 2
                sequence = 1 if self.bad_sequence else 0
                return binary(stream_id, sequence, 0, self.payload)
            if self.download_stage == 2:
                self.download_stage = 3
                return control(
                    "stream.close",
                    streamId=stream_id,
                    finalSequence=0,
                    sha256=hashlib.sha256(self.payload).hexdigest(),
                )
            self.pending_request = None
            return control(
                "response",
                sessionId=request["sessionId"],
                requestId=request_id,
                ok=True,
                result={
                    "streamId": stream_id,
                    "bytes": len(self.payload),
                    "sha256": hashlib.sha256(self.payload).hexdigest(),
                    "chunks": 1,
                },
            )
        raise AssertionError(f"unexpected fake Oracle method {method}")

    def close(self, code: int = 1000, reason: str = "") -> None:  # noqa: ARG002
        self.closed = True


class FakeConnector:
    def __init__(self, payload: bytes, *, node_id: str, bad_sequence: bool = False):
        self.payload = payload
        self.node_id = node_id
        self.bad_sequence = bad_sequence
        self.calls: list[dict[str, Any]] = []
        self.sockets: list[FakeOracleSocket] = []

    def __call__(self, uri: str, **kwargs: Any) -> FakeOracleSocket:
        self.calls.append({"uri": uri, **kwargs})
        socket = FakeOracleSocket(self.payload, node_id=self.node_id, bad_sequence=self.bad_sequence)
        self.sockets.append(socket)
        return socket


def connection_factory(connector: FakeConnector):
    def make(**kwargs: Any) -> OracleLiveConnection:
        return OracleLiveConnection(connector=connector, **kwargs)

    return make


def test_orl1_decoder_rejects_bad_length() -> None:
    frame = binary("stream-1", 0, 0, b"abc")
    header, payload = _decode_binary(frame)
    assert header["streamId"] == "stream-1"
    assert payload == b"abc"
    with pytest.raises(OracleLiveError, match="payload length"):
        _decode_binary(frame[:-1])


def test_remote_mount_binds_exact_node_and_does_not_expose_token(tmp_path: Path) -> None:
    payload = b"phase5-oracle-transfer\x00bytes"
    connector = FakeConnector(payload, node_id="kratos-node")
    mount = OracleRemoteNodeMount(
        base_url="https://oracle.example.test",
        node_id="kratos-node",
        token="super-secret-live-token",
        transfer_root=tmp_path,
        connection_factory=connection_factory(connector),
    )

    snapshot = mount.snapshot()
    assert snapshot == {
        "owner": "oracle",
        "available": True,
        "node_id": "kratos-node",
        "platform": "linux",
        "arch": "x64",
        "hostname": "kratos-node",
        "file_retrieval": True,
        "remote_application_attachment": {
            "available": False,
            "reason": "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE",
        },
    }
    assert connector.calls[0]["additional_headers"] == {
        "Authorization": "Bearer super-secret-live-token"
    }
    assert "super-secret-live-token" not in json.dumps(snapshot)
    assert "nodeId=kratos-node" in connector.calls[0]["uri"]


def test_remote_retrieval_requires_approval_and_verifies_stream(tmp_path: Path) -> None:
    payload = b"remote artifact bytes" * 300
    connector = FakeConnector(payload, node_id="kratos-node")
    mount = OracleRemoteNodeMount(
        base_url="https://oracle.example.test",
        node_id="kratos-node",
        token="secret",
        transfer_root=tmp_path,
        connection_factory=connection_factory(connector),
    )

    with pytest.raises(OracleLiveError, match="explicit approval"):
        mount.retrieve_file("/home/kratos/result.bin", approved=False)

    receipt = mount.retrieve_file("/home/kratos/result.bin", approved=True)
    assert receipt["owner"] == "oracle"
    assert receipt["node_id"] == "kratos-node"
    assert receipt["bytes_transferred"] == len(payload)
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert Path(receipt["local_path"]).read_bytes() == payload
    candidate = receipt["artifact_candidate"]
    assert candidate["owner"] == "oracle"
    assert candidate["sha256"] == receipt["sha256"]
    assert candidate["path"] == receipt["local_path"]

    sent = [item for socket in connector.sockets for item in socket.sent]
    assert any(item.get("kind") == "ack" and item.get("scope") == "stream" for item in sent)
    assert not any(item.get("method") in {"filesystem.write", "process.start", "terminal.exec"} for item in sent)


def test_remote_node_identity_substitution_fails_closed(tmp_path: Path) -> None:
    connector = FakeConnector(b"x", node_id="wrong-node")
    mount = OracleRemoteNodeMount(
        base_url="https://oracle.example.test",
        node_id="expected-node",
        token="secret",
        transfer_root=tmp_path,
        connection_factory=connection_factory(connector),
    )
    with pytest.raises(OracleLiveError, match="different Node identity"):
        mount.snapshot()


def test_remote_stream_sequence_mismatch_removes_partial_file(tmp_path: Path) -> None:
    connector = FakeConnector(b"tampered-order", node_id="kratos-node", bad_sequence=True)
    mount = OracleRemoteNodeMount(
        base_url="https://oracle.example.test",
        node_id="kratos-node",
        token="secret",
        transfer_root=tmp_path,
        connection_factory=connection_factory(connector),
    )
    with pytest.raises(OracleLiveError, match="sequence/offset mismatch"):
        mount.retrieve_file("/home/kratos/result.bin", approved=True)
    assert list(tmp_path.glob("*.partial")) == []
    assert list(tmp_path.iterdir()) == []
