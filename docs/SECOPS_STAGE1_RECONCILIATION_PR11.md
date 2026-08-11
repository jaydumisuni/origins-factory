# Sec-Ops Stage-1 Reconciliation — Origins PR #11

Review stage: **focused contract-model reconciliation**

Original verdict: `NEEDS_WORK`

Reconciliation verdict: **PASS**

This PASS approves the corrected `ExecutionScope + CapabilityLease` v1.1 contract model as a sound foundation for later implementation. It is **not implementation approval** and does not activate or authorize browser, MCP, candidate-worktree mutation, generalized agent terminal authority, filesystem/network sandboxing or production lease issuance.

Stage-2 implementation red-team remains mandatory before powerful model-controlled authority may be enabled.

## Evidence reviewed

Corrected authority model:

- `docs/ADR-0012-EXECUTION-SCOPE-CAPABILITY-LEASE.md`;
- `python/origins_contracts/authority.py` / `authority_v11.py`;
- `typescript/authority.ts` / `authority_v11.ts`;
- `rust/origins-authority-contracts/src/lib.rs` / `v11.rs`;
- `contracts/authority-fixtures.json`;
- `contracts/authority-adversarial-fixtures.json`.

Proof on pre-reconciliation documentation head `0c7d17cac17df0fadd1435729a2cffb6692a711a`:

- Python authority/contract tests — PASS;
- TypeScript authority/contract tests — PASS;
- Rust 1.75 Clippy with `-D warnings` — PASS;
- Rust authority/contract tests — PASS;
- Rust/Python/TypeScript Contract Spine equivalence — PASS;
- canonical v1.1 authority fixture SHA-256 agreement in all three runtimes — PASS;
- shared v1.1 adversarial corpus in all three runtimes — PASS;
- Rust formatting — PASS;
- full Origins Daemon Foundation regressions — PASS;
- authority activation guard — PASS.

No production authority path was added during reconciliation.

## SEC-001 — CLOSED

Finding: `parent_lease_id` existed without enforceable lease-to-lease delegation semantics.

v1.1 decision:

- remove `parent_lease_id` entirely;
- lease-to-lease delegation is unsupported in v1.1;
- the legacy field is an unknown-field validation failure;
- delegated narrowing is represented by child `ExecutionScope` followed by a separately issued bounded lease.

Security conclusion:

**CLOSED_BY_CONTRACT.** There is no informational parent-lease reference that can be used to imply unenforced authority inheritance.

Any future lease-to-lease delegation requires a new contract version and its own security review.

## SEC-002 — CLOSED

Finding: child scopes could relabel semantic operation/candidate identity while remaining inside mechanical resource ceilings.

v1.1 rules:

- child `workspace_id` must equal parent;
- child `operation_id` must equal parent;
- child `parent_scope_id` must identify parent;
- candidate identity is bind-once:
  - unbound parent may remain unbound or bind one candidate;
  - once parent candidate is non-empty, descendants must retain exactly that candidate;
  - candidate cannot switch or clear after binding.

Shared attacks cover operation substitution, candidate A→B substitution and candidate clearing.

Security conclusion:

**CLOSED_BY_CONTRACT** for semantic relabeling. Authentic issuance of root/child scopes remains a Stage-2 trusted-store/issuer obligation.

## SEC-003 — CLOSED

Finding: capability id did not identify the exact provider implementation that was approved.

v1.1 lease now binds:

```text
capability_id
provider_id
provider_manifest_digest
provider_generation
```

The provider-binding relation rejects:

- provider identity substitution;
- manifest substitution;
- stale/different provider generation.

Security conclusion:

**CLOSED_BY_CONTRACT** for provider-binding representation and comparison semantics.

Stage 2 must obtain the current provider manifest/generation from trusted runtime state and re-check it on every invocation.

## SEC-004 — CLOSED

Finding: `ExecutionScope` lacked explicit stale-generation/lifecycle fencing.

v1.1 scope now contains:

```text
state = active | suspended | revoked | expired
fence >= 1
revision >= 1
```

Current-generation validation requires exact identity, revision, fence and canonical document digest and rejects a current scope that is not active.

Shared attacks cover lower-fence/revision replay and revoked-scope use.

Security conclusion:

**CLOSED_BY_CONTRACT** for lifecycle/fence representation and stale-presentation semantics.

Durable state transitions, atomic updates and restart recovery are **REQUIRES_RUNTIME_RECHECK** and remain Stage-2 blockers.

## SEC-005 — CLOSED

Finding: generic `host[:port]` authority left protocol and omitted-port meaning ambiguous.

v1.1 removes `network_hosts` and defines exact endpoints:

```text
protocol
host
port
```

Candidate protocols:

```text
http | https | tcp | udp | ws | wss
```

Port is mandatory (`1..65535`). `network_redirect_policy` is explicit and currently only permits `deny_outside_endpoints`.

Delegation may move to `deny`; otherwise network class, redirect policy and endpoint tuples can only remain equal/subset. Protocol substitution and endpoint widening fail.

Security conclusion:

**CLOSED_BY_CONTRACT** for protocol/host/port authority representation and monotonic delegation.

DNS resolution/rebinding, proxies, actual redirects, IPv4/IPv6 routing equivalence, browser subresources/websockets and local-MCP socket creation remain **REQUIRES_PROVIDER_ENFORCEMENT / REQUIRES_OS_PROVIDER_ENFORCEMENT** at Stage 2.

Unsupported endpoint forms must fail rather than widening authority.

## Additional hardening — ACCEPTED

### Canonical holder identity

Lease holder uses:

```text
holder_kind
holder_id = canonical Origins UUID
holder_generation >= 1
```

This prevents a recycled human-readable name from inheriting old authority by string collision.

The runtime mapping between UUID/generation and durable Session/provider subject is a Stage-2 proof obligation.

### Relational issuance chronology

v1.1 relation validation requires:

- child scope `issued_at >= parent.updated_at`;
- lease `issued_at >= scope.updated_at`;
- delegated expiry cannot exceed parent/scope expiry.

This closes simple chronology/replay inconsistencies at the contract relation layer. Atomic issuance remains Stage-2 work.

## Residual mitigation classification

| Attack class | Classification after v1.1 | Activation requirement |
|---|---|---|
| raw absolute/`..`/backslash prefix traversal | `CLOSED_BY_CONTRACT` | keep same validation in production Contract Spine |
| operation/candidate relabeling | `CLOSED_BY_CONTRACT` | production issuer must use relation validator |
| parent-lease laundering | `CLOSED_BY_CONTRACT` | lease-to-lease delegation remains unsupported |
| provider implementation substitution | `CLOSED_BY_CONTRACT` + `REQUIRES_RUNTIME_RECHECK` | compare trusted current provider manifest/generation every invocation |
| stale scope presentation | `CLOSED_BY_CONTRACT` + `REQUIRES_RUNTIME_RECHECK` | durable current generation/fence store required |
| ambiguous protocol/port authority | `CLOSED_BY_CONTRACT` | provider must consume exact endpoint tuples |
| resource-ID rebinding | `REQUIRES_RUNTIME_RECHECK` | non-recyclable resource identity/current generation required |
| symlink/junction/reparse/mount/hard-link/special-file escape | `REQUIRES_OS_PROVIDER_ENFORCEMENT` | OS-specific open/mutation proof required |
| sibling/main worktree mutation | `REQUIRES_RUNTIME_RECHECK` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | exact current worktree/common-dir resolution at mutation boundary |
| DNS/proxy/redirect/network escape | `REQUIRES_PROVIDER_ENFORCEMENT` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Stage-2 network/provider proof required |
| stale lease handle | `REQUIRES_RUNTIME_RECHECK` | durable lease state/fence lookup every invocation |
| process-tree survival after revocation | `REQUIRES_OS_PROVIDER_ENFORCEMENT` | Windows/Linux containment proof required |
| self-disable via model-writable config | `REQUIRES_RUNTIME_RECHECK` + `REQUIRES_OS_PROVIDER_ENFORCEMENT` | trusted security state outside delegated writes |
| confused deputy | `REQUIRES_PROVIDER_ENFORCEMENT` | requester effective authority must propagate through every deputy |
| approval/proposal authenticity | `REQUIRES_RUNTIME_RECHECK` | durable trusted AgentOps record required; digest alone is not authenticity |

## Stage-1 final gate

```yaml
verdict: PASS
stage1_secops_reconciled: true
contract_model_accepted: true
ready_for_sergeant_review: true
ready_for_pr11_merge: false
stage2_secops_required: true
powerful_capability_activation_allowed: false
```

`ready_for_pr11_merge` remains false in this Sec-Ops verdict only because normal repository promotion still requires the post-verdict documentation/proof/review gate. It is no longer blocked by SEC-001..SEC-005.

## Mandatory Stage-2 targets

Before powerful authority activation, Sec-Ops must attack the actual implementation for:

- durable AgentOps approval authenticity/replay resistance;
- atomic approval/scope/provider/resource-to-lease issuance;
- trusted root/child ExecutionScope issuance;
- current scope/lease fence persistence and restart behavior;
- invocation-time provider manifest/generation binding;
- current resource generation/path resolution;
- filesystem/worktree OS escape primitives;
- Windows/Linux process-tree revocation;
- DNS/proxy/redirect/network enforcement;
- browser subresource/websocket handling;
- local persistent MCP complete-lifetime confinement;
- remote delegated-authority propagation;
- holder UUID/generation binding to actual durable subjects;
- confused-deputy attempts through Hunter, CodeOps, Oracle and providers;
- self-disable attempts against policy/security storage.

Stage-1 PASS must never be cited as implementation-level approval for code that did not exist during this review.
