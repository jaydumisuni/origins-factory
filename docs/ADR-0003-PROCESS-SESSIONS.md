# ADR-0003 — Supervised Process Sessions v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 Contract Spine, ADR-0002 originsd Foundation

## Purpose

Add the first real mechanical work execution capability to Origins without jumping to a fake terminal UI or treating arbitrary shell strings as a universal tool protocol.

This slice is for bounded non-interactive processes used by repository work, build/test proof, CodeOps adapters, Sergeant and later specialist integrations.

PTY/interactive terminal sessions are a separate later slice because they require stronger attachment, stream, cancellation and restart semantics.

## New contract projection

Contract registry v1.1 adds `session_projection`.

A Session projection contains Origins-owned mechanical state only:

- `session_id`;
- `workspace_id`;
- `command_id`;
- capability ID;
- session kind;
- bounded workspace root;
- lifecycle state;
- process ID when available;
- start/update/end timestamps;
- exit code when known;
- timeout flag;
- stdout/stderr byte counts and SHA-256;
- output truncation state.

It does not copy AgentOps Attempt state or claim that one process Session equals one semantic Operation.

## Process command

`POST /v1/commands` accepts the existing `command_envelope`.

The first executable capability is:

```text
origins.process.run
```

Required effect:

```text
execute
```

Capability-specific payload:

```json
{
  "workspace_root": "/absolute/path/to/repository",
  "executable": "cargo",
  "args": ["test", "--all-targets"],
  "cwd": ".",
  "timeout_seconds": 300,
  "max_output_bytes": 1048576
}
```

## Execution boundary

The v1 runner:

- requires an existing Origins Workspace;
- canonicalizes and verifies `workspace_root` is an existing directory;
- requires `cwd` to be relative and resolve inside the canonical Workspace root;
- accepts an executable name, not an arbitrary command line;
- passes arguments as an argv array without shell parsing;
- rejects path separators in `executable`;
- rejects known shell executables in this generic capability;
- uses a conservative built-in executable allowlist for the first proof;
- inherits the daemon environment but does not accept request-supplied environment overrides yet;
- provides no stdin in v1;
- enforces timeout bounds;
- drains stdout/stderr while retaining only a bounded amount;
- hashes the complete observed stdout/stderr byte streams;
- never writes raw output into the hash-chained event journal;
- requires the same local bearer authentication as other mutation/execution routes.

A later explicit shell capability may exist if justified, but it must have its own descriptor, authority and proof. `origins.process.run` is not secretly `sh -c`.

## Initial executable allowlist

The first built-in allowlist exists to prove the architecture, not to become a permanent hard-coded product limitation.

Expected development tools include program-name variants for:

- Git;
- Python / `py`;
- pytest;
- Cargo / Rustc;
- Node / npm / npx;
- Hunter CodeOps CLI surfaces;
- Sergeant CLI.

Later capability manifests and Node discovery replace hard-coded development assumptions.

## Durable session lifecycle

States:

```text
starting
→ running
→ completed | failed | timed_out
```

On daemon startup, any durable `starting` or `running` process Session from a previous daemon instance becomes:

```text
interrupted
```

Origins does not invent process reattachment. A surviving orphan OS process is not treated as a recovered Session unless a later explicit reattachment mechanism proves identity and control.

## Output evidence

Raw bounded stdout/stderr bytes are stored outside the `session_projection` contract in an authenticated local output record.

The Session projection stores:

- total stdout bytes observed;
- total stderr bytes observed;
- SHA-256 of the full observed streams;
- whether retained output was truncated.

Authenticated read surface:

```text
GET /v1/sessions/{session_id}/output
```

Output is local evidence, not an AgentOps or Sergeant verdict.

## API additions

```text
POST /v1/commands
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
```

All require the local bearer token.

## Journal events

No raw command arguments or output are journaled.

The journal records bounded metadata events such as:

```text
process.session.started
process.session.completed
process.session.failed
process.session.timed_out
process.session.interrupted
```

Each event correlates Workspace, Session and command IDs without persisting secrets from argv/stdout/stderr.

## Recovery proof

The Challenge pass must prove:

1. an allowed process can run inside a Workspace root;
2. stdout and stderr are captured and hashed;
3. an executable outside the allowlist is rejected before spawn;
4. a known shell executable is rejected;
5. a `cwd` escape is rejected;
6. timeout kills/waits the child and records `timed_out`;
7. a non-zero process records `failed` and retains the exit code;
8. a successful process records `completed`;
9. unauthenticated command/session surfaces are rejected;
10. daemon restart changes stale `starting/running` Sessions to `interrupted` rather than claiming recovery;
11. raw argv/output are absent from journal events;
12. existing Contract Spine and originsd Foundation proofs remain green.

## Non-goals

This slice does not provide:

- PTY allocation;
- interactive stdin;
- terminal resize;
- live terminal WebSocket streaming;
- process reattachment after daemon crash;
- AgentOps approval integration;
- CodeOps semantic lifecycle integration;
- arbitrary shell execution;
- container execution;
- remote Node execution.

Those are layered after this mechanical process truth is proven.
