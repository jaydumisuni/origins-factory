# Origins Factory — AI Handoff

**Canonical architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Current truth:** `CURRENT_STATE.md`  
**Merged checkpoint:** Phase 8A / PR #21 / `df0bbcef9da640d93518be87356733851ae8451e`  
**Frozen/proven product head:** `108c4fef9777bb8c1d25d39f372423ded6159ced`  
**Active phase:** Phase 8 — Custom OS consumption and later Ptah  
**Current slice:** Phase 8B — pinned Origins release consumption  
**Implementation status:** Phase 8A shipped/proven; custom-OS consumption not yet implemented  
**Phase-7 proof:** `proof/phase7-capability-evolution-freeze.md`  
**Phase-8A proof:** `proof/phase8a-portable-release-freeze.md`

## Recovery order

Read, in order:

1. this file;
2. `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. `proof/phase8a-portable-release-freeze.md`;
5. `proof/phase7-capability-evolution-freeze.md` when earlier authority matters;
6. current branches, PRs, issues and source before making a new change.

Do not ask the owner to repeat state recoverable from those authorities.

## Ownership lock

- Hunter/Pete own intelligence.
- AgentOps owns semantic Operation/approval truth.
- CodeOps owns repository engineering/provider routing.
- Sergeant owns independent engineering review/verdicts.
- Origins/originsd owns local mechanical Workspace/Repository/Session/application/Artifact truth plus canary/Generation/rollback/Mission-resume state.
- Oracle owns browser and reviewed remote workstation transport.
- Lumi owns acquisition/queue/resume truth.
- TECHGUYTOOL Huawei Gateway owns Huawei physical-session/operation/journal truth.
- TTG Device X-Ray owns read-first device evidence/certification truth.
- THETECHGUY Software Builder owns final packaging/signing/release authority.
- The custom OS consumes a pinned Origins release; it must not absorb or duplicate Origins source.
- Ptah is the future mechanical substrate and remains runtime-unauthorized until separately accepted and proven.

Origins coordinates and projects these owners. It does not duplicate their engines.

## Phase 8A shipped checkpoint

Exact proven product head:

```text
108c4fef9777bb8c1d25d39f372423ded6159ced
```

Frozen product tree:

```text
48a682ea212fcefa4bfff61a9fcafca28577cb3d
```

Merged `main` checkpoint:

```text
df0bbcef9da640d93518be87356733851ae8451e
```

Release contract:

```text
origins.release.v1
status = candidate
```

Phase 8A ships the bounded portable release contract and proof tooling. It does **not** ship custom-OS installation or final production packaging.

### Phase 8A proof

All five exact-head workflows passed:

```text
Origins Daemon Foundation         run 33625215701
Origins Contract Spine            run 33625215702
Origins Phase 3 Workspace         run 33625215693
Stage-2 Authority Containment     run 33625215669
Phase 8 Portable Release          run 33625215653
```

The Phase 8 proof included deterministic double-build, independent archive/runtime/restart verification and clean-source verification. Stage-2 containment passed on Ubuntu and Windows.

Fresh CodeRabbit review of exact head `108c4fef...` found **no blocking issues**. Earlier actionable review threads are resolved/outdated and there are no unresolved inline threads.

Tenfold Gen1 binding:

```text
campaign = origins-phase8a-runtime-metadata-integrity-v2
freeze_binding_sha256 = dce6325c287c14c98bb0ca43cd9f4155b37f10740b07930d240c0738ff200c85
state = SHIPPED
```

Full proof: `proof/phase8a-portable-release-freeze.md`.

## Phase 8A contract boundary — do not widen implicitly

The release manifest remains candidate-only and preserves these nonclaims:

```text
prime_component_format_claimed = false
prime_installation_claimed = false
builder_final_release_proven = false
ptah_prime_native_proven = false
production_release_accepted = false
runtime_authority_expansion = false
```

The Python runtime contract is source-derived from `python/pyproject.toml`, checked against the pinned Phase 8A values, emitted into the manifest, then independently checked against wheel METADATA.

## Historical merge note

The GitHub provider's ready-for-review mutation failed on a GraphQL response-schema field. The normal merge endpoint then refused the still-draft PR. The owner-authorized fallback created an exact two-parent no-ff merge using the proven product tree and fast-forwarded `main` without force. GitHub records PR #21 as merged at `df0bbcef...`; its lingering historical `draft=true` flag is not unfinished engineering.

## Preserved earlier authority

Phase 7 remains closed and proven. Its AgentOps/CodeOps/Sergeant owner bindings, canary Generation, rollback and Mission-resume proof remain canonical in `proof/phase7-capability-evolution-freeze.md`.

Phase 6 remains read-only for device integration. Capability evolution and release packaging do not grant device-write authority.

## Preserved truthful nonclaims

### AgentOps ↔ Huawei Gateway typed link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

Do not manufacture a shadow join.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

### Ptah runtime

```text
available = false
reason = PTAH_RUNTIME_NOT_AUTHORIZED
```

Do not implement a hidden Ptah clone inside Origins or the custom OS.

## Exact next action

Continue **Phase 8B — custom-OS consumption of the pinned Origins release**:

1. recover the canonical custom-OS repository and its current state before changing code;
2. identify its real release/packaging/install/launcher authority and existing contracts;
3. consume the exact pinned Origins artifact through `origins.release.v1` with no source duplication;
4. preserve Origins version/provenance, external data, health/restart and rollback;
5. leave final product packaging/signing with THETECHGUY Software Builder;
6. leave Ptah runtime unavailable until a separately authorized/proven Provider boundary exists.

Do not rebuild Phase 8A unless new reproducible evidence proves a regression.
