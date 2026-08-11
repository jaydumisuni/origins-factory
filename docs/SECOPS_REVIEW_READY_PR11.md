# PR #11 — Sec-Ops Review-Ready Checkpoint

Status: **stage-1 review package complete; PR remains draft; runtime authority remains inactive.**

This checkpoint exists to prevent future work from adding lease/runtime authority while the contract model is awaiting adversarial review, and to prevent a future stage-1 PASS from being misrepresented as implementation approval.

## Review stages

Origins authority security review is explicitly two-stage:

```text
Stage 1 — Contract-model review (PR #11)
  Can ExecutionScope + CapabilityLease safely describe bounded authority?

Stage 2 — Implementation red-team (future activation gate)
  Does the actual issuer/enforcement/revocation/containment code enforce that authority under attack?
```

A stage-1 `PASS` may allow PR #11 to merge after reconciliation and exact-head proof. It does **not** permit powerful model-controlled capabilities to be enabled.

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

## What is proven before stage-1 review

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

The refined review package that adds mitigation classification and the mandatory stage-2 implementation gate passed both full proof suites on exact head:

`3636ed8d666f61b18a966351ef0fb5a7d1419c49`

- Origins Contract Spine: PASS
- Origins Daemon Foundation: PASS

## What stage-1 Sec-Ops must distinguish

For filesystem/resource/worktree/network findings, Sec-Ops must classify whether an attack is:

- `CLOSED_BY_CONTRACT`;
- `REQUIRES_RUNTIME_RECHECK`;
- `REQUIRES_OS_PROVIDER_ENFORCEMENT`;
- `REQUIRES_PROVIDER_ENFORCEMENT`;
- `OPEN_DESIGN_GAP`.

This prevents a flat theoretical threat list from obscuring which attacks the contract already removes by construction and which remain live at runtime.

## What is deliberately impossible in this PR

The branch must fail proof if any of these appear before Sec-Ops reconciliation:

- `originsd` dependency on `origins-authority-contracts`;
- `/v1/scopes`, `/v1/leases`, `/v1/authority`, or equivalent activation route;
- production lease mint/issue/activate function;
- runtime filesystem/network sandbox activation from candidate leases;
- browser/MCP/candidate-worktree mutation authority derived from a lease.

## Required next evidence

No more authority implementation is valid merely from design reasoning.

Next evidence must be a **stage-1 Sec-Ops verdict** using:

`docs/SECOPS_VERDICT_TEMPLATE_PR11.md`

Allowed next outcomes:

```text
PASS
→ reconcile any non-blocking requirements
→ final exact-head proof
→ Sergeant / merge review as required
→ PR #11 may merge
→ implementation work may begin under accepted constraints
→ stage-2 Sec-Ops remains mandatory before activation

NEEDS_WORK
→ make only finding-backed contract/review corrections
→ extend adversarial proof for each finding
→ return to Sec-Ops

BLOCK
→ redesign the affected trust boundary
→ do not activate runtime authority
```

## Mandatory future stage-2 gate

After the actual lease issuer, persistence, invocation-time enforcement, revocation/fencing and OS/provider containment are implemented, Sec-Ops must perform a new adversarial review against the real code and proofs.

Stage 2 must cover at minimum:

- approval-to-lease TOCTOU/substitution;
- resource rebinding and path races;
- symlink/junction/reparse/mount escape;
- stale handles and fence replay;
- restart during issuance/invocation/revocation;
- process-tree survival after revocation;
- DNS/proxy/redirect behavior;
- persistent local MCP lifetime confinement;
- remote delegated authority propagation;
- confused-deputy paths;
- self-disable attempts.

Until stage 2 is reconciled, powerful model-controlled capabilities remain activation-blocked.

## Explicit stop rule

Until stage-1 Sec-Ops is reconciled, do not implement:

- production lease persistence/issuance;
- AgentOps approval-to-lease activation;
- ProcessPolicy lease enforcement;
- filesystem/network sandbox providers;
- process-tree revocation semantics;
- candidate worktree mutation;
- MCP execution;
- browser control based on the candidate lease model.
