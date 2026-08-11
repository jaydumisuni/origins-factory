# Sec-Ops Verdict Template — Origins PR #11

Use this structure when returning the **stage-1 contract-model authority review** so findings can be reconciled mechanically rather than becoming another free-form design thread.

A stage-1 PASS is not implementation approval. A second Sec-Ops implementation red-team is mandatory before powerful model-controlled capabilities are enabled.

```yaml
review_target:
  repository: jaydumisuni/origins-factory
  pull_request: 11
  authority_adr: docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md
  review_packet: docs/SECOPS_REVIEW_PACKET_PR11.md
  review_stage: contract_model

verdict: PASS | NEEDS_WORK | BLOCK

summary: |
  Concise security conclusion for the contract model only.

merge_blockers:
  - id: SEC-001
    severity: critical | high | medium | low
    title: ""
    affected_contracts: []
    affected_enforcement_points: []
    attack_path: ""
    required_change: ""
    required_proof: ""

mitigation_classification:
  - id: MIT-001
    attack: ""
    classification: CLOSED_BY_CONTRACT | REQUIRES_RUNTIME_RECHECK | REQUIRES_OS_PROVIDER_ENFORCEMENT | REQUIRES_PROVIDER_ENFORCEMENT | OPEN_DESIGN_GAP
    reason: ""
    required_enforcement_point: ""
    required_proof: ""

required_contract_changes:
  - id: CONTRACT-001
    field_or_rule: ""
    reason: ""
    required_semantics: ""

required_runtime_enforcement:
  - id: RUNTIME-001
    enforcement_point: ""
    required_behavior: ""
    os_specific: true | false

required_adversarial_tests:
  - id: TEST-001
    attack: ""
    expected_fail_closed_behavior: ""

deferred_os_specific_work:
  - id: OS-001
    platform: linux | windows | macos | provider-specific
    requirement: ""
    blocks_pr11_merge: true | false
    blocks_stage2_activation: true | false

accepted_invariants:
  - ""

stage2_implementation_review:
  required: true
  activation_blocked_until_reconciled: true
  minimum_targets:
    - approval_to_lease_issuance_transaction
    - invocation_time_resource_resolution
    - stale_handle_and_fence_replay
    - restart_during_issuance_invocation_revocation
    - process_tree_revocation
    - filesystem_worktree_escape
    - dns_proxy_redirect_enforcement
    - persistent_local_mcp_lifetime
    - delegated_remote_authority_propagation
    - confused_deputy_paths
    - self_disable_attempts
  additional_requirements: []

explicit_non_claims_confirmed:
  - "no production lease issuer in PR #11"
  - "no filesystem/network sandbox activation in PR #11"
  - "no browser/MCP/candidate-worktree mutation activation in PR #11"
  - "stage-1 PASS does not approve future implementation code"

final_gate:
  stage1_secops_reconciled: true | false
  contract_model_accepted: true | false
  ready_for_sergeant_review: true | false
  ready_for_pr11_merge: true | false
  stage2_secops_required: true
  powerful_capability_activation_allowed: false
```

## Verdict semantics

- **PASS** — candidate contract boundary is acceptable for PR #11; later implementation may proceed only under the listed runtime/OS/provider requirements and remains subject to stage-2 Sec-Ops review.
- **NEEDS_WORK** — bounded contract/review corrections are required before PR #11 can merge.
- **BLOCK** — a core trust-boundary assumption is unsafe and must be redesigned before proceeding.

## Mitigation classification semantics

- **CLOSED_BY_CONTRACT** — current contract representation/invariants prevent the attack class by construction if validators are correctly enforced.
- **REQUIRES_RUNTIME_RECHECK** — contract is sufficient to describe authority, but safety depends on current invocation-time resolution/revalidation.
- **REQUIRES_OS_PROVIDER_ENFORCEMENT** — safety depends on platform containment primitives not representable by contract validation alone.
- **REQUIRES_PROVIDER_ENFORCEMENT** — an external/local provider such as browser or MCP must enforce the restriction throughout its lifetime.
- **OPEN_DESIGN_GAP** — the authority contract itself is insufficient and must change before implementation.

## Two-stage rule

A stage-1 PASS only approves the **contract model as a foundation**. It does not approve code that does not yet exist.

Before terminal/browser/MCP/candidate-worktree or comparable model-controlled authority becomes generally enabled, the implemented issuer, enforcement, revocation and containment boundary must receive its own stage-2 Sec-Ops adversarial review and reconciled verdict.
