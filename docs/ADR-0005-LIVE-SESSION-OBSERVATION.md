# ADR-0005 — Live Session Observation v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0004

## Purpose

Let an Origins client observe durable events and bounded process output while work is still running, disconnect, reconnect with cursors, and continue without making a UI/WebSocket buffer the source of truth.

This slice adds two projections over existing durable state:

1. live journal-event delivery over the proven event-sequence cursor;
2. incremental retained stdout/stderr observation over the existing `session_outputs` record.

No second raw-output database or duplicate retained-output copy is introduced.

## One-copy output rule

`session_outputs` remains the single local retained raw-output store.

During process execution, the capture tasks append only the bytes that fit inside the already-approved retention bound to the existing stdout/stderr blobs and update their retained-byte digests transactionally.

The final Session projection still records complete observed stream byte counts and SHA-256 values. When a stream exceeds the retained-output limit, the database keeps only the retained prefix while the final projection proves the size/hash of the complete observed stream.

The permanent hash-chained journal continues to contain process metadata and digests only; raw output does not enter the journal.

## Reconnectable output cursor

Authenticated read surface:

```text
GET /v1/sessions/{session_id}/output/delta
    ?stdout_after=<byte-offset>
    &stderr_after=<byte-offset>
    &limit=<bytes-per-stream>
```

Each stream returns:

- requested byte offset;
- next byte offset;
- current retained head offset;
- exact bytes as hexadecimal;
- UTF-8 text only when the returned bytes are valid UTF-8.

Offsets refer to retained bytes, not complete-stream byte counts after truncation. A cursor beyond the retained head is rejected rather than silently reset.

## Live transport

Origins exposes authenticated server-sent event projections:

```text
GET /v1/events/live?after_sequence=<n>
GET /v1/sessions/{session_id}/output/live
    ?stdout_after=<n>&stderr_after=<n>
```

The live journal stream repeatedly reads the durable journal cursor and emits validated `event_envelope` projections.

The live output stream repeatedly reads durable retained-output byte cursors and emits only newly available retained bytes. When the Session becomes terminal, it drains the final retained delta, emits terminal metadata, and closes.

The push connection is not durable truth. A disconnected client resumes through the same query cursors used by ordinary authenticated reads.

## Retention and integrity

This generation keeps ADR-0003 retention bounds. It does not create unbounded output history.

Incremental writes:

- never exceed the per-stream retained prefix chosen by the command;
- update retained-byte SHA-256 after each durable append;
- fail the process Session closed if incremental output persistence fails.

Reads verify retained-byte digests before returning data.

## Proof requirements

Before promotion the exact head must prove:

1. output becomes readable before a deliberately slow process completes;
2. only one retained raw-output copy exists in SQLite;
3. byte-cursor delta reads return no duplicates;
4. disconnect/reconnect with prior byte cursors resumes at the next byte;
5. truncation remains bounded while final complete-stream byte count/hash remain truthful;
6. retained-output tampering still fails closed;
7. event live delivery begins after the requested journal sequence;
8. journal live reconnect resumes without duplicate durable events;
9. output live delivery drains final retained bytes and terminates after Session terminal state;
10. live endpoints require authentication;
11. raw output remains absent from the permanent journal;
12. every ADR-0002/0003/0004 and cross-language contract proof remains green.

## Explicit non-claims

This slice does not provide or claim:

- PTY/interactive terminal semantics;
- stdin or terminal resize;
- process reattachment after daemon restart;
- unbounded output retention;
- remote Node streaming;
- React UI ownership of event/output truth;
- AgentOps/CodeOps/Sergeant semantic orchestration.
