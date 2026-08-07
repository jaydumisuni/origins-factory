# ADR-0003 — Supervised Process Sessions v1

**Status:** PROVEN
**Date:** 2026-08-07
**Depends on:** ADR-0001 Contract Spine, ADR-0002 originsd Foundation

## Decision

Origins Factory has a proven first non-interactive mechanical execution capability: `origins.process.run`.

It uses a typed `command_envelope`, durable `session_projection`, authenticated local API, bounded process supervision, exact evidence, and fail-closed recovery. It is not a generic shell, PTY, semantic Operation, or unrestricted model-execution surface.

## Contract and API

Contract registry v1.1 adds `session_projection` with equivalent Rust, Python, and TypeScript validation.

The projection records Origins-owned mechanical facts: Workspace/Session/command identity, capability, authorized Workspace root, lifecycle state, process ID when available, timestamps, real exit code when known, timeout state, stdout/stderr byte counts and SHA-256, and output-truncation state.

Routes added:

```text
POST /v1/commands
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
```

All require the Origins local bearer token.

## Execution boundary

`origins.process.run` accepts an executable program name plus argv array. It does not parse a shell command string.

The runner:

- requires an existing Origins Workspace;
- requires the canonical working root to be under `ORIGINS_WORKSPACE_ROOTS`;
- requires relative `cwd` to resolve inside that root;
- rejects generic shell interpreters in this capability;
- uses a conservative built-in executable allowlist for this proof generation;
- clears the child environment and forwards only a reviewed minimal set needed for ordinary tool execution;
- does not forward Origins credentials or arbitrary daemon environment variables;
- accepts no caller-supplied environment or stdin in v1;
- enforces timeout and retained-output bounds;
- hashes complete observed stdout/stderr streams;
- separately hashes retained output bytes so local-output tampering fails closed;
- keeps raw argv and output out of the permanent event journal.

`ORIGINS_WORKSPACE_ROOTS` is a working-root authorization policy, not a claim of complete operating-system isolation. Stronger containment remains separate future work.

## Replay identity

`command_id` is durably bound to the canonical SHA-256 of the complete validated command envelope.

```text
same command_id + same digest
→ return existing Session; do not execute twice

same command_id + different digest
→ conflict; do not execute
```

## Mechanical lifecycle

```text
starting
→ running
→ completed | failed | timed_out | interrupted
```

- `completed`: real portable exit code `0` observed.
- `failed`: real non-zero portable exit code observed.
- `timed_out`: bounded timeout reached; no exit code is invented.
- `interrupted`: Origins cannot truthfully claim ordinary portable completion or a real numeric exit code.

Spawn/wait/output-capture infrastructure failures and termination without a portable numeric exit code use `interrupted`. Stale `starting`/`running` Sessions after daemon restart also become `interrupted`. This generation does not claim process reattachment.

## Output evidence

The Session projection retains complete-stream byte counts and SHA-256 values. Bounded stdout/stderr bytes are stored in an authenticated local output record with independent retained-byte digests.

Output reads fail closed on retained-byte digest mismatch. The API returns UTF-8 text when valid plus exact hexadecimal retained bytes for binary/non-UTF-8 evidence.

Output is mechanical evidence, not an AgentOps or Sergeant verdict.

## Journal boundary

The hash-chained journal records bounded correlation metadata only:

```text
process.session.starting
process.session.running
process.session.completed
process.session.failed
process.session.timed_out
process.session.interrupted
```

The starting event records command-envelope and argv digests, not raw arguments. Raw stdout/stderr are not journaled.

## Proof

The exact normalized branch head passed:

- Python contract proof;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript canonical JSON, validity/error, and SHA-256 equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/integrity tests;
- originsd build on frozen Rust 1.75;
- existing originsd auth/persistence/journal/restart proof;
- hosted supervised-process proof covering success, real non-zero exit, spawn interruption, timeout, output truncation, exact replay, changed replay conflict, environment credential hygiene, shell rejection, cwd/root policy, Workspace Session references, journal hygiene, and retained-output tamper detection;
- repository whitespace and rustfmt gates.

A proof-gated normalization step produced the exact Rust formatting/dependency state, and that normalized source received a fresh complete proof before this ADR was frozen.

## Explicit non-claims

This generation does not provide or claim:

- PTY/interactive terminal sessions;
- stdin, resize, or live process streaming;
- asynchronous command acceptance/cancellation semantics;
- process reattachment after daemon restart;
- complete OS-level process/filesystem isolation;
- AgentOps approval integration;
- CodeOps semantic lifecycle integration;
- Sergeant semantic review integration;
- arbitrary shell execution;
- remote Node execution;
- React UI.

Those remain separate capability slices with independent authority and proof gates.
