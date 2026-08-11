# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current merged authority checkpoint:** PR #12 merged; recovery continues from `main` at/after `7454f581d9bdde84e030a9b22f9b2f1f41e06a93`
**Security state:** Stage-1 contract model PASS; Stage-2 implementation review not yet started

## Merged proven foundation

`main` now contains:

1. Contract Spine v1.2.
2. Persistent `originsd` foundation.
3. Supervised Process Sessions.
4. Active Session Control.
5. Live Session Observation.
6. Repository/Git Sessions.
7. Engineering Assurance Bridge protocol.
8. Production Engineering Mount doctor.
9. Live Engineering Mount v1.
10. Hunter Intelligence Mount v1.
11. `@chat` reference semantics through Hunter and dormant `@memory` semantics without shadow storage.
12. model `CapabilityProposal` with mandatory owner approval and no self-approval.
13. Sec-Ops-accepted `ExecutionScope + CapabilityLease` v1.1 contract model.
14. non-activating Lease Issuer Preflight v1.
15. cross-repo proof tool joining AgentOps durable approval + one-time Auth to Origins preflight without activating authority.

## Stage-1 authority state

Origins PR #11 merged at:

```text
5a7f3cd6e73eed9326b4c6deedbf4e9658271233
```

Sec-Ops Stage-1 contract review: **PASS** after SEC-001 through SEC-005 reconciliation.

Canonical Stage-1 records:

- `docs/SECOPS_STAGE1_VERDICT_PR11.md` — historical NEEDS_WORK verdict;
- `docs/SECOPS_STAGE1_RECONCILIATION_PR11.md` — focused PASS reconciliation;
- `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md` — accepted v1.1 authority contract boundary.

Stage-1 PASS approves the contract model only. It is not implementation-level approval for runtime authority.

## Durable AgentOps prerequisite — complete

Owning repository: `jaydumisuni/Hunter-AgentOps`

PR #16 merged at:

```text
721be17f1afbdf73cbc4302d89c733596d5160b6
```

Exact tested PR head:

```text
e2d6282fbcce03d6bf0bdf2b7923f5da24a71dff
```

Live Ubuntu proof host:

```text
kratos-HP-290-G4-Microtower-PC
```

Oracle result:

```text
oracle_control/results/0000-agentops-pr16-exact-proof-20260812-0128.json
```

Proof state:

- exact SHA checkout: PASS;
- full AgentOps pytest: 89 passed;
- AgentOps self-proof: PASS;
- durable approval restart recovery: PASS;
- durable approval tamper rejection: PASS;
- Origins issuance Auth/replay tests: 6 passed;
- AgentOps repository contract: PASS.

AgentOps remains the owner of durable approval/authentication evidence. Origins does not own a shadow approval authority.

## Lease Issuer Preflight v1 — complete and merged

Origins PR #12 merged at:

```text
7454f581d9bdde84e030a9b22f9b2f1f41e06a93
```

Exact tested PR head:

```text
3e4a8e8b3a6c0126f350e0226f948185a2b0db79
```

Hosted proof on that exact head:

- Origins Contract Spine run `31543617488`: PASS;
- Origins Daemon Foundation run `31543617471`: PASS.

Combined Ubuntu proof used merged AgentOps `721be17f1afbdf73cbc4302d89c733596d5160b6` plus exact Origins PR head `3e4a8e8b3a6c0126f350e0226f948185a2b0db79`.

Oracle result:

```text
oracle_control/results/0001-origins-pr12-crossrepo-proof-20260812-0136.json
```

Receipt SHA-256:

```text
cddaa85246077bdf5df926ebbcfb7d820f886881512240e3902f74786f36f61c
```

Combined proof state:

- durable AgentOps approval: PASS;
- restart digest continuity: PASS;
- exact one-time Auth binding: PASS;
- Auth replay rejection: PASS;
- Origins preflight eligibility: PASS;
- `issuer_enabled = false`;
- `lease_created = false`;
- `runtime_authority_activated = false`.

Canonical preflight design:

```text
docs/ADR-0013-LEASE-ISSUER-PREFLIGHT.md
```

## Current non-activation boundary

Still absent/inactive by design:

- production CapabilityLease issuer;
- durable Origins lease persistence/recovery;
- invocation-time scope/lease runtime enforcement;
- filesystem/network sandbox enforcement;
- OS process-tree containment/revocation;
- browser authority;
- MCP authority;
- parallel candidate-worktree mutation;
- generalized agent terminal authority.

Do not infer runtime authority from Stage-1 PASS, AgentOps durability, or preflight eligibility.

## Stage-2 security gate — mandatory

The next authority phase may implement the real issuance/enforcement boundary, but powerful authority must remain inactive until a separate Stage-2 Sec-Ops red-team attacks the actual implementation.

Stage 2 must cover at minimum:

- atomic proposal/approval/Auth/scope/provider/policy/resource-to-lease issuance;
- durable lease state/revision/fence recovery;
- current-authority revalidation at every invocation;
- revocation and stale-handle/process behavior;
- provider manifest/generation changes;
- resource-generation/path revalidation;
- symlink/junction/reparse/mount/hard-link/special-file containment;
- sibling/main worktree mutation isolation;
- Linux/Windows process-tree revocation;
- DNS/proxy/redirect/network behavior;
- persistent local MCP lifetime confinement;
- remote delegated-authority propagation;
- holder identity/generation binding;
- confused-deputy paths through Hunter/CodeOps/Oracle/providers;
- model self-disable attempts against policy/security storage.

## Next valid work

Do **not** reopen PR #11, SEC-001..005, AgentOps PR #16, or Origins PR #12 as unfinished work.

Continue with a new Stage-2 implementation slice:

```text
recover merged AgentOps + Origins checkpoints
→ design production lease-issuance transaction from proven preflight evidence
→ implement persistence/enforcement/revocation behind existing host ceilings
→ prove Linux/Windows containment semantics
→ independent review
→ Stage-2 Sec-Ops implementation red-team
→ only after Stage-2 PASS consider powerful capability activation
```

## Other current limitations

Still not proven/implemented:

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
