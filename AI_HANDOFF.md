# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current implementation truth:** `CURRENT_STATE.md`
**Active candidate:** draft PR #11

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/SECOPS_STAGE1_VERDICT_PR11.md`;
4. `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`;
5. `docs/SECOPS_REVIEW_PACKET_PR11.md`;
6. current PR/source/proof;
7. owning external repositories for any mounted capability being changed.

Do not ask the owner to repeat recoverable evidence.

## Product identity lock

Origins Factory is a model-optional, evidence-native mission operating environment. It is not an OS, IDE clone, AI sidebar, dashboard, model router or replacement for its specialist systems.

Three truths remain separate:

- **Semantic:** Hunter + AgentOps.
- **Mechanical:** `originsd`, specialist Gateways, Nodes, later authorized Ptah integration.
- **Assurance:** Sergeant, X-Ray, deterministic proof, specialist governors and human acceptance.

Ownership remains:

- Hunter / Pete — mission intelligence and optional outside reasoning;
- AgentOps — semantic lifecycle/approval/completion;
- CodeOps — repository engineering and provider/model/client routing;
- Sergeant — independent engineering review;
- Origins — persistent workspace, mechanical integration and capability enforcement;
- Oracle/Lumi/X-Ray/specialist Gateways — their existing specialist boundaries.

Do not duplicate an owning engine inside Origins.

## Merged proven implementation

`main` contains:

1. Contract Spine v1.2;
2. persistent `originsd` foundation;
3. Supervised Process Sessions;
4. Active Session Control;
5. Live Session Observation;
6. Repository/Git Sessions;
7. Engineering Assurance Bridge protocol;
8. Production Engineering Mount doctor;
9. Live Engineering Mount v1.

## Draft PR #11

PR #11 remains **draft and unmerged**.

It contains:

- Hunter Intelligence Mount v1;
- `@chat` reference semantics through Hunter;
- dormant `@memory` semantics without shadow storage;
- model `CapabilityProposal` with `approval_required=true` and `self_approvable=false`;
- candidate `ExecutionScope + CapabilityLease` semantics in Python/TypeScript/Rust;
- shared canonical/adversarial authority corpus;
- CI guard proving no runtime authority activation exists yet.

## Sec-Ops stage-1 verdict

The actual contract-model attack review returned:

```text
NEEDS_WORK
```

Canonical findings:

```text
docs/SECOPS_STAGE1_VERDICT_PR11.md
```

Five merge blockers must be corrected before PR #11 can be accepted:

1. **SEC-001:** `parent_lease_id` has no enforceable child-lease monotonicity semantics.
2. **SEC-002:** child scopes can currently relabel `operation_id` / `candidate_id` without explicit relation rules.
3. **SEC-003:** lease is not bound to exact provider identity/manifest generation.
4. **SEC-004:** `ExecutionScope` lifecycle/fencing semantics are incomplete.
5. **SEC-005:** generic network authority is under-specified by `host[:port]` alone.

Also harden:

- lease holder identity so it is canonical and non-recyclable;
- issuance chronology across parent scope, child scope and lease.

## Current stop rule

Do not implement runtime authority while the stage-1 contract findings remain open.

Specifically do not add:

- production lease persistence/issuance;
- AgentOps approval-to-lease activation;
- `ProcessPolicy` lease enforcement;
- filesystem/network sandbox providers;
- process-tree revocation semantics;
- candidate worktree mutation;
- MCP execution;
- browser control based on the candidate lease model.

## Next valid work

Only bounded finding-backed corrections:

```text
SEC-001 .. SEC-005
    -> correct Python / TypeScript / Rust candidate semantics
    -> extend shared adversarial corpus
    -> prove same canonical JSON/SHA/error semantics
    -> re-run all inherited Origins proofs
    -> return exact head for focused Sec-Ops stage-1 reconciliation
```

Do not re-plan Origins.

## Two-stage security rule

A future **stage-1 PASS** means only that the authority contract model is acceptable to implement.

After real issuer/persistence/enforcement/revocation/containment exists, a separate **stage-2 Sec-Ops red-team against the actual implementation is mandatory** before powerful model-controlled terminal/browser/MCP/candidate-worktree authority can be enabled.

## Anti-drift rules

- Do not merge PR #11 while the current `NEEDS_WORK` findings remain unresolved.
- Do not call candidate authority semantics a sandbox implementation.
- Do not create a shadow AgentOps approval database.
- Do not create a shadow Hunter chat/memory database.
- Do not let a capability approve, mint or enlarge its own authority.
- Do not bypass `originsd`/specialist authority for convenience.
- Failed/partial attempts remain visible.

## Session close rule

After substantial Origins work:

1. preserve code/proof checkpoint;
2. update `CURRENT_STATE.md`;
3. update this handoff when the next valid action changes;
4. update the product plan only for owner-accepted architecture changes;
5. preserve unresolved limitations explicitly;
6. leave one clean continuation point.
