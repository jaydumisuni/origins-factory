# ADR-0004 — Active Session Control v1

**Status:** PROVEN
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

Before the in-memory cancellation signal is delivered, Origins commits `process.session.cancel_requested` to the durable journal.

The existing `session_projection` contract is not expanded solely for this slice. A successfully cancelled process ends as:

```text
state = interrupted
exit_code = null
timed_out = false
```

and its terminal event carries the `cancelled_by_client` reason. This preserves ADR-0003 mechanical truth rather than inventing a portable exit code.

`starting` Sessions are not claimed cancellable in v1. Terminal Sessions cannot be cancelled as though still active. A durable-active Session without a current daemon control handle reports conflict rather than false control.

## Supervisor boundary

The in-process `ProcessSupervisor` owns only ephemeral local cancellation senders. SQLite remains durable mechanical truth.

On daemon restart the supervisor map is empty. ADR-0003 recovery converts stale `starting`/`running` Sessions to `interrupted`; this generation does not claim process reattachment.

## Reconnectable event cursor

Authenticated read surface:

```text
GET /v1/events?after_sequence=<n>&limit=<n>
```

The store verifies the journal before returning validated canonical `event_envelope` records in ascending sequence order. The response includes the requested cursor, next cursor, current head sequence, and current hash-chain head.

A client can disconnect, retain its last sequence, reconnect, and replay only later durable events. This is pull-based event replay, not yet push streaming.

## Proof

The challenged exact source passed:

- Python, TypeScript, and Rust contract proof;
- exact three-runtime canonical/validity/error/SHA equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/event/integrity tests;
- originsd build under Rust 1.75;
- ADR-0002 auth/persistence/journal/restart hosted proof;
- ADR-0003 process/integrity hosted proof adapted to asynchronous command acceptance;
- hosted active-control proof demonstrating early HTTP 202 return, immediate Session readability, active exact replay, running-process cancellation, terminal re-cancel rejection, authenticated ordered event pagination, durable cancellation-event ordering, and event replay after daemon restart;
- repository sanitation and rustfmt.

The proof-gated Rust normalizer produced no unresolved semantic delta. The documentation-adjusted head must retain the same full green proof before merge.

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
