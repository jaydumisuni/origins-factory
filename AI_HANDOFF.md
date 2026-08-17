# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current truth:** `CURRENT_STATE.md`  
**Merged checkpoint:** Phase 7 / PR #19 / `2f93f79f78502959fd09b50350b878ab659fee84`  
**Active phase:** Phase 8 — Custom OS consumption and later Ptah  
**Implementation status:** Phase 7 shipped and proven; Phase 8 not started  
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`  
**Phase-7 proof:** `proof/phase7-capability-evolution-freeze.md`

## Recovery order

Read this file, `CURRENT_STATE.md`, the accepted product plan, and the merged Phase-7 proof record. Before any Phase-8 code change, recover the canonical custom-OS repository, its packaging/release authority, existing Origins install/launcher contracts, and the current Ptah authorization boundary. Check existing branches/PRs/issues first. Do not ask the owner to repeat recoverable state.

## Ownership lock

- Hunter/Pete own intelligence.
- AgentOps owns semantic Operation/approval truth.
- CodeOps owns repository engineering/provider routing.
- Sergeant owns independent review/verdicts.
- Origins/originsd owns local mechanical Workspace/Repository/Session/application/Artifact truth plus Phase-7 canary/Generation/rollback/Mission-resume state.
- Oracle owns browser and reviewed remote workstation transport.
- Lumi owns acquisition/queue/resume truth.
- TECHGUYTOOL Huawei Gateway owns Huawei physical-session/operation/journal truth.
- TTG Device X-Ray owns read-first device evidence/certification truth.
- The custom OS consumes a pinned Origins release; it must not absorb or duplicate Origins source.
- Ptah remains the future mechanical substrate and is not runtime-authorized merely because Phase 8 names it.

Origins coordinates and projects these owners. It does not duplicate their engines.

## Phase 7 shipped checkpoint

PR #19 merged at:

```text
2f93f79f78502959fd09b50350b878ab659fee84
```

Frozen exact candidate:

```text
2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e
```

Construction history:

```text
archive/phase7-capability-evolution-construction
```

Exact owner revisions used by the frozen KRATOS proof:

```text
Hunter-AgentOps
0eeb69027aec9d70303e724129ebf5585f373ca1

hunter-codeops
348f133cb72ab6d18a7959d4a954158f7b881068

Sergeant
22879a8c47df379d19fb8537c79b745750df4077
```

### Phase 7 authority boundary

Origins requests and observes AgentOps approval/lifecycle state through MCP/RPC. Origins exposes no AgentOps approval-decision method or route.

Capability synthesis uses:

```text
owner_approval_required
```

Isolated/reversible candidate engineering uses:

```text
review_required
candidate_only = true
runtime_authority_expansion = false
```

The AgentOps MCP bearer credential is local service authentication only; it is not owner authorization. The exact approved engineering subject is read from durable Origins binding at execution time, so the client cannot replay an approval against a changed task/plan/repository request.

AgentOps owns the child external capability-upgrade Operation, CodeOps owns the repository candidate, Sergeant owns the independent verdict, and Origins owns canary/Generation/promotion/rollback/Mission-resume mechanical truth.

### Phase 7 proof

All eight hosted Origins regression workflows passed on frozen candidate `2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e`.

Independent adversarial Pass B was tests-only and passed:

```text
12 passed in 0.10s
```

Frozen exact-host KRATOS proof returned:

```text
PHASE7_LIVE_OWNER_MCP_OK
exitCode = 0
```

It proved:

- AgentOps transport `mcp/rpc`;
- no AgentOps decision tools exposed by Origins;
- real CodeOps plan application through the pinned CodeOps revision;
- pinned Sergeant executable provenance and `PASS` for promote + rollback campaigns;
- undispatched AgentOps child Operation at approval time;
- canary Session recovery across originsd restart;
- exact pre-upgrade Mission resume state;
- rollback does not activate the candidate Generation;
- no model self-approval;
- no production credentials;
- no runtime authority expansion.

Full record: `proof/phase7-capability-evolution-freeze.md`.

## Phase 6 preserved authority

Phase 6 remains closed and observational. The merged Gateway mount permits only:

```text
health
doctor
snapshot
get_physical_session
get_operation
list_events
verify_journal
```

Projection still requires:

```text
device_authority = none
xray_authority = read_only
journal_valid = true
```

Do not add physical-session mutation, endpoint recording, Gateway Operation mutation/resume, provider/worker mutation, Execution Lease consumption or device-write paths unless a later approved phase explicitly changes authority.

## Preserved truthful nonclaims

### AgentOps ↔ Huawei Gateway typed link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Current owners do not expose a reversible typed join. Do not create an Origins mapping table or reinterpret hashes as IDs.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Capability evolution does not grant device-write authority.

### Ptah runtime

```text
available = false
reason = PTAH_RUNTIME_NOT_AUTHORIZED
```

Phase 8 may consume frozen Ptah vocabulary and later swap interim Providers only after separate owner authorization and proof. Do not implement a hidden Ptah clone inside Origins or the custom OS.

## Exact next action

Start **Phase 8 — Custom OS consumption and later Ptah** with evidence recovery, not implementation:

1. recover the canonical custom-OS repository and its current state/roadmap;
2. identify the packaging/release authority that should produce the pinned Origins release consumed by the OS;
3. inspect existing Origins installation, launcher, health, update and rollback surfaces before adding anything;
4. inspect current Ptah authorization/proven Provider contracts and explicitly separate usable vocabulary from unavailable runtime;
5. define the smallest no-source-duplication consumption contract;
6. implement only after those authorities agree.

Do not reopen Phase 7 unless new reproducible evidence proves a regression.
