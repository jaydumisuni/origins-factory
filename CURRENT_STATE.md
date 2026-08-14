# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current merged product checkpoint:** Phase 4 / PR #15 merge `877a25557cfddb451d154f01e238a55e972040bf`  
**Active roadmap phase:** Phase 5 — Oracle, Lumi, applications  
**Active branch:** `build/phase5-oracle-lumi-applications`  
**Promotion lane:** draft PR #16  
**Security state:** Stage-1/Stage-2 authority mechanics remain proven and merged; generalized model/runtime activation remains false.

## Do not reopen completed work

Treat these as existing authority, not work to rebuild:

- Origins PR #11 — Stage-1 `ExecutionScope + CapabilityLease` v1.1;
- Hunter-AgentOps PR #16 — durable approval/Auth evidence;
- Origins PR #12 — Lease Issuer Preflight v1;
- Origins PR #13 — dormant Stage-2 authority runtime/native containment;
- Origins PR #14 — Phase-3 Workspace shell, merge `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`;
- Hunter-AgentOps PR #17 — restart-durable Department Operations, merge `054a09e7571b08e5865499d66ea6db5ae6eb43a6`;
- Oracle PR #117 — Live terminal exit-status truth, merge `50521d5c215f09a212ffd016f487cacb198ff087`;
- Origins PR #15 — Phase-4 intelligence/assurance owner plane, merge `877a25557cfddb451d154f01e238a55e972040bf`.

Earlier Engineering Assurance / Production Engineering / Live Engineering / Hunter intelligence mounts are also part of Origins history. Do not create parallel AgentOps, CodeOps, Sergeant, Hunter, Oracle or Lumi engines inside Origins.

## Ownership lock

- **Hunter / Pete:** mission intelligence and optional outside reasoning;
- **AgentOps:** semantic Operation lifecycle, approvals, authorization and semantic evidence;
- **CodeOps:** repository engineering and provider/model/client routing;
- **Sergeant:** independent engineering review and verdict semantics;
- **Origins / originsd:** Workspace, Repository, Session, mechanical admission, native application launch, local Artifact/content handling, evidence projection and capability enforcement;
- **Oracle:** retained browser and reviewed remote Node/workstation transport;
- **Lumi:** download queues, resume, acquisition history and verification;
- **X-Ray / specialist Gateways:** specialist evidence/execution boundaries.

A mounted owner remains canonical. Origins may project or coordinate it; it must not shadow the owner's database or duplicate its engine.

## Phase 3 — complete and merged

PR #14 provides the React/TypeScript Workspace shell and bounded native editor/process/recovery surfaces. The seven core views are Factory, Workspace, Hunter, Armoury, Evidence, Sergeant and Recovery. Repository editing remains root-confined; supervised command execution remains direct argv through originsd.

## Phase 4 — complete and merged

PR #15 mounts current Hunter/AgentOps/CodeOps/Sergeant authorities without widening Stage-2 authority.

Phase-4 target-host evidence includes:

- AgentOps owner proof — durable Operation accepted and restart replay idempotent;
- four-owner Kratos proof — `PHASE4_LIVE_OWNER_STACK_OK`;
- owner revisions used by that proof:
  - Origins `ecefbb081cd977c4faed21e0703e80f9de57b6eb`;
  - AgentOps `054a09e7571b08e5865499d66ea6db5ae6eb43a6`;
  - CodeOps `e72afe60ebab41d9f36dc729ad798d5aa4071e83`;
  - Sergeant `fe491502a960e6b581a7d07e35683aa28e58b9f8`;
- selected CodeOps provider `fireworks-code` from three enabled routes;
- independent Sergeant verdict `BLOCK`, retained without reinterpretation.

Generalized model-facing terminal/browser/MCP/network authority remains dormant.

## Phase 5 — pre-UI backend implemented; hold at UI

The owner explicitly requested that all remaining pre-UI Phase-5 work be completed and that work stop before Workspace UI implementation.

### Oracle retained browser mount

Implemented in the Python integration plane:

- loopback-only Oracle browser owner endpoint;
- real Oracle authority vocabulary: `observe`, `assist`, `act`;
- explicit approval before `act` handoff;
- dedicated human takeover path;
- Oracle pairing capability sent as Bearer auth;
- browser availability is false when the local bridge is alive but no browser is attached;
- public Phase-5 health does not expose owner details or credentials.

### Lumi queue / Artifact candidate handoff

Implemented as a thin owner mount:

- Lumi remains owner of destination paths, request envelopes, cookies/headers, resume state and queue history;
- Origins may request a bounded URL/filename/queue/priority handoff;
- only a completed Lumi task can become an Artifact candidate;
- Origins does not accept caller overrides for Lumi destination or request-secret state.

### Native application registry / launcher

Implemented in `originsd`:

- server-side application registry;
- caller selects only a registered application ID;
- executable, argv and working directory come from server configuration;
- no shell and no caller-supplied launch arguments;
- Workspace-bound launch records;
- durable caller-supplied launch IDs for idempotency;
- launch intent persisted before process spawn;
- retries do not duplicate a launch;
- sanitized child environment;
- accepted launch activity is journaled.

### Artifact store / shared contract

Implemented in `originsd` and the shared contract spine:

- immutable content-addressed Artifact materialization;
- source path must be an absolute regular file under configured `ORIGINS_ARTIFACT_ROOTS`;
- copy/hash into Origins-owned object storage;
- Workspace-scoped exact-byte deduplication;
- source/provenance records retained;
- retrieval by registered Artifact ID rather than arbitrary host path;
- `artifact_projection` validated in Rust, Python and TypeScript with shared valid/invalid fixtures.

### Oracle remote Node + approved file retrieval

Origins now mounts Oracle's already-frozen `oracle.live.v1` workstation/file transport rather than creating a second remote executor.

The backend:

- uses a server-configured exact Oracle Node ID; callers cannot substitute a Node;
- verifies the routed Node using `node.ping`;
- checks Node capability inventory before retrieval;
- uses read-only `filesystem.stat`, `filesystem.hash` and `filesystem.download.start`;
- requires explicit approval before remote retrieval;
- caller cannot provide local destination, token, headers, upload/write or overwrite authority;
- receives ORL1 binary chunks with exact sequence/absolute-offset checks;
- sends required stream ACK/backpressure frames;
- enforces a bounded transfer size;
- verifies pre-transfer SHA-256, streamed bytes, response SHA-256 and stream-close SHA-256;
- fsyncs and atomically promotes the completed local transfer;
- removes partial files after failure;
- emits a sanitized Oracle remote-file receipt plus an Artifact candidate;
- requires the configured remote-transfer root to be included in `ORIGINS_ARTIFACT_ROOTS` before native Artifact promotion.

Oracle transport authority remains external. No Oracle token is returned through the Phase-5 API.

### Remote application attachment — truthful owner gap

**Not implemented and must not be faked.**

Oracle Phase 18 — Desktop eyes and hands — is not yet frozen/implemented in the Oracle owner roadmap. Oracle Phase 6 supplies workstation/files/process primitives, but there is no accepted durable remote native-application attachment Session contract for Origins to mount.

Origins therefore reports:

```text
remote_application_attachment.available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Do not substitute `process.start`, generic pixels, or an Origins-owned desktop-control engine for that missing owner contract.

## Phase-5 proof state

Dedicated workflow: `.github/workflows/phase5-oracle-lumi.yml`.

The pre-UI gate mechanically refuses any `workspace/` delta.

Pre-documentation implementation head `b71bc99a3bb6a95a85b65db17d50858881150f19` passed:

- exact Python package/dependency installation;
- Python compile;
- Oracle/Lumi authority tests;
- Oracle remote Node/ORL1 transfer integrity tests;
- Rust 1.75 formatting;
- Clippy with warnings denied;
- all Rust tests;
- repository whitespace gate.

The inherited Contract Spine initially exposed that its old test environment installed only `pytest` while now collecting tests that import the declared Phase-5 runtime dependency. The workflow was corrected to install the repository Python package and declared dependencies before running the full Python corpus. Final documentation head must re-run all inherited gates before promotion.

Oracle/Kratos execution is available through the canonical Live terminal lane. Kratos checkout remains:

```text
/home/kratos/origins-factory
```

A direct Oracle fetch for the Phase-5 branch completed with transport `oracle.live.v1`, `githubInteractivePathUsed=false`, terminal exit code 0.

Target-host proof tool:

```text
tools/prove_phase5_oracle_remote.py
```

It is intended to prove exact Node routing, read-only approved transfer, byte/SHA integrity, Artifact-candidate projection and non-exposure of the Live token against the real Oracle service.

## Configuration boundary for Phase 5 backend

Required/relevant server-side settings include:

```text
ORIGINS_LOCAL_TOKEN
ORIGINS_ORACLE_BROWSER_URL
ORACLE_PAIRING_TOKEN
ORIGINS_LUMI_URL
ORIGINS_APPLICATIONS_JSON
ORIGINS_ARTIFACT_ROOTS
ORACLE_LIVE_URL
ORIGINS_ORACLE_NODE_ID (or ORACLE_LIVE_NODE_ID)
ORACLE_LIVE_TOKEN or ORACLE_LIVE_TOKEN_FILE
ORIGINS_REMOTE_TRANSFER_ROOT
ORIGINS_ORACLE_MAX_TRANSFER_BYTES
```

Secrets are local configuration/reference material and must not be committed, echoed into proof output or accepted from browser request bodies.

## Stage-2 authority runtime — unchanged

The durable scope/lease, invocation revalidation, Repository resource resolution, Linux Landlock/seccomp/process fencing and Windows AppContainer/ACL/Job Object containment remain the mechanical security floor. Phase 5 does not activate generalized model authority.

Still not implicitly authorized:

- generalized model terminal authority;
- model-facing lease issuance;
- MCP authority;
- unrestricted network endpoint authority;
- delegated remote mutation;
- unrestricted candidate mutation;
- self-expanding capability authority.

## Exact next action / hold point

1. Re-prove the final Phase-5 pre-UI documentation head across the dedicated Phase-5 gate and all inherited Origins gates.
2. Run the real Oracle/Kratos `tools/prove_phase5_oracle_remote.py` proof against the exact reviewed head.
3. Update draft PR #16 with the proof and explicit remote-application owner gap.
4. **STOP before changing any `workspace/` file.**
5. Resume only when the owner asks to start the Phase-5 Workspace UI surfaces.

PR #16 must remain draft at this hold point; Phase 5 is not complete until the UI surface and final post-UI acceptance proof are added.
