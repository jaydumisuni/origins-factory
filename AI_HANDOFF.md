# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current implementation truth:** `CURRENT_STATE.md`
**Active candidate:** draft PR #11

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/SECOPS_STAGE1_RECONCILIATION_PR11.md`;
4. historical `docs/SECOPS_STAGE1_VERDICT_PR11.md`;
5. `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`;
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

PR #11 remains **draft and unmerged** until the normal post-verdict review/promotion gate completes.

It contains:

- Hunter Intelligence Mount v1;
- `@chat` reference semantics through Hunter;
- dormant `@memory` semantics without shadow storage;
- model `CapabilityProposal` with `approval_required=true` and `self_approvable=false`;
- corrected authority-contract v1.1 semantics in Python/TypeScript/Rust;
- shared canonical/adversarial authority corpus;
- CI guard proving no runtime authority activation exists yet.

## Sec-Ops stage-1 state

Historical first verdict:

```text
NEEDS_WORK
```

Historical findings:

```text
docs/SECOPS_STAGE1_VERDICT_PR11.md
```

SEC-001 through SEC-005 were corrected and re-proven.

Focused reconciliation verdict:

```text
PASS
```

Canonical reconciliation:

```text
docs/SECOPS_STAGE1_RECONCILIATION_PR11.md
```

### Closed findings

1. **SEC-001:** `parent_lease_id` removed; lease-to-lease delegation unsupported in v1.1.
2. **SEC-002:** operation identity immutable; candidate identity bind-once and non-switchable/non-clearable after binding.
3. **SEC-003:** lease binds exact `provider_id + provider_manifest_digest + provider_generation`.
4. **SEC-004:** ExecutionScope now has state/fence/revision and exact current-generation stale-scope validation.
5. **SEC-005:** network authority now uses exact `protocol + host + port` endpoints and explicit `deny_outside_endpoints` redirect policy.

Additional hardening accepted:

- holder UUID + holder generation;
- child/lease issuance chronology relative to current parent/scope generation.

## Stage-1 PASS semantics

Stage-1 PASS approves only the **authority contract model as a foundation for implementation**.

It does not approve or activate:

- production lease issuance/persistence;
- filesystem/network sandboxing;
- process-tree revocation;
- browser control;
- MCP execution;
- candidate-worktree mutation;
- generalized agent terminal authority.

## Stage-2 security rule

After real issuer/persistence/invocation enforcement/revocation/OS-provider containment exists, a separate **Stage-2 Sec-Ops implementation red-team is mandatory** before powerful model-controlled authority can be enabled.

Stage 2 must attack at minimum:

- durable AgentOps approval authenticity/replay resistance;
- trusted root/child scope issuance;
- atomic lease issuance transaction;
- scope/lease current-state/fence persistence;
- provider manifest/generation revalidation;
- current resource/path generation;
- symlink/junction/reparse/mount/hard-link/special-file escape;
- candidate/sibling/main worktree mutation isolation;
- Windows/Linux process-tree revocation;
- DNS/proxy/redirect/network behavior;
- persistent local MCP lifetime confinement;
- remote delegated-authority propagation;
- holder UUID/generation binding to real durable subjects;
- confused-deputy paths;
- model self-disable attempts against policy/security storage.

Stage-1 PASS must never be cited as implementation-level approval.

## Current stop rule

Do not jump directly into powerful capability activation merely because Stage 1 passed.

Still forbidden until their own later design/implementation gates:

- converting volatile AgentOps approval into durable lease authority;
- browser/MCP/candidate-worktree/general agent authority that bypasses accepted runtime enforcement;
- direct UI/model/Python execution bypassing `originsd` or specialist authority.

## Next valid work

Complete PR #11 promotion, not another architecture redesign:

```text
Sec-Ops Stage-1 PASS
→ freeze reconciliation/current state/handoff
→ exact-head Contract Spine + Daemon Foundation proof
→ independent Sergeant/repository review
→ promote/merge PR #11 if clean
```

After PR #11 merge, begin a **separate authority-runtime phase** starting with durable AgentOps approval evidence and production issuer/enforcement design under the accepted v1.1 model.

Do not re-plan Origins.

## Anti-drift rules

- Preserve the historical NEEDS_WORK verdict and the later PASS reconciliation; do not rewrite history.
- Do not call stage-1 contract semantics a sandbox implementation.
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
