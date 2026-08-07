# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine + persistent originsd + Process Sessions + Active Control + Live Observation + Repository/Git Sessions implemented and mechanically proven

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. Its accepted mechanical foundation now provides cross-language contracts, persistent Rust state, bounded local process execution, asynchronous control/cancellation, reconnectable event/output observation, and durable read-first repository/Git identity beneath CodeOps.

## Proven foundation

### Contract Spine v1.2

Rust, Python, and TypeScript share exact validation/canonicalization for:

- `authority_ref`;
- `workspace_projection`;
- `capability_descriptor`;
- `command_envelope`;
- `event_envelope`;
- `session_projection`;
- `repository_projection`.

The spine enforces deterministic JSON/SHA identity, no floats, cross-language safe integers, unknown-field rejection, no capability self-promotion, and fail-closed Repository attached/detached/unborn state rules. Exact three-runtime validity/error/canonical/SHA equivalence is proven across the current 15-case corpus.

### originsd persistence

The Rust 1.75 daemon provides:

- loopback-only service binding;
- per-install local bearer authentication;
- SQLite core schema v2 with WAL/foreign keys;
- durable Workspace and Session projections;
- core and subsystem capability projections in one durable registry;
- append-only SHA-256 hash-chained event journal;
- canonical validation/digest checks on durable reads;
- Workspace, journal, retained-output, and Repository projection tamper detection;
- restart recovery;
- proof-frozen Rust dependency state.

### Supervised Process Sessions v1

`origins.process.run` provides bounded non-interactive execution through registered executable + argv, authorized Workspace roots, contained relative `cwd`, cleared/minimal child environment, timeout/output bounds, complete-stream byte/SHA evidence, exact command replay binding, truthful terminal states, and honest `interrupted` restart recovery.

Generic shells remain rejected. After Repository/Git v1, public generic process commands also reject `git`/`git.exe`; Git mechanical reads now have one dedicated authority path.

### Active Session Control v1

- `POST /v1/commands` returns HTTP 202 before child completion;
- active exact replay does not execute twice;
- controlled `running` Sessions can be cancelled;
- cancellation intent is journaled before the process-control signal;
- cancelled work resolves through truthful `interrupted` state with null exit code;
- durable event history is replayable by sequence cursor across disconnect/restart.

### Live Session Observation v1

- incremental retained stdout/stderr uses the existing one-copy `session_outputs` storage;
- no duplicate raw-output/chunk database exists;
- retained-output digests update transactionally;
- final Session evidence still describes complete observed streams beyond retention bounds;
- authenticated output delta reads use retained-byte cursors;
- authenticated SSE events project the durable journal cursor;
- authenticated SSE output resumes from durable byte cursors and drains on terminal state;
- raw output remains outside the permanent hash-chained journal.

### Repository/Git Sessions v1

Origins now owns read-first mechanical Git truth beneath CodeOps:

- dedicated Repository/Git subsystem schema v1;
- subsystem-owned capability manifests `origins.repository.inspect` and `origins.repository.diff` registered into the shared capability table;
- durable Repository identity keyed by Workspace + canonical worktree root;
- canonical worktree, Git directory, and Git common-directory identity;
- attached branch, detached HEAD, and unborn state representation;
- exact HEAD OID/ref/branch truth;
- staged, unstaged, and untracked counts;
- SHA-256 over the complete raw porcelain status stream;
- bounded staged/unstaged diff retention with complete observed byte count/SHA and truncation truth;
- linked-worktree identity preserving distinct Git directories and shared common directory;
- Repository projections survive daemon restart and fail closed on digest/contract tamper;
- raw diff content stays out of the permanent journal;
- direct Git argv only, no shell and no Git mutation capability.

CodeOps continues to own semantic repository recovery/analysis, patch planning/application, proof, correction, rollback, cross-repository engineering, and Sergeant handoff.

## Current authenticated routes

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
POST /v1/repositories/inspect
GET  /v1/repositories?workspace_id=<workspace_id>
GET  /v1/repositories/{repository_id}
GET  /v1/repositories/{repository_id}/diff?kind=staged|unstaged&limit=<bytes>
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

The Repository/Git candidate has passed substantive challenge on normalized Rust source:

- 10 Python contract tests;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript equivalence across 15 cases;
- Clippy with warnings denied under Rust 1.75;
- all Rust daemon/session/event/output/repository/integrity tests;
- originsd build;
- every inherited ADR-0002 through ADR-0005 hosted proof;
- Repository/Git hosted proof for authentication, authorized roots, non-Git rejection, attached HEAD identity, clean/dirty status SHA/counts, bounded staged/unstaged diff evidence, generic Git process rejection, permanent-journal hygiene, detached HEAD, linked worktree common-dir identity, restart recovery, and deliberate Repository projection tamper detection;
- repository whitespace gate.

Challenge corrections remain visible:

- Repository/Git capability descriptors were moved out of the core built-in manifest and into their owning subsystem manifest while sharing the same durable registry;
- inherited Process Session health proof was advanced from three core capabilities to the five-capability initialized runtime;
- ADR-0006 was corrected from its pre-implementation route sketch to the API and contract shape actually proven.

The proof-gated normalizer produced the exact Rust formatting/dependency state at `71bc6144…`. This state record and frozen ADR are owner-authored evidence updates; final merge still requires a fresh exact-head runtime + Contract Spine proof after these documentation commits.

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
- `docs/ADR-0005-LIVE-SESSION-OBSERVATION.md`;
- `docs/ADR-0006-REPOSITORY-GIT-SESSIONS.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not implemented or proven yet:

- Git mutation capabilities in Origins;
- CodeOps semantic repository loop mounted through Origins;
- AgentOps lifecycle/approval mount;
- Sergeant correction/completion loop inside Origins;
- accepted Python Origins integration runtime;
- production Hunter mount;
- PTY/interactive terminal Sessions;
- stdin and terminal resize;
- process reattachment after daemon restart;
- stronger OS-level process/resource isolation;
- React workspace shell;
- Oracle integration;
- Lumi integration;
- specialist Gateway clients;
- Ptah runtime integration;
- Windows/Linux desktop packages;
- release proof.

## Next valid implementation slice

The mechanical substrate is now strong enough to mount the first semantic/assurance engineering loop **without broad UI work**:

1. recover the current AgentOps ↔ CodeOps runner/approval/evidence contracts and Sergeant verdict adapter from their owning repositories;
2. define thin Origins reference/projection contracts only where Origins needs stable IDs/status display;
3. create the Python Origins integration runtime that binds Hunter/AgentOps/CodeOps to originsd rather than bypassing it;
4. execute repository work against durable Origins Repository IDs and mechanical Sessions;
5. preserve CodeOps as engineering authority and Sergeant as independent reviewer;
6. prove `NEEDS WORK → bounded correction Attempt → fresh proof → PASS` while AgentOps owns lifecycle/completion;
7. only after that proof begin broad React Workspace construction.

## Blocking rule

Do not let UI, Python workers, models, CodeOps, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
