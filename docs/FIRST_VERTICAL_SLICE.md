# Origins Factory — First Repository-Engineering Vertical Slice

**Status:** FROZEN implementation target  
**Architecture:** Origins Factory v1.0  
**Purpose:** prove the complete mission-continuity loop before broad UI work

## Mission

A user opens one repository Workspace and gives Hunter a plain-language engineering objective. Origins must preserve the complete mission while AgentOps, CodeOps, native processes and Sergeant perform their bounded responsibilities.

## Required path

```text
Owner objective
→ Origins Workspace
→ Hunter context/plan
→ AgentOps Operation
→ Capability Compiler selects CodeOps formation
→ CodeOps produces bounded candidate changes
→ originsd supervises repository/process sessions
→ proof evidence is retained
→ Sergeant reviews independently
→ NEEDS WORK loops through a new Attempt when required
→ PASS/accepted result returns to AgentOps
→ Workspace can close/reopen and recover exact state
→ sanitation closes temporary work
```

## Scope

### Included

- one local Git repository;
- one Origins `workspace_projection`;
- one linked AgentOps Operation;
- CodeOps route selection and coding request;
- approved provider/model selection where available;
- Rust-supervised process execution;
- Git status/diff projection;
- evidence references;
- Sergeant review;
- at least one restart/reconnect proof;
- explicit sanitation state.

### Explicitly excluded from Slice 1

- physical-device writes;
- Ptah runtime;
- custom OS packaging;
- Oracle OS remote control;
- Software Builder release packaging;
- arbitrary extension marketplace;
- production customer data.

Those are not needed to prove the core architecture.

## Twenty bounded lanes / two governing passes

Origins development and later mission execution may use a Sergeant-style high-parallelism formation. “20-for-2” is a work-budget pattern, not a requirement to spawn 20 models.

The planner may activate up to these focused lanes when evidence justifies them:

1. authority recovery;
2. repository topology;
3. dependency analysis;
4. architecture/contracts;
5. implementation;
6. tests;
7. static analysis;
8. security;
9. concurrency/performance;
10. platform compatibility;
11. packaging implications;
12. documentation drift;
13. migration/backward compatibility;
14. failure diagnosis;
15. correction planning;
16. artifact/provenance capture;
17. sanitation/duplicate detection;
18. independent challenge preparation;
19. recovery/handoff;
20. capability-gap detection.

They reconcile through two governing passes:

### Pass A — Build

Recover → plan → implement → test → collect evidence.

### Pass B — Challenge

Re-read fresh state → Sergeant review → contradiction check → correction/proof → freeze candidate.

Parallel lanes do not independently mutate the same files. A single accepted candidate owner coordinates overlapping changes.

## Slice 1 state model

Origins-owned durable records:

- Workspace projection;
- local runtime Session references;
- capability descriptors/bindings;
- command and event journal;
- sanitation state.

Referenced foreign truth:

- AgentOps Operation/Attempt;
- Git repository and commit;
- CodeOps evidence;
- Sergeant result/report.

## Minimum endpoints

`originsd` must eventually expose at least:

```text
GET  /v1/health
POST /v1/workspaces
GET  /v1/workspaces/{id}
GET  /v1/capabilities
POST /v1/commands
GET  /v1/sessions
WS   /v1/events
```

Slice 1 can introduce these incrementally; no endpoint is considered stable until contract tests exist.

## Required recovery proof

1. create Workspace;
2. bind repository and Operation references;
3. start at least one supervised process/session;
4. record events;
5. stop the UI/client;
6. keep `originsd` alive;
7. reconnect with a new client;
8. recover the same Workspace and session references;
9. if `originsd` itself restarts, recover durable projections and mark non-resumable process state honestly rather than inventing success.

Origins must distinguish:

- UI reconnect;
- worker/process reconnect;
- daemon restart recovery.

They are not the same proof.

## Sergeant correction proof

A complete Slice 1 acceptance mission must exercise:

```text
candidate
→ Sergeant NEEDS WORK
→ AgentOps records a new correction Attempt
→ CodeOps corrects within approved scope
→ fresh proof
→ Sergeant PASS
```

If the available project naturally passes on the first review, use a safe synthetic fixture to prove the correction loop separately.

## Capability-gap proof

Slice 1 must be able to record, but not necessarily self-build, a structured capability gap containing:

- required effect;
- capability requested;
- available capability/version;
- observed limitation;
- evidence refs;
- affected Operation;
- proposed upgrade owner;
- required proof before activation.

This proves that “the model could not do it” becomes engineering evidence rather than an excuse for blind self-modification.

## Completion gate

Slice 1 is complete only when all are true:

- typed contracts are frozen and cross-language canonicalization is proven;
- `originsd` durable state is proven;
- repository/process sessions are supervised by Rust;
- AgentOps and CodeOps are mounted through recovered boundaries;
- Sergeant is independent and its verdict is retained unchanged;
- reconnect proof passes;
- failed Attempts remain visible;
- temporary work is sanitized;
- no duplicate foreign truth is stored as canonical Origins state;
- the repository can be handed to another chat using `AI_HANDOFF.md` and `CURRENT_STATE.md` without replanning the product.
