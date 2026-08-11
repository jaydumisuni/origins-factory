# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current implementation truth:** `CURRENT_STATE.md`
**Current authority checkpoint:** PR #12 merged; continue from `main` at/after `7454f581d9bdde84e030a9b22f9b2f1f41e06a93`

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/SECOPS_STAGE1_RECONCILIATION_PR11.md`;
4. historical `docs/SECOPS_STAGE1_VERDICT_PR11.md`;
5. `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`;
6. `docs/ADR-0013-LEASE-ISSUER-PREFLIGHT.md`;
7. current `main` source/proof;
8. owning external repositories for any mounted capability being changed.

Do not ask the owner to repeat recoverable evidence.

## Product identity lock

Origins Factory is a model-optional, evidence-native mission operating environment. It is not an OS, IDE clone, AI sidebar, dashboard, model router or replacement for its specialist systems.

Three truths remain separate:

- **Semantic:** Hunter + AgentOps.
- **Mechanical:** `originsd`, specialist Gateways, Nodes, later authorized Ptah integration.
- **Assurance:** Sergeant, X-Ray, deterministic proof, specialist governors and human acceptance.

Ownership remains:

- Hunter / Pete — mission intelligence and optional outside reasoning;
- AgentOps — semantic lifecycle/approval/completion and durable approval evidence;
- CodeOps — repository engineering and provider/model/client routing;
- Sergeant — independent engineering review;
- Origins — persistent workspace, mechanical integration and capability enforcement;
- Oracle/Lumi/X-Ray/specialist Gateways — their existing specialist boundaries.

Do not duplicate an owning engine inside Origins.

## Merged proven authority chain

### Origins Stage-1 foundation

PR #11 merged at:

```text
5a7f3cd6e73eed9326b4c6deedbf4e9658271233
```

It established:

- Hunter Intelligence Mount v1;
- `@chat` through Hunter and dormant `@memory` without shadow storage;
- model `CapabilityProposal` with mandatory owner approval/no self-approval;
- `ExecutionScope + CapabilityLease` v1.1 in Python/TypeScript/Rust;
- shared canonical/adversarial authority proof;
- no-activation guard.

Sec-Ops Stage-1 verdict after reconciliation: **PASS**.

Stage-1 PASS approves the contract model only.

### AgentOps durable approval prerequisite

Owning repo: `jaydumisuni/Hunter-AgentOps`

PR #16 merged at:

```text
721be17f1afbdf73cbc4302d89c733596d5160b6
```

Exact tested PR head:

```text
e2d6282fbcce03d6bf0bdf2b7923f5da24a71dff
```

Ubuntu Oracle proof:

```text
oracle_control/results/0000-agentops-pr16-exact-proof-20260812-0128.json
```

PASS evidence:

- 89 AgentOps pytest tests;
- AgentOps self-proof;
- durable approval restart recovery/tamper rejection;
- Origins issuance Auth/replay tests 6/6;
- repository contract.

AgentOps remains the sole owner of approval/Auth evidence. Origins must not create a shadow approval database or infer owner identity from a digest alone.

### Origins Lease Issuer Preflight v1

PR #12 merged at:

```text
7454f581d9bdde84e030a9b22f9b2f1f41e06a93
```

Exact tested PR head:

```text
3e4a8e8b3a6c0126f350e0226f948185a2b0db79
```

Hosted exact-head proof:

- Contract Spine run `31543617488`: PASS;
- Daemon Foundation run `31543617471`: PASS.

Combined Ubuntu proof against merged AgentOps:

```text
oracle_control/results/0001-origins-pr12-crossrepo-proof-20260812-0136.json
```

Receipt SHA-256:

```text
cddaa85246077bdf5df926ebbcfb7d820f886881512240e3902f74786f36f61c
```

The combined proof establishes:

- durable AgentOps approval evidence;
- restart digest continuity;
- exact one-time TTG Auth binding to the issuance context;
- Auth replay rejection;
- Origins preflight eligibility;
- no production authority activation.

Hard preflight outputs remain:

```text
issuer_enabled = false
lease_created = false
runtime_authority_activated = false
```

## Current security boundary

Still not implemented/activated:

- production lease issuer;
- durable Origins lease persistence;
- invocation-time scope/lease enforcement;
- filesystem/network sandbox;
- process-tree containment/revocation;
- browser/MCP authority;
- candidate-worktree mutation;
- generalized agent terminal authority.

Do not cite Stage-1 PASS, AgentOps durable approval, or preflight eligibility as permission to activate these surfaces.

## Stage-2 security rule

A separate **Stage-2 Sec-Ops implementation red-team is mandatory** after the real issuance/persistence/enforcement/revocation/OS containment boundary exists and before powerful model-controlled authority can be enabled.

Stage 2 must attack at minimum:

- atomic lease issuance and TOCTOU substitution;
- durable scope/lease state, revision and fence recovery;
- invocation-time current-authority evaluation;
- provider manifest/generation revalidation;
- resource-generation/path revalidation;
- symlink/junction/reparse/mount/hard-link/special-file escape;
- candidate/sibling/main worktree mutation isolation;
- Linux/Windows process-tree revocation;
- DNS/proxy/redirect/network behavior;
- persistent local MCP lifetime confinement;
- remote delegated-authority propagation;
- holder identity/generation binding;
- confused-deputy paths through Hunter/CodeOps/Oracle/providers;
- model self-disable attempts against policy/security storage.

Stage-1 PASS must never be cited as implementation-level approval.

## Next valid work

Do not reopen PR #11, SEC-001..005, AgentOps PR #16, or Origins PR #12 as active implementation.

Start a new Stage-2 slice from the merged checkpoints:

```text
recover AgentOps >= 721be17f...
recover Origins >= 7454f581...
→ design exact production lease issuance from the proven preflight evidence
→ implement lease persistence/current-generation recovery
→ bind originsd invocation to host ceiling ∩ current scope ∩ current lease ∩ provider/resource generations
→ implement revocation/fencing and OS containment
→ prove mechanically
→ independent review
→ Stage-2 Sec-Ops red-team
→ only after PASS consider activation
```

Do not re-plan Origins from scratch.

## Anti-drift rules

- Preserve the historical Stage-1 NEEDS_WORK verdict and later PASS reconciliation.
- Do not call Stage-1 contract semantics a sandbox implementation.
- Do not create shadow AgentOps or Hunter storage.
- Do not let a capability approve, mint or enlarge its own authority.
- Do not bypass `originsd`/specialist authority for convenience.
- Failed/partial attempts remain visible.
- Keep powerful authority inactive until Stage-2 implementation review passes.

## Session close rule

After substantial Origins work:

1. preserve code/proof checkpoint;
2. update `CURRENT_STATE.md`;
3. update this handoff when the next valid action changes;
4. update the product plan only for owner-accepted architecture changes;
5. update central `TTG-progress`/`TTG-ecosystem` recovery when ecosystem status changes;
6. preserve unresolved limitations explicitly;
7. leave one clean continuation point.
