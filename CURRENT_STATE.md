# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged implementation:** `main` through Live Engineering Mount v1
**Active candidate:** draft PR #11 — Hunter Intelligence Mount + context/proposal layer + authority-contract v1.1

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
- optional Hunter capability synchronization, including configured→disabled cleanup;
- corrected `ExecutionScope + CapabilityLease` v1.1 validators in Python, TypeScript and isolated Rust;
- shared canonical/adversarial authority corpus across all three runtimes;
- CI no-activation guard proving candidate authority is not wired into `originsd` runtime enforcement.

## Sec-Ops stage-1 review

Original stage-1 verdict:

```text
NEEDS_WORK
```

Historical findings:

```text
docs/SECOPS_STAGE1_VERDICT_PR11.md
```

SEC-001 through SEC-005 were corrected without activating runtime authority.

Focused reconciliation verdict:

```text
PASS
```

Canonical reconciliation:

```text
docs/SECOPS_STAGE1_RECONCILIATION_PR11.md
```

This PASS accepts the **contract model only** as a foundation for later implementation. It is not approval of an issuer, sandbox, runtime enforcement, browser, MCP, candidate-worktree mutation or generalized agent terminal authority.

## Authority contract v1.1 — accepted stage-1 shape

```text
host policy ceiling
    ∩ current ExecutionScope
    ∩ current CapabilityLease
    ∩ current provider manifest
    = effective invocation authority
```

### SEC-001 — closed

- `parent_lease_id` removed;
- lease-to-lease delegation unsupported in v1.1;
- delegated narrowing uses child ExecutionScope + separately issued lease.

### SEC-002 — closed

- operation identity immutable across child scopes;
- candidate identity may bind once from an unbound parent;
- once bound, candidate identity cannot switch or clear.

### SEC-003 — closed

CapabilityLease now binds:

```text
capability_id
provider_id
provider_manifest_digest
provider_generation
```

Current provider identity/manifest/generation must match before future invocation.

### SEC-004 — closed at contract-model stage

ExecutionScope now carries:

```text
state
fence
revision
```

Current-generation validation rejects non-active, lower-fence/revision, identity-changed or canonical-content-stale scope presentations.

Durable state transitions/restart atomicity remain stage-2 runtime work.

### SEC-005 — closed

`network_hosts` removed. Network authority uses exact endpoint tuples:

```text
protocol
host
port
```

Supported candidate protocol classes:

```text
http | https | tcp | udp | ws | wss
```

Port is mandatory. Redirect policy is explicit and currently fixed to `deny_outside_endpoints`.

DNS/proxy/redirect/routing/provider lifetime enforcement remains stage-2 work.

### Additional hardening accepted

- holder authority uses canonical Origins UUID + holder generation;
- child scope issuance cannot predate parent current generation;
- lease issuance cannot predate scope current generation;
- delegated expiry cannot extend parent authority.

## Proof state

Pre-reconciliation documentation head `0c7d17cac17df0fadd1435729a2cffb6692a711a` passed:

- Python authority/contract proof;
- TypeScript authority/contract proof;
- Rust 1.75 Clippy with `-D warnings`;
- Rust authority/contract proof;
- Contract Spine Rust/Python/TypeScript equivalence;
- shared v1.1 authority canonical SHA-256 agreement across all three runtimes;
- shared v1.1 adversarial corpus across all three runtimes;
- Rust formatting;
- all Origins Daemon Foundation inherited proofs;
- authority no-activation guard.

The reconciliation/state documentation head must also remain green before promotion.

## Stage-2 security gate — still mandatory

Before powerful authority is enabled, Sec-Ops must red-team the **actual implementation** of:

- durable AgentOps approval authenticity/replay resistance;
- trusted root/child ExecutionScope issuance;
- atomic approval/scope/policy/provider/resource-to-lease issuance;
- durable scope/lease state, revision and fence recovery;
- invocation-time current-authority evaluation;
- provider manifest/generation revalidation;
- resource-generation/path revalidation;
- symlink/junction/reparse/mount/hard-link/special-file containment;
- sibling/main worktree mutation isolation;
- Windows/Linux process-tree revocation;
- DNS/proxy/redirect/network behavior;
- persistent local MCP lifetime confinement;
- delegated remote authority propagation;
- holder UUID/generation binding to durable runtime subjects;
- confused-deputy paths through Hunter/CodeOps/Oracle/providers;
- self-disable attempts against policy/security storage.

Stage-1 PASS must never be cited as implementation-level approval.

## Current security stop rule

Even after stage-1 PASS, do **not** yet implement or enable:

- production lease issuance from volatile AgentOps approval;
- browser/MCP/candidate-worktree/general agent authority without accepted runtime design;
- any route that lets UI/model/Python bypass `originsd` or specialist authority;
- any powerful capability activation before stage-2 Sec-Ops review of its implemented boundary.

## Next valid work

PR #11 is no longer blocked by SEC-001..SEC-005.

Next promotion sequence:

```text
stage-1 Sec-Ops PASS
→ freeze reconciliation/current-state/handoff
→ exact-head full proof
→ independent Sergeant/repository review
→ PR #11 promotion/merge if clean
```

After PR #11 merge, the next separate authority-runtime phase begins with durable AgentOps approval evidence and production issuer/enforcement design under the accepted v1.1 contract model.

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
