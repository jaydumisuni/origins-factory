# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine + persistent originsd + supervised Process Sessions + Active Session Control implemented and mechanically proven

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. Its accepted implementation foundation now has cross-language contracts, persistent Rust state, bounded local process execution, asynchronous Session control, cancellation, and reconnectable durable event replay.

## Proven foundation

### Contract Spine

Rust, Python, and TypeScript share exact validation/canonicalization for:

- `authority_ref`;
- `workspace_projection`;
- `capability_descriptor`;
- `command_envelope`;
- `event_envelope`;
- `session_projection`.

The spine enforces deterministic JSON/SHA identity, no floats, cross-language safe integers, unknown-field rejection, and no capability self-promotion. Exact three-runtime validity/error/canonical/SHA equivalence is proven.

### originsd persistence

The Rust 1.75 daemon provides:

- loopback-only service binding;
- per-install local bearer authentication;
- SQLite schema v2 with WAL/foreign keys;
- durable Workspace and Session projections;
- built-in capability projections;
- append-only SHA-256 hash-chained event journal;
- canonical validation and digest checks on durable reads;
- Workspace, journal, and retained-output tamper detection;
- restart recovery;
- proof-frozen Rust dependency state.

### Supervised Process Sessions v1

`origins.process.run` provides:

- registered executable + argv execution without generic shell parsing;
- installation-authorized Workspace-root policy and contained relative `cwd`;
- cleared child environment with reviewed minimal forwarding;
- no caller-supplied environment or stdin;
- timeout and retained-output bounds;
- complete stdout/stderr byte counts and SHA-256;
- independent retained-output digests;
- exact command-envelope digest bound to command ID;
- exact replay idempotency and changed-replay conflict;
- truthful `starting → running → completed | failed | timed_out | interrupted` state;
- no invented exit codes;
- stale active Session → `interrupted` restart recovery;
- Workspace Session references and journal metadata without raw argv/stdout/stderr.

### Active Session Control v1

Active work is no longer hidden behind a long command HTTP request:

- `POST /v1/commands` returns HTTP 202 with a durable Session identity before child completion;
- the Session is immediately readable while work continues in the daemon;
- exact replay while active returns the same Session without duplicate execution;
- `POST /v1/sessions/{session_id}/cancel` cancels a currently controlled `running` Session;
- cancellation intent is journaled before the process-control signal;
- cancelled work resolves through existing truthful `interrupted` state with null exit code and `timed_out=false`;
- `GET /v1/events?after_sequence=&limit=` provides authenticated, validated, ordered journal replay with cursor/head metadata;
- event cursors survive client disconnect and daemon restart.

Current routes:

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
POST /v1/commands
GET  /v1/events
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
POST /v1/sessions/{session_id}/cancel
```

## Proof state

The current exact-head challenge has passed:

- Python contract proof;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/event/integrity tests;
- originsd build under Rust 1.75;
- existing daemon auth/persistence/journal/restart hosted proof;
- ADR-0003 process proof adapted to asynchronous acceptance;
- hosted active-control proof demonstrating early HTTP return, immediate Session readability, active exact replay, running-process cancellation, terminal re-cancel rejection, authenticated ordered event pagination, cancel-event ordering, and event replay after daemon restart;
- repository sanitation and rustfmt.

Challenge corrections remain visible in the ADR/source history. In particular, v1 cancellation was narrowed to `running` Sessions rather than claiming unproved cancel-before-spawn behavior.

## Canonical repository authority

Recovery order:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. implementation ADRs, current source, PRs, and proof;
5. the owning repository for every mounted external capability.

Implementation ADRs:

- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/ADR-0002-ORIGINSD-FOUNDATION.md`;
- `docs/ADR-0003-PROCESS-SESSIONS.md`;
- `docs/ADR-0004-ACTIVE-SESSION-CONTROL.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not implemented or proven yet:

- push/live event streaming;
- incremental live stdout/stderr persistence/streaming;
- cancellation while a Session is only `starting`;
- PTY/interactive terminal Sessions;
- process reattachment after daemon restart;
- stronger OS-level process/resource isolation;
- native Git/repository Session model beyond invoking registered Git tooling;
- accepted Python Origins integration runtime;
- production Hunter mount;
- AgentOps lifecycle/approval mount;
- CodeOps mission loop inside Origins;
- Sergeant correction/completion loop inside Origins;
- React workspace shell;
- Oracle integration;
- Lumi integration;
- specialist Gateway clients;
- Ptah runtime integration;
- Windows/Linux desktop packages;
- release proof.

## Next valid implementation slice

Continue mechanical observability before broad UI work:

1. define reconnect-safe live event delivery as a projection over the proven journal cursor;
2. add bounded incremental process-output persistence/observation without putting raw output into the permanent journal;
3. prove disconnect/reconnect without output duplication or loss inside the retained-output boundary;
4. preserve restart honesty — do not claim process reattachment;
5. then recover and freeze the native repository/Git Session boundary needed by CodeOps;
6. mount AgentOps + CodeOps + Sergeant through their owning contracts;
7. prove `NEEDS WORK → correction Attempt → fresh proof → PASS` through Origins;
8. begin broad React Workspace construction only after those mechanical/assurance truths exist.

## Blocking rule

Do not let UI, Python workers, models, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
