# ADR-0004 — Active Session Control v1

**Status:** PROVEN CANDIDATE — final normalized-head proof required before promotion
**Date:** 2026-08-07
**Depends on:** ADR-0001 Contract Spine, ADR-0002 originsd Foundation, ADR-0003 Supervised Process Sessions

## Decision

Active Origins process work no longer depends on a long-running command HTTP request.

This generation provides:

- asynchronous `origins.process.run` acceptance;
- immediate durable Session identity;
- exact active replay;
- cancellation of a locally controlled `running` Session;
- authenticated reconnectable event-history reads by journal sequence.

PTY interaction, live output chunks, remote Nodes, and semantic AgentOps/CodeOps/Sergeant orchestration remain separate slices.

## Asynchronous command acceptance

```text
POST /v1/commands
→ validate command + policy
→ create durable starting Session
→ register local supervisor control
→ schedule background process work
→ return HTTP 202 with Session identity
```

The HTTP response does not wait for process completion. The Session is immediately readable through the existing Session endpoint.

Exact replay uses the ADR-0003 command ID + canonical command-digest binding and never launches a second process. Changed replay remains conflict.

## Cancellation

Authenticated control surface:

```text
POST /v1/sessions/{session_id}/cancel
```

V1 cancellation is intentionally narrow: only a Session observed as `running` and controlled by the current daemon generation is cancellable.

Before the in-memory cancellation signal is delivered, Origins commits:

```text
process.session.cancel_requested
```

The existing `session_projection` contract is not expanded solely for this slice. A successfully cancelled process ends as:

```text
state = interrupted
exit_code = null
timed_out = false
```

and its terminal event carries the `cancelled_by_client` reason. This preserves the ADR-0003 rule that Origins does not invent a portable exit code when normal process completion was not observed.

`starting` Sessions are not claimed cancellable in v1. Terminal Sessions cannot be cancelled as though still active. A durable-active Session without a current daemon control handle reports conflict rather than false control.

## Supervisor boundary

The in-process `ProcessSupervisor` owns only ephemeral local cancellation senders. SQLite remains durable mechanical truth.

On daemon restart the supervisor map is empty. ADR-0003 recovery converts stale `starting`/`running` Sessions to `interrupted`; this generation does not claim process reattachment.

## Reconnectable event cursor

Authenticated read surface:

```text
GET /v1/events?after_sequence=<n>&limit=<n>
```

The store verifies the journal before returning validated canonical `event_envelope` records in ascending sequence order. The response includes:

- requested `after_sequence`;
- returned events;
- `next_sequence` cursor;
- current `head_sequence`;
- current hash-chain head.

A client can therefore disconnect, retain its last sequence, reconnect, and replay only later durable events. This is pull-based event replay, not yet push streaming.

## Challenge evidence

The substantive candidate has passed the inherited runtime/contract gates plus a hosted active-control proof covering:

1. a deliberately slow command returns HTTP 202 before child completion;
2. the returned Session identity is immediately readable;
3. the Session later reaches its truthful terminal state;
4. exact replay while active returns the same Session;
5. changed replay remains conflict;
6. a running process receives an explicit cancellation request;
7. cancellation resolves to `interrupted` with null exit code and `timed_out=false`;
8. terminal re-cancel is rejected;
9. event reads require authentication;
10. event cursor pages are ordered and non-duplicating;
11. `cancel_requested` is durably ordered before the cancellation terminal event;
12. reconnect after daemon restart replays the same post-cursor events;
13. ADR-0002 restart and ADR-0003 process/integrity proofs remain green;
14. Clippy, Rust tests/build, contract equivalence, and repository sanitation remain mandatory.

The Rust source/dependency normalizer runs only after substantive proof. Its normalized head must receive a fresh complete proof before this ADR is promoted to `PROVEN`.

## Explicit non-claims

This generation does not provide or claim:

- cancellation before a process reaches `running`;
- a dedicated `cancelled` Session state;
- PTY/interactive terminal control;
- live stdout/stderr push streaming;
- process reattachment after daemon restart;
- complete operating-system isolation;
- remote Node execution;
- AgentOps approval integration;
- CodeOps or Sergeant semantic loops;
- React UI.
