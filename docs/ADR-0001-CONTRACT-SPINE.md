# ADR-0001 — Origins Factory Contract Spine v1

**Status:** ACCEPTED for initial implementation  
**Date:** 2026-08-07  
**Authority:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`

## Context

Origins integrates independently owned systems written in Rust, Python and TypeScript. It must preserve semantic, mechanical and assurance truth without copying the owning system's database or creating UI-owned state.

The Huawei project already proves exact Python/Rust canonical JSON and SHA-256 identity. Oracle and Lumi prove local/HTTP client surfaces. Huawei Phase 3 proves a persistent Rust control plane with reconnect-safe clients. Sergeant and AgentOps prove independent lifecycle and assurance boundaries.

## Decision

Origins Contract Spine v1 consists of:

1. versioned JSON contracts;
2. deterministic canonical JSON;
3. SHA-256 identity;
4. explicit authority references rather than copied foreign records;
5. a persistent Rust daemon named `originsd`;
6. a Python intelligence/integration runtime that is a client of `originsd` and owning systems;
7. a React/TypeScript UI that is also a client, never a durable authority;
8. local command transport over loopback HTTP JSON and event/stream transport over WebSocket;
9. future remote-Node transport treated as a separate authenticated provider transport rather than silently exposing the loopback API.

The desktop wrapper remains packaging, not runtime authority. Tauri, Qt or another wrapper may host the UI later without changing the `originsd` contract.

## Canonical JSON

Origins reuses the proven Huawei canonicalization theorem:

- UTF-8;
- object keys lexicographically sorted;
- no insignificant whitespace;
- array order preserved;
- integers only in authoritative contract numeric fields;
- floating point rejected;
- Unicode preserved;
- SHA-256 calculated over canonical UTF-8 bytes.

Cross-language fixtures must prove identical canonical bytes and digest in Rust, Python and TypeScript before the registry is frozen.

## Initial Origins-owned contract types

Origins owns only integration records and projections:

### `authority_ref`

Stable reference to truth owned elsewhere.

Examples:

- AgentOps Operation ID;
- Git commit;
- Sergeant report;
- Oracle Browser Run;
- Lumi handoff/task;
- X-Ray bundle;
- Huawei Gateway operation;
- future Ptah Object/Activity/Artifact.

It may contain a URI, revision and digest but never a copied mutable foreign record as authority.

### `workspace_projection`

Origins-owned projection describing which authoritative records, repositories and live sessions are attached to one user-facing Workspace. It is explicitly a projection and can be rebuilt from owning authorities.

### `capability_descriptor`

Normalized statement of what a capability can do, its effect class, maturity, permissions, placement requirements and independent-review requirements. The descriptor may be generated from an owning capability manifest but does not grant authority.

### `command_envelope`

Versioned request from a client to `originsd` or an Origins adapter. It carries operation/workspace correlation, requested capability, effect class and payload. It cannot contain an arbitrary shell string when a typed operation exists.

### `event_envelope`

Immutable Origins event projection carrying correlation IDs, producer, timestamp, event kind, payload and evidence references.

## Effect classes

The initial generic effect vocabulary is:

- `observe`
- `draft`
- `mutate`
- `execute`
- `verify`
- `publish`

A capability may declare multiple effects, but an invocation requests one bounded effect. Specialist domains may be stricter.

`verify` does not imply permission to `mutate` or `execute`.

## Authority rule

The following IDs remain foreign truth and are referenced, not re-created:

- Hunter conversation/context IDs;
- AgentOps Operation/Attempt IDs;
- CodeOps mission/evidence IDs;
- Sergeant verdict/report IDs;
- Oracle session IDs;
- Lumi handoff/task IDs;
- X-Ray scan/bundle IDs;
- specialist Gateway session/operation IDs;
- Ptah IDs when runtime is later authorized.

Origins may generate its own `workspace_id`, `session_id`, local `command_id`, local `event_id` and cache/projection revision IDs.

## Local transport v1

`originsd` will bind only to loopback by default.

### Command/query plane

HTTP JSON:

```text
GET  /v1/health
GET  /v1/workspaces/{workspace_id}
POST /v1/workspaces
POST /v1/commands
GET  /v1/capabilities
GET  /v1/sessions
```

The initial implementation may add routes only through a versioned ADR/change.

### Event/stream plane

WebSocket:

```text
GET /v1/events
```

The stream carries `event_envelope` documents. Terminal byte streams may later use a dedicated channel but must retain session and Attempt correlation.

### Local authentication

Even loopback is not treated as trusted by default. `originsd` will require a per-install local capability token for mutation/execute endpoints once those endpoints exist. The first contract-only and read-only health implementation may start without mutation surfaces.

## Persistence v1

`originsd` will use SQLite for durable Origins-owned state because the proven Huawei Gateway already demonstrates SQLite crash recovery and journal discipline.

SQLite will contain only Origins-owned projections, local sessions, bindings, capability registry state and event/journal metadata. It will not mirror foreign application databases.

WAL mode and migration/version checks are required before durability is claimed.

## Rust/Python boundary

Rust owns:

- durable local state;
- process/PTTY/session supervision;
- filesystem and Git mediation;
- capability registry enforcement;
- local transport;
- cancellation and resource limits;
- event/journal emission.

Python owns:

- Hunter integration;
- AgentOps integration;
- CodeOps orchestration;
- model/provider adapters;
- context compilation;
- capability formation and gap analysis;
- reconciliation.

Python is never allowed to bypass Rust/native or specialist authority merely because it can execute a subprocess itself.

## UI boundary

The React/TypeScript UI consumes the same contracts. It may cache projections but cannot own Operation, device, browser, download or review truth.

## Upgrade rule

No capability may modify and activate its own replacement in one unchecked path.

A capability gap requires:

```text
evidence of missing required effect
→ AgentOps child upgrade Operation
→ CodeOps implementation
→ independent Sergeant review
→ proof/canary
→ owner or policy acceptance
→ explicit generation activation
→ original Operation resume
```

## Rejected alternatives

### Tauri commands as the primary runtime API

Rejected as the core boundary because it couples durable work to one desktop wrapper and does not naturally serve Python, browser/web clients or later remote Nodes.

### One Python process for everything

Rejected because long-lived native process/session authority, PTYs, filesystem mediation and crash-safe local control are stronger in the persistent Rust plane, while Python remains the better integration/intelligence environment for existing Hunter systems.

### Copying external state into one Origins database

Rejected because it creates competing truth, stale replicas and recovery ambiguity.

### Arbitrary shell as the universal tool protocol

Rejected because it destroys capability boundaries, effect classification and proofability. Shell execution remains a bounded native capability where genuinely required.

## Proof gates

Contract Spine v1 is not frozen until:

1. valid/invalid fixtures exist;
2. Rust and Python canonicalization match exactly;
3. unknown fields and floating-point values fail closed;
4. contract digests match exactly;
5. workspace projections cannot claim foreign authority;
6. capability descriptors cannot grant permissions they merely describe;
7. the first vertical slice runs through typed envelopes rather than UI-owned state.
