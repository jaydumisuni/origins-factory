# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Mechanical foundation through Repository/Git proven; Engineering Assurance Bridge protocol-proven; Production Engineering Mount doctor compatibility-proven; live target-host owner stack still pending

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. The accepted foundation now provides cross-language contracts, persistent Rust state, bounded process execution, active control, reconnectable observation, durable read-first Repository/Git truth, an AgentOps/CodeOps/Sergeant assurance bridge, and a production-mount doctor that can distinguish owner presence from behavioral compatibility without installing or repairing external systems.

## Proven implementation sequence

1. **Contract Spine v1.2** — Rust/Python/TypeScript canonical contracts and exact equivalence.
2. **originsd persistence foundation** — loopback auth, SQLite durability, Workspace/capability state, hash-chained journal, tamper detection, restart recovery.
3. **Supervised Process Sessions v1** — bounded argv execution, durable Sessions, environment/root policy, replay binding, output evidence.
4. **Active Session Control v1** — async acceptance, running-session cancellation, durable event replay.
5. **Live Session Observation v1** — one-copy retained output, byte/event cursors, authenticated SSE projections.
6. **Repository/Git Sessions v1** — read-first durable Repository identity, HEAD/worktree/status/diff evidence, no generic Git mutation path.
7. **Engineering Assurance Bridge v1** — protocol-proven Python bridge for AgentOps-gated CodeOps work and independent Sergeant review through originsd.
8. **Production Engineering Mount v1 doctor** — compatibility-proven doctor for current AgentOps/CodeOps Python contracts and CodeOps/Sergeant CLI surfaces.

## Engineering Assurance Bridge v1

`origins_integration.engineering` dynamically targets the owning modules:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

All CodeOps/Sergeant mechanical execution goes through durable originsd Sessions. AgentOps packet validation remains the approval boundary, CodeOps owns engineering semantics, Sergeant remains independent, and CodeOps owns verdict ingestion.

Exact recommendations remain:

```text
PASS       → complete_candidate
NEEDS WORK → correct
BLOCK      → block
UNKNOWN    → unresolved
```

`complete_candidate` is advice to AgentOps, not Origins completion authority.

Hosted protocol proof demonstrated the same external operation ID across distinct Attempts: `NEEDS WORK → rejected unapproved correction → approved correction → fresh PASS`, plus separate BLOCK and UNKNOWN routing. This is protocol proof, not proof that the private owner stack is installed on a target host.

## Production Engineering Mount v1 doctor

`origins_integration.doctor.EngineeringMountDoctor` now checks the exact current owner surfaces without Python subprocess or automatic repair.

Observed owner identities from current repositories:

```text
hunter-agentops       0.3.0
hunter-codeops        0.3.0
sergeant-reviewer     0.4.1
hunter-codeops-switcher
sergeant
```

The doctor evaluates four required surfaces:

```text
agentops_python
codeops_python
codeops_cli
sergeant_cli
```

Status semantics:

```text
missing    → owner cannot be found or started
available  → present but required contract behavior is not compatible
compatible → required non-mutating behavior passes
proven     → reserved for a separate live engineering receipt
```

Doctor rules:

- AgentOps compatibility instantiates the actual packet/approval interface against the Origins Repository worktree;
- CodeOps semantic compatibility delegates PASS/NEEDS WORK/BLOCK fixtures to the owner ingest function;
- CodeOps/Sergeant CLI `--help` probes execute only through `origins.process.run` Sessions;
- CLI Session IDs and stdout SHA evidence are retained in the doctor result;
- overall status is the weakest required surface;
- `live_engineering_proven` is always false in doctor-only v1;
- the doctor never pip-installs, edits PATH, clones/pulls owner repos, rewrites APIs, or substitutes fixtures on a production path.

Hosted doctor proof used fixture owner packages/CLIs with exact recovered identities plus real originsd and a real durable Repository. All-compatible fixtures yielded `compatible`. After restart with Sergeant deliberately absent from PATH, `sergeant_cli=missing` forced overall `missing`, and the doctor did not recreate or repair it.

**This proves doctor behavior, not the user's actual target host installation.**

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

At candidate head `46f31faf9ca3df3b26f7199ec0c5a77ba2e251e8`, both proof suites passed:

- Python doctor and bridge tests;
- TypeScript contract proof;
- Rust contract proof;
- exact Rust/Python/TypeScript equivalence;
- Clippy with warnings denied;
- all Rust tests and originsd build;
- every hosted proof from ADR-0002 through ADR-0007;
- hosted Production Engineering Mount doctor proof;
- repository whitespace and rustfmt.

Doctor unit proof includes no-Python-subprocess, exact owner names, all-compatible never becoming proven, missing AgentOps, incompatible AgentOps packet, changed CodeOps ingest semantics, missing/nonzero/truncated CLI classification, and weakest-link overall status.

This ADR/state/handoff freeze is documentation-only after the green candidate. Final promotion requires a fresh exact-head runtime + Contract Spine proof.

## Canonical repository authority

Recovery order:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. implementation ADRs, current source, PRs, and proof;
5. the owning repository for every mounted external capability.

Implementation ADRs now run through `docs/ADR-0008-PRODUCTION-ENGINEERING-MOUNT.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not production-proven yet:

- actual target-host AgentOps/CodeOps Python package installation/compatibility;
- actual target-host `hunter-codeops-switcher` / `sergeant` CLI compatibility;
- a live actual-owner Engineering Assurance Attempt producing a `proven` receipt;
- AgentOps production persistent lifecycle/audit/completion backend;
- semantic restart recovery owned by AgentOps;
- provider/model execution through the engineering bridge;
- production Hunter mount;
- PTY/interactive terminal Sessions, stdin, resize, or process reattachment;
- stronger OS-level resource isolation;
- React workspace shell;
- Oracle/Lumi/specialist Gateway clients;
- Ptah runtime integration;
- Windows/Linux desktop packages and release proof.

## Next valid implementation slice

Do not convert fixture compatibility into production proof and do not auto-install external owners.

Next:

1. define a controlled **live engineering mount smoke** that consumes the doctor result and refuses to run unless every required surface is compatible;
2. use the actual installed AgentOps/CodeOps/Sergeant owners on a controlled Origins host when available;
3. produce a bounded live receipt that can promote the mount from `compatible` to `proven` without changing AgentOps completion semantics;
4. keep every CLI command through originsd and every verdict through CodeOps' owner ingestion;
5. recover the current Hunter production client/API contract in parallel;
6. after live engineering-owner proof, choose the next major slice from evidence: Hunter mount or broad React Workspace.

## Blocking rule

Do not let UI, Python workers, models, CodeOps, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
