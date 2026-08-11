# ADR-0013 — Lease Issuer Preflight v1

Status: candidate. Non-activating. This ADR does not authorize or implement CapabilityLease issuance.

## Purpose

Sec-Ops Stage-1 accepted the `ExecutionScope + CapabilityLease` v1.1 authority model. Before Origins can build a production lease issuer, the owning AgentOps system must supply durable approval evidence and the issuer transaction must bind all current authority inputs without inferring authority from model prose or stale observations.

This ADR defines a **preflight only**:

```text
approved capability intent
+ durable AgentOps approval evidence
+ one-time authenticated issuance binding
+ current ExecutionScope generation
+ current provider manifest generation
+ current host-policy generation
+ current resource generations
→ integrity-addressed preflight receipt
```

The result answers only:

> Are the observed inputs structurally eligible to enter a future atomic lease-issuance transaction?

It never answers:

> Has a lease been issued or activated?

## Hard non-activation theorem

Every receipt has:

```text
issuer_enabled = false
lease_created = false
runtime_authority_activated = false
```

This slice adds no:

- `originsd` authority route;
- scope/lease persistence table;
- production issuer;
- lease id allocation;
- Session binding;
- filesystem/network enforcement;
- browser/MCP/provider activation.

## Approval and authentication are separate

AgentOps durable approval evidence proves the stored approval request/decision and its integrity/restart continuity. It does not authenticate the human by itself.

Owner-level issuance therefore requires both:

1. durable AgentOps approval evidence for the exact `CapabilityProposal`;
2. a valid one-time TTG Auth authorization observation whose actor matches the durable AgentOps approver.

Origins must never treat any of these alone as authority:

```text
durable=true
approved
approval SHA-256
raw approvals.json
```

## CapabilityProposal boundary

The current `CapabilityProposal` is intentionally high-level. For example, it may name hosts but does not define exact network protocol/port tuples or Origins resource generations.

Therefore a future issuer must **not infer exact lease authority from CapabilityProposal metadata**.

The proposal is used to bind:

- Workspace;
- capability intent;
- requested high-level effects/context;
- owner approval request.

Exact mechanical authority remains bounded by the current accepted `ExecutionScope`, provider manifest, host policy and current resource identities.

## Exact issuance binding

Preflight derives a canonical issuance-binding document from current observations:

```text
schema
workspace_id
capability_id
proposal_digest
approval_id
approval_record_digest
scope_id
scope_digest
scope_revision
scope_fence
provider_id
provider_manifest_digest
provider_generation
host_policy_digest
host_policy_generation
resource_bindings[]
```

Each resource binding contains only:

```text
resource_id
generation
digest
```

No host path is placed in the Auth binding or receipt.

The one-time authorization observation must include a `binding_digest` equal to the canonical SHA-256 of this exact issuance binding.

This means the authenticated approval cannot be replayed onto a different scope generation, provider implementation, host policy generation or resource generation without failing preflight.

The production TTG Auth adapter that emits/consumes this exact issuance binding is a later owner-system integration requirement. Fixture observations may prove preflight semantics but are not live authority.

## Current-scope requirements

Preflight validates the v1.1 `ExecutionScope` contract and requires:

- `state == active`;
- Workspace matches the approved proposal;
- scope has not expired at the supplied observation time;
- canonical scope digest is calculated with the accepted authority contract canonicalizer.

Preflight does not persist a current scope or claim that a supplied scope came from trusted runtime storage. Trusted current-scope storage/transition atomicity remains Stage-2 implementation work.

## AgentOps durable evidence requirements

The observation must contain:

- `durable == true`;
- `status == approved`;
- complete immutable request and decision record;
- request digest;
- proposal-metadata digest;
- decision-record digest;
- ledger event digest.

Preflight recomputes the request, metadata and decision-record digests using Origins canonical JSON rules and requires:

```text
request.metadata == exact CapabilityProposal document
metadata_digest == proposal_digest
request.target == proposal.capability_id
request.gate == owner_approval_required
request.mode == capability_extension
record.approval_id == request.approval_id
record.decision == approved
```

The ledger event digest is treated as an observation from the AgentOps authority and must be a valid SHA-256 value. Full AgentOps ledger replay remains AgentOps-owned.

## Auth observation requirements

The normalized authorization observation must contain at least:

```text
valid = true
approval_id
primary_actor
method
proof_id
binding_digest
```

It must satisfy:

```text
authorization.approval_id == durable approval id
authorization.primary_actor == durable record.decided_by
authorization.binding_digest == exact issuance-binding digest
```

The future production adapter must obtain this observation from AgentOps/TTG Auth, not manufacture it inside Origins.

## Provider observation

Preflight requires:

```text
capability_id
provider_id
provider_manifest_digest
provider_generation >= 1
```

The capability must equal the approved proposal capability. Provider identity/manifest/generation are included in the Auth issuance binding.

## Host-policy observation

Preflight requires:

```text
digest
generation >= 1
```

Origins does not define the production host-policy store in this slice. The observation merely makes the future issuance dependency explicit and bindable.

## Resource observations

Every distinct `resource_id` referenced by current scope reads/writes/denies must have exactly one current observation:

```text
resource_id
generation >= 1
digest
```

Missing, duplicate or extra resource observations fail preflight. This prevents an apparently valid preflight from hiding which resource generations were authenticated.

Path resolution, symlink/junction/reparse/mount/hard-link handling and resource-ID rebinding remain Stage-2 runtime/OS obligations.

## Receipt

A successful or failed preflight returns an integrity-addressed receipt containing only compact identities/digests/generations plus failure codes. It does not duplicate proposal text, approval records, secrets, host paths or Auth proof contents.

`eligible=true` means only that the presented observations are structurally consistent enough for a future issuer transaction.

## Stage-2 boundary

A production issuer still requires:

- merged/proven AgentOps durable approval evidence;
- production Auth issuance-binding adapter;
- trusted current ExecutionScope storage;
- trusted host-policy generation;
- trusted provider manifest generation;
- trusted current resource generations;
- atomic issuance/fencing/persistence;
- invocation-time enforcement and revocation;
- Stage-2 Sec-Ops red-team before powerful authority activation.
