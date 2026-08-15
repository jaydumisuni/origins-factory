# Phase 5 — Oracle, Lumi, Applications and Artifacts — Proof Record

## Classification

**Completion candidate, pending PR promotion.**

This record freezes the completed Phase-5 implementation/proof boundary without merging PR #16 or claiming Oracle capabilities that its owner does not yet provide.

Canonical architecture remains `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`.

## Proven implementation head

```text
655d149622094a9a9a0cd2f306e01f9337b0906a
```

Branch:

```text
build/phase5-oracle-lumi-applications
```

PR:

```text
#16 — draft
```

## Implemented boundary

Phase 5 now includes:

- Oracle retained-browser projection with real `observe / assist / act`, explicit Act approval and human takeover;
- exact Oracle remote Node projection and read-only approved file retrieval over frozen `oracle.live.v1`;
- Lumi queue/download projection while Lumi retains acquisition, destination, resume and request-secret ownership;
- originsd server-owned native application registry and durable/idempotent launcher;
- originsd immutable content-addressed Artifact storage, provenance, retrieval and Workspace-scoped deduplication;
- first-class Workspace surfaces: Core, Oracle, Logistics and Applications;
- Artifact promotion from verified Oracle and completed Lumi owner output;
- honest disconnected/auth-required states;
- authenticated owner connection truth: the UI cannot report connected unless at least one protected owner projection authenticated.

Origins does not duplicate Oracle or Lumi engines.

## Explicit remote-application nonclaim

Oracle has not frozen/implemented a durable remote native-application attachment Session contract. Phase 5 therefore renders and returns:

```text
remote_application_attachment.available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Generic process launch, pixels or a new Origins remote-desktop engine are not substituted for that missing owner contract.

## Hosted exact-head proof

All required workflows passed on implementation head `655d149622094a9a9a0cd2f306e01f9337b0906a`:

```text
Phase 5 Oracle Lumi Applications   31865760841  PASS
Origins Contract Spine             31865760805  PASS
Origins Daemon Foundation          31865760821  PASS
Origins Phase 3 Workspace          31865760850  PASS
Phase 4 Intelligence Plane         31865760860  PASS
Stage-2 Authority Containment      31865760867  PASS (Ubuntu + Windows)
```

The Phase-5 workflow proves:

- exact Python package/dependency installation;
- Python compile including both Phase-5 host proof tools;
- Oracle/Lumi owner and remote-transfer tests;
- Rust 1.75 formatting;
- Clippy with warnings denied;
- all Rust tests;
- repository whitespace;
- Workspace Node 24 `npm ci`;
- Workspace TypeScript typecheck;
- Workspace Vitest suite;
- Workspace production build.

## Real Oracle/Kratos remote-file proof

Oracle command/result:

```text
origins-phase5-remote-file-proof-ui-head-655d149-20260815-0500
```

Result:

```text
transport                 oracle.live.v1
githubInteractivePathUsed false
terminal exit              0
timeout                    false
proof                      PHASE5_ORACLE_REMOTE_FILE_OK
node_id                    kratos-HP-290-G4-Microtower-PC
remote_path                /home/kratos/origins-factory/README.md
bytes                      4804
chunks                     1
sha256                     33f70ec221efbf0528be397c916670cbd7bea3d9edfc9ba1d1b514adb6ebb2f9
artifact_candidate         true
live_token_exposed         false
remote_application_attachment_available false
```

The proof used the existing HTTPS Oracle Live gateway and file-backed local token reference. The token value was never committed, printed or returned by Origins.

## Real-Chrome Workspace UI proof

Oracle command/result:

```text
origins-phase5-workspace-ui-proof-r2-655d149-20260815-0459
```

Result:

```text
transport                 oracle.live.v1
githubInteractivePathUsed false
terminal exit              0
timeout                    false
proof                      PHASE5_WORKSPACE_UI_OK
browser                    system-google-chrome-headless
source_head                655d149622094a9a9a0cd2f306e01f9337b0906a
production_credentials_used false
fixture_bearer_rendered     false
oracle_act_requires_explicit_approval true
remote_application_attachment_available false
```

The UI proof launches an isolated real system Google Chrome profile plus deterministic loopback owner fixtures with a non-secret proof bearer. It does not type or expose production credentials.

It verifies rendered Core, Oracle, Logistics and Applications surfaces and checks:

- Oracle retained browser Session;
- exact Node identity projection;
- approved read-only file-retrieval wording;
- Act begins disabled until explicit approval;
- human takeover is visible;
- missing Oracle desktop application Session is shown truthfully;
- Lumi owner state and queue-acquisition surface;
- durable Artifact list/provenance surface;
- server-owned application launch boundary;
- browser-supplied executable/argv/cwd are not accepted.

Rendered screenshot evidence retained on Kratos:

```text
Oracle
  bytes  204207
  sha256 3a8ec8ce64b88ad0b79f519c3efba8c5ad4066594e661de3dcf8e10f22ba427b

Logistics
  bytes  159798
  sha256 7ccf8ea881397b604b2fc3af0ef97af0a1a960d1a8f670d410a3044c485e4c2e

Applications
  bytes  168424
  sha256 d02bfa638620fe3295837998351b5aa4e5ab2c8a267241fb18020f488e2f1d7c
```

The existing production Oracle browser was not repurposed for this acceptance. It correctly suppressed semantic inspection when it saw a password field on Origins. That privacy boundary was respected; an isolated clean Chrome proof was used instead.

## Review corrections discovered during Phase 5

Two evidence-driven corrections were made before freeze:

1. Phase-5 UI connection truth originally used `Promise.allSettled` but could mark connected even if every protected owner request rejected. It now fails closed unless at least one protected owner projection authenticated, with dedicated regression coverage.
2. The first isolated Chrome proof harness used substring matching and treated `disconnected` as containing `connected`. The product UI was unchanged; the harness was corrected to require exact connection status and then passed.

## Promotion boundary

Phase-5 implementation and acceptance are complete at this candidate boundary. PR #16 remains draft until the owner decides to promote/merge it.

Do not advance the merged checkpoint or start a later phase merely because this branch is proven. Merge/promotion remains a separate owner decision.
