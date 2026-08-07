# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Mechanical foundation proven through Repository/Git Sessions; Engineering Assurance Bridge v1 protocol-proven on real originsd; live private-package mount pending

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. The accepted foundation now provides cross-language contracts, persistent Rust state, bounded process execution, active control, reconnectable observation, durable read-first Repository/Git truth, and a Python bridge that can route an AgentOps/CodeOps/Sergeant engineering attempt through originsd without duplicating their authorities.

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

The spine enforces deterministic JSON/SHA identity, no floats, cross-language safe integers, unknown-field rejection, no capability self-promotion, and fail-closed Repository state rules. Exact three-runtime validity/error/canonical/SHA equivalence is proven across the current 15-case corpus.

### originsd persistence

The Rust 1.75 daemon provides loopback-only binding, local bearer authentication, SQLite durability, Workspace/Session/Repository/capability projections, append-only SHA-256 hash-chained events, tamper detection, restart recovery, and a proof-frozen Rust dependency state.

### Supervised Process Sessions v1

`origins.process.run` provides bounded non-interactive registered executable + argv execution, authorized Workspace roots, contained relative `cwd`, minimal child environment, timeout/output bounds, complete-stream byte/SHA evidence, exact replay binding, truthful terminal states, and honest interrupted restart recovery.

Generic shells remain rejected. Public generic process commands also reject `git`/`git.exe`; Git mechanical reads have one dedicated authority path.

### Active Session Control v1

- HTTP 202 command acceptance before child completion;
- active exact replay without duplicate execution;
- cancellation of controlled `running` Sessions;
- cancellation event before control signal;
- truthful `interrupted` cancellation result with null exit code;
- durable event replay by sequence cursor across disconnect/restart.

### Live Session Observation v1

- one-copy incremental retained stdout/stderr in existing `session_outputs`;
- authenticated retained-byte delta cursors;
- authenticated SSE over durable event/output cursors;
- complete-stream final evidence beyond retention bounds;
- no raw output in the permanent hash-chained journal.

### Repository/Git Sessions v1

Origins owns read-first mechanical Git truth beneath CodeOps:

- subsystem schema v1 and subsystem-owned `origins.repository.inspect` / `origins.repository.diff` manifests;
- durable Repository identity by Workspace + canonical worktree root;
- canonical worktree, Git directory, and common directory;
- attached, detached, and unborn HEAD representation;
- exact HEAD OID/ref/branch;
- staged/unstaged/untracked counts and complete porcelain-status SHA;
- bounded staged/unstaged diff retention with complete observed bytes/SHA/truncation truth;
- linked-worktree identity;
- restart persistence and tamper rejection;
- direct Git argv only, no shell or Git mutation capability;
- raw diff content absent from the permanent journal.

CodeOps retains semantic repository recovery/analysis, patch planning/application, proof, correction, rollback, cross-repository work, and Sergeant handoff.

### Engineering Assurance Bridge v1 — protocol proven

The Origins Python plane now contains `origins_integration.engineering`.

Production contract loading dynamically targets the current owning modules:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

The bridge:

- receives external AgentOps `operation_id`, task, approval intent, and Origins `repository_id`;
- obtains mechanical Repository/worktree identity from originsd;
- delegates operation-packet validation to the AgentOps adapter;
- routes `hunter-codeops-switcher` commands only through durable `origins.process.run` Sessions;
- never uses Python `subprocess` for CodeOps/Sergeant execution;
- allows plan apply only after the AgentOps packet accepts approved apply intent;
- obtains Sergeant argv through CodeOps `sergeant-command` and constrains it to the recovered `sergeant app-review` contract;
- executes Sergeant independently through originsd;
- requires successful, non-truncated review output;
- delegates verdict normalization to CodeOps' `ingest_sergeant_result_text` interface;
- returns exact recommendations: `PASS → complete_candidate`, `NEEDS WORK → correct`, `BLOCK → block`, `UNKNOWN → unresolved`;
- keeps PASS as a recommendation to AgentOps, not Origins completion authority;
- returns operation/Repository/Session IDs and review SHA without duplicating raw review output into the compact evidence record.

The hosted proof uses **protocol fixtures** for the private AgentOps/CodeOps package surfaces while using real originsd, real Repository projections, and real durable Sessions. It proves:

```text
same external AgentOps operation ID
→ Attempt 1
→ NEEDS WORK
→ unapproved correction rejected before Session creation
→ approved bounded correction in distinct Sessions
→ fresh independent PASS
```

It separately proves `BLOCK → block` and ambiguous/noncanonical review text → `UNKNOWN → unresolved`.

**Important limitation:** this does not yet prove that the user's private AgentOps/CodeOps Python packages and their CLI binaries are installed and compatible on a target Origins host. AgentOps' own production lifecycle/audit backend is also still explicitly pending in its owning repository. Origins has not created a shadow lifecycle database.

## Current authenticated originsd routes

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

At exact candidate head `8906cf184c57d7c4e0e1fbffcbf1f87350518c0f`, both proof suites passed:

- Python bridge/contract tests, including no-Python-subprocess, path controls, exact verdict actions, Sergeant argv constraint, and exact owning-module loader targets;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript equivalence;
- Clippy with warnings denied;
- all Rust daemon/session/event/output/repository tests;
- originsd build;
- all hosted ADR-0002 through ADR-0006 proofs;
- hosted Engineering Assurance Bridge protocol fixture proving NEEDS WORK → approved correction → fresh PASS, plus BLOCK/UNKNOWN separation;
- repository whitespace and rustfmt.

Challenge history remains visible: the first bridge hosted proof failed because its test simultaneously prohibited and required the normalized `NEEDS WORK` verdict in the compact evidence record. Only the proof assertion was corrected; the sanitation rule remains that raw review summary/output is not duplicated while the normalized verdict is retained.

This ADR/state/handoff freeze is documentation-only after the green candidate. Final promotion requires a fresh exact-head runtime + Contract Spine proof after these documentation commits.

## Canonical repository authority

Recovery order:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. implementation ADRs, current source, PRs, and proof;
5. the owning repository for every mounted external capability.

Implementation ADRs now run through:

- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/ADR-0002-ORIGINSD-FOUNDATION.md`;
- `docs/ADR-0003-PROCESS-SESSIONS.md`;
- `docs/ADR-0004-ACTIVE-SESSION-CONTROL.md`;
- `docs/ADR-0005-LIVE-SESSION-OBSERVATION.md`;
- `docs/ADR-0006-REPOSITORY-GIT-SESSIONS.md`;
- `docs/ADR-0007-ENGINEERING-ASSURANCE-BRIDGE.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not implemented or production-proven yet:

- live installed private AgentOps/CodeOps Python package compatibility on an Origins host;
- live installed `hunter-codeops-switcher` / Sergeant CLI compatibility through the bridge;
- AgentOps production persistent lifecycle/audit/completion backend;
- semantic restart recovery owned by AgentOps;
- provider/model execution through the engineering bridge;
- production Hunter mount;
- Origins Git mutation endpoints (deliberately absent; CodeOps owns engineering mutation);
- PTY/interactive terminal Sessions, stdin, and resize;
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

Do **not** build a shadow AgentOps backend and do not jump to broad React UI yet.

Next:

1. add a production integration doctor for the exact owning AgentOps/CodeOps Python modules and CodeOps/Sergeant executable surfaces;
2. distinguish `available`, `compatible`, and `proven` rather than treating PATH/import presence as successful integration;
3. prove the doctor fail-closed for missing/incompatible owners without installing or mutating external repositories automatically;
4. prepare a controlled live-host smoke path that uses the actual installed private packages/binaries when available;
5. keep all mechanical execution through originsd;
6. in parallel recover the current production Hunter client/API contract for the next intelligence mount;
7. only after the owning engineering stack is live-proven decide whether the next major slice is Hunter mounting or the broad React Workspace shell.

## Blocking rule

Do not let UI, Python workers, models, CodeOps, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
