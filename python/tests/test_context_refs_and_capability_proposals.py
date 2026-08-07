from __future__ import annotations

import inspect

import pytest

from origins_integration import capability_proposals, context_refs
from origins_integration.capability_proposals import CapabilityProposal, CapabilityProposalError
from origins_integration.context_refs import (
    ContextReferenceError,
    ContextReferenceResolver,
    extract_context_references,
    parse_context_reference,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
CHAT_ID = "origins-11111111-1111-4111-8111-111111111111-phase-4"


class FakeTransport:
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing
        self.calls: list[tuple[str, dict]] = []

    def get_workspace(self, workspace_id: str) -> dict:
        return {"workspace_id": workspace_id}

    def request(self, workspace_id: str, operation: str, payload: dict | None = None) -> dict:
        assert workspace_id == WORKSPACE_ID
        payload = payload or {}
        self.calls.append((operation, payload))
        assert operation == "chat_load"
        if self.missing:
            return {
                "transport": {"http_status": 404},
                "body": {"ok": False, "error": "CHAT_NOT_FOUND"},
            }
        return {
            "transport": {"http_status": 200},
            "body": {
                "ok": True,
                "session": {
                    "id": payload["id"],
                    "title": "Huawei recovery",
                    "messages": [
                        {"role": "user", "content": "inspect phone"},
                        {"role": "assistant", "content": "evidence recovered"},
                        {"role": "tool", "content": "must be dropped"},
                    ],
                    "createdAt": 10,
                    "updatedAt": 20,
                    "archived": False,
                    "pinned": True,
                },
            },
        }


class FakeHunter:
    def __init__(self, transport: FakeTransport) -> None:
        self.transport = transport


def test_chat_reference_parses_and_resolves_against_hunter_authority() -> None:
    reference = parse_context_reference(f"@chat:{CHAT_ID}")
    assert reference.kind == "chat"
    assert reference.authority == "hunter.chat"

    resolved = ContextReferenceResolver(FakeHunter(FakeTransport())).resolve(WORKSPACE_ID, reference)  # type: ignore[arg-type]
    assert resolved.status == "resolved"
    assert resolved.title == "Huawei recovery"
    assert resolved.payload["session_id"] == CHAT_ID
    assert resolved.payload["pinned"] is True
    assert resolved.payload["messages"] == [
        {"role": "user", "content": "inspect phone"},
        {"role": "assistant", "content": "evidence recovered"},
    ]


def test_chat_reference_not_found_is_unavailable_not_fabricated() -> None:
    reference = parse_context_reference(f"@chat:{CHAT_ID}")
    resolved = ContextReferenceResolver(FakeHunter(FakeTransport(missing=True))).resolve(  # type: ignore[arg-type]
        WORKSPACE_ID, reference
    )
    assert resolved.status == "unavailable"
    assert resolved.reason == "hunter_chat_not_found"
    assert resolved.payload == {"session_id": CHAT_ID}


def test_memory_reference_is_typed_but_storage_remains_unwired() -> None:
    reference = parse_context_reference("@memory:TECHGUYTOOL-Huawei:verlist-recovery")
    resolved = ContextReferenceResolver(FakeHunter(FakeTransport())).resolve(WORKSPACE_ID, reference)  # type: ignore[arg-type]
    assert reference.kind == "memory"
    assert reference.authority == "hunter.memory.lesson"
    assert resolved.status == "unavailable"
    assert resolved.reason == "hunter_memory_storage_unwired"
    assert resolved.payload == {
        "project": "TECHGUYTOOL-Huawei",
        "key": "verlist-recovery",
        "authority": "hunter.memory.lesson",
    }


def test_reference_extraction_deduplicates_in_message_order() -> None:
    text = (
        f"Compare @chat:{CHAT_ID} with @memory:origins-factory:runtime-proof "
        f"and reuse @chat:{CHAT_ID}"
    )
    references = extract_context_references(text)
    assert [item.kind for item in references] == ["chat", "memory"]
    assert len(references) == 2


@pytest.mark.parametrize(
    "value",
    [
        "@chat:../../escape",
        "@chat:",
        "@memory:missing-key",
        "@memory:project:../escape",
        "@unknown:item",
    ],
)
def test_malformed_context_references_fail_closed(value: str) -> None:
    with pytest.raises(ContextReferenceError):
        parse_context_reference(value)


def test_capability_proposal_maps_to_existing_agentops_owner_approval_shape() -> None:
    proposal = CapabilityProposal.create(
        workspace_id=WORKSPACE_ID,
        task_title="Recover documentation from authenticated site",
        capability_id="origins.browser.control",
        reason="The required evidence exists only in a rendered authenticated browser session.",
        expected_benefit="Avoid manual copying and preserve source-linked evidence for the operation.",
        requested_effects=("observe", "execute"),
        filesystem_read_scope=("workspace",),
        filesystem_write_scope=(),
        network_mode="allowlist",
        network_hosts=("support.example.com",),
        environment_names=("ORIGINS_BROWSER_PROFILE",),
        persistent_lease=False,
        delegated_remote_authority=False,
        alternatives=("Ask the owner to copy the page manually",),
        risks=("Authenticated browser session may expose private account data",),
        requested_by="hunter:model-route",
    )
    request = proposal.agentops_approval_request()
    assert request["mode"] == "capability_extension"
    assert request["gate"] == "owner_approval_required"
    assert request["target"] == "origins.browser.control"
    metadata = request["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["approval_required"] is True
    assert metadata["self_approvable"] is False
    assert metadata["environment_names"] == ["ORIGINS_BROWSER_PROFILE"]
    assert metadata["network_mode"] == "allowlist"


def test_capability_proposal_requires_a_reason_and_expected_benefit() -> None:
    with pytest.raises(CapabilityProposalError):
        CapabilityProposal.create(
            workspace_id=WORKSPACE_ID,
            task_title="Need a tool",
            capability_id="origins.mcp.example",
            reason="",
            expected_benefit="Useful",
            requested_effects=("observe",),
        )

    with pytest.raises(CapabilityProposalError):
        CapabilityProposal.create(
            workspace_id=WORKSPACE_ID,
            task_title="Need a tool",
            capability_id="origins.mcp.example",
            reason="Existing capabilities cannot obtain the required evidence.",
            expected_benefit="",
            requested_effects=("observe",),
        )


def test_network_and_environment_scope_fail_closed() -> None:
    with pytest.raises(CapabilityProposalError):
        CapabilityProposal.create(
            workspace_id=WORKSPACE_ID,
            task_title="Bad network proposal",
            capability_id="origins.mcp.example",
            reason="Need remote evidence.",
            expected_benefit="Retrieve it.",
            requested_effects=("observe",),
            network_mode="deny",
            network_hosts=("example.com",),
        )

    with pytest.raises(CapabilityProposalError):
        CapabilityProposal.create(
            workspace_id=WORKSPACE_ID,
            task_title="Secret smuggling",
            capability_id="origins.browser.control",
            reason="Need browser.",
            expected_benefit="Use account.",
            requested_effects=("observe",),
            environment_names=("API_KEY=secret",),
        )


def test_remote_mcp_style_authority_must_be_explicit() -> None:
    with pytest.raises(CapabilityProposalError):
        CapabilityProposal.create(
            workspace_id=WORKSPACE_ID,
            task_title="Remote MCP",
            capability_id="origins.mcp.remote",
            reason="A remote specialist service has the required capability.",
            expected_benefit="Use the specialist without rebuilding it locally.",
            requested_effects=("observe",),
            network_mode="delegated_remote",
            network_hosts=("mcp.example.com",),
            delegated_remote_authority=False,
        )


def test_reference_and_proposal_modules_have_no_execution_or_network_authority() -> None:
    source = inspect.getsource(context_refs) + inspect.getsource(capability_proposals)
    for forbidden in ("subprocess", "os.system", "requests.", "urllib.request", "httpx.", "aiohttp."):
        assert forbidden not in source
