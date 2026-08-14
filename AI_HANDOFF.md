# Origins Factory — AI Handoff

**Status:** Mandatory recovery entry point  
**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current implementation truth:** `CURRENT_STATE.md`  
**Current merged checkpoint:** Phase 4 / PR #15 merge `877a25557cfddb451d154f01e238a55e972040bf`  
**Active phase:** Phase 5 — Oracle, Lumi, applications  
**Active branch:** `build/phase5-oracle-lumi-applications`  
**Active PR:** #16, draft  
**Owner hold:** finish pre-UI backend/proof, then STOP before Workspace UI.

## Recover before acting

Read in this order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. current `main` and current Phase-5 branch;
5. owning external repositories for any mounted capability being changed;
6. current proof/CI/Oracle evidence.

Do not ask the owner to repeat recoverable evidence. Do not reopen completed phases because an older handoff or conversation says they were pending.

## Product / ownership lock

Origins Factory is a model-optional, evidence-native mission operating environment. Keep semantic, mechanical and assurance truth separate.

Ownership:

- Hunter/Pete — mission intelligence/reasoning;
- AgentOps — durable semantic Operation lifecycle and approval/authorization evidence;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering review;
- Origins/originsd — Workspace/Repository/Session mechanical truth, native application launch, local Artifact handling and capability enforcement;
- Oracle — retained browser + reviewed remote Node/workstation transport;
- Lumi — download queues/resume/acquisition verification;
- X-Ray/specialist Gateways — specialist evidence/execution.

Never duplicate an owning engine inside Origins.

## Completed checkpoints — do not reopen

- Origins PR #13 — dormant Stage-2 authority runtime/native containment — merged.
- Origins PR #14 — Phase-3 Workspace shell — merge `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`.
- Hunter-AgentOps PR #17 — durable Department Operations — merge `054a09e7571b08e5865499d66ea6db5ae6eb43a6`.
- Oracle PR #117 — terminal exit-status truth — merge `50521d5c215f09a212ffd016f487cacb198ff087`.
- Origins PR #15 — Phase-4 intelligence/assurance plane — merge `877a25557cfddb451d154f01e238a55e972040bf`.

Phase 4 target-host proof already established the real AgentOps/CodeOps/Sergeant owner chain on Kratos. Do not rebuild it.

## Phase 5 — current implementation

### Oracle browser

`python/origins_integration/phase5_runtime.py` mounts the existing Oracle browser authority:

- loopback owner endpoint;
- Oracle authority modes `observe / assist / act`;
- explicit approval before `act`;
- dedicated human takeover;
- pairing token sent as Bearer auth;
- disconnected browser remains unavailable;
- no shadow browser state database.

### Lumi

Origins projects Lumi queues/downloads and can hand a completed owner task into Artifact-candidate flow. Lumi keeps destination, resume, request envelope and secret ownership. Browser callers cannot inject Lumi destination, headers or cookies.

### Native applications

`rust/originsd/src/applications.rs` provides a server-configured application registry and durable/idempotent launcher. The caller selects an application ID only; executable/argv/cwd remain server-owned. Launch intent is persisted before spawn; environment is sanitized; replay does not spawn twice.

### Artifacts

`rust/originsd/src/artifacts.rs` provides content-addressed immutable Artifact materialization/retrieval. Sources must be regular files under configured `ORIGINS_ARTIFACT_ROOTS`. Exact-byte dedupe is Workspace-scoped and provenance remains visible.

`artifact_projection` is shared and adversarially validated across Rust/Python/TypeScript.

### Oracle remote Node / file retrieval

`python/origins_integration/oracle_live.py` is a thin client over Oracle's frozen `oracle.live.v1` contract. It does not implement an alternate remote executor.

Server-owned configuration selects the exact Node. The browser cannot provide Node ID, token, destination, upload/write or overwrite authority.

Read-only retrieval uses:

```text
node.ping
node.capabilities
filesystem.stat
filesystem.hash
stream.open
filesystem.download.start
ORL1 binary chunks
stream ACK/backpressure
stream.close SHA-256
```

Origins verifies:

- routed Node identity;
- required file capabilities;
- regular-file status;
- bounded size;
- chunk sequence and absolute offset;
- pre-transfer SHA;
- received-byte SHA;
- request-result SHA;
- stream-close SHA;
- byte count;
- partial-file cleanup on failure.

Successful transfer is atomically placed under the configured Origins transfer root and returned as a sanitized Oracle receipt + Artifact candidate. The transfer root must also be in `ORIGINS_ARTIFACT_ROOTS` before native Artifact promotion.

### Remote native application attachment

Do **not** implement around the owner.

Oracle's roadmap still marks **Phase 18 — Desktop eyes and hands — NOT STARTED**. The frozen workstation RPC is sufficient for Node/file/process primitives, but there is no accepted durable remote native-application attachment Session contract.

Origins must therefore expose:

```text
available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Do not substitute process launch, generic pixels, or a new Origins remote-desktop engine.

## Phase-5 proof state

Dedicated workflow:

```text
.github/workflows/phase5-oracle-lumi.yml
```

The workflow explicitly fails if the branch contains a `workspace/` delta, enforcing the owner's current UI hold.

Pre-documentation implementation head `b71bc99a3bb6a95a85b65db17d50858881150f19` passed the dedicated Phase-5 gate:

- exact Python package/dependency install;
- compile;
- Oracle/Lumi authority tests;
- remote Node/ORL1 stream integrity tests;
- Rust 1.75 format;
- Clippy `-D warnings`;
- all Rust tests;
- whitespace.

Contract Spine initially failed only because that inherited workflow installed `pytest` while collecting Phase-5 tests requiring the newly declared runtime dependency. `.github/workflows/contract-spine.yml` has been corrected to install the Python package and declared dependencies before the full Python corpus. Final branch head must re-prove all gates.

Target-host proof tool:

```text
tools/prove_phase5_oracle_remote.py
```

It must be run on the exact reviewed head against real Oracle Live before this pre-UI backend is frozen.

## Oracle/Kratos execution rules

Target Node:

```text
kratos-hp-290-g4-microtower-pc
```

Origins checkout:

```text
/home/kratos/origins-factory
```

Use Oracle Live direct argv. Treat terminal exit code, timeout and signal as command truth; transport `ok` alone is insufficient.

A Phase-5 branch fetch already returned terminal exit code 0 over `oracle.live.v1` with `githubInteractivePathUsed=false`.

Do not echo Oracle Live tokens. Use the existing local token/token-file configuration.

## Dormant authority boundary

Phase 5 does not activate generalized model/runtime authority. Still not implicitly authorized:

- generalized model terminal authority;
- model-facing lease issuance;
- MCP authority;
- unrestricted endpoint/network authority;
- delegated remote mutation;
- unrestricted candidate mutation;
- self-expanding capability authority.

Remote file retrieval is an explicit human-approved, read-only mounted capability; it is not generalized remote authority.

## Exact next action — then HOLD

1. Re-prove the final documentation head in the dedicated Phase-5 workflow and all inherited Origins gates.
2. Pin `/home/kratos/origins-factory` to that exact head.
3. Install the declared Python package in an isolated Kratos proof environment.
4. Run focused Phase-5 tests through Oracle.
5. Run `tools/prove_phase5_oracle_remote.py` against a harmless real file through Oracle Live; require exact Node, byte count, SHA and token non-disclosure.
6. Update draft PR #16 with final pre-UI proof and the explicit Oracle desktop/application owner gap.
7. **STOP. Do not modify `workspace/`.**

Resume only when the owner explicitly says to start the Phase-5 UI.

## Session close rule

After this pre-UI freeze, leave:

- exact branch SHA;
- exact workflow run IDs/results;
- exact Oracle result/proof identity;
- PR #16 still draft;
- remote application attachment limitation explicit;
- one continuation point: Phase-5 Workspace UI.

Do not update the master product plan unless the owner accepts an architecture change; this work implements the existing plan.
