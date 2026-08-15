# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current truth:** `CURRENT_STATE.md`  
**Merged checkpoint:** Phase 5 / PR #16 / `d26bb68a621fb0e98f0a1766cbe3fea19228b2d8`  
**Active phase:** Phase 6 — device read-only integration  
**Branch:** `build/phase6-device-readonly-integration`  
**PR:** #17, draft  
**Phase-5 proof record:** `proof/phase5-workspace-ui-freeze.md`

## Recovery order

Read this file, `CURRENT_STATE.md`, the accepted product plan, PR #17/current branch, then the owning Huawei Gateway and TTG Device X-Ray repositories at the recovered revisions below. Recover latest proof before changing implementation. Do not ask the owner to repeat recoverable state.

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

Phase 5 is merged. PR #16 merged as:

```text
d26bb68a621fb0e98f0a1766cbe3fea19228b2d8
```

Do not reopen Phase-5 implementation unless new evidence proves a regression.

## Recovered Phase-6 owner revisions

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

Huawei Gateway owner facts:

- loopback JSON-lines protocol, default `127.0.0.1:49321`;
- persistent SQLite physical sessions and Gateway Operations;
- hash-chained journal and deterministic `doctor`/`snapshot`;
- restart preserves identity; active Operations recover explicitly;
- `device_authority=none`;
- `xray_authority=read_only`;
- full EndpointObservation is journalled;
- accepted shared contracts are journalled as canonical JSON + SHA-256.

TTG Device X-Ray owner facts:

- read-first only;
- candidate grouping precedes identity correlation;
- multi-device ambiguity is `UNSAFE`;
- profile results retain `write_allowed=false`;
- bundle schema v2 seals every completed evidence file with SHA-256;
- optional HMAC signature report is separate from digest integrity;
- promoted Kirin/VOG capability is replay-supported/read-only only.

## PR #17 implementation

### Read-only Huawei Gateway mount

`python/origins_integration/device_readonly.py` permits exactly:

```text
health
 doctor
 snapshot
 get_physical_session
 get_operation
 list_events
 verify_journal
```

Any other Gateway command is rejected before network I/O. Do not add session/endpoint/Operation mutation, provider/worker mutation, contract publication, shutdown, lease consumption or executor invocation to Phase 6.

Projection fails closed unless:

```text
device_authority == none
xray_authority == read_only
journal_valid == true
```

Journal projections recover endpoint observations and owner-accepted Device Evidence/Twin, Decision Verdict, Mode Lease, historical Execution Lease/Executor Result, Verification Result and Recovery Plan.

### X-Ray sealed-bundle mount

`ORIGINS_XRAY_BUNDLE_DIR` is server-owned. Browser callers cannot choose a bundle path.

Origins verifies schema 2.0, `write_allowed=false`, canonical manifest SHA-256, every file path/size/SHA, and signature-report manifest binding. HMAC is considered verified only when a server-side `ORIGINS_XRAY_SIGNING_KEY_FILE` exists and matches. Never return or print the key.

### Phase-6 HTTP service

`python/origins_integration/phase6_server.py`, default loopback port `48730`.

Protected GET only:

```text
/v1/device
/v1/huawei/gateway
/v1/xray/bundle
```

Sanitized public:

```text
/v1/health
```

POST/PUT/PATCH/DELETE are hard `405 PHASE6_READ_ONLY`.

### Workspace

`Phase6App` preserves the full Phase-5 workspace under `Workspace` and adds top-level `XRAY`.

XRAY displays owner health, authority, journal, physical sessions, Gateway Operations, endpoint observations, Device Twin/Evidence, verdicts, leases, verification, Recovery Plan and verified X-Ray evidence. It has no device action control.

## Explicit gaps / blocks

### AgentOps ↔ Gateway durable Operation link

Current truth:

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Do not create an Origins-owned mapping table or reinterpret Gateway `request_sha256` as an AgentOps ID without an owning cross-system contract.

### Device write execution

Current truth:

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

The Huawei repository contains later lease/executor code. That does not authorize Origins Phase 6 to call it.

### Remaining acceptance

Phase 6 is not complete yet. Required evidence still includes:

- hosted PR #17 + inherited regression gates;
- historical VOG handover/recovery recovery;
- target-host real Gateway read-only proof;
- restart/reconnect proof preserving exact physical/Gateway Operation state;
- real sealed X-Ray bundle verification/projection;
- AgentOps↔Gateway reference-contract resolution;
- isolated rendered XRAY acceptance;
- final recovery-head reproof.

## Dedicated proof

```text
.github/workflows/phase6-device-readonly.yml
tools/prove_phase6_device_readonly.py
```

The target-host proof must report `PHASE6_DEVICE_READONLY_OK`, exact source head, authority/journal status, counts and X-Ray integrity without printing secret values.

## Exact next action

1. Inspect PR #17 workflow failures/successes; correct evidence-backed failures only.
2. Recover the historical VOG handover and current target-host owner state.
3. Prove Gateway/X-Ray read-only integration and restart/reconnect mechanically.
4. Resolve AgentOps↔Gateway link under owner authority.
5. Add proof record/update these recovery files only after evidence exists.
6. Keep PR #17 draft until Phase-6 acceptance is complete.
