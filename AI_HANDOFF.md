# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current truth:** `CURRENT_STATE.md`
**Merged checkpoint:** Phase 5 / PR #16 / `d26bb68a621fb0e98f0a1766cbe3fea19228b2d8`
**Active phase:** Phase 6 — device read-only integration
**Branch:** `build/phase6-device-readonly-integration`
**PR:** #17, promotion candidate
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`

## Recovery order

Read this file, `CURRENT_STATE.md`, the accepted product plan, PR #17/current branch, then the owning Huawei Gateway and TTG Device X-Ray repositories at the pinned revisions. Recover latest proof before changing implementation. Do not ask the owner to repeat recoverable state.

## Ownership lock

- Hunter/Pete own intelligence.
- AgentOps owns semantic Operation/approval truth.
- CodeOps owns repository engineering/provider routing.
- Sergeant owns independent review/verdicts.
- Origins/originsd owns local mechanical Workspace/Repository/Session/application/Artifact truth.
- Oracle owns browser and reviewed remote workstation transport.
- Lumi owns acquisition/queue/resume truth.
- TECHGUYTOOL Huawei Gateway owns Huawei physical-session/operation/journal truth.
- TTG Device X-Ray owns read-first device evidence/certification truth.

Origins coordinates and projects these owners. It does not duplicate their engines.

## Merged checkpoint

Phase 5 is merged at:

```text
d26bb68a621fb0e98f0a1766cbe3fea19228b2d8
```

Do not reopen Phase 5 unless new evidence proves a regression.

## Phase-6 owner revisions

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

Huawei Gateway facts:

- loopback JSON-lines protocol on `127.0.0.1:49321` by default;
- persistent physical Sessions and Gateway Operations;
- hash-chained journal;
- restart preserves identity and active Operations recover explicitly;
- `device_authority=none`;
- `xray_authority=read_only`;
- endpoint observations and accepted shared contracts are recoverable owner truth.

TTG Device X-Ray facts:

- read-first only;
- ambiguity fails unsafe;
- profile results retain `write_allowed=false`;
- sealed bundle v2 hashes every evidence file;
- optional HMAC verification is separate from digest integrity;
- Kirin/VOG support remains replay/read-only only.

## Phase-6 mounted boundary

Origins permits exactly these Huawei Gateway commands:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

Every other command is refused before network I/O. Projection fails closed unless `device_authority=none`, `xray_authority=read_only` and the owner journal verifies.

`ORIGINS_XRAY_BUNDLE_DIR` and optional `ORIGINS_XRAY_SIGNING_KEY_FILE` are server-owned references. Browser callers cannot select paths or keys.

Phase-6 HTTP is protected GET-only for `/v1/device`, `/v1/huawei/gateway` and `/v1/xray/bundle`; public `/v1/health` is sanitized; mutation verbs are `405 PHASE6_READ_ONLY`.

The top-level Workspace preserves Phase 5 under `Workspace` and adds `XRAY`. XRAY is observational only and exposes no device action control.

## Completed Phase-6 proof

Frozen implementation proof head:

```text
4e788a584505fc5728a07a1bf73ece1e8a6bfd17
```

Evidence:

- all seven hosted regression workflows green;
- Oracle/Kratos backend + reconnect suite: `8 passed`, exit code 0;
- reconnect preserves physical Session ID, Gateway Operation ID, request SHA and recovery counters while remaining inside the read-only allowlist;
- isolated system Chrome: `PHASE6_WORKSPACE_UI_OK`, exit code 0;
- no production credentials used or rendered;
- no XRAY write controls;
- `device_authority=none`;
- `xray_authority=read_only`;
- X-Ray integrity verified;
- screenshot SHA-256 `9b5665285ad84d32d229b8dd55fe9bd5c6620b40221b05068e3313acd5bb24af`.

Full record: `proof/phase6-device-readonly-freeze.md`.

## Accepted truthful nonclaims

### AgentOps ↔ Huawei Gateway typed link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Current AgentOps and Huawei owner contracts do not expose a reversible typed join. Do not create an Origins mapping table or reinterpret hashes as IDs. This belongs to future owner-contract evolution.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Do not mount physical-session mutation, endpoint recording, Gateway Operation mutation/resume, provider/worker mutation, contract publication, Execution Lease consumption, executor invocation or any device write path in Phase 6.

### Current physical handset

Historical VOG/P30 evidence is lineage only and predates sealed-bundle v2. No current attached Huawei target is proven in recovered device/host records. Do not fabricate current-device certification or use this absence to reopen the completed software read-only integration.

## Exact next action

1. Re-prove the final recovery/documentation head through all hosted gates and Oracle/Kratos.
2. Update PR #17 body to the frozen evidence and promote it from draft.
3. Merge only with an exact-head guard.
4. Normalize recovery on `main` to the Phase-6 merge checkpoint.
5. Recover Phase 7 capability-evolution owner contracts before implementation.
