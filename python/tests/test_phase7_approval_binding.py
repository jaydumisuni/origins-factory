from __future__ import annotations

from pathlib import Path

import pytest

from origins_integration.capability_evolution import CapabilityEvolutionError
from origins_integration.phase7_runtime import Phase7RuntimeError, _find_pending_owner_approval
from origins_integration.capability_evolution_approvals import (
    EvolutionApprovalBindings,
    EvolutionEngineeringApprovalBindings,
)

D = "d" * 64


def evidence(approval_id: str, status: str) -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "status": status,
        "durable": True,
        "request_digest": D,
        "metadata_digest": "e" * 64,
        "record_digest": "" if status == "pending" else "f" * 64,
        "ledger_event_digest": "1" * 64,
        "request": {"approval_id": approval_id},
        "record": None if status == "pending" else {"decision": status},
    }


def test_binding_survives_restart_and_advances_to_approved(tmp_path: Path) -> None:
    path = tmp_path / "phase7.sqlite"
    first = EvolutionApprovalBindings(path)
    pending = first.bind("evolution-7", evidence("approval-7", "pending"))
    assert pending["status"] == "pending"

    second = EvolutionApprovalBindings(path)
    recovered = second.get("evolution-7")
    assert recovered is not None
    assert recovered["approval_id"] == "approval-7"
    approved = second.bind("evolution-7", evidence("approval-7", "approved"))
    assert approved["status"] == "approved"
    assert second.require_approved("evolution-7", "approval-7")["request_digest"] == D


def test_pending_or_approved_binding_cannot_be_replaced(tmp_path: Path) -> None:
    bindings = EvolutionApprovalBindings(tmp_path / "phase7.sqlite")
    bindings.bind("evolution-7", evidence("approval-7", "pending"))
    with pytest.raises(CapabilityEvolutionError, match="cannot replace"):
        bindings.bind("evolution-7", evidence("approval-other", "pending"))
    bindings.bind("evolution-7", evidence("approval-7", "approved"))
    with pytest.raises(CapabilityEvolutionError, match="cannot replace"):
        bindings.bind("evolution-7", evidence("approval-other", "rejected"))


def test_rejected_binding_can_be_replaced_by_new_request(tmp_path: Path) -> None:
    bindings = EvolutionApprovalBindings(tmp_path / "phase7.sqlite")
    bindings.bind("evolution-7", evidence("approval-old", "rejected"))
    replacement = bindings.bind("evolution-7", evidence("approval-new", "pending"))
    assert replacement["approval_id"] == "approval-new"
    assert replacement["status"] == "pending"


def test_engineering_binding_survives_restart_with_exact_subject(tmp_path: Path) -> None:
    path = tmp_path / "phase7.sqlite"
    subject = {"repository_id": "repo-7", "task": "bounded edit", "apply_plan": True}
    first = EvolutionEngineeringApprovalBindings(path)
    first.bind("evolution-7", subject=subject, evidence=evidence("engineering-7", "approved"))

    second = EvolutionEngineeringApprovalBindings(path)
    recovered = second.require_approved("evolution-7", subject)
    assert recovered["approval_id"] == "engineering-7"
    assert recovered["status"] == "approved"


def test_engineering_approval_cannot_authorize_changed_subject(tmp_path: Path) -> None:
    bindings = EvolutionEngineeringApprovalBindings(tmp_path / "phase7.sqlite")
    original = {"repository_id": "repo-7", "task": "bounded edit", "apply_plan": True}
    changed = {"repository_id": "repo-7", "task": "different edit", "apply_plan": True}
    bindings.bind("evolution-7", subject=original, evidence=evidence("engineering-7", "approved"))
    with pytest.raises(CapabilityEvolutionError, match="engineering request changed"):
        bindings.require_approved("evolution-7", changed)


def test_capability_approval_binding_is_not_engineering_approval(tmp_path: Path) -> None:
    path = tmp_path / "phase7.sqlite"
    capability = EvolutionApprovalBindings(path)
    engineering = EvolutionEngineeringApprovalBindings(path)
    capability.bind("evolution-7", evidence("capability-7", "approved"))
    subject = {"repository_id": "repo-7", "task": "bounded edit", "apply_plan": True}
    with pytest.raises(CapabilityEvolutionError, match="no durable AgentOps engineering approval"):
        engineering.require_approved("evolution-7", subject)


class _PendingService:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items

    def list_pending(self) -> list[dict[str, object]]:
        return self.items


def _pending(approval_id: str, metadata: dict[str, object]) -> dict[str, object]:
    return {"request": {"approval_id": approval_id, "metadata": metadata}, "record": None, "approved": False}


def test_pending_owner_approval_recovery_is_exact_and_ambiguous_matches_fail() -> None:
    expected = {"origins_approval_kind": "capability", "evolution_id": "evolution-7"}
    service = _PendingService([
        _pending("other", {"origins_approval_kind": "capability", "evolution_id": "other"}),
        _pending("match", expected),
    ])
    assert _find_pending_owner_approval(service, expected) == "match"
    duplicate = _PendingService([_pending("a", expected), _pending("b", expected)])
    with pytest.raises(Phase7RuntimeError, match="multiple pending"):
        _find_pending_owner_approval(duplicate, expected)


def test_concurrent_first_capability_binding_cannot_replace_pending_binding(tmp_path: Path) -> None:
    import threading

    path = tmp_path / "phase7.sqlite"
    bindings = EvolutionApprovalBindings(path)
    start = threading.Barrier(3)
    errors: list[Exception] = []

    def bind(approval_id: str) -> None:
        start.wait(timeout=5)
        try:
            bindings.bind("evolution-7", evidence(approval_id, "pending"))
        except Exception as exc:  # expected loser
            errors.append(exc)

    threads = [threading.Thread(target=bind, args=(approval_id,)) for approval_id in ("approval-a", "approval-b")]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert len(errors) == 1
    assert "cannot replace" in str(errors[0])
    stored = EvolutionApprovalBindings(path).get("evolution-7")
    assert stored is not None and stored["approval_id"] in {"approval-a", "approval-b"}
