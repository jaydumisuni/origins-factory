# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine v1 + originsd persistence + supervised Process Sessions v1 implemented and mechanically proven

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. The accepted implementation foundation now contains a cross-language contract spine, persistent Rust control plane, and the first bounded mechanical execution capability.

## Proven foundation

### Contract Spine

The shared Rust/Python/TypeScript contract layer provides:

- `authority_ref`;
- `workspace_projection`;
- `capability_descriptor`;
- `command_envelope`;
- `event_envelope`;
- `session_projection`;
- deterministic canonical JSON and SHA-256 identity;
- unknown-field rejection;
- floating-point rejection and cross-language safe-integer bounds;
- explicit capability self-promotion rejection;
- exact three-runtime validity/error/canonical/SHA equivalence proof.

### originsd persistence

The persistent Rust daemon provides:

- Rust 1.75 proof boundary;
- loopback-only service binding;
- per-install local bearer authentication;
- SQLite schema v2 with WAL and foreign keys;
- durable Origins Workspace projections;
- built-in capability projections;
- append-only hash-chained event journal;
- canonical validation/digest checks on durable reads;
- Workspace and journal tamper detection;
- clean daemon restart recovery;
- proof-frozen Rust dependency graph.

### Supervised Process Sessions v1

`origins.process.run` now provides bounded non-interactive execution through typed commands and durable Sessions:

- `POST /v1/commands` for the registered process capability only;
- authenticated Session list/read/output surfaces;
- authorized Workspace-root policy;
- contained relative working-directory resolution;
- executable allowlist and generic-shell rejection;
- argv execution without shell-string parsing;
- cleared child environment with reviewed minimal inherited variables;
- no caller-supplied environment or stdin;
- timeout and retained-output bounds;
- complete stdout/stderr stream byte counts and SHA-256;
- independently digested retained output bytes;
- exact command-envelope digest bound to command ID;
- same-command replay idempotency;
- changed-envelope replay conflict;
- durable `starting → running → completed | failed | timed_out | interrupted` truth;
- no synthetic exit code when a real portable code was not observed;
- stale active Session → `interrupted` restart recovery;
- Workspace Session references and revision advancement;
- permanent journal metadata without raw argv/stdout/stderr.

Current routes:

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
POST /v1/commands
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
```

## Proof state

The challenged and normalized Process Sessions candidate has passed:

- Python contract tests;
- TypeScript contract tests;
- Rust contract tests;
- exact three-runtime contract equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/integrity tests;
- originsd build;
- existing daemon auth/persistence/journal/restart hosted proof;
- hosted process proof for success, real non-zero exit, spawn interruption, timeout, output truncation, replay binding, changed replay conflict, environment credential hygiene, shell rejection, cwd/root policy, Workspace references, journal hygiene, and retained-output tamper detection;
- repository whitespace and rustfmt gates.

Corrections discovered by Challenge remain part of the engineering history:

- Rust function signatures were refactored into typed Session mutation structures rather than suppressing Clippy;
- command replay was strengthened from ID-only to ID + exact command-envelope digest;
- child environment inheritance was replaced by explicit minimal forwarding;
- root selection was bounded by installation-authorized Workspace roots;
- infrastructure/no-code failures were classified as `interrupted` rather than assigned fake exit codes;
- retained output gained its own integrity digest;
- proof-gated source/dependency normalization was added so formatting/lock cleanup cannot precede substantive proof.

## Canonical repository authority

Recovery order remains:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. current source, ADRs, PRs, and proof;
5. the owning repository for every mounted external capability.

Implementation ADRs now include:

- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/ADR-0002-ORIGINSD-FOUNDATION.md`;
- `docs/ADR-0003-PROCESS-SESSIONS.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative and must not be revived as the implementation base.

## Explicit current limitations

Not implemented or proven yet:

- asynchronous command acceptance and cancellation;
- live event/output streaming;
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

Before broad UI work, Origins should make active mechanical work independently controllable and observable:

1. define asynchronous command acceptance so a caller receives a durable Session identity without waiting for process completion;
2. add explicit cancellation semantics and proof;
3. add authenticated live event/output streaming over the existing typed event/session truth;
4. preserve restart honesty — do not claim reattachment until separately proven;
5. then recover/freeze the native repository/Git Session boundary required by CodeOps;
6. mount AgentOps + CodeOps + Sergeant through their owning contracts;
7. prove `NEEDS WORK → correction Attempt → fresh proof → PASS` through Origins before broad React workspace construction.

## Blocking rule

Do not let UI, Python workers, models, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
