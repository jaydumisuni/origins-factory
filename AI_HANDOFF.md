# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current implementation truth:** `CURRENT_STATE.md`

## Read before acting

Every new chat, AI, agent, developer, or reviewer must recover Origins Factory in this order:

1. this `AI_HANDOFF.md`;
2. `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. current implementation ADRs;
5. current source, branches, pull requests, tests, and proof;
6. the owning repository for every mounted external capability being changed.

Do not ask the owner to repeat information recoverable from these records.

## Product identity lock

Origins Factory is a **model-optional, evidence-native mission operating environment** combining durable work ownership, full-stack engineering, cyber-physical control, independent verification, cross-machine continuity, and controlled capability synthesis.

Origins is the portable workspace the owner opens to work with Hunter. It is not an operating system, IDE clone, AI sidebar, dashboard, thin desktop wrapper, model router, or replacement for its specialist systems.

## Non-negotiable architecture

```text
Owner intent
→ Origins Factory
→ Hunter semantic understanding
→ AgentOps durable Mission/Operation graph
→ Capability Compiler
→ persistent mechanical execution
→ Sergeant/X-Ray/deterministic assurance
→ Artifacts, recovery, sanitation, and governed capability evolution
```

Three truths remain separate:

- **Semantic truth:** Hunter + AgentOps.
- **Mechanical truth:** originsd, specialist Gateways, Nodes, and later authorized Ptah integration.
- **Assurance truth:** Sergeant, X-Ray, deterministic proof, specialist governors, and human acceptance.

Models amplify the system. They do not manufacture mechanical completion or independent assurance.

## Runtime planes

- **React + TypeScript:** visible Workspace and projections.
- **Rust:** persistent native control plane, mechanical Sessions, repositories/Git, processes, later PTYs/filesystem/Nodes/events/recovery.
- **Python:** Hunter, AgentOps, CodeOps, provider/model integration, context compilation, reconciliation, and governed capability evolution.

The UI must not own durable runtime truth.

## Capability ownership

- Hunter — intelligence/context;
- AgentOps — semantic lifecycle/approvals/completion;
- CodeOps — repository engineering;
- Sergeant — independent engineering review;
- Oracle — browser/OS perception and authorised control;
- Lumi — downloads/transfers;
- X-Ray — read-first and post-operation evidence;
- specialist Gateways — domain/device state and bounded execution;
- Software Builder — packaging/releases;
- Ptah — future neutral mechanical substrate after authorization;
- Origins — mission workspace, native integration, capability compilation, and user control surfaces.

Do not duplicate an owning engine inside Origins.

## Accepted implementation sequence

1. **Contract Spine v1** — Rust/Python/TypeScript canonical contracts and exact equivalence.
2. **originsd persistence foundation** — local auth, SQLite durability, Workspace projections, capability projections, hash-chained journal, tamper detection, restart recovery.
3. **Supervised Process Sessions v1** — bounded non-interactive process execution, durable Sessions, replay binding, evidence hashes, environment/root policy, honest interrupted recovery.
4. **Active Session Control v1** — asynchronous Session acceptance, exact active replay, cancellation of controlled running Sessions, durable event replay.
5. **Live Session Observation v1** — one-copy incremental retained output, stdout/stderr byte cursors, authenticated live event/output SSE, reconnect without socket-owned truth.
6. **Repository/Git Sessions v1** — read-first durable Repository identity, attached/detached/worktree Git truth, status/diff evidence, subsystem capabilities, restart recovery, tamper detection beneath CodeOps.
7. **Engineering Assurance Bridge v1** — Python bridge routes AgentOps-gated CodeOps/Sergeant work through durable originsd Sessions and preserves exact independent-review actions.

Read `CURRENT_STATE.md` for exact promotion/proof state. An item on an open PR remains a candidate until merged even when exact-head proof is green.

## Engineering Assurance Bridge lock

The bridge does not become AgentOps, CodeOps, or Sergeant.

Production dynamic imports are pinned to:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

Mechanical execution remains:

```text
AgentOps packet/approval
→ Origins Repository ID
→ CodeOps command
→ originsd Session
→ CodeOps Sergeant-command
→ originsd Sergeant Session
→ CodeOps verdict ingestion
→ recommendation back to AgentOps
```

Exact recommendation semantics:

```text
PASS       → complete_candidate
NEEDS WORK → correct
BLOCK      → block
UNKNOWN    → unresolved
```

`complete_candidate` is not AgentOps completion. Origins never upgrades PASS into lifecycle completion itself.

The current bridge is **protocol-proven on real originsd using contract fixtures for the private owner packages**. Do not rewrite that as “live production AgentOps/CodeOps/Sergeant integration is proven.” The private package/CLI installation compatibility and AgentOps persistent lifecycle backend remain pending.

Do not create a shadow AgentOps operation database merely to add semantic restart behavior before the owning AgentOps backend exists.

## Mechanical execution and observation boundary

Do not silently expand `origins.process.run` into a generic shell or unrestricted execution path.

Current design separates:

- program + argv from shell command strings;
- real process exits from infrastructure interruptions;
- complete-stream evidence from bounded retained output;
- command identity from replayed command content;
- configured Workspace roots from complete OS isolation;
- mechanical Session state from AgentOps semantic Operation state;
- durable SQLite/event truth from ephemeral cancellation handles;
- raw retained output from permanent journal metadata;
- durable cursors from SSE connection state;
- Repository mechanical truth from CodeOps semantic engineering truth;
- bridge protocol proof from live installed-owner compatibility proof.

V1 cancellation is proven only for `running` Sessions controlled by the current daemon generation. Live output retains exactly one raw-output path in `session_outputs`. SSE is transport only.

## Repository/Git boundary

Origins has one public mechanical Git truth path:

```text
POST /v1/repositories/inspect
GET  /v1/repositories
GET  /v1/repositories/{repository_id}
GET  /v1/repositories/{repository_id}/diff
```

`origins.process.run` must not regain generic `git`/`git.exe` access merely for convenience.

Repository/Git v1 remains read-only. CodeOps owns engineering mutation and proof. Any future Origins Git mutation capability requires its own typed authority/proof slice and must not bypass AgentOps/CodeOps.

## Huawei acceptance story

The Huawei P30 Pro/VOG case remains the canonical evidence for Origins mission continuity and cyber-physical architecture. The Drive handover is recovery context; live truth remains in current repository authority, persistent Gateway state, Recovery Plans/Artifacts, and fresh X-Ray evidence.

## Anti-drift rules

- Do not create another Origins master plan.
- Update accepted authority in place; do not append competing architectures.
- Keep implementation status in `CURRENT_STATE.md`.
- Recover repository evidence before proposing technologies or rewrites.
- Failed and partial Attempts remain visible.
- Do not convert a model claim, command exit, Git read, stream frame, fixture proof, or UI acknowledgement into stronger proof than it actually provides.
- Do not let a capability approve or activate its own upgrade.
- Do not revive `build/initial-workspace` as the implementation base.

## Current next valid work

Before broad React UI, close the live owner-mount gap:

1. implement an Origins production integration doctor for the exact AgentOps/CodeOps Python modules and CodeOps/Sergeant executable interfaces;
2. report `missing`, `available`, `compatible`, and `proven` distinctly;
3. fail closed on incompatible contracts; do not vendor replacements or auto-modify external repositories;
4. prepare a controlled live-host smoke path using the actual private packages/binaries when installed;
5. keep every mechanical command through originsd;
6. recover the current production Hunter client/API contract in parallel for the following intelligence mount;
7. after live engineering-owner compatibility is proven, choose the next major slice from evidence: Hunter mount or broad React Workspace.

## Session close rule

After substantial Origins work:

1. preserve code and proof checkpoints;
2. update `CURRENT_STATE.md`;
3. update this handoff when the recovery path or next valid action changes;
4. update the product plan only for an owner-accepted architecture change;
5. preserve unresolved limitations explicitly;
6. leave one clean continuation point for the next chat or machine.
