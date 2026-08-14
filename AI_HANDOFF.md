# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current truth:** `CURRENT_STATE.md`
**Merged checkpoint:** Phase 4 / PR #15 / `877a25557cfddb451d154f01e238a55e972040bf`
**Active phase:** Phase 5
**Branch:** `build/phase5-oracle-lumi-applications`
**PR:** #16, draft
**Owner instruction:** finish pre-UI Phase-5 backend/proof, then stop before any `workspace/` change.

## Recovery order

Read this file, `CURRENT_STATE.md`, the product plan, current `main`, current Phase-5 branch, then the owning Oracle/Lumi/etc. repositories and latest proof evidence. Do not ask the owner to repeat recoverable state.

## Ownership lock

Hunter/Pete own intelligence; AgentOps owns semantic Operation/approval truth; CodeOps owns repository engineering/provider routing; Sergeant owns independent review; Origins/originsd owns local mechanical Workspace/Repository/Session/application/Artifact truth; Oracle owns browser and reviewed remote workstation transport; Lumi owns download acquisition; X-Ray/Gateways retain specialist boundaries.

Do not duplicate owner engines inside Origins. Generalized model/runtime activation remains false.

## Completed checkpoints

Phase 3 Workspace is merged at `106cae1172207ce6b1c1d9b9aaeb076e83b3bb3f`. Phase 4 intelligence/assurance is merged at `877a25557cfddb451d154f01e238a55e972040bf`. Stage-2 durable authority/containment and the earlier Engineering Assurance/Hunter mounts remain authoritative and must not be rebuilt.

## Phase 5 pre-UI backend

Implemented:

- Oracle retained-browser projection with `observe / assist / act`, explicit `act` approval, human takeover and honest disconnect state;
- Lumi queue/download projection with destination/request-secret ownership retained by Lumi and completed-task-only Artifact handoff;
- originsd server-side application registry and durable/idempotent launcher with no arbitrary executable/argv/cwd authority;
- originsd content-addressed Artifact materialization/retrieval with configured source roots and shared Rust/Python/TypeScript `artifact_projection` contract;
- Oracle remote Node/read-only file retrieval client over frozen `oracle.live.v1`;
- exact server-configured Node binding and `node.ping` verification;
- `filesystem.stat/hash/download.start` only for remote retrieval;
- explicit approval before remote file transfer;
- no caller Node/token/destination/upload/write/overwrite authority;
- ORL1 sequence/offset validation, ACK/backpressure, byte limits, SHA checks, fsync/atomic promotion and partial cleanup;
- sanitized remote-file receipt plus Artifact candidate;
- transfer root configured as an allowed Artifact source root for promotion.

Remote native-application attachment remains explicitly unavailable:

```text
available = false
reason = ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE
```

Oracle has not yet frozen its Desktop eyes-and-hands phase. Do not fake this with generic process launch or a new remote-control engine.

## Proof state

Dedicated workflow: `.github/workflows/phase5-oracle-lumi.yml`. It fails if `origin/main...HEAD` contains any `workspace/` file.

Pre-documentation implementation head `b71bc99a3bb6a95a85b65db17d50858881150f19` passed the complete Phase-5 hosted gate. Contract Spine was updated to install declared Python runtime dependencies before collecting the full Python test corpus.

Kratos target:

```text
kratos-HP-290-G4-Microtower-PC
/home/kratos/origins-factory
```

Oracle proof rules: use direct argv; terminal exit code/timeout/signal are command truth; transport `ok` alone is insufficient; retryable socket closure may occur after execution, so inspect host state before repeating mutations.

Proven on Kratos so far:

- Phase-5 branch fetch: exit 0 through `oracle.live.v1`;
- exact Phase-5 checkout: exit 0;
- isolated proof environment created;
- exact `websockets 16.1.1` project dependency present;
- focused Phase-5 suite: 15/15 passed, exit 0.

Real file proof tool:

```text
tools/prove_phase5_oracle_remote.py
```

Oracle service references are file-backed:

```text
ORACLE_LIVE_TOKEN_FILE=/home/kratos/.oracle/live-token
ORACLE_NODE_ID_FILE=/home/kratos/.oracle/node-id
```

Persistent Node ID is case-sensitive: `kratos-HP-290-G4-Microtower-PC`.

Do not copy or print the token value.

## Final pre-UI actions, then HOLD

1. Re-prove the normalized recovery-document head through the dedicated Phase-5 and inherited gates.
2. Complete the real Oracle Live file transfer against a harmless file with exact Node/bytes/SHA and token non-disclosure.
3. Update draft PR #16 with the final pre-UI proof and explicit remote-application owner gap.
4. Stop. Do not modify `workspace/`.

Resume only on explicit owner instruction to start the Phase-5 UI.
