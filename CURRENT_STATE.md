# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Merged checkpoint:** Phase 5 / PR #16 / `d26bb68a621fb0e98f0a1766cbe3fea19228b2d8`
**Active phase:** Phase 6 — device read-only integration
**Branch:** `build/phase6-device-readonly-integration`
**PR:** #17, promotion candidate
**Phase-5 proof:** `proof/phase5-workspace-ui-freeze.md`
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`

## Completed authority — do not rebuild

Origins PRs #11–#16 are merged authority. Phase 5 added the proven Oracle, Lumi, native-application, Artifact and Workspace application/browser/logistics surfaces. Origins remains a coordinator/client of specialist owners rather than a replacement for them.

Ownership remains separate:

- Hunter/Pete — intelligence and model routing;
- AgentOps — semantic Operation/approval truth;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering verdicts;
- Origins/originsd — Workspace/Repository/Session/native application/Artifact mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — acquisition/queue/resume truth;
- TECHGUYTOOL Huawei Gateway — Huawei physical-session/operation/journal truth;
- TTG Device X-Ray — read-first device evidence/certification truth.

## Phase 6 recovered owner authority

### TECHGUYTOOL Huawei

```text
repository = jaydumisuni/TECHGUYTOOL-Huawei
revision = fd3f7bb1587b65faaa7d37e0057683dcb07975ed
default_gateway = 127.0.0.1:49321
device_authority = none
xray_authority = read_only
```

The owner persists physical Sessions, Gateway Operations, providers/workers and a hash-chained journal. Restart retains physical/Operation identity and active Operations recover explicitly. Endpoint observations and accepted shared contracts are journalled with canonical owner truth.

### TTG Device X-Ray

```text
repository = jaydumisuni/TTG-Device-X-Ray
revision = 34feb55ab937fa865726cbb22c44b09b52084114
write_allowed = false
```

X-Ray remains read-first. Sealed bundle v2 hashes every evidence file, optional HMAC verification is separate from digest integrity, and promoted Kirin/VOG capability carries no loader, partition-write, OEMINFO-write, flashing, reboot, unlock or relock authority.

## Phase 6 implementation

### Huawei Gateway read-only mount

Origins permits exactly these Gateway commands:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

Every other Gateway command is rejected before network I/O. Projection fails closed unless:

```text
device_authority = none
xray_authority = read_only
journal_valid = true
```

Journal projection recovers endpoint observations plus Device Evidence/Twin, Decision Verdict, Mode Lease, historical Execution Lease/Executor Result, Verification Result and Recovery Plan. Historical execution evidence is display-only; Phase 6 never consumes an Execution Lease.

### X-Ray sealed-bundle mount

`ORIGINS_XRAY_BUNDLE_DIR` is server-owned. The browser cannot choose the bundle path. Origins verifies bundle schema 2.0, `write_allowed=false`, canonical manifest SHA-256, contained file paths, file sizes/hashes and signature-manifest binding. A SIGNED label is cryptographically trusted only when the server-side HMAC key reference exists and verifies.

### HTTP and Workspace boundary

`python/origins_integration/phase6_server.py` is loopback-only. Protected routes are GET-only:

```text
GET /v1/device
GET /v1/huawei/gateway
GET /v1/xray/bundle
```

`GET /v1/health` is sanitized/public. POST/PUT/PATCH/DELETE return `405 PHASE6_READ_ONLY`.

The Workspace preserves Phase 5 under `Workspace` and adds first-class `XRAY`. XRAY displays owner health, journal, physical Sessions, Gateway Operations/recovery counts, endpoints, Device Twin/Evidence, verdicts, leases, verification, Recovery Plan and sealed X-Ray evidence. It exposes no device action control.

## Phase 6 proof state

Implementation proof head:

```text
4e788a584505fc5728a07a1bf73ece1e8a6bfd17
```

At that exact head:

- all seven hosted regression workflows passed;
- Oracle/Kratos Phase-6 backend + reconnect suite passed 8/8;
- reconnect preserved owner Session ID, Gateway Operation ID, request SHA and recovery counters without mutation;
- isolated real Chrome returned `PHASE6_WORKSPACE_UI_OK`;
- XRAY rendered no write controls and no production credentials;
- X-Ray integrity remained verified;
- rendered screenshot SHA-256 is `9b5665285ad84d32d229b8dd55fe9bd5c6620b40221b05068e3313acd5bb24af`.

See `proof/phase6-device-readonly-freeze.md` for the frozen evidence and exact nonclaims.

## Accepted nonclaims — not promotion blockers

### AgentOps ↔ Gateway durable link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Neither owner currently exposes a reversible typed semantic↔mechanical reference. Origins does not create a shadow mapping database or reinterpret Gateway hashes as AgentOps IDs. A future link belongs under owner-approved contract evolution.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Phase 6 does not gain write authority merely because later Huawei lease/executor code exists.

### Current physical Huawei attachment

Historical VOG/P30 recovery evidence is preserved as lineage and predates X-Ray sealed-bundle v2. No current attached Huawei target is proven in the recovered device registry/host records, so Phase 6 makes no current-device certification or write claim. This does not invalidate the proven software read-only integration.

## Promotion boundary

Phase 6 implementation and acceptance evidence are complete. PR #17 is ready for promotion once the final recovery/documentation head re-runs the hosted and target-host proofs. After merge, normalize this file to the Phase-6 merge checkpoint and recover Phase 7 before implementation.
