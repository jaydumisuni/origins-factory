# ADR-0005 — Live Session Observation v1

**Status:** PROVEN CANDIDATE — final exact normalized-head proof required before promotion
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0004

## Decision

Origins can project durable events and bounded process output while work is still running without making a socket, UI buffer, or second raw-output database authoritative.

This generation adds:

1. authenticated live journal-event delivery over the proven event-sequence cursor;
2. incremental retained stdout/stderr persistence in the existing `session_outputs` record;
3. authenticated byte-cursor delta reads;
4. authenticated live output delivery over the same durable retained-byte cursors.

## One-copy output rule

`session_outputs` remains the single local retained raw-output store.

During process execution, capture tasks append only bytes that fit inside the command's existing retention bound to the existing stdout/stderr blobs. Each append transactionally verifies the prior retained digest and writes the next retained digest.

No `session_output_chunks` or other second raw-output table is introduced.

The final Session projection continues to record complete observed stream byte counts and SHA-256. If a stream exceeds retention, SQLite holds only the retained prefix while the final projection describes the complete observed stream.

The permanent hash-chained journal remains metadata/digest-only; raw stdout/stderr do not enter it.

## Reconnectable output cursor

Authenticated read surface:

```text
GET /v1/sessions/{session_id}/output/delta
    ?stdout_after=<byte-offset>
    &stderr_after=<byte-offset>
    &limit=<bytes-per-stream>
```

Each stream returns:

- requested retained-byte offset;
- next retained-byte offset;
- current retained head offset;
- exact bytes as hexadecimal;
- UTF-8 text only when that returned slice is valid UTF-8.

A repeated read from the returned `next` offset produces only later retained bytes. A cursor beyond the retained head is conflict rather than silent reset.

## Live transport

Authenticated server-sent event projections:

```text
GET /v1/events/live?after_sequence=<n>
GET /v1/sessions/{session_id}/output/live
    ?stdout_after=<n>&stderr_after=<n>
```

The journal stream repeatedly reads the verified durable event cursor and emits canonical `event_envelope` records with their durable sequence as SSE ID.

The output stream repeatedly reads the durable retained stdout/stderr cursors and emits only later retained bytes. Its SSE ID is the pair `stdout_next:stderr_next`.

When a Session becomes terminal, the output stream drains remaining retained bytes, emits terminal metadata, and closes.

SSE is a transport projection only. Disconnect/reconnect resumes from the ordinary durable query cursors; stream connection state is not mechanical truth.

## Retention and integrity

ADR-0003 output bounds remain authoritative. This slice does not create unbounded output history.

Incremental persistence failure is a mechanical execution failure: the capture path fails and the Session does not continue as though output remained observable.

Authenticated delta/live reads verify retained-byte digests before returning data.

## Challenge evidence

The substantive candidate passed:

- Rust 1.75 dependency generation with `tokio-stream 0.1.17`;
- Clippy with warnings denied;
- all Rust contract/daemon/Session/event/output tests;
- originsd build;
- ADR-0002 authentication, persistence, journal, tamper, and restart hosted proof;
- ADR-0003 supervised process proof;
- ADR-0004 asynchronous acceptance, cancellation, and durable event-cursor proof;
- a new hosted Live Session Observation proof demonstrating:
  1. stdout retained bytes are durably readable before a slow process completes;
  2. the same byte cursor read twice does not duplicate data;
  3. disconnect/reconnect continues after the prior stdout/stderr cursors;
  4. live journal SSE starts strictly after the supplied durable sequence;
  5. journal SSE reconnect continues after the prior durable sequence;
  6. live output SSE resumes from retained-byte cursors;
  7. terminal live output emits terminal metadata and closes;
  8. live routes require local authentication;
  9. final retained stdout/stderr exactly match the incrementally persisted bytes;
  10. SQLite contains one retained raw-output table/row path rather than a duplicate chunk store;
  11. raw output is absent from permanent journal entries.
- repository whitespace sanitation.

The three-language Contract Spine proof also passed all semantic/equivalence gates on the substantive candidate; its only failure was rustfmt. The proof-gated owner-branch normalizer then produced the exact formatting/dependency state at head `5e6b32dd035d5b21f07f75764337a29385cff8d1`.

GitHub did not execute PR workflows on that bot-authored normalization commit, so this owner-authored evidence update is the trigger for the required exact normalized-head proof. A pre-normalization green run alone is not the merge gate.

## Explicit non-claims

This slice does not provide or claim:

- PTY/interactive terminal semantics;
- stdin or terminal resize;
- process reattachment after daemon restart;
- unbounded output retention;
- remote Node streaming;
- React UI ownership of event/output truth;
- AgentOps/CodeOps/Sergeant semantic orchestration.
