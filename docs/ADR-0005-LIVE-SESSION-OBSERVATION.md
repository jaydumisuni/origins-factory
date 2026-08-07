# ADR-0005 — Live Session Observation v1

**Status:** PROVEN
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0004

## Decision

Origins can project durable events and bounded process output while work is still running without making a socket, UI buffer, or second raw-output database authoritative.

This generation provides:

1. authenticated live journal-event delivery over the durable event-sequence cursor;
2. incremental retained stdout/stderr persistence in the existing `session_outputs` record;
3. authenticated byte-cursor output delta reads;
4. authenticated live output delivery over the same durable retained-byte cursors.

## One-copy output rule

`session_outputs` remains the single local retained raw-output store.

During execution, capture tasks append only bytes that fit inside the command's existing retention bound to the existing stdout/stderr blobs. Every append verifies the prior retained digest and commits the next retained digest transactionally.

No second raw-output/chunk table is introduced.

The final Session projection records complete observed stream byte counts and SHA-256. If output exceeds retention, SQLite holds only the retained prefix while the Session projection proves the complete observed stream size/hash.

The hash-chained journal remains metadata/digest-only; raw stdout/stderr never become journal payload.

## Reconnectable byte cursors

Authenticated read surface:

```text
GET /v1/sessions/{session_id}/output/delta
    ?stdout_after=<byte-offset>
    &stderr_after=<byte-offset>
    &limit=<bytes-per-stream>
```

Each stream returns requested offset, next offset, retained head, exact hexadecimal bytes, and UTF-8 text only when the returned slice is valid UTF-8.

Repeating from the returned `next` offset yields only later retained bytes. A cursor beyond the retained head fails rather than silently rewinding.

## Live transport

Authenticated server-sent event projections:

```text
GET /v1/events/live?after_sequence=<n>
GET /v1/sessions/{session_id}/output/live
    ?stdout_after=<n>&stderr_after=<n>
```

Journal SSE reads the verified durable journal cursor and emits canonical `event_envelope` records with durable sequence as SSE ID.

Output SSE reads durable retained stdout/stderr cursors and emits only later retained bytes. Its SSE ID is `stdout_next:stderr_next`.

When the Session becomes terminal, output SSE drains any remaining retained bytes, emits terminal metadata, and closes.

SSE is transport only. Disconnect/reconnect resumes from durable query cursors; connection state is never mechanical truth.

## Integrity and retention

ADR-0003 output bounds remain authoritative. This generation creates no unbounded output history.

Incremental output-persistence failure causes capture failure and prevents the Session from pretending observation remained intact.

Authenticated delta/live reads verify retained-byte digests before returning data.

## Proof

The exact normalized and documentation-adjusted source passed:

- Rust 1.75 dependency compatibility including `tokio-stream 0.1.17`;
- Python, TypeScript, and Rust Contract Spine proof;
- exact three-runtime canonical/validity/error/SHA equivalence;
- Clippy with warnings denied;
- all Rust contract/daemon/Session/event/output/integrity tests;
- originsd build;
- ADR-0002 auth/persistence/journal/tamper/restart hosted proof;
- ADR-0003 supervised process hosted proof;
- ADR-0004 asynchronous acceptance/cancellation/event-cursor hosted proof;
- hosted Live Session Observation proof demonstrating:
  - output readable before a slow process completes;
  - no duplicate bytes from byte-cursor reads;
  - output disconnect/reconnect after prior cursors;
  - live journal delivery strictly after supplied durable sequence;
  - journal live reconnect without duplicate durable events;
  - live output reconnect over stdout/stderr cursors;
  - terminal output drain and close;
  - local authentication on live endpoints;
  - final retained output exactly matching incrementally persisted bytes;
  - one retained raw-output SQLite path rather than a duplicate chunk store;
  - raw output absent from permanent journal entries;
- repository sanitation and rustfmt.

The proof-gated normalizer produced the exact Rust formatting/dependency state at `5e6b32dd035d5b21f07f75764337a29385cff8d1`. An owner-authored evidence commit then triggered and passed fresh complete runtime and Contract Spine proof on the normalized source before this ADR was frozen.

## Explicit non-claims

This generation does not provide or claim:

- PTY/interactive terminal semantics;
- stdin or terminal resize;
- process reattachment after daemon restart;
- unbounded output retention;
- remote Node streaming;
- React UI ownership of event/output truth;
- AgentOps/CodeOps/Sergeant semantic orchestration.
