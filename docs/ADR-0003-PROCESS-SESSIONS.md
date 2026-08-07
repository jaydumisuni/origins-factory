# ADR-0003 — Supervised Process Sessions v1

**Status:** PROVEN CANDIDATE — final exact-head verification required before promotion
**Date:** 2026-08-07
**Depends on:** ADR-0001 Contract Spine, ADR-0002 originsd Foundation

## Purpose

Add the first bounded non-interactive mechanical work capability to Origins without treating an arbitrary shell string as the universal execution protocol.

This slice supports repository engineering, deterministic build/test work, CodeOps adapters, Sergeant adapters, and later specialist integrations. Interactive PTY sessions remain a separate slice.

## Session contract

Contract registry v1.1 adds `session_projection` with equivalent Rust, Python, and TypeScript validation.

The projection records Origins-owned mechanical facts:

- Session, Workspace, and command identity;
- capability and Session kind;
- authorized Workspace root;
- lifecycle state;
- process ID when available;
- timestamps;
- real exit code when one is observed;
- timeout state;
- stdout/stderr byte counts and SHA-256;
- output truncation state.

It does not duplicate AgentOps Attempt state and does not imply that a process Session equals a semantic Operation.

## Command boundary

`POST /v1/commands` accepts a validated `command_envelope` for:

```text
capability: origins.process.run
effect: execute
```

Payload shape:

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

The runner:

- requires an existing Origins Workspace;
- requires the canonical Workspace root to be under an installation-authorized `ORIGINS_WORKSPACE_ROOTS` path;
- requires `cwd` to remain inside that root;
- accepts a registered executable name plus argv array rather than a shell command string;
- rejects generic shell interpreters in this capability;
- uses a conservative built-in executable allowlist for this proof generation;
- starts the child with a cleared environment and forwards only a reviewed minimal set needed for ordinary tool discovery/runtime behavior;
- does not forward Origins credentials or arbitrary daemon environment variables;
- accepts no caller-supplied environment or stdin in v1;
- enforces timeout and output-retention bounds;
- hashes the complete observed stdout/stderr streams while retaining bounded output;
- independently protects the retained output bytes with digests;
- keeps raw argv and raw output out of the permanent hash-chained journal;
- requires local bearer authentication on execution and Session read surfaces.

`ORIGINS_WORKSPACE_ROOTS` restricts which working trees Origins accepts for this capability. It is not claimed as complete operating-system isolation. Stronger process/resource isolation is later work and must receive its own proof.

## Replay identity

A command ID is bound to the canonical SHA-256 of the complete validated command envelope.

```text
same command_id + same command digest
→ return existing Session
→ do not execute twice

same command_id + different command digest
→ conflict
→ do not execute
```

This prevents an accepted command identity from being reused for changed arguments or bounds.

## Lifecycle truth

```text
starting
→ running
→ completed | failed | timed_out | interrupted
```

- `completed`: a real portable exit code `0` was observed.
- `failed`: a real non-zero portable exit code was observed.
- `timed_out`: the execution exceeded its bound; no exit code is invented.
- `interrupted`: Origins cannot truthfully claim ordinary portable process completion or a real numeric exit code.

Infrastructure cases such as spawn failure, unavailable process identity, wait failure, non-numeric termination, output-capture failure, or daemon restart without proven process reattachment are recorded as `interrupted` rather than assigned a synthetic exit code.

On daemon startup, stale durable `starting` or `running` Sessions become `interrupted`. Origins does not claim process reattachment in this generation.

## Output evidence

The Session projection records complete-stream byte counts and SHA-256 values. Bounded retained stdout/stderr bytes are stored separately behind authenticated Session output reads.

The retained byte records have independent digests. A mismatch is reported as corrupt state rather than returned as valid output.

`GET /v1/sessions/{session_id}/output` provides text when retained bytes are valid UTF-8 and also exposes an exact hexadecimal representation for binary/non-UTF-8 evidence.

Output is mechanical evidence, not an AgentOps or Sergeant verdict.

## API additions

```text
POST /v1/commands
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
```

All require the Origins local bearer token.

## Journal events

The journal records bounded process metadata only:

```text
process.session.starting
process.session.running
process.session.completed
process.session.failed
process.session.timed_out
process.session.interrupted
```

The starting record includes command-envelope and argv digests, not raw arguments. Raw stdout/stderr are not journaled.

## Challenge evidence

The candidate has already passed substantive hosted proof for:

1. allowed process execution under an authorized Workspace root;
2. stdout/stderr byte counts and full-stream SHA-256;
3. child-environment credential hygiene;
4. exact replay idempotency;
5. changed-envelope replay conflict;
6. non-zero exit truth;
7. spawn failure as `interrupted` without a synthetic exit code;
8. timeout truth;
9. bounded retained output with complete-stream evidence;
10. shell rejection;
11. relative working-directory escape rejection;
12. unauthorized Workspace-root rejection;
13. bearer authentication;
14. durable Workspace Session references and revision advancement;
15. raw credential/argv/output absence from daemon logs and journal events;
16. retained-output tamper detection;
17. stale active Session → `interrupted` recovery;
18. preservation of the existing originsd restart proof.

Clippy with warnings denied, Rust tests, daemon build, hosted foundation recovery, hosted process proof, and repository sanitation have all passed on the challenged source. The source was then mechanically normalized by the proof-gated formatter/dependency freezer. The normalized head must receive a fresh complete proof before promotion.

## Explicit non-claims

This slice does not claim:

- PTY allocation or interactive terminals;
- stdin/resize/live process streams;
- process reattachment after daemon restart;
- complete OS-level process/filesystem isolation;
- AgentOps approval integration;
- CodeOps semantic lifecycle integration;
- Sergeant semantic review integration;
- arbitrary shell execution;
- remote Node execution;
- React UI.

Those capabilities remain separate future slices with their own authority and proof gates.
