# ADR-0002 — originsd Foundation v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** `ADR-0001-CONTRACT-SPINE.md`

## Purpose

Implement the first persistent Rust mechanical-control surface for Origins Factory without coupling durability to the future React desktop wrapper or to Python intelligence workers.

## Initial technology set

The first proof candidate uses:

- Rust 1.75;
- Tokio for the local async runtime;
- Axum for loopback HTTP and later WebSocket transport;
- SQLite through Rusqlite for Origins-owned durable state;
- the frozen `origins-contracts` crate for validation/canonical identity;
- SHA-256 for journal chaining;
- UUID v4 for Origins-owned IDs.

These versions remain candidates until the branch proves compilation, Clippy, tests, restart recovery and loopback behavior under the pinned Rust toolchain. A failed compatibility proof means the dependency choice is corrected; it does not authorize changing the product boundary.

## v1 server boundary

`originsd` binds to a loopback address only. A non-loopback bind is refused rather than exposed accidentally.

Default development bind:

```text
127.0.0.1:48700
```

Override:

```text
ORIGINS_BIND=127.0.0.1:<port>
```

The first routes are:

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
```

`/v1/health` is loopback-readable without the local token. All state/capability routes require the per-install bearer token.

The remaining Contract Spine routes are added after their durable semantics exist; no placeholder success endpoint will pretend a capability is implemented.

## Local authentication

Mutation begins in this slice because Workspace creation is a durable write. Therefore the daemon implements the Contract Spine authentication rule immediately.

Priority:

1. `ORIGINS_LOCAL_TOKEN` when explicitly supplied;
2. otherwise load an existing token from `<data-dir>/local-token.txt`;
3. otherwise generate a new high-entropy local token and persist it.

The token is never returned by health/status APIs and never written to the event journal.

## Data directory

Priority:

1. `ORIGINS_DATA_DIR`;
2. default `.origins` for the first development runtime.

The custom OS and packaged desktop application will later supply an explicit platform-owned data directory. The repository is not allowed to treat `.origins` as a source-controlled artifact.

## SQLite authority

SQLite stores Origins-owned state only:

- schema metadata;
- Workspace projections;
- normalized capability projections;
- append-only Origins event journal.

It does not mirror Hunter, AgentOps, CodeOps, Sergeant, Oracle, Lumi, X-Ray, specialist Gateway or Ptah databases.

Required database settings:

- schema version check;
- WAL mode;
- foreign keys enabled;
- explicit migration boundary;
- fail closed on unknown newer schema versions.

## Workspace persistence

The daemon generates Origins-owned Workspace IDs and timestamps, builds a `workspace_projection`, validates it through `origins-contracts`, calculates canonical SHA-256 and stores the canonical bytes.

Foreign authority remains represented only by validated `authority_ref` contracts.

## Event journal

Every accepted durable mutation emits a validated `event_envelope`.

The SQLite journal stores:

- monotonic sequence;
- event ID;
- Workspace ID;
- canonical event JSON;
- event contract SHA-256;
- previous journal-entry hash;
- current journal-entry hash;
- creation time.

Journal entry hashing is domain-separated:

```text
SHA256("origins-journal-v1\0" || previous_hash || "\0" || event_sha256)
```

Startup/health verification recalculates contract hashes and the complete chain. Corruption is reported; it is never silently repaired.

## Capability registry

The first built-in registry contains only capabilities actually owned by the daemon foundation. External systems are added only when their adapter exists.

A `capability_descriptor` describes a capability but never grants authority.

## Restart theorem

This slice must prove both:

1. client/UI independence — the daemon can continue while a client disappears;
2. daemon restart recovery — after process restart, Workspace projections and the event chain recover from SQLite.

A live process/PTTY is not yet claimed resumable. That becomes a later explicit session contract and proof.

## Non-goals

This slice does not implement:

- Hunter reasoning;
- AgentOps lifecycle storage;
- CodeOps execution;
- Sergeant review;
- terminals/PTTYs;
- Oracle;
- Lumi;
- devices;
- Ptah;
- React UI;
- custom OS packaging.

Those systems mount after the persistent control plane proves its own truth.
