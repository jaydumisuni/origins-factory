# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged implementation:** `main` through Live Engineering Mount v1
**Active candidate:** draft PR #11 — Hunter Intelligence Mount + context/proposal layer + authority-contract candidate

## Merged proven foundation

1. Contract Spine v1.2.
2. Persistent `originsd` foundation.
3. Supervised Process Sessions.
4. Active Session Control.
5. Live Session Observation.
6. Repository/Git Sessions.
7. Engineering Assurance Bridge protocol.
8. Production Engineering Mount doctor.
9. Live Engineering Mount v1.

## PR #11 candidate

Implemented but not merged:

- Hunter Intelligence Mount v1 through Rust-owned `originsd` transport;
- Python Hunter semantic adapter with no Hunter credential/network authority;
- `@chat:<hunter-session-id>` through Hunter authority;
- dormant `@memory:<project>:<key>` with no shadow memory store;
- model `CapabilityProposal` with mandatory owner approval and no self-approval;
- candidate `ExecutionScope + CapabilityLease` validators in Python, TypeScript and isolated Rust;
- shared canonical/adversarial authority corpus;
- CI no-activation guard proving candidate authority is not wired into `originsd` runtime enforcement;
- optional Hunter capability synchronization, including configured→disabled cleanup.

## Sec-Ops stage-1 result

The actual contract-model attack review is complete.

```text
VERDICT: NEEDS_WORK
```

Canonical verdict:

```text
docs/SECOPS_STAGE1_VERDICT_PR11.md
```

The overall `ExecutionScope + CapabilityLease` direction is viable, but PR #11 must not merge until these five contract-level blockers are corrected:

1. **SEC-001 — parent lease delegation gap**
   - `parent_lease_id` exists but has no enforceable child-lease monotonicity relation.
   - Preferred v1 correction: remove lease-to-lease delegation until a real child-lease contract exists.

2. **SEC-002 — operation/candidate identity laundering**
   - child scopes currently constrain Workspace/parent authority but not `operation_id` / `candidate_id` transitions.
   - operation identity must remain stable; candidate binding must be explicitly one-way and non-switchable.

3. **SEC-003 — provider semantic substitution**
   - lease binds `capability_id` but not exact provider identity/manifest generation.
   - future lease must bind provider identity + provider manifest digest or equivalent recoverable authority-input binding.

4. **SEC-004 — ExecutionScope lifecycle/fencing gap**
   - scope has revision/expiry but no complete revocation/stale-reference model.
   - choose immutable scope generations + separate revocation, or add explicit scope state/fence semantics.

5. **SEC-005 — network authority under-specified**
   - `host[:port]` is insufficiently precise for generic authority because protocol/transport and omitted-port semantics are ambiguous.
   - network endpoint authority must be explicit before implementation.

Additional hardening required:

- canonical, non-recyclable lease holder identity;
- relational issuance chronology between parent scope, child scope and lease.

## Accepted mitigation classification

- raw absolute path / `..` / backslash representation attacks — **CLOSED_BY_CONTRACT**;
- symlink/junction/reparse/mount/hard-link/special-file escape — **REQUIRES_OS_PROVIDER_ENFORCEMENT**;
- resource-ID rebinding — **REQUIRES_RUNTIME_RECHECK**, and becomes **OPEN_DESIGN_GAP** if resource IDs can be recycled/rebound without generation binding;
- sibling worktree/main-checkout mutation — **REQUIRES_RUNTIME_RECHECK + OS/provider enforcement**;
- DNS/redirect/proxy behavior — **REQUIRES_PROVIDER/OS ENFORCEMENT**;
- ambiguous protocol/port authority — **OPEN_DESIGN_GAP**;
- stale lease handle — **REQUIRES_RUNTIME_RECHECK** using lease state/fence;
- stale parent scope — **OPEN_DESIGN_GAP** until SEC-004 is resolved;
- process-tree survival — **REQUIRES_OS_PROVIDER_ENFORCEMENT**;
- confused deputy through Hunter/CodeOps/Oracle/provider — **REQUIRES_PROVIDER ENFORCEMENT** with requester authority propagation.

## Security stop rule

Until stage-1 findings are reconciled and the corrected exact head is re-reviewed, do **not** implement:

- production lease persistence/issuance;
- AgentOps approval-to-lease activation;
- `ProcessPolicy` lease enforcement;
- filesystem/network sandbox providers;
- process-tree revocation semantics;
- candidate worktree mutation;
- MCP execution;
- browser control based on the candidate lease model.

## Next valid work

Only finding-backed contract corrections are valid:

```text
SEC-001 .. SEC-005
    -> update authority contracts in Python / TypeScript / Rust
    -> extend shared adversarial fixtures for every finding
    -> prove exact cross-runtime canonical/error equivalence
    -> run all inherited Origins runtime proofs
    -> focused Sec-Ops stage-1 reconciliation
```

A future stage-1 `PASS` approves only the contract model as an implementation foundation.

A **stage-2 Sec-Ops implementation red-team remains mandatory** after the real issuer, persistence, invocation-time enforcement, revocation/fencing and OS/provider containment exist, before terminal/browser/MCP/candidate-worktree authority can be enabled.

## Other current limitations

Still not proven/implemented:

- durable AgentOps approval persistence;
- production CapabilityLease issuer;
- scope/lease runtime binding;
- filesystem/network sandbox enforcement;
- OS process-tree containment;
- browser provider;
- MCP provider;
- parallel candidate-worktree mutation;
- generalized agent terminal authority;
- actual production Hunter-owner credential proof;
- durable Hunter Project Memory storage;
- React Workspace UI;
- Ptah runtime integration.
