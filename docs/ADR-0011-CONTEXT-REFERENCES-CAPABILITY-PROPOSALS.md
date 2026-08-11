# ADR-0011 — Context references, capability proposals, and candidate presentation

Status: candidate on paused PR #11. This ADR does not authorize new execution capability.

## Decision

Origins will borrow selected presentation and confinement lessons from Kilo Code without importing Kilo as a runtime dependency or creating another orchestrator.

Hunter/Pete, AgentOps, CodeOps, Sergeant, and Origins keep their existing ownership:

```text
Hunter / Pete
  -> mission understanding and optional outside reasoning

AgentOps
  -> durable operation lifecycle and approvals

CodeOps
  -> repository-aware engineering and provider/model/client routing

Origins
  -> durable mechanical workspace, sessions, capability enforcement and presentation

Sergeant
  -> independent engineering review
```

Kilo Agent Manager therefore contributes a presentation pattern for parallel sessions/candidates, not a replacement brain or lifecycle engine.

## Context references

Origins may expose references before the final React workspace exists.

Initial syntax:

```text
@chat:<hunter-session-id>
@memory:<project>:<key>
```

### `@chat`

`@chat` resolves through Hunter's existing verified-owner chat authority. Origins does not copy chat history into a second database.

The reference may expose a bounded presentation projection containing the Hunter session id, title, retained messages, and update metadata. Hunter remains the source of truth.

### `@memory`

CodeOps already defines typed `MemoryLesson` records, but its current module explicitly does not write them to durable Hunter storage yet. Therefore `@memory` is typed now but must report `unavailable` until Hunter runtime memory storage is mounted.

Origins must not create a shadow Project Memory database merely to make the UI look complete.

## Capability proposals

A model may discover that an unavailable capability would materially improve task delivery. Examples include a terminal facility, browser control, an MCP tool, remote service access, or a future specialist capability.

The model may **propose** the capability. It may not grant it to itself.

Every proposal must contain:

- requested capability id;
- task title and current Workspace;
- why the capability is needed;
- expected task-delivery benefit;
- requested effects;
- requested filesystem read/write scope;
- requested network scope/hosts;
- requested environment variable names, never secret values;
- whether a persistent process/lease is needed;
- whether authority is delegated to a remote service;
- alternatives considered;
- identified risks;
- `approval_required = true`;
- `self_approvable = false`.

Origins converts the proposal into AgentOps' existing `owner_approval_required` request shape. AgentOps/owner approval remains the authority for approval or rejection.

Approval is not execution. After approval, a separate capability provider must still exist, satisfy its capability manifest, and obtain the bounded lease required by Origins.

## Confinement invariants

Origins adopts the following negative invariants before parallel candidate worktrees, model-originated browser/terminal access, or MCP become generally available:

1. Enforcement lives in the persistent mechanical backend, never only in UI/tool-list filtering.
2. A model/tool may restrict its own scope but can never expand the effective scope.
3. Policy is re-checked at invocation time so stale tool handles cannot bypass a later restriction.
4. Delegated child work inherits a scope no broader than its parent.
5. A candidate worktree may write its own approved worktree but not sibling worktrees or the main checkout.
6. Global deny paths remain authoritative even when roots overlap.
7. Model-writable project/config files cannot disable or expand the active confinement lease.
8. Network capability is classified explicitly. Network-denied sessions cannot regain web/MCP/network tools through stale handles.
9. Local persistent MCP/background processes require a captured persistent lease for their complete lifetime and child tree.
10. Remote MCP is explicit delegated remote authority. It is not described as locally confined.
11. Unknown local MCP processes are not labeled network-safe without an enforceable declaration/boundary.
12. Credentials and secret values are never inserted into model-visible proposal metadata merely because a tool requires them.

These rules are donor lessons, not a dependency on Kilo's implementation.

## Candidate/session presentation

The future Origins workspace should expose the useful parts of an Agent Manager visually without duplicating AgentOps or CodeOps.

A candidate/session card may show:

- operation / candidate id;
- parent mission;
- model/provider route chosen by CodeOps;
- Node;
- repository/worktree;
- current state;
- terminal/process activity;
- evidence/proof status;
- Sergeant verdict when available;
- capability leases and pending requests.

One mission can therefore present parallel candidates as lanes while one shared Origins backend retains the durable mechanical truth.

The UI must not imply that every mission uses multiple models or worktrees. CodeOps' minimal effective loadout remains authoritative.

## Context picker presentation

The composer may expose an `@` picker with authority-aware sections:

```text
Chats
  Hunter chat history

Project Memory
  Hunter/CodeOps verified lessons

Evidence
  Origins / Sergeant evidence references

Artifacts
  retained artifacts and handovers
```

Only authority surfaces that are actually connected may resolve. Unwired surfaces remain visible as unavailable/dormant rather than silently creating duplicate storage.

## Non-claims

This ADR does not claim:

- React UI implementation;
- worktree candidate execution;
- MCP runtime support;
- browser control implementation;
- terminal lease expansion beyond current Process Sessions;
- durable Hunter Project Memory storage;
- automatic approval;
- unrestricted autonomous mode;
- Kilo Code integration or dependency.
