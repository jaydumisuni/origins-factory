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
- AgentOps — semantic lifecycle/approvals;
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

## Proven implementation checkpoint

The accepted implementation sequence is:

1. **Contract Spine v1** — Rust/Python/TypeScript canonical contracts and exact equivalence.
2. **originsd persistence foundation** — local auth, SQLite durability, Workspace projections, capability projections, hash-chained journal, tamper detection, restart recovery.
3. **Supervised Process Sessions v1** — bounded non-interactive process execution, durable Sessions, replay binding, evidence hashes, environment/root policy, and honest interrupted recovery.
4. **Active Session Control v1** — asynchronous Session acceptance, exact active replay, cancellation of controlled running Sessions, and authenticated journal-cursor replay across disconnect/restart.
5. **Live Session Observation v1** — one-copy incremental retained output, stdout/stderr byte cursors, authenticated live journal/output SSE, and cursor-based reconnect without socket-owned truth.
6. **Repository/Git Sessions v1** — read-first durable Repository identity, attached/detached/worktree Git truth, status/diff evidence, subsystem-owned repository capabilities, restart recovery, and tamper detection beneath CodeOps.

Read `CURRENT_STATE.md` for exact promoted state. An item on an open PR remains a candidate until merged even when its exact-head proof is green.

## Mechanical execution and observation boundary

Do not silently expand `origins.process.run` into a generic shell or unrestricted execution path.

Current design deliberately separates:

- program + argv from shell command strings;
- real non-zero process exits from infrastructure interruptions;
- complete-stream evidence from bounded retained output;
- command identity from replayed command content;
- configured Workspace roots from complete OS isolation;
- mechanical Session state from AgentOps semantic Operation state;
- durable SQLite/event truth from ephemeral cancellation handles;
- raw retained output from permanent journal metadata;
- durable journal/byte cursors from SSE connection state;
- Repository mechanical truth from CodeOps semantic engineering truth.

V1 cancellation is proven only for `running` Sessions controlled by the current daemon generation. It uses `interrupted` with explicit cancellation reason and no invented exit code.

Live output has exactly one retained raw-output path: the existing `session_outputs` record. Do not add a second chunk/output database merely for streaming.

SSE is transport only. Reconnect starts from durable event sequence or stdout/stderr byte cursors. A socket/UI buffer cannot become recovery authority.

## Repository/Git boundary

Origins now has one public mechanical Git truth path:

```text
POST /v1/repositories/inspect
GET  /v1/repositories
GET  /v1/repositories/{repository_id}
GET  /v1/repositories/{repository_id}/diff
```

`origins.process.run` must not regain generic `git`/`git.exe` access merely for convenience.

Repository/Git v1 is deliberately read-only. Origins owns durable worktree/Git-directory/common-directory identity, HEAD/ref/branch state, status counts/status SHA, and bounded diff evidence. CodeOps continues to own repository analysis, patch planning/application, proof, correction, rollback, cross-repository engineering, and Sergeant handoff.

Do not add Git mutation endpoints to Origins as a shortcut around CodeOps/AgentOps authority. Any future mutation capability requires its own typed authority/proof slice.

## Huawei acceptance story

The Huawei P30 Pro/VOG case remains the canonical evidence for Origins mission continuity and cyber-physical architecture. The Drive handover is recovery context; live truth remains in current repository authority, persistent Gateway state, Recovery Plans/Artifacts, and fresh X-Ray evidence.

## Anti-drift rules

- Do not create another Origins master plan.
- Update accepted authority in place; do not append competing architectures.
- Keep implementation status in `CURRENT_STATE.md`.
- Recover repository evidence before proposing technologies or rewrites.
- Failed and partial Attempts remain visible.
- Do not convert a model claim, command exit, Git read, stream frame, or UI acknowledgement into proof of completion.
- Do not let a capability approve or activate its own upgrade.
- Do not revive `build/initial-workspace` as the implementation base.

## Current next valid work

With Repository/Git mechanical truth available, the next slice is the **first semantic + independent-assurance engineering loop**, still before broad UI work:

1. recover current AgentOps CodeOps runner/approval/evidence contracts and Sergeant verdict ingestion from their owning repositories;
2. define only the thin Origins references/projections needed to bind those authorities to Workspace/Repository/Session IDs;
3. create the Python Origins integration runtime; it must call originsd for mechanical work rather than bypass it;
4. mount CodeOps against durable Origins Repository IDs while CodeOps retains engineering authority;
5. mount Sergeant as an independent reviewer whose verdict cannot be rewritten by CodeOps or Origins;
6. keep AgentOps as lifecycle/approval/completion owner;
7. prove `NEEDS WORK → bounded correction Attempt → fresh proof → PASS` end-to-end through Origins;
8. only after that proof begin broad React Workspace construction.

## Session close rule

After substantial Origins work:

1. preserve code and proof checkpoints;
2. update `CURRENT_STATE.md`;
3. update this handoff when the recovery path or next valid action changes;
4. update the product plan only for an owner-accepted architecture change;
5. preserve unresolved limitations explicitly;
6. leave one clean continuation point for the next chat or machine.
