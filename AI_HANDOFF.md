# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current truth:** `CURRENT_STATE.md`
**Proof record:** `proof/phase5-workspace-ui-freeze.md`
**Merged checkpoint:** Phase 4 / PR #15 / `877a25557cfddb451d154f01e238a55e972040bf`
**Active phase:** Phase 5
**Branch:** `build/phase5-oracle-lumi-applications`
**PR:** #16, draft
**Phase-5 implementation status:** complete/proven candidate; pending owner promotion/merge decision.
**Proven implementation head:** `655d149622094a9a9a0cd2f306e01f9337b0906a`

## Recovery order

Read this file, `CURRENT_STATE.md`, `proof/phase5-workspace-ui-freeze.md`, the product plan, current `main`, current Phase-5 branch, then owning Oracle/Lumi/etc. repositories and latest proof evidence. Do not ask the owner to repeat recoverable state.

## Ownership lock

- Hunter/Pete own intelligence.
- AgentOps owns semantic Operation/approval truth.
- CodeOps owns repository engineering/provider routing.
- Sergeant owns independent review/verdicts.
- Origins/originsd owns local mechanical Workspace/Repository/Session/application/Artifact truth.
- Oracle owns browser and reviewed remote workstation transport.
- Lumi owns download acquisition/queue/resume truth.
- X-Ray and specialist Gateways retain specialist boundaries.

Do not duplicate owner engines inside Origins. Generalized model/runtime activation remains false.

## Completed merged checkpoints

Phase 3 Workspace is merged at `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`. Phase 4 intelligence/assurance is merged at `877a25557cfddb451d154f01e238a55e972040bf`. Stage-2 durable authority/containment and earlier Engineering Assurance/Hunter mounts remain authoritative and must not be rebuilt.

## Phase 5 — implemented and proven on branch

### Backend/mechanical

Implemented owner mounts and native mechanics:

- Oracle retained browser projection with `observe / assist / act`, explicit Act approval, human takeover and honest disconnect state;
- Lumi queue/download projection with destination/request-secret/resume ownership retained by Lumi and completed-task-only Artifact handoff;
- originsd server-owned application registry and durable/idempotent launcher with no arbitrary executable/argv/cwd authority;
- originsd content-addressed Artifact storage/retrieval with configured roots and shared Rust/Python/TypeScript `artifact_projection` contract;
- exact Oracle remote Node/read-only file retrieval client over frozen `oracle.live.v1`;
- exact server-configured Node binding and `node.ping` verification;
- explicit approval before remote retrieval;
- no caller Node/token/destination/upload/write/overwrite authority;
- ORL1 sequence/offset validation, ACK/backpressure, size limits, SHA validation, fsync/atomic promotion and partial cleanup;
- sanitized Oracle remote-file receipt plus Artifact candidate.

### Workspace UI

Phase 5 preserves the Phase-4 mission UI under **Core** and adds first-class:

```text
Oracle
Logistics
Applications
```

Oracle shows retained browser authority, human takeover, exact Node truth, approved file retrieval and verified transfer → Artifact promotion.

Logistics shows Lumi owner state, queue acquisition, task/candidate state and durable Artifacts.

Applications shows the server-owned application registry/launcher boundary and separate remote-application attachment truth.

The local bearer remains memory-only in the UI. The Phase-5 console now fails closed if every protected owner projection rejects; it cannot label that state connected.

## Remote application attachment — do not fake

Oracle has not frozen/implemented a durable remote native-application attachment Session contract.

Canonical Phase-5 truth remains:

```text
available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Do not replace this with `process.start`, generic pixels or a new Origins remote-control engine.

## Exact hosted proof

All required workflows passed on implementation head `655d149622094a9a9a0cd2f306e01f9337b0906a`:

```text
Phase 5 Oracle Lumi Applications   31865760841  PASS
Origins Contract Spine             31865760805  PASS
Origins Daemon Foundation          31865760821  PASS
Origins Phase 3 Workspace          31865760850  PASS
Phase 4 Intelligence Plane         31865760860  PASS
Stage-2 Authority Containment      31865760867  PASS (Ubuntu + Windows)
```

The Phase-5 lane proves backend/Rust plus Workspace Node 24 install, TypeScript typecheck, Vitest and production build. Both Phase-5 host proof scripts compile in that lane.

## Oracle/Kratos proof

Target:

```text
kratos-HP-290-G4-Microtower-PC
/home/kratos/origins-factory
```

Oracle result truth requires terminal exit code 0, no timeout and no signal failure; transport `ok` alone is not enough.

### Real remote file

```text
origins-phase5-remote-file-proof-ui-head-655d149-20260815-0500
PHASE5_ORACLE_REMOTE_FILE_OK
```

Exact evidence:

```text
bytes  4804
chunks 1
sha256 33f70ec221efbf0528be397c916670cbd7bea3d9edfc9ba1d1b514adb6ebb2f9
artifact_candidate true
live_token_exposed false
```

The Oracle Live token is file-backed at `/home/kratos/.oracle/live-token`; never print or copy the value. Persistent Node identity is case-sensitive: `kratos-HP-290-G4-Microtower-PC`.

### Real-Chrome Workspace UI

```text
origins-phase5-workspace-ui-proof-r2-655d149-20260815-0459
PHASE5_WORKSPACE_UI_OK
```

The proof uses isolated system Google Chrome plus deterministic loopback fixtures and a non-secret bearer. It does not type or expose production credentials.

Verified:

- Core / Oracle / Logistics / Applications render;
- Oracle Act starts disabled until explicit approval;
- human takeover is present;
- exact Node and remote-application unavailable truth render;
- Lumi queue/Artifact surfaces render;
- native application registry boundary renders;
- browser-supplied executable/argv/cwd are explicitly not accepted.

Screenshot SHA-256:

```text
Oracle       3a8ec8ce64b88ad0b79f519c3efba8c5ad4066594e661de3dcf8e10f22ba427b
Logistics    7ccf8ea881397b604b2fc3af0ef97af0a1a960d1a8f670d410a3044c485e4c2e
Applications d02bfa638620fe3295837998351b5aa4e5ab2c8a267241fb18020f488e2f1d7c
```

The production Oracle browser's sensitive-page suppression was respected. Do not bypass it for proof.

## Evidence-driven corrections already closed

1. Wrong/expired bearer could previously leave the UI labelled connected because owner calls were collected with `Promise.allSettled`; now at least one protected owner projection must authenticate.
2. The first Chrome proof harness matched `connected` inside `disconnected`; the harness was corrected to exact status matching. Product UI code did not change for that harness correction.

## Exact next action

1. Re-prove the final documentation/proof-record branch head across Phase-5 and all inherited hosted gates.
2. Update PR #16 body to the completed Phase-5 candidate evidence and final head.
3. Keep PR #16 draft unless the owner explicitly chooses promotion/merge.
4. Do not advance the merged checkpoint or start a later phase solely from branch proof.

If the owner says to promote Phase 5, recover the then-current PR head/checks first and merge only the proven stable head.
