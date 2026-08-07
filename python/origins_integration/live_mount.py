from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from origins_contracts import canonical_json

from .doctor import EngineeringMountDoctor, EngineeringMountDoctorResult
from .engineering import (
    BridgeError,
    ContractAdapter,
    EngineeringAttemptRequest,
    EngineeringBridge,
    ExternalContracts,
    OriginsClient,
)

CANONICAL_PROJECT_VERDICTS = {"PASS", "NEEDS WORK", "BLOCK"}


class MountSmokeError(BridgeError):
    """Raised when a live engineering mount smoke cannot safely proceed."""


class _ProofScope(Enum):
    FIXTURE = "fixture"
    LIVE_OWNER = "live_owner"


@dataclass(frozen=True)
class LiveEngineeringMountReceipt:
    proof_scope: str
    mount_status: str
    live_engineering_proven: bool
    repository_id: str
    repository_revision: int
    repository_head_oid: str
    operation_id: str
    doctor_surfaces: tuple[dict[str, Any], ...]
    route_session_id: str
    sergeant_command_session_id: str
    sergeant_review_session_id: str
    review_sha256: str
    project_verdict: str
    recommended_agentops_action: str

    def body_dict(self) -> dict[str, Any]:
        return {
            "proof_scope": self.proof_scope,
            "mount_status": self.mount_status,
            "live_engineering_proven": self.live_engineering_proven,
            "repository_id": self.repository_id,
            "repository_revision": self.repository_revision,
            "repository_head_oid": self.repository_head_oid,
            "operation_id": self.operation_id,
            "doctor_surfaces": [dict(surface) for surface in self.doctor_surfaces],
            "route_session_id": self.route_session_id,
            "sergeant_command_session_id": self.sergeant_command_session_id,
            "sergeant_review_session_id": self.sergeant_review_session_id,
            "review_sha256": self.review_sha256,
            "project_verdict": self.project_verdict,
            "recommended_agentops_action": self.recommended_agentops_action,
        }

    @property
    def receipt_sha256(self) -> str:
        body = canonical_json(self.body_dict()).encode("utf-8")
        return hashlib.sha256(body).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


class LiveEngineeringMount:
    """Doctor-gated read-only smoke over the actual engineering-owner bridge."""

    def __init__(
        self,
        client: OriginsClient,
        *,
        doctor: EngineeringMountDoctor,
        bridge: EngineeringBridge,
        proof_scope: _ProofScope,
    ) -> None:
        if not isinstance(proof_scope, _ProofScope):
            raise TypeError("proof_scope must be an internal Origins proof-scope token")
        self.client = client
        self.doctor = doctor
        self.bridge = bridge
        self._proof_scope = proof_scope

    @classmethod
    def production(cls, client: OriginsClient) -> "LiveEngineeringMount":
        contracts = ExternalContracts.load()
        return cls(
            client,
            doctor=EngineeringMountDoctor(client),
            bridge=EngineeringBridge(client, contracts),
            proof_scope=_ProofScope.LIVE_OWNER,
        )

    @classmethod
    def _for_fixture(
        cls,
        client: OriginsClient,
        *,
        doctor: EngineeringMountDoctor,
        contracts: ContractAdapter,
    ) -> "LiveEngineeringMount":
        return cls(
            client,
            doctor=doctor,
            bridge=EngineeringBridge(client, contracts),
            proof_scope=_ProofScope.FIXTURE,
        )

    def run(
        self,
        repository_id: str,
        *,
        config: str,
        files: tuple[str, ...] = (),
        review_mode: str = "pull_request",
    ) -> LiveEngineeringMountReceipt:
        doctor_result = self.doctor.run(repository_id)
        self._require_compatible_doctor(doctor_result)

        operation_id = f"origins-live-mount-{uuid.uuid4()}"
        attempt = self.bridge.run_attempt(
            EngineeringAttemptRequest(
                operation_id=operation_id,
                repository_id=repository_id,
                task="Verify the installed Origins engineering owner stack without project mutation",
                config=config,
                files=files,
                plan="",
                apply_plan=False,
                approval_state="not_required",
                provider_id="",
                required_capability="",
                review="required",
                review_mode=review_mode,
            )
        )

        if attempt.plan_preview is not None or attempt.plan_apply is not None:
            raise MountSmokeError("live mount smoke must not create plan/apply Sessions")
        if attempt.verdict not in {"PASS", "NEEDS WORK", "BLOCK", "UNKNOWN"}:
            raise MountSmokeError(f"unsupported project verdict: {attempt.verdict!r}")

        canonical = attempt.verdict in CANONICAL_PROJECT_VERDICTS
        live_proven = self._proof_scope is _ProofScope.LIVE_OWNER and canonical
        mount_status = "proven" if live_proven else "compatible"

        return LiveEngineeringMountReceipt(
            proof_scope=self._proof_scope.value,
            mount_status=mount_status,
            live_engineering_proven=live_proven,
            repository_id=attempt.repository_id,
            repository_revision=attempt.repository_revision,
            repository_head_oid=attempt.repository_head_oid,
            operation_id=attempt.operation_id,
            doctor_surfaces=tuple(_compact_doctor_surface(surface) for surface in doctor_result.surfaces),
            route_session_id=attempt.route.session_id,
            sergeant_command_session_id=attempt.sergeant_command.session_id,
            sergeant_review_session_id=attempt.sergeant_review.session_id,
            review_sha256=attempt.review_sha256,
            project_verdict=attempt.verdict,
            recommended_agentops_action=attempt.recommended_agentops_action,
        )

    @staticmethod
    def _require_compatible_doctor(result: EngineeringMountDoctorResult) -> None:
        if result.overall_status != "compatible":
            detail = "; ".join(result.blockers) or f"overall status is {result.overall_status}"
            raise MountSmokeError(f"engineering mount doctor is not compatible: {detail}")
        incompatible = [surface for surface in result.surfaces if surface.status != "compatible"]
        if incompatible:
            detail = "; ".join(
                f"{surface.surface}={surface.status}" for surface in incompatible
            )
            raise MountSmokeError(f"engineering mount doctor surfaces are not compatible: {detail}")
        if result.live_engineering_proven:
            raise MountSmokeError(
                "doctor-only result unexpectedly claims live engineering proof"
            )


def _compact_doctor_surface(surface: Any) -> dict[str, Any]:
    return {
        "surface": str(surface.surface),
        "status": str(surface.status),
        "version": str(surface.version),
        "session_id": str(surface.session_id),
        "evidence_sha256": str(surface.evidence_sha256),
    }
