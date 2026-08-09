# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current implementation truth:** `CURRENT_STATE.md`
**Active candidate:** draft PR #11

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. current ADRs, especially ADR-0010 through ADR-0012;
5. current PR/source/proof;
6. the owning repository for every external capability being changed.

Do not ask the owner to repeat recoverable evidence.

## Product identity lock

Origins Factory is a **model-optional, evidence-native mission operating environment** combining durable work ownership, full-stack engineering, cyber-physical control, independent verification, cross-machine continuity and controlled capability synthesis.

Origins is not an OS, IDE clone, AI sidebar, dashboard, thin desktop wrapper, model router, or replacement for specialist systems.

## Three truths

- **Semantic:** Hunter + AgentOps.
- **Mechanical:** `originsd`, specialist Gateways, Nodes, later authorized Ptah integration.
- **Assurance:** Sergeant, X-Ray, deterministic proof, specialist governors and human acceptance.

Models amplify the system. They do not manufacture mechanical success or independent assurance.

## Ownership lock

- Hunter / Pete — mission intelligence and optional outside reasoning;
- AgentOps — semantic operation lifecycle, approvals and completion;
- CodeOps — repository-aware engineering and provider/model/client routing;
- Sergeant — independent engineering review;
- X-Ray — read-first/post-operation evidence;
- Oracle — authorized browser/OS perception and control;
- Lumi — downloads/transfers;
- specialist Gateways — domain/device state and bounded execution;
- Origins — persistent workspace, mechanical integration, capability compilation/enforcement and user surfaces.

Do not duplicate an owning engine inside Origins.

## Merged proven implementation

`main` currently contains:

1. Contract Spine v1.2;
2. persistent `originsd` foundation;
3. Supervised Process Sessions;
4. Active Session Control;
5. Live Session Observation;
6. Repository/Git Sessions;
7. Engineering Assurance Bridge protocol;
8. Production Engineering Mount doctor;
9. Live Engineering Mount v1.

Read `CURRENT_STATE.md` for exact proof/limitations.

## Draft PR #11 lock

PR #11 is **not merged** and must remain draft until the security boundary is reviewed/reconciled.

It contains:

### Hunter Intelligence Mount v1

- narrow Rust-owned Hunter transport through `originsd`;
- Python semantic adapter with no Hunter token/network authority;
- Hunter chat/session remains semantic authority;
- metadata/digest transport evidence only;
- Hunter-disabled fallback;
- configured→disabled cleanup of optional `origins.hunter.transport` capability.

### Context references

```text
@chat:<hunter-session-id>
→ Hunter authority

@memory:<project>:<key>
→ typed/dormant
→ unavailable until Hunter memory storage exists
```

Do not create a shadow memory/chat database.

### CapabilityProposal

A model may explain why a missing capability would improve task delivery and propose bounded effects/resources/network/environment/persistence/delegated authority.

Invariant:

```text
approval_required = true
self_approvable = false
```

Proposal is not execution.

## Candidate authority law — ADR-0012

Current security-review candidate:

```text
host policy ceiling
    ∩ ExecutionScope
    ∩ CapabilityLease
    = effective authority
```

A model-facing resource grant uses an Origins-owned resource identity plus normalized relative prefix, not arbitrary host path authority.

Candidate validators exist separately in:

- Python `python/origins_contracts/authority.py`;
- TypeScript `typescript/authority.ts`;
- Rust `rust/origins-authority-contracts`.

They share `contracts/authority-fixtures.json` and fixed canonical hashes.

**Do not register these candidate types as active Contract Spine authority yet.**

## Approval durability block

Current AgentOps approval semantics are valid, but current in-memory `ApprovalService` persistence is insufficient to mint production security authority.

Therefore until the owning AgentOps backend supplies durable approval evidence:

- do not create a production CapabilityLease issuer;
- do not persist a shadow AgentOps approval database inside Origins;
- do not convert volatile approval into durable mechanical authority;
- do not activate browser/MCP/candidate mutation/general agent terminal capability from these candidate contracts.

Future lease issuance must bind:

```text
exact CapabilityProposal digest
+ durable AgentOps approval-record digest
+ current parent ExecutionScope
+ current host policy
+ current provider
→ bounded lease
```

## Sec-Ops continuation point

The next valid work is **security review**, not more execution capability.

Review:

```text
docs/SECOPS_REVIEW_PACKET_PR11.md
docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md
```

Requested result:

```text
PASS | NEEDS WORK | BLOCK
```

After review:

1. recover the exact Sec-Ops findings;
2. correct only evidenced defects;
3. re-run three-runtime candidate proof and all inherited Origins proof;
4. only after accepted security design, promote accepted scope/lease types into the shared Contract Spine;
5. require durable AgentOps approval evidence before implementing lease issuance;
6. then extend existing Sessions/providers with scope/lease provenance, invocation checks and revocation/fencing.

## Kilo donor lock

Do not integrate Kilo Code as a runtime dependency.

Borrow only useful donor patterns:

- candidate/session presentation;
- sibling-worktree/main-checkout denial;
- backend enforcement rather than UI-only permissions;
- invocation-time stale-handle checks;
- non-self-disablable policy;
- persistent local MCP/background-process lifetime confinement;
- explicit delegated-remote authority.

## Anti-drift rules

- Do not create another Origins master plan.
- Do not merge PR #11 merely because candidate validators are green.
- Do not call candidate authority semantics a sandbox implementation.
- Do not call fixture Hunter proof production-owner proof.
- Do not let a capability approve or activate its own upgrade.
- Do not bypass `originsd` or specialist authority for convenience.
- Do not revive `build/initial-workspace` as implementation base.
- Failed/partial attempts remain visible.

## Session close rule

After substantial Origins work:

1. preserve code/proof checkpoint;
2. update `CURRENT_STATE.md`;
3. update this handoff when the next valid action changes;
4. update the product plan only for owner-accepted architecture changes;
5. preserve unresolved limitations explicitly;
6. leave one clean continuation point.
