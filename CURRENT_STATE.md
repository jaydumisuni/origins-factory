# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 5 / PR #16 / `d26bb68a621fb0e98f0a1766cbe3fea19228b2d8`
**Active phase:** Phase 6 — device read-only integration
**Branch:** `build/phase6-device-readonly-integration`
**PR:** #17, draft
**Phase-5 proof record:** `proof/phase5-workspace-ui-freeze.md`

## Completed authority — do not rebuild

Origins PRs #11–#16 are merged authority. Phase 5 added the proven Oracle, Lumi, native-application and Artifact mechanics plus Workspace surfaces. The Phase-5 merge checkpoint is `d26bb68a621fb0e98f0a1766cbe3fea19228b2d8`.

Ownership remains separate:

- Hunter/Pete — intelligence and model routing;
- AgentOps — semantic Operation/approval truth;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering verdicts;
- Origins/originsd — Workspace/Repository/Session/native application/Artifact mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — acquisition/queue/resume truth;
- TECHGUYTOOL Huawei Gateway — persistent Huawei physical-session/operation/journal authority;
- TTG Device X-Ray — read-first device evidence/certification authority.

Origins is a client/coordinator. It does not absorb specialist engines.

## Phase 6 recovered owner authority

### TECHGUYTOOL Huawei

Repository: `jaydumisuni/TECHGUYTOOL-Huawei`
Recovered default-branch revision: `fd3f7bb1587b65faaa7d37e0057683dcb07975ed`

Relevant frozen owner contract:

- loopback JSON-lines Gateway on `127.0.0.1:49321`;
- SQLite-backed physical sessions, operation sessions, providers, workers and hash-chained journal;
- `device_authority = none`;
- `xray_authority = read_only`;
- Gateway restart retains physical/operation identity and marks active Operations `recovering` until owner-controlled resume;
- endpoint observations are journalled with their full observation payload;
- accepted shared contracts are journalled with canonical validated JSON and SHA-256;
- shared contract vocabulary includes Device Evidence/Twin, Decision Verdict, Mode Lease, Execution Lease, Verification Result and Recovery Plan.

### TTG Device X-Ray

Repository: `jaydumisuni/TTG-Device-X-Ray`
Recovered default-branch revision: `34feb55ab937fa865726cbb22c44b09b52084114`

Relevant frozen owner contract:

- read-first evidence producer only;
- candidate grouping occurs before identity correlation;
- multiple physical candidates produce `UNSAFE` / `MULTIPLE_DEVICE_CANDIDATES`;
- profile routing never grants write authority;
- sealed bundle v2 contains a SHA-256 manifest for every evidence file and optional HMAC-SHA256 signature report;
- manifest fixes `write_allowed = false`;
- promoted Kirin/VOG capability remains replay-supported/read-only and carries no loader, partition-write, OEMINFO-write, flashing, reboot, unlock or relock authority.

## Phase 6 implementation on PR #17

### Huawei Gateway read-only mount

`python/origins_integration/device_readonly.py` mounts only the owner-defined read commands:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

The client refuses every other Gateway command before opening a socket. In particular, Phase 6 does not mount physical-session creation/closure, endpoint recording, Operation creation/transition/resume, provider/worker registration, contract publication, worker mutation or Gateway shutdown.

The projection fails closed unless owner truth reports:

```text
device_authority = none
xray_authority = read_only
journal_valid = true
```

Gateway events are projected into:

- endpoint observations;
- Device Evidence;
- Device Twin;
- Decision Verdict;
- Mode Lease;
- historical Execution Lease/Executor Result where present;
- Verification Result;
- Recovery Plan.

Historical execution records are display-only. Phase 6 never consumes an Execution Lease.

### TTG Device X-Ray sealed-bundle mount

Origins accepts one server-configured `ORIGINS_XRAY_BUNDLE_DIR`. The browser cannot provide or override the bundle path.

Before projection, Origins verifies:

- bundle schema `2.0`;
- manifest `write_allowed = false`;
- manifest SHA-256 using the X-Ray canonical serialization rule;
- every listed file path remains inside the configured bundle root;
- every listed file size and SHA-256 matches;
- signature report references the same manifest.

For a `SIGNED` bundle, HMAC is called cryptographically verified only when `ORIGINS_XRAY_SIGNING_KEY_FILE` is configured server-side and the HMAC matches. A `SIGNED` label by itself is not treated as proof. Signature material/key values are not returned to the Workspace.

### Phase-6 HTTP boundary

`python/origins_integration/phase6_server.py` is loopback-only and exposes protected GET projections:

```text
GET /v1/device
GET /v1/huawei/gateway
GET /v1/xray/bundle
```

`GET /v1/health` is sanitized/public. `POST`, `PUT`, `PATCH` and `DELETE` return `405 PHASE6_READ_ONLY`.

Write execution is always projected as:

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

### Workspace XRAY surface

`Phase6App` preserves the complete Phase-5 Workspace under `Workspace` and adds first-class `XRAY`.

XRAY displays:

- Gateway health/doctor/journal truth;
- physical Device Sessions;
- Gateway Operations and recovery counts;
- endpoint observations;
- Device Twin/Evidence;
- Decision Verdict;
- Mode Lease;
- historical Execution Lease with a display-only warning;
- Verification Result;
- Recovery Plan;
- sealed X-Ray bundle integrity/signature/freshness;
- Certification/Profile Match/Recommended Plan/Device Identity projections.

The XRAY surface provides no device action control. Refresh/disconnect are the only operational controls.

## Explicit Phase-6 gaps / nonclaims

### AgentOps ↔ Gateway durable link

Not yet mounted. Current truth:

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Do not invent a second mapping database or overload Gateway `request_sha256` without recovering/fixing the owning cross-system reference contract.

### Device write execution

Not authorized in Phase 6 even though the Huawei repository contains later lease/executor implementation. Origins may display owner lease/result evidence but must not request, consume or execute it.

### Production physical-device proof

Not yet complete on PR #17. Hosted tests/CI, target-host Gateway/X-Ray proof, restart/reconnect evidence, historical VOG recovery-handover recovery and rendered Workspace acceptance remain required before Phase 6 can be promoted.

## Dedicated proof

Workflow: `.github/workflows/phase6-device-readonly.yml`
Target-host proof tool: `tools/prove_phase6_device_readonly.py`

The dedicated gate proves:

- Phase-6 Python compile;
- read-only Gateway command allowlist;
- expanded owner authority fails closed;
- X-Ray manifest/evidence tampering fails closed;
- optional HMAC verification requires the server key reference;
- Workspace TypeScript typecheck;
- Vitest;
- production bundle build;
- repository whitespace.

## Relevant Phase-6 configuration

```text
ORIGINS_LOCAL_TOKEN
ORIGINS_PHASE6_BIND
ORIGINS_PHASE6_PORT
ORIGINS_HUAWEI_GATEWAY_HOST
ORIGINS_HUAWEI_GATEWAY_PORT
ORIGINS_HUAWEI_GATEWAY_TIMEOUT
ORIGINS_XRAY_BUNDLE_DIR
ORIGINS_XRAY_SIGNING_KEY_FILE
```

Secrets remain local references and must not be committed, printed, returned by APIs or typed through browser automation.

## Exact next actions

1. Let PR #17 hosted and inherited regression gates review the current implementation; correct evidence-backed failures only.
2. Recover the historical VOG handover/recovery evidence required by the canonical Phase-6 vertical.
3. Prove the real Huawei Gateway read-only mount on the target host, including journal and restart/reconnect truth.
4. Prove a real sealed TTG Device X-Ray bundle and render its evidence through Origins.
5. Resolve the AgentOps↔Gateway reference contract under the correct owner authority; do not fabricate the link.
6. Run isolated rendered XRAY acceptance and re-run all inherited gates on the final recovery head.
7. Keep PR #17 draft/unmerged until those proofs are complete.
