# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine + persistent originsd + Process Sessions + Active Control + Live Session Observation implemented and mechanically proven

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. Its accepted mechanical foundation now provides cross-language contracts, persistent Rust state, bounded local process execution, asynchronous control, cancellation, durable event replay, live authenticated event projection, and reconnectable one-copy retained process output.

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

- `POST /v1/commands` returns HTTP 202 with durable Session identity before child completion;
- active exact replay returns the same Session without duplicate execution;
- controlled `running` Sessions can be cancelled explicitly;
- cancellation intent is journaled before the process-control signal;
- cancelled work resolves through truthful `interrupted` state with null exit code;
- durable event history is readable by `after_sequence` cursor across disconnect/restart.

### Live Session Observation v1

Live transport is now a projection over durable state rather than a new source of truth:

- incremental retained stdout/stderr bytes are written into the existing `session_outputs` row while a process runs;
- there is no second raw-output/chunk store;
- each retained append verifies and updates its retained-byte SHA-256 transactionally;
- final Session evidence still describes the complete observed stream even when retention truncates it;
- authenticated output delta reads use independent stdout/stderr retained-byte cursors;
- authenticated SSE journal delivery starts after a supplied durable event sequence;
- authenticated SSE output delivery resumes from retained byte cursors;
- output SSE drains remaining retained bytes, emits terminal metadata, and closes when the Session becomes terminal;
- raw process output remains absent from the permanent hash-chained journal.

Current routes:

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
POST /v1/commands
GET  /v1/events
GET  /v1/events/live
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
GET  /v1/sessions/{session_id}/output/delta
GET  /v1/sessions/{session_id}/output/live
POST /v1/sessions/{session_id}/cancel
```

## Proof state

The Live Observation challenge has passed on normalized source:

- Python contract proof;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/event/output/integrity tests;
- originsd build under Rust 1.75;
- existing daemon auth/persistence/journal/restart proof;
- ADR-0003 supervised process proof;
- ADR-0004 asynchronous control/cancellation/event-cursor proof;
- hosted ADR-0005 proof demonstrating output-before-completion, non-duplicating byte cursors, output disconnect/reconnect, live journal cursor reconnect, live output reconnect, terminal drain, authentication, exact final retained output, one-copy SQLite raw-output storage, and permanent-journal output hygiene;
- repository sanitation and rustfmt.

The proof-gated normalizer produced exact dependency/format state, and an owner-authored evidence commit triggered a fresh full runtime + Contract Spine proof on the normalized source before this state record was advanced.

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
- `docs/ADR-0004-ACTIVE-SESSION-CONTROL.md`;
- `docs/ADR-0005-LIVE-SESSION-OBSERVATION.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not implemented or proven yet:

- PTY/interactive terminal Sessions;
- stdin and terminal resize;
- process reattachment after daemon restart;
- stronger OS-level process/resource isolation;
- native repository/Git Session model beyond invoking registered Git tooling;
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

Mechanical process observation is now sufficient to begin the **native repository/Git Session boundary required by CodeOps**, still before broad UI work:

1. recover current CodeOps repository/open/diff/status/proof interfaces from its owning repository;
2. define an Origins-owned repository Session projection that references canonical Git repository/revision truth rather than copying CodeOps state;
3. implement read-first repository discovery/status/diff through registered deterministic Git capability boundaries;
4. preserve branch/worktree identity and exact revisions across reconnect;
5. keep mutations behind explicit typed capabilities rather than generic process execution;
6. then mount AgentOps + CodeOps + Sergeant through their owning contracts;
7. prove `NEEDS WORK → correction Attempt → fresh proof → PASS` through Origins;
8. begin broad React Workspace construction only after those mechanical and assurance truths exist.

## Blocking rule

Do not let UI, Python workers, models, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
