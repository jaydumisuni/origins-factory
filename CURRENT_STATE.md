# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine v1 merged; `originsd` persistence foundation implemented and mechanically proven

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace, but it now has both the frozen cross-language Contract Spine and a proven persistent Rust daemon foundation rather than only architecture documents.

## Accepted foundation already on `main`

Contract Spine v1 is merged and contains:

- `authority_ref`;
- `workspace_projection`;
- `capability_descriptor`;
- `command_envelope`;
- `event_envelope`;
- deterministic canonical JSON;
- SHA-256 contract identity;
- unknown-field rejection;
- floating-point rejection;
- cross-language safe-integer enforcement;
- explicit self-promotion rejection;
- Python, Rust and TypeScript validators/canonicalizers;
- exact three-runtime validity/error/canonical/SHA equivalence proof.

Canonical implementation documents:

- `docs/INTERFACE_RECOVERY_MATRIX.md`;
- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/FIRST_VERTICAL_SLICE.md`.

## `originsd` persistence foundation

The proven daemon foundation includes:

- Rust 1.75 runtime boundary;
- loopback-only bind with explicit rejection of non-loopback addresses;
- per-install local bearer token handling;
- SQLite schema version 1;
- WAL mode and foreign keys;
- Origins-owned Workspace projection persistence;
- built-in Origins-owned capability projections;
- append-only hash-chained `event_envelope` journal;
- canonical contract validation and SHA verification on durable reads;
- health diagnostics and journal verification;
- authenticated Workspace create/read and capability-read HTTP routes;
- real process startup, shutdown and restart recovery proof;
- deliberate Workspace-digest and journal-chain tamper tests;
- proof-frozen dependency lock.

Current routes:

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
```

No placeholder terminal, command, model, device or external-system route is exposed.

## Challenge evidence

The daemon Challenge pass established:

- Rusqlite `0.32.1` is incompatible with the frozen Rust 1.75 boundary because it uses newer C-string literal syntax;
- the dependency was corrected to Rusqlite `0.31.0` rather than weakening the Rust proof boundary;
- Clippy passes with warnings denied;
- all Rust contract and daemon tests pass;
- `originsd` builds successfully;
- the real daemon refuses `0.0.0.0` binding;
- missing bearer authentication is rejected for protected reads and durable writes;
- an authenticated Workspace survives daemon termination and restart through the same SQLite database;
- the event journal recovers with a valid non-empty chain head;
- deliberate Workspace projection digest tampering is detected;
- deliberate journal chain tampering is detected;
- the local token is not emitted in daemon stdout/stderr during the hosted proof;
- repository whitespace gates pass;
- rustfmt passes across the complete multi-crate Rust workspace;
- `rust/Cargo.lock` was frozen only after successful runtime proof;
- the frozen lock then received a fresh exact-head daemon proof;
- the complete Rust/Python/TypeScript Contract Spine proof also passes on the same locked head.

No independent PR review finding or unresolved review thread currently contradicts this evidence.

## Current repository authority

Recovery order remains:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. current source/PRs/proof;
5. the owning repository for any mounted capability.

The exploratory `build/initial-workspace` branch remains non-authoritative and must not be revived as the implementation base.

## What remains unimplemented

- process/PTTY/session supervision;
- Git/repository native session layer;
- `POST /v1/commands` execution semantics;
- WebSocket event streaming;
- accepted Python Origins integration runtime;
- production Hunter mount;
- production AgentOps lifecycle mount;
- CodeOps mission loop inside Origins;
- Sergeant correction/completion loop inside Origins;
- React workspace shell;
- Oracle OS-control/remote-session integration;
- Lumi Workspace integration;
- application registry implementation beyond built-in daemon capabilities;
- specialist Gateway client implementation inside Origins;
- Ptah runtime integration;
- Windows/Linux desktop package;
- custom OS integration;
- release proof.

## Next valid work

1. implement supervised repository/process sessions in Rust;
2. define their durable session/recovery semantics before adding terminal UI;
3. add `POST /v1/commands` only for typed registered capabilities;
4. add event streaming over the frozen `event_envelope` contract;
5. mount AgentOps + CodeOps + Sergeant through recovered boundaries;
6. prove `NEEDS WORK → correction Attempt → fresh proof → PASS` through Origins;
7. begin the React Workspace shell only after those mechanical truths exist.

## Blocking rule

Do not let UI, Python workers, models or external adapters bypass `originsd` or specialist authority just because direct subprocess/network access would be easier. The persistent mechanical and assurance boundaries are part of the product, not implementation decoration.
