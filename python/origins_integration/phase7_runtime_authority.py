from __future__ import annotations

from typing import Mapping

from .capability_evolution import CapabilityEvolutionError
from .phase7_runtime_mcp import Phase7Runtime as _McpPhase7Runtime
from .phase7_runtime_mcp import Phase7RuntimeError


class Phase7Runtime(_McpPhase7Runtime):
    """Public Phase 7 runtime with no client-reasserted AgentOps authorization state.

    AgentOps approval IDs and engineering subjects are read only from durable Origins
    bindings that were populated from AgentOps MCP/RPC evidence. The HTTP/UI caller
    therefore cannot choose or modify already-approved execution semantics.
    """

    def create_child_upgrade_operation(self, evolution_id: str) -> dict[str, object]:
        binding = self.approvals.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps capability approval binding")
        approval_id = str(binding.get("approval_id") or "").strip()
        if not approval_id:
            raise Phase7RuntimeError("durable AgentOps capability approval binding omitted approval_id")
        return super().create_child_upgrade_operation(evolution_id, approval_id)

    def implement_candidate(self, evolution_id: str) -> dict[str, object]:
        binding = self.engineering_approvals.get(evolution_id)
        if binding is None:
            raise CapabilityEvolutionError("evolution has no durable AgentOps engineering approval binding")
        subject = binding.get("subject")
        if not isinstance(subject, Mapping) or not subject:
            raise Phase7RuntimeError("durable engineering approval binding omitted the exact subject")
        return super().implement_candidate(evolution_id, dict(subject))
