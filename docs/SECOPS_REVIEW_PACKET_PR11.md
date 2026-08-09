# Sec-Ops Review Packet — Origins PR #11 Authority Candidate

Status: **request for adversarial review**. PR #11 remains draft. No production lease issuer or generalized sandbox activation exists.

## Review target

Primary design authority:

- `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`

Executable candidate semantics:

- `python/origins_contracts/authority.py`
- `typescript/authority.ts`
- `rust/origins-authority-contracts/`
- `contracts/authority-fixtures.json`
- `contracts/authority-adversarial-fixtures.json`

Review-completeness artifacts:

- `docs/SECOPS_ENFORCEMENT_POINT_MATRIX_PR11.md` — exact current/future enforcement hooks and implementation status;
- `docs/SECOPS_AUTHORITY_THREAT_MODEL_PR11.md` — issuance/invocation TOCTOU, resource/path/network/restart/confused-deputy threat model;
- `docs/SECOPS_VERDICT_TEMPLATE_PR11.md` — structured PASS / NEEDS_WORK / BLOCK response format;
- `python/tests/test_authority_inactive.py` — mechanical proof that candidate authority cannot activate `originsd` before review.

Related proposal/context boundary:

- `docs/ADR-0011-CONTEXT-REFERENCES-CAPABILITY-PROPOSALS.md`
- `python/origins_integration/capability_proposals.py`
- `python/origins_integration/context_refs.py`

Existing mechanical enforcement donors that are **not being replaced**:

- `rust/originsd/src/process.rs`
- `rust/originsd/src/workspace_roots.rs`
- `rust/originsd/src/sessions.rs`
- `rust/originsd/src/repository.rs`
- hash-chained Origins journal/store

## Pre-review mechanical proof state

The candidate authority semantics are deliberately separated from active runtime authority.

Required pre-review proof:

```text
Python authority validator                         PASS
TypeScript authority validator                     PASS
Rust origins-authority-contracts validator         PASS
shared valid/invalid authority corpus              PASS
shared adversarial relation/contract corpus        PASS in all three runtimes
canonical SHA-256 agreement                        PASS
originsd has no authority-crate dependency         PASS
originsd has no scope/lease/mint activation route  PASS
all inherited Origins runtime proofs               PASS
```

If any of those become false, PR #11 is not ready for Sec-Ops reconciliation.

## Trust model

Treat as potentially hostile:

- all model output;
- repository/worktree contents;
- filenames and links;
- browser/web content;
- MCP servers and MCP-returned data;
- remote services;
- candidate worktrees;
- task-provided environment/config values;
- stale handles from previously authorized capability providers.

Do not assume a model is malicious for normal operation, but design the authority boundary so compromise or adversarial prompt content cannot enlarge mechanical authority.

## Intended authority chain

```text
Owner intent
  -> Hunter / AgentOps semantic operation
  -> CapabilityProposal
  -> durable owner approval (future AgentOps persistence)
  -> current parent ExecutionScope + current host policy
  -> CapabilityLease
  -> originsd invocation-time enforcement
  -> existing mechanical Session/provider
  -> evidence / Sergeant review
```

Important: current AgentOps `ApprovalService` semantics exist, but its in-process storage is not durable enough to mint a production security lease. PR #11 intentionally provides **no production lease issuer**.

## Candidate invariants to attack

1. Host policy is an immutable ceiling from the delegated model's perspective.
2. ExecutionScope may only narrow host policy.
3. CapabilityLease may only narrow its ExecutionScope.
4. Child scope/lease authority can never exceed its parent.
5. A model cannot approve, mint, extend, resume, revoke-and-reissue, or otherwise self-authorize a lease.
6. Lease is bound to the exact approved CapabilityProposal digest and durable approval-record digest.
7. Approval is not execution; provider existence/current policy/current scope must still be validated.
8. Resource authority uses Origins-owned resource IDs plus normalized relative prefixes rather than model-selected raw host paths.
9. Origins resolves resource IDs to canonical current host paths at invocation time.
10. Parent denies cannot be dropped by child scope or lease.
11. Candidate worktree mutation must not reach sibling worktrees or the main checkout.
12. Network-denied authority cannot regain network through stale handles/tools.
13. Network authority cannot silently change class from local allowlist to delegated remote authority.
14. Persistent local MCP/background processes must remain confined for their entire process-tree lifetime.
15. Remote MCP is explicit delegated remote authority and is not represented as locally sandboxed.
16. Secret values never appear in model-visible scope/proposal metadata; environment contracts name variables only.
17. Model-writable project/config data cannot disable or enlarge an active scope/lease.
18. Suspended/revoked/expired leases fail closed at invocation time.
19. Restart cannot resurrect revoked/expired authority.
20. Revocation must terminate/disconnect all bound execution, including child processes/providers where enforceable.
21. Security denial/failure evidence remains visible and cannot be rewritten as success.

## Specific attack classes requested

Challenge:

- privilege escalation;
- proposal/approval/lease substitution;
- approval TOCTOU;
- stale capability handles;
- fence/revision replay;
- resource-ID rebinding;
- symlink/junction/reparse-point/mount escape;
- path normalization disagreement between Windows/Linux/macOS;
- Git common-dir/worktree attacks;
- sibling worktree/main-checkout mutation;
- executable substitution/PATH attacks;
- environment/proxy credential leakage;
- DNS rebinding and redirect widening;
- local MCP opening its own undeclared network connection;
- long-lived MCP/background child survival after revocation;
- confused-deputy behavior through Hunter, CodeOps, Oracle, browser automation, remote Nodes or specialist providers;
- self-disable through writable config/project files;
- daemon crash/restart during approval, issuance, invocation or revocation;
- forged/replayed approval digest;
- lease state rollback or lower-fence replay;
- break-glass authority bypass/audit gaps.

## Questions for Sec-Ops

1. Are `resource_id + normalized relative prefix` grants sufficient as the portable model-facing resource authority representation?
2. Should resource grants bind to an immutable resource revision/digest as well as resource ID to prevent rebinding?
3. Is exact-host network authority adequate, or must the contract distinguish hostname, resolved IP set, port, protocol and redirect policy?
4. What must be captured in a lease to safely enforce DNS/proxy/redirect behavior?
5. Is the proposed monotonic network rule correct: child may become `deny`; otherwise it must remain in the parent's authority class with a subset of hosts?
6. What is the correct process-tree primitive per supported OS for revocation guarantees?
7. What should happen when a platform cannot prove complete process/network confinement?
8. What durable approval fields/signatures/digests must AgentOps expose before Origins may issue a lease?
9. Should approval/lease issuance require freshness/nonces in addition to proposal + approval digests?
10. What fence/revision semantics are required to prevent restart/stale-handle replay?
11. What additional global deny resources must never be delegable?
12. What break-glass design preserves owner emergency control without teaching models an escalation path?

## Required response

Use `docs/SECOPS_VERDICT_TEMPLATE_PR11.md`.

Return exactly one overall verdict:

- `PASS`
- `NEEDS_WORK`
- `BLOCK`

Then provide:

- exploitable attack paths;
- missing invariants;
- contract fields that must be added/removed/changed;
- mandatory backend enforcement points;
- mandatory adversarial tests;
- platform-specific limitations;
- any condition that must be satisfied before browser, MCP, candidate-worktree mutation, generalized agent terminal authority or remote providers are enabled.

## Non-claims

This review packet does not claim:

- Sec-Ops approval;
- production lease issuance;
- durable AgentOps approval persistence;
- filesystem/network sandbox implementation;
- browser/MCP/candidate execution;
- UI implementation;
- Ptah runtime availability.
