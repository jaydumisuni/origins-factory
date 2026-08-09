# PR #11 — Sec-Ops Review-Ready Checkpoint

Status: **review package complete; PR remains draft; runtime authority remains inactive.**

This checkpoint exists to prevent future work from adding lease/runtime authority while the security model is awaiting adversarial review.

## Review package

Sec-Ops should read in this order:

1. `docs/SECOPS_REVIEW_PACKET_PR11.md`
2. `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`
3. `docs/SECOPS_ENFORCEMENT_POINT_MATRIX_PR11.md`
4. `docs/SECOPS_AUTHORITY_THREAT_MODEL_PR11.md`
5. `docs/SECOPS_VERDICT_TEMPLATE_PR11.md`
6. `docs/ADR-0011-CONTEXT-REFERENCES-CAPABILITY-PROPOSALS.md`

Executable candidate semantics:

- `python/origins_contracts/authority.py`
- `typescript/authority.ts`
- `rust/origins-authority-contracts/`

Shared proof corpora:

- `contracts/authority-fixtures.json`
- `contracts/authority-adversarial-fixtures.json`

No-activation guard:

- `python/tests/test_authority_inactive.py`

## What is proven before review

- candidate `execution_scope` validates consistently in Python, TypeScript and Rust;
- candidate `capability_lease` validates consistently in Python, TypeScript and Rust;
- canonical valid fixture SHA-256 values are fixed across runtimes;
- shared invalid contract fixtures fail closed;
- shared adversarial mutation/relation corpus runs in all three runtimes;
- child scopes cannot expand parent resource/network/environment/process authority;
- parent denies cannot be dropped;
- leases cannot expand scope resource/network/environment/persistence authority;
- proposal and approval digests are mandatory candidate lease fields;
- Hunter optional capability synchronization does not leave a configured→disabled stale capability;
- all inherited Origins daemon/runtime proofs remain required.

## What is deliberately impossible in this PR

The branch must fail proof if any of these appear before Sec-Ops reconciliation:

- `originsd` dependency on `origins-authority-contracts`;
- `/v1/scopes`, `/v1/leases`, `/v1/authority`, or equivalent activation route;
- production lease mint/issue/activate function;
- runtime filesystem/network sandbox activation from candidate leases;
- browser/MCP/candidate-worktree mutation authority derived from a lease.

## Required next evidence

No more authority implementation is valid merely from design reasoning.

Next evidence must be a Sec-Ops verdict using:

`docs/SECOPS_VERDICT_TEMPLATE_PR11.md`

Allowed next outcomes:

```text
PASS
→ reconcile any non-blocking requirements
→ final exact-head proof
→ Sergeant / merge review as required

NEEDS_WORK
→ make only finding-backed contract/review corrections
→ extend adversarial proof for each finding
→ return to Sec-Ops

BLOCK
→ redesign the affected trust boundary
→ do not activate runtime authority
```

## Explicit stop rule

Until Sec-Ops is reconciled, do not implement:

- production lease persistence/issuance;
- AgentOps approval-to-lease activation;
- ProcessPolicy lease enforcement;
- filesystem/network sandbox providers;
- process-tree revocation semantics;
- candidate worktree mutation;
- MCP execution;
- browser control based on the candidate lease model.
