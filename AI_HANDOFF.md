# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`
**Current truth:** `CURRENT_STATE.md`
**Merged checkpoint:** Phase 6 / PR #17 / `9a9f05a984b0ba5fd2edd8e8c0b27b5645117697`
**Active phase:** Phase 7 — capability evolution recovery
**Implementation status:** Phase 7 not started
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`

## Recovery order

Read this file, `CURRENT_STATE.md`, the accepted product plan, then the merged Phase-6 proof record. Before any Phase-7 code change, recover current AgentOps, CodeOps, Sergeant and capability-evolution owner contracts and check for existing branches/PRs/issues. Do not ask the owner to repeat recoverable state.

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

## Phase 6 merged checkpoint

PR #17 merged at:

```text
9a9f05a984b0ba5fd2edd8e8c0b27b5645117697
```

Final promotion head:

```text
284b1145fac5e93edd0235c43a6d395db392e78e
```

Owner revisions frozen for Phase 6:

```text
TECHGUYTOOL-Huawei
fd3f7bb1587b65faaa7d37e0057683dcb07975ed

TTG-Device-X-Ray
34feb55ab937fa865726cbb22c44b09b52084114
```

The merged Gateway mount permits only:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

Every other command is refused before network I/O. The projection requires `device_authority=none`, `xray_authority=read_only` and a verified journal. Phase-6 HTTP remains loopback/protected GET-only and the XRAY Workspace remains observational only.

## Phase 6 proof

All seven hosted workflows passed at the final promotion head.

Oracle/Kratos exact-head proof:

```text
8 passed in 2.09s
PHASE6_WORKSPACE_UI_OK
exitCode = 0
```

The reconnect proof preserved physical Session ID, Gateway Operation ID, request SHA and recovery counters without mutation. Real Chrome rendered no write controls, no production credentials, `device_authority=none`, `xray_authority=read_only`, verified X-Ray integrity and screenshot SHA-256:

```text
9b5665285ad84d32d229b8dd55fe9bd5c6620b40221b05068e3313acd5bb24af
```

Full record: `proof/phase6-device-readonly-freeze.md`.

## Preserved truthful nonclaims

### AgentOps ↔ Huawei Gateway typed link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Current owners do not expose a reversible typed join. Do not create an Origins mapping table or reinterpret hashes as IDs. This is future owner-contract work.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Do not add physical-session mutation, endpoint recording, Gateway Operation mutation/resume, provider/worker mutation, contract publication, Execution Lease consumption, executor invocation or device write paths unless a later approved phase explicitly changes authority.

### Historical VOG/P30

Recovered evidence is historical lineage and predates sealed-bundle v2. No current attached Huawei target is proven. Do not fabricate current-device certification or reopen the proven software read-only integration because a handset is not presently attached.

## Exact next action

Recover Phase 7 capability-evolution evidence and owner contracts before implementation. Check existing Origins, AgentOps, CodeOps and Sergeant work first; extend authority rather than duplicating it.
