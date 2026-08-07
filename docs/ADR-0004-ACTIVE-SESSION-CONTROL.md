# ADR-0004 — Active Session Control v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 Contract Spine, ADR-0002 originsd Foundation, ADR-0003 Supervised Process Sessions

## Purpose

Make active Origins mechanical work independently controllable and observable without waiting for a long-running `POST /v1/commands` request to finish.

This slice adds:

- asynchronous process command acceptance;
- immediate durable Session identity;
- explicit cancellation;
- reconnectable event-history reads by journal sequence.

It does not add PTY interaction, live output chunks, remote Nodes, or semantic AgentOps/CodeOps/Sergeant orchestration.

## Asynchronous command theorem

A valid new `origins.process.run` command is durably accepted before its child process is allowed to become invisible behind a long HTTP request.

```text
POST /v1/commands
→ validate command + policy
→ create durable starting Session
→ register local supervisor control
→ schedule background process work
→ return HTTP 202 with Session identity
```

Exact replay of the same command ID + command digest returns the existing Session without executing twice. A changed envelope using the same command ID remains conflict.

## Cancellation

Authenticated local control adds:

```text
POST /v1/sessions/{session_id}/cancel
```

Cancellation is accepted only for a currently controllable local active process Session.

The Session contract adds terminal state:

```text
cancelled
```

A successful owner/client cancellation records `cancelled`, no synthetic exit code, `timed_out=false`, and a bounded journal event.

Terminal Sessions cannot be cancelled again as though they were active. If a Session is durable-active but no longer controlled by this daemon generation, Origins reports the contradiction rather than claiming cancellation.

## Supervisor boundary

The in-process supervisor owns only live local process-control handles. SQLite remains the durable truth.

On daemon restart:

- in-memory cancellation handles are gone;
- stale `starting`/`running` Sessions become `interrupted` under ADR-0003;
- Origins does not claim process reattachment or cancellation control over unknown surviving OS processes.

## Reconnectable event observation

Authenticated read surface:

```text
GET /v1/events?after_sequence=<n>&limit=<n>
```

The response returns validated canonical `event_envelope` records in ascending sequence order plus the current cursor/head information.

This provides deterministic reconnect/replay:

```text
client remembers last sequence
→ disconnects
→ reconnects
→ asks after_sequence=last_seen
→ receives only later durable events
```

This is not yet push streaming. A later WebSocket/SSE layer can project the same cursor semantics without becoming event truth.

## Proof requirements

Before promotion the exact head must prove:

1. command HTTP response returns before a deliberately slow child completes;
2. the returned Session identity is immediately readable;
3. the Session later reaches its truthful terminal state;
4. exact replay while active does not execute twice;
5. changed replay still conflicts;
6. cancellation of a running child reaches `cancelled`;
7. cancelled Session has no invented exit code and is not marked timed out;
8. cancellation of a terminal Session fails explicitly;
9. event reads require authentication;
10. event cursor replay returns ordered non-duplicated validated events;
11. reconnect after daemon restart can continue from a prior event sequence;
12. all ADR-0003 process, recovery, contract-equivalence, sanitation, and formatting proofs remain green.

## Explicit non-claims

This slice does not claim:

- PTY/interactive terminal control;
- live stdout/stderr streaming;
- process reattachment after daemon restart;
- complete operating-system isolation;
- remote Node execution;
- AgentOps approvals;
- CodeOps or Sergeant semantic loops;
- React UI.
