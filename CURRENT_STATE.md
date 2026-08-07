# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Contract Spine v1 implemented and mechanically proven; persistent runtime not yet implemented

## Contribution status

This phase contributes **New implementation foundation + Verification**.

Origins Factory is not yet a complete runnable workspace. The first accepted implementation layer is the shared contract spine used to keep Rust, Python and TypeScript aligned before `originsd` and the workspace UI are built.

## Accepted product state

The permanent product architecture remains `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`.

Origins Factory remains a model-optional, evidence-native mission operating environment with:

- durable mission/workspace continuity;
- Hunter semantic intelligence;
- AgentOps durable Operation lifecycle;
- a Capability Compiler;
- React/TypeScript UI plane;
- persistent Rust native control plane;
- Python intelligence/integration plane;
- CodeOps engineering;
- Sergeant assurance;
- Oracle browser/OS control;
- Lumi acquisition;
- X-Ray evidence;
- specialist Gateway execution;
- Software Builder productization;
- Ptah-compatible future mechanical integration;
- controlled capability synthesis.

## Implemented and proven now

Contract Spine v1 contains:

- `contracts/registry.json`;
- `authority_ref`;
- `workspace_projection`;
- `capability_descriptor`;
- `command_envelope`;
- `event_envelope`;
- deterministic canonical JSON;
- SHA-256 contract identity;
- unknown-field rejection;
- floating-point rejection;
- cross-language safe-integer enforcement;
- explicit self-promotion rejection;
- shared valid/invalid fixture corpus;
- Python validator/canonicalizer;
- Rust validator/canonicalizer and proof CLI;
- TypeScript validator/canonicalizer;
- exact Rust/Python/TypeScript equivalence proof;
- CI gates for Python, TypeScript, Clippy, Rust tests/build, cross-language equivalence, whitespace and rustfmt.

The interface recovery matrix and first repository-engineering vertical slice are frozen in:

- `docs/INTERFACE_RECOVERY_MATRIX.md`;
- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/FIRST_VERTICAL_SLICE.md`.

## Proof state

The Contract Spine challenge pass has produced a fully green workflow with:

- Python contract tests passing;
- TypeScript contract tests passing;
- Rust Clippy passing with warnings denied;
- Rust tests passing;
- Rust proof CLI building;
- exact three-runtime canonical JSON/SHA-256/error equivalence passing;
- repository whitespace gate passing;
- rustfmt gate passing.

Earlier failures remain part of the engineering history rather than being hidden:

- an over-broad Python canonical-whitespace assertion was corrected;
- rustfmt exposed mechanical formatting debt;
- Clippy exposed one needless Rust borrow;
- the TypeScript lane exposed the need to bound authoritative integers to the JavaScript safe range.

Those corrections strengthened the frozen contract rather than being treated as product failures.

## Repository state

Canonical recovery files remain:

- `README.md` — concise repository boundary;
- `AI_HANDOFF.md` — mandatory recovery entry point;
- `CURRENT_STATE.md` — implementation truth and next action;
- `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md` — accepted product and architecture authority;
- `docs/HOST_HP_290_G4.md` — evidence-backed initial host inventory.

Implementation foundation files now include:

- `docs/INTERFACE_RECOVERY_MATRIX.md`;
- `docs/ADR-0001-CONTRACT-SPINE.md`;
- `docs/FIRST_VERTICAL_SLICE.md`;
- `contracts/`;
- `python/origins_contracts/`;
- `rust/origins-contracts/`;
- `typescript/`;
- `tools/prove_contract_equivalence.py`;
- `.github/workflows/contract-spine.yml`.

The exploratory `build/initial-workspace` branch remains non-authoritative and must not be revived as the runtime base.

## What is not implemented or proven

- no accepted Rust `originsd` daemon yet;
- no SQLite Origins durable-state schema/migrations yet;
- no persistent Origins Workspace database yet;
- no process/PTTY/session supervisor yet;
- no local HTTP/WebSocket runtime implementation yet;
- no accepted Python Origins integration runtime yet;
- no production AgentOps mounting;
- no CodeOps production mission loop inside Origins;
- no Sergeant completion/correction loop inside Origins;
- no React workspace shell;
- no Oracle OS-control/remote-session integration;
- no Lumi workspace integration;
- no application registry implementation;
- no specialist Gateway client implementation inside Origins;
- no Ptah runtime integration;
- no Windows/Linux package;
- no custom OS integration;
- no release proof.

## Known authoritative dependencies

Exact callable boundaries recovered so far are recorded in `docs/INTERFACE_RECOVERY_MATRIX.md`.

Do not guess the still-partial surfaces for:

- current production Hunter client/auth integration;
- final AgentOps persistent lifecycle backend;
- Oracle cross-platform Node Agent/remote session;
- Software Builder's stable machine-callable packaging surface;
- Ptah runtime, which remains unauthorized.

## Next valid work

1. Merge/freeze Contract Spine v1 after the final documentation-only rerun remains green.
2. Create a fresh `originsd` implementation branch from that frozen `main`.
3. Implement the persistent Rust daemon foundation:
   - loopback health endpoint;
   - SQLite schema/version table;
   - WAL mode;
   - workspace projection persistence;
   - append-only event journal;
   - capability registry read surface;
   - clean startup/shutdown and recovery diagnostics.
4. Prove daemon restart recovery separately from UI reconnect.
5. Add supervised repository/process sessions only after durable state is correct.
6. Mount AgentOps, CodeOps and Sergeant through the recovered contracts.
7. Build the first React workspace surfaces only after those runtime truths exist.

## Blocking rule

Do not start broad UI scaffolding before the persistent Rust state/recovery layer is proven. UI may project the frozen contracts, but it must not define or simulate durable runtime truth.
