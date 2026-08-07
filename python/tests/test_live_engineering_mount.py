from __future__ import annotations

from types import SimpleNamespace

import pytest

from origins_integration.doctor import EngineeringMountDoctorResult, MountSurfaceResult
from origins_integration.engineering import MechanicalResult
from origins_integration.live_mount import (
    LiveEngineeringMount,
    MountSmokeError,
    _ProofScope,
)


class FakeDoctor:
    def __init__(self, result: EngineeringMountDoctorResult) -> None:
        self.result = result
        self.calls = 0

    def run(self, repository_id: str) -> EngineeringMountDoctorResult:
        self.calls += 1
        assert repository_id == self.result.repository_id
        return self.result


class FakeBridge:
    def __init__(self, verdict: str = "PASS") -> None:
        self.verdict = verdict
        self.calls = 0
        self.requests = []

    def run_attempt(self, request):
        self.calls += 1
        self.requests.append(request)
        mechanical = lambda name: MechanicalResult(  # noqa: E731 - compact deterministic fixture
            session_id=name,
            session={"stdout_sha256": "a" * 64},
            output={"stdout": "fixture"},
            payload={"ok": True},
        )
        action = {
            "PASS": "complete_candidate",
            "NEEDS WORK": "correct",
            "BLOCK": "block",
            "UNKNOWN": "unresolved",
        }[self.verdict]
        return SimpleNamespace(
            repository_id=request.repository_id,
            repository_revision=9,
            repository_head_oid="b" * 40,
            operation_id=request.operation_id,
            route=mechanical("route-session"),
            plan_preview=None,
            plan_apply=None,
            sergeant_command=mechanical("command-session"),
            sergeant_review=mechanical("review-session"),
            review_sha256="c" * 64,
            verdict=self.verdict,
            recommended_agentops_action=action,
        )


class DummyClient:
    pass


def doctor_result(status: str = "compatible") -> EngineeringMountDoctorResult:
    surfaces = tuple(
        MountSurfaceResult(name, status, "1.0.0", f"{name} {status}")
        for name in ("agentops_python", "codeops_python", "codeops_cli", "sergeant_cli")
    )
    blockers = () if status == "compatible" else (f"agentops_python: {status}",)
    return EngineeringMountDoctorResult(
        repository_id="repo-1",
        repository_revision=7,
        repository_head_oid="a" * 40,
        surfaces=surfaces,
        overall_status=status,
        live_engineering_proven=False,
        blockers=blockers,
    )


def test_incompatible_doctor_blocks_before_bridge_attempt() -> None:
    doctor = FakeDoctor(doctor_result("missing"))
    bridge = FakeBridge()
    mount = LiveEngineeringMount(
        DummyClient(), doctor=doctor, bridge=bridge, proof_scope=_ProofScope.FIXTURE
    )
    with pytest.raises(MountSmokeError):
        mount.run("repo-1", config="/integration/codeops.json")
    assert doctor.calls == 1
    assert bridge.calls == 0


def test_fixture_scope_can_never_become_live_proven() -> None:
    doctor = FakeDoctor(doctor_result())
    bridge = FakeBridge("PASS")
    mount = LiveEngineeringMount(
        DummyClient(), doctor=doctor, bridge=bridge, proof_scope=_ProofScope.FIXTURE
    )
    receipt = mount.run("repo-1", config="/integration/codeops.json")
    assert receipt.proof_scope == "fixture"
    assert receipt.mount_status == "compatible"
    assert receipt.live_engineering_proven is False
    assert receipt.project_verdict == "PASS"
    request = bridge.requests[0]
    assert request.config == "/integration/codeops.json"
    assert request.plan == ""
    assert request.apply_plan is False
    assert request.provider_id == ""
    assert receipt.as_dict().get("config") is None


def test_unknown_verdict_does_not_prove_even_in_live_owner_scope() -> None:
    mount = LiveEngineeringMount(
        DummyClient(),
        doctor=FakeDoctor(doctor_result()),
        bridge=FakeBridge("UNKNOWN"),
        proof_scope=_ProofScope.LIVE_OWNER,
    )
    receipt = mount.run("repo-1", config="C:\\Hunter\\CodeOps\\config.json")
    assert receipt.proof_scope == "live_owner"
    assert receipt.mount_status == "compatible"
    assert receipt.live_engineering_proven is False
    assert receipt.project_verdict == "UNKNOWN"


def test_canonical_live_owner_verdict_can_prove_mount() -> None:
    for verdict in ("PASS", "NEEDS WORK", "BLOCK"):
        mount = LiveEngineeringMount(
            DummyClient(),
            doctor=FakeDoctor(doctor_result()),
            bridge=FakeBridge(verdict),
            proof_scope=_ProofScope.LIVE_OWNER,
        )
        receipt = mount.run("repo-1", config="codeops.json")
        assert receipt.mount_status == "proven"
        assert receipt.live_engineering_proven is True
        assert receipt.project_verdict == verdict


def test_production_constructor_is_the_live_owner_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel_contracts = object()

    monkeypatch.setattr(
        "origins_integration.live_mount.ExternalContracts.load", lambda: sentinel_contracts
    )
    mount = LiveEngineeringMount.production(DummyClient())
    assert mount._proof_scope is _ProofScope.LIVE_OWNER
    assert mount.bridge.contracts is sentinel_contracts


def test_constructor_rejects_forged_string_scope() -> None:
    with pytest.raises(TypeError):
        LiveEngineeringMount(
            DummyClient(),
            doctor=FakeDoctor(doctor_result()),
            bridge=FakeBridge(),
            proof_scope="live_owner",  # type: ignore[arg-type]
        )
