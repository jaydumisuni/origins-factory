# Origins Factory — Current State

**Recorded:** 2026-08-09
**Architecture version:** 1.0.0 — accepted product/architecture authority
**Canonical merged implementation:** `main` through Live Engineering Mount v1
**Active candidate:** draft PR #11 — Hunter Intelligence Mount + context/proposal layer + ExecutionScope/CapabilityLease security-review candidate

## Contribution status

Current PR #11 contributes **New implementation + Correction + Verification**, but remains **candidate** until review and merge.

## Merged proven foundation

1. Contract Spine v1.2 — Rust/Python/TypeScript canonical contracts and exact equivalence.
2. `originsd` persistence foundation — loopback auth, SQLite durability, capability state, hash-chained journal, tamper detection and restart recovery.
3. Supervised Process Sessions v1 — bounded argv execution, cleared environment, root/executable policy, durable output evidence.
4. Active Session Control v1 — asynchronous acceptance, cancellation and event replay.
5. Live Session Observation v1 — one-copy retained output and reconnectable byte/event cursors.
6. Repository/Git Sessions v1 — read-first Repository/worktree/common-dir/HEAD/status/diff truth.
7. Engineering Assurance Bridge v1 — AgentOps/CodeOps/Sergeant protocol through real `originsd`.
8. Production Engineering Mount doctor — compatibility classification without self-install/repair.
9. Live Engineering Mount v1 — fresh Repository truth, controlled live-owner smoke path, fixture non-promotion and canonical receipt SHA-256.

## PR #11 — current proven candidate

### Hunter Intelligence Mount v1

Implemented on the draft branch:

- Rust-owned Hunter HTTP transport under `originsd`;
- no arbitrary Hunter URL/path authority;
- Hunter bearer credential remains out of Python, argv, SQLite content and journal payloads;
- Workspace-bound Python Hunter semantic mount;
- Hunter remains conversation/session authority;
- successful and failed transport attempts retain metadata/digest evidence rather than raw response bodies;
- Hunter-disabled operation leaves existing Origins mechanical services healthy;
- optional `origins.hunter.transport` capability is synchronized with actual runtime configuration, including configured→disabled removal.

The actual production Hunter owner credential is **not** proven by CI fixtures.

### Context references and Project Memory boundary

Implemented dormant semantics:

```text
@chat:<hunter-session-id>
→ resolves through Hunter chat authority

@memory:<project>:<key>
→ typed now
→ reports unavailable until Hunter runtime memory storage is wired
```

Origins does not create a second chat or Project Memory database.

### CapabilityProposal

A model may propose that an unavailable capability would improve task delivery. The proposal records reason, expected benefit, effects, filesystem/network/environment scope, persistent/delegated authority requirements, alternatives and risks.

It maps to AgentOps `owner_approval_required` semantics and is invariantly:

```text
approval_required = true
self_approvable = false
```

The proposal layer has no execution/network authority.

## ADR-0012 — security-review candidate

`docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md` defines the candidate authority law:

```text
host policy ceiling
    ∩ ExecutionScope
    ∩ CapabilityLease
    = effective authority
```

The candidate is intentionally **not registered as an active Contract Spine authority type** and does not activate runtime sandboxing or lease issuance.

### Candidate resource authority

Model-facing scope uses Origins-owned resource identities plus normalized relative prefixes instead of arbitrary host paths:

```text
workspace:<id>
repository:<id>
worktree:<id>
artifact:<id>
```

`originsd` will later resolve these references to canonical current host resources at invocation time and apply the existing host ceiling.

### Candidate ExecutionScope / CapabilityLease proof

Executable candidate validators now exist in:

- Python — `python/origins_contracts/authority.py`;
- TypeScript — `typescript/authority.ts`;
- Rust — isolated `rust/origins-authority-contracts` crate.

Shared evidence:

- `contracts/authority-fixtures.json`;
- same valid/invalid corpus across runtimes;
- fixed canonical SHA-256 for the valid scope and lease fixtures;
- monotonic child-scope and lease-within-scope challenge tests;
- denial inheritance, network authority class, expiry, resource-prefix, digest/fence/revision and escalation tests.

Trusted exact head `14636197bd8761085e6f3015dbee16868b399174` passed:

- **Origins Contract Spine — success**;
- **Origins Daemon Foundation — success**.

This proves candidate semantics and regression safety. It does **not** prove OS filesystem/network isolation, process-tree revocation or Sec-Ops acceptance.

## Approval durability gate

Current AgentOps approval semantics are correct but its current `ApprovalService` stores requests/decisions in process memory. That is insufficient to mint security authority that must survive/recover safely across restarts.

Therefore:

- no production CapabilityLease issuer exists;
- no volatile approval is converted into durable Origins authority;
- Origins does not create a shadow AgentOps approval database;
- future lease issuance must bind the exact approved CapabilityProposal digest and durable AgentOps approval-record digest to current parent scope, host policy and capability provider.

## Kilo donor decision

Do not integrate/fork Kilo Code.

Borrowed concepts only:

- Agent Manager candidate/session presentation;
- sibling-worktree/main-checkout denial lessons;
- backend rather than UI-only enforcement;
- invocation-time re-checks against stale handles;
- non-self-disablable policy;
- persistent local MCP/background-process lifetime confinement;
- explicit remote-MCP delegated authority.

Pete/Hunter, AgentOps, CodeOps, Origins and Sergeant ownership remains unchanged.

## Sec-Ops gate

Review packet:

```text
docs/SECOPS_REVIEW_PACKET_PR11.md
```

Primary candidate ADR:

```text
docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md
```

Requested verdict:

```text
PASS | NEEDS WORK | BLOCK
```

PR #11 remains **draft** until this review is reconciled.

## Explicit current limitations

Not authorized/proven yet:

- Sec-Ops acceptance of ExecutionScope/CapabilityLease;
- production lease issuance;
- durable AgentOps approval persistence;
- binding process Sessions to scope/lease IDs;
- lease revocation/fencing enforcement;
- filesystem sandbox enforcement;
- network sandbox enforcement;
- process-tree revocation guarantees per OS;
- browser capability provider;
- MCP execution;
- parallel candidate-worktree mutation;
- generalized agent terminal authority;
- actual production Hunter owner credential proof;
- durable Hunter Project Memory storage;
- React Workspace UI;
- Ptah runtime integration.

## Next valid work

Do **not** continue into browser/MCP/candidate-worktree mutation or generalized agent terminal authority yet.

1. obtain/recover Sec-Ops review against the PR #11 review packet;
2. classify the result `PASS / NEEDS WORK / BLOCK`;
3. correct only evidenced authority-contract/enforcement defects;
4. re-prove candidate semantics across Rust/Python/TypeScript;
5. only after accepted security boundary, promote the accepted authority types into the shared Contract Spine;
6. separately require durable AgentOps approval evidence before implementing a production lease issuer;
7. then bind existing Process Sessions/providers to scope/lease provenance and implement revocation/fencing under the accepted design.

## Blocking rule

Do not let UI, models, Hunter, CodeOps, Python workers or external providers bypass `originsd`/specialist authority because direct subprocess/network access is easier. Approval is not execution. A capability may request authority but may never approve, mint or enlarge its own authority.
