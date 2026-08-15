# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 4 / PR #15 / `877a25557cfddb451d154f01e238a55e972040bf`
**Active phase:** Phase 5 — Oracle, Lumi, applications
**Branch:** `build/phase5-oracle-lumi-applications`
**PR:** #16, draft
**Phase-5 status:** implementation + backend + Workspace UI + target-host acceptance complete; pending owner promotion/merge decision.
**Proven implementation head:** `655d149622094a9a9a0cd2f306e01f9337b0906a`

## Completed authority — do not rebuild

Origins PRs #11–#15, Hunter-AgentOps durable approval/Operation work, CodeOps/Sergeant owner integrations and Oracle terminal exit-status truth are established authority. Phase 3 Workspace is merged at `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`; Phase 4 intelligence/assurance is merged at `877a25557cfddb451d154f01e238a55e972040bf`.

Ownership remains separate:

- Hunter/Pete — intelligence and optional outside reasoning;
- AgentOps — semantic Operations, approvals and authorization evidence;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent review/verdicts;
- Origins/originsd — Workspace, Repository, Session, native application and Artifact mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — download acquisition/queue/resume ownership;
- X-Ray/specialist Gateways — their specialist boundaries.

Do not duplicate owner engines inside Origins. Generalized model/runtime activation remains false.

## Phase 5 implementation — complete candidate

### Oracle retained browser

The Phase-5 owner plane projects the retained Oracle browser, real `observe / assist / act` authority modes, explicit owner approval before Act, dedicated human takeover and honest unavailable/disconnected state. Public health remains sanitized and browser credentials are not exported.

### Oracle remote Node / file retrieval

Origins mounts Oracle's frozen `oracle.live.v1` workstation/file transport instead of creating another executor.

The backend:

- binds an exact server-configured Oracle Node ID;
- verifies routing through `node.ping`;
- checks Node capability inventory;
- exposes only approved read retrieval using `filesystem.stat`, `filesystem.hash` and `filesystem.download.start`;
- rejects caller Node/token/destination/upload/write/header/overwrite substitution;
- validates ORL1 sequence and absolute offset;
- ACKs/backpressures the stream;
- enforces bounded transfer size;
- validates remote/result/close SHA-256 plus byte count;
- fsyncs and atomically promotes completed bytes;
- removes partial files after failure;
- returns a sanitized Oracle receipt and Artifact candidate.

The remote transfer root must also be included in `ORIGINS_ARTIFACT_ROOTS` before native Artifact promotion.

### Lumi / Logistics

Lumi remains owner of destination, request-envelope, cookies/headers, resume and acquisition history. Origins can queue bounded downloads, inspect owner task state and promote only completed Lumi output into an Artifact candidate.

### Native applications

`originsd` owns the application registry and durable/idempotent launcher. The browser chooses only a registered application ID and Workspace. Executable, argv and cwd remain server-owned; no shell or arbitrary launch arguments are accepted. Launch intent is persisted before spawn and child environment is sanitized.

### Artifacts

`originsd` materializes immutable content-addressed Artifacts from regular files under configured roots, preserves provenance, deduplicates exact bytes per Workspace and retrieves by registered Artifact ID. `artifact_projection` remains shared and adversarially validated in Rust, Python and TypeScript.

### Workspace UI

Phase 5 extends the already-proven Phase-4 mission UI instead of replacing it.

First-class Phase-5 surfaces are now:

```text
Core
Oracle
Logistics
Applications
```

Core preserves the Phase-4 Factory/Workspace/Hunter/Armoury/Evidence/Sergeant/Recovery experience.

Oracle exposes:

- retained browser Session state;
- Observe/Assist/Act controls;
- explicit Act approval checkbox;
- immediate human takeover;
- exact remote Node truth;
- approved read-only remote file retrieval;
- verified transfer → Artifact promotion;
- truthful remote-application unavailable state.

Logistics exposes:

- Lumi owner state;
- bounded queue acquisition;
- task refresh/completion state;
- Lumi Artifact candidate recovery/promotion;
- durable Artifact filtering/listing/download by registered Artifact ID.

Applications exposes:

- server-owned registry;
- Workspace-bound durable launch identity;
- registered local application launch;
- explicit no-browser executable/argv/cwd authority;
- separate truthful remote application attachment status.

The Phase-5 UI now fails closed on authentication truth: it cannot report connected when every protected owner projection rejects, and a refresh that loses all protected owner projections returns to disconnected state.

## Remote application attachment — explicit owner gap

Oracle has not yet frozen/implemented a durable remote native-application attachment Session contract. Origins therefore reports and renders:

```text
remote_application_attachment.available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Do not substitute generic process launch, pixels or a new Origins remote-desktop engine for that missing owner contract.

## Exact proof state

Canonical Phase-5 proof record:

```text
proof/phase5-workspace-ui-freeze.md
```

### Hosted exact-head proof

All required workflows passed on implementation head `655d149622094a9a9a0cd2f306e01f9337b0906a`:

```text
Phase 5 Oracle Lumi Applications   31865760841  PASS
Origins Contract Spine             31865760805  PASS
Origins Daemon Foundation          31865760821  PASS
Origins Phase 3 Workspace          31865760850  PASS
Phase 4 Intelligence Plane         31865760860  PASS
Stage-2 Authority Containment      31865760867  PASS (Ubuntu + Windows)
```

### Oracle/Kratos exact-head remote-file proof

Command/result:

```text
origins-phase5-remote-file-proof-ui-head-655d149-20260815-0500
```

PASS:

```text
PHASE5_ORACLE_REMOTE_FILE_OK
node_id     kratos-HP-290-G4-Microtower-PC
remote_path /home/kratos/origins-factory/README.md
bytes       4804
chunks      1
sha256      33f70ec221efbf0528be397c916670cbd7bea3d9edfc9ba1d1b514adb6ebb2f9
artifact_candidate true
live_token_exposed false
```

Transport was `oracle.live.v1`, terminal exit code was 0, no timeout occurred and `githubInteractivePathUsed=false`.

### Real-Chrome Workspace UI proof

Command/result:

```text
origins-phase5-workspace-ui-proof-r2-655d149-20260815-0459
```

PASS:

```text
PHASE5_WORKSPACE_UI_OK
browser system-google-chrome-headless
production_credentials_used false
fixture_bearer_rendered false
oracle_act_requires_explicit_approval true
remote_application_attachment_available false
```

Rendered screenshot hashes:

```text
Oracle       3a8ec8ce64b88ad0b79f519c3efba8c5ad4066594e661de3dcf8e10f22ba427b
Logistics    7ccf8ea881397b604b2fc3af0ef97af0a1a960d1a8f670d410a3044c485e4c2e
Applications d02bfa638620fe3295837998351b5aa4e5ab2c8a267241fb18020f488e2f1d7c
```

The production Oracle browser's sensitive-page suppression was respected; visual acceptance used an isolated clean Chrome profile with deterministic loopback fixtures and a non-secret proof bearer.

## Relevant server configuration

```text
ORIGINS_LOCAL_TOKEN
ORIGINS_ORACLE_BROWSER_URL
ORACLE_PAIRING_TOKEN
ORIGINS_LUMI_URL
ORIGINS_APPLICATIONS_JSON
ORIGINS_ARTIFACT_ROOTS
ORACLE_LIVE_URL
ORIGINS_ORACLE_NODE_ID or ORACLE_LIVE_NODE_ID
ORACLE_LIVE_TOKEN or ORACLE_LIVE_TOKEN_FILE
ORIGINS_REMOTE_TRANSFER_ROOT
ORIGINS_ORACLE_MAX_TRANSFER_BYTES
```

Secrets remain local references. They must not be committed, returned by APIs, echoed by proof tools or accepted from browser request bodies where the owner contract keeps them server-side.

## Exact next action

1. Re-prove the final documentation/proof-record head through the Phase-5 and inherited hosted gates.
2. Update draft PR #16 with final Phase-5 implementation and acceptance evidence.
3. Keep PR #16 draft until the owner explicitly chooses promotion/merge.
4. Do not advance the merged checkpoint or begin a later phase solely because this candidate branch is proven.
