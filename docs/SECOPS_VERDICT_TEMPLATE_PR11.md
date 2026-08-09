# Sec-Ops Verdict Template — Origins PR #11

Use this structure when returning the authority-boundary review so findings can be reconciled mechanically rather than becoming another free-form design thread.

```yaml
review_target:
  repository: jaydumisuni/origins-factory
  pull_request: 11
  authority_adr: docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md
  review_packet: docs/SECOPS_REVIEW_PACKET_PR11.md

verdict: PASS | NEEDS_WORK | BLOCK

summary: |
  Concise security conclusion.

merge_blockers:
  - id: SEC-001
    severity: critical | high | medium | low
    title: ""
    affected_contracts: []
    affected_enforcement_points: []
    attack_path: ""
    required_change: ""
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

accepted_invariants:
  - ""

explicit_non_claims_confirmed:
  - "no production lease issuer in PR #11"
  - "no filesystem/network sandbox activation in PR #11"
  - "no browser/MCP/candidate-worktree mutation activation in PR #11"

final_gate:
  secops_reconciled: true | false
  ready_for_sergeant_review: true | false
  ready_for_pr11_merge: true | false
```

## Verdict semantics

- **PASS** — candidate contract boundary is acceptable for PR #11; later runtime enforcement may proceed under the listed required implementation controls.
- **NEEDS_WORK** — bounded contract/review corrections are required before PR #11 can merge.
- **BLOCK** — a core trust-boundary assumption is unsafe and must be redesigned before proceeding.

A PASS does not mean browser/MCP/network/filesystem sandboxing is already implemented. It means the candidate authority model is acceptable as the contract foundation for those later implementations.
