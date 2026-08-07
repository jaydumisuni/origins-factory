# ADR-0002 — originsd Foundation v1

**Status:** PROVEN CANDIDATE — final exact locked-head verification pending
**Date:** 2026-08-07
**Depends on:** `ADR-0001-CONTRACT-SPINE.md`

## Purpose

Implement the first persistent Rust mechanical-control surface for Origins Factory without coupling durability to the future React desktop wrapper or to Python intelligence workers.

## Proven technology set

The foundation uses:

- Rust 1.75;
- Tokio `1.42.0` for the local async runtime;
- Axum `0.7.9` for loopback HTTP and later WebSocket transport;
- Rusqlite `0.31.0` with bundled SQLite for Origins-owned durable state;
- the frozen `origins-contracts` crate for validation/canonical identity;
- SHA-256 for journal chaining;
- UUID v4 for Origins-owned IDs.

The Challenge pass rejected Rusqlite `0.32.1` because it uses C-string literal syntax unavailable on Rust 1.75. Origins kept the frozen Rust proof boundary and corrected the dependency to `0.31.0`, which passed Clippy, tests, daemon build, and hosted restart proof. The exact dependency graph is frozen in `rust/Cargo.lock` only after the runtime proof passes.

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

The hosted proof verifies both protected reads and durable writes reject missing authentication, and checks daemon output from accepted and rejected startup paths for token disclosure.

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

Stored Workspace projections are revalidated and rehashed before they are returned. A controlled database-tamper test proves digest mismatch is reported as corruption rather than returned as valid state.

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

Startup/health verification recalculates contract hashes and the complete chain. Corruption is reported; it is never silently repaired. A deliberate journal-tamper test proves a modified chain hash fails closed.

## Capability registry

The first built-in registry contains only capabilities actually owned by the daemon foundation. External systems are added only when their adapter exists.

A `capability_descriptor` describes a capability but never grants authority.

## Restart theorem

This slice proves:

1. the real daemon starts on an ephemeral loopback port;
2. non-loopback startup is refused explicitly;
3. authenticated Workspace creation persists a canonical projection and event;
4. the process can be terminated;
5. a new daemon process can reopen the same SQLite database;
6. the exact Workspace projection is recovered;
7. the event chain recovers with the same non-empty journal head;
8. local bearer credentials do not appear in daemon output.

A live process/PTTY is not yet claimed resumable. That becomes a later explicit session contract and proof.

## Dependency freeze

The owner-branch workflow generates the exact lockfile only after logic and recovery proof succeed, then commits it as:

```text
Freeze originsd dependency lock
```

The frozen lock must receive a fresh owner-triggered exact-head proof before the PR is promoted. A pre-lock green run alone is insufficient.

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
