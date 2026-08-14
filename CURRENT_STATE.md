# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 4 / PR #15 / `877a25557cfddb451d154f01e238a55e972040bf`
**Active phase:** Phase 5 — Oracle, Lumi, applications
**Branch:** `build/phase5-oracle-lumi-applications`
**PR:** #16, draft
**Owner hold:** complete pre-UI backend/proof, then stop before `workspace/` changes.

## Completed authority — do not rebuild

Origins PRs #11–#15, Hunter-AgentOps durable approval/Operation work, and Oracle terminal exit-status truth are already established. Phase 3 Workspace is merged at `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`; Phase 4 intelligence/assurance is merged at `877a25557cfddb451d154f01e238a55e972040bf`.

Ownership remains separate: Hunter/Pete own intelligence, AgentOps owns semantic Operations/approval evidence, CodeOps owns repository engineering/provider routing, Sergeant owns independent verdicts, Origins owns local mechanical Workspace/Repository/Session/application/Artifact truth, Oracle owns browser/remote workstation transport, Lumi owns download acquisition, and specialist Gateways/X-Ray retain their own domains.

Generalized model/runtime activation remains false.

## Phase 5 pre-UI implementation

### Oracle browser

The Python owner mount provides retained-browser projection, real `observe / assist / act` authority modes, explicit approval before `act`, dedicated human takeover, bearer pairing, and honest disconnected state. Public health is sanitized.

### Lumi

Origins can project queues and request bounded downloads. Lumi retains destination, resume, request-envelope and secret ownership. Only completed Lumi tasks become Artifact candidates; caller destination/header/cookie overrides are rejected.

### Native applications

`originsd` owns a server-side application registry and durable/idempotent launcher. Callers select a registered ID only. Executable, argv and cwd remain server-owned; no shell or arbitrary launch arguments are exposed. Launch intent is persisted before spawn and child environment is sanitized.

### Artifacts

`originsd` materializes immutable content-addressed Artifacts from regular files under configured `ORIGINS_ARTIFACT_ROOTS`, preserves provenance, deduplicates exact bytes per Workspace and retrieves by Artifact ID. `artifact_projection` is shared and adversarially validated in Rust, Python and TypeScript.

### Oracle remote Node / approved file retrieval

`python/origins_integration/oracle_live.py` mounts Oracle's frozen `oracle.live.v1` workstation protocol rather than duplicating it.

The backend uses an exact server-configured Node ID, verifies it via `node.ping`, checks capability inventory, and exposes only approved read retrieval through `filesystem.stat`, `filesystem.hash`, `stream.open` and `filesystem.download.start`. Callers cannot override Node, token, local destination, upload/write or overwrite authority.

ORL1 chunks are checked for exact sequence and absolute offset. Origins ACKs stream progress, enforces a transfer ceiling, validates pre-transfer/content/result/close SHA-256, validates byte count, fsyncs and atomically promotes the completed file, removes partial state after failure, and returns a sanitized Oracle receipt plus Artifact candidate. The transfer root must also be included in `ORIGINS_ARTIFACT_ROOTS` for native Artifact promotion.

### Remote application attachment

Unavailable by owner contract and must not be faked. Oracle's roadmap has not yet frozen/implemented its Desktop eyes-and-hands phase, so Origins reports:

```text
remote_application_attachment.available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Do not substitute generic process launch, pixels or an Origins-owned desktop engine.

## Proof state

Dedicated pre-UI workflow: `.github/workflows/phase5-oracle-lumi.yml`.

It mechanically fails if any `workspace/` delta appears.

Implementation head `b71bc99a3bb6a95a85b65db17d50858881150f19` passed exact Python install/compile, Phase-5 owner and remote-transfer tests, Rust 1.75 format, Clippy `-D warnings`, Rust tests and whitespace. Contract Spine was corrected to install the repository's declared Python dependencies before collecting the full Python test corpus.

Kratos proof checkout: `/home/kratos/origins-factory`.

Oracle Live has proven branch fetch and exact-head checkout with terminal exit code 0. Focused target-host Phase-5 tests passed 15/15. The live-file proof is being completed against Oracle's file-backed token reference and exact persistent Node identity; transport/socket failures are not counted as proof.

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

Secrets remain local references and must not be committed, returned by APIs or echoed by proof tools.

## Exact hold point

1. Re-prove the final documentation head across Phase 5 and all inherited gates.
2. Finish one real Oracle Live read-only file-transfer proof with exact Node/bytes/SHA and no token disclosure.
3. Update draft PR #16 with final pre-UI evidence.
4. Stop before changing `workspace/`.
5. Resume only when the owner asks to start the Phase-5 Workspace UI.

PR #16 remains draft because Phase 5 is not complete until UI and post-UI acceptance proof are added.
