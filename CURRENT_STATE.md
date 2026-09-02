# Origins Factory — Current State

**Architecture:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`  
**Merged checkpoint:** Phase 8A / PR #21 / `df0bbcef9da640d93518be87356733851ae8451e`  
**Frozen/proven product head:** `108c4fef9777bb8c1d25d39f372423ded6159ced`  
**Active phase:** Phase 8 — Custom OS consumption and later Ptah  
**Current slice:** Phase 8B — consume the pinned Origins release in the custom OS  
**Implementation status:** Phase 8A shipped and proven; custom-OS consumption is not yet implemented; Ptah runtime remains unauthorized  
**Phase-5 proof:** `proof/phase5-workspace-ui-freeze.md`  
**Phase-6 proof:** `proof/phase6-device-readonly-freeze.md`  
**Phase-7 proof:** `proof/phase7-capability-evolution-freeze.md`  
**Phase-8A proof:** `proof/phase8a-portable-release-freeze.md`

## Completed authority — do not rebuild

Origins PRs #11–#21 are merged authority. Phase 8A is part of `main` and closes the portable pinned-release contract slice.

Origins continues to coordinate existing owners rather than absorb them:

- Hunter/Pete — intelligence and model routing;
- AgentOps — semantic Operation/approval truth;
- CodeOps — repository engineering/provider routing;
- Sergeant — independent engineering verdicts;
- Origins/originsd — Workspace/Repository/Session/native application/Artifact, canary, Generation, rollback and Mission-resume mechanical truth;
- Oracle — browser and reviewed remote workstation transport;
- Lumi — acquisition/queue/resume truth;
- TECHGUYTOOL Huawei Gateway — Huawei physical-session/operation/journal truth;
- TTG Device X-Ray — read-first device evidence/certification truth;
- THETECHGUY Software Builder — final packaging/signing/release authority;
- Ptah Space — future mechanical substrate, not currently runtime-authorized.

## Phase 8A merged authority

PR #21 exact product head:

```text
108c4fef9777bb8c1d25d39f372423ded6159ced
```

Merged to `main` at:

```text
df0bbcef9da640d93518be87356733851ae8451e
```

Frozen product tree:

```text
48a682ea212fcefa4bfff61a9fcafca28577cb3d
```

Phase 8A now provides `origins.release.v1`, a bounded Linux x86_64 candidate release contract containing:

- native `originsd` artifact;
- Python integration wheel;
- Workspace static bundle;
- exact source and build-environment provenance;
- SHA-256/size-bound artifact records;
- deterministic archive/checksum construction;
- external persistent data-dir requirement;
- health, restart and persistence proof;
- independent archive/manifest/artifact/wheel/Workspace/runtime verification;
- source-derived Python runtime metadata bound from `python/pyproject.toml` into the manifest and checked against wheel METADATA.

The release remains candidate-only. Phase 8A does **not** claim Prime/custom-OS installation, final Software Builder release, production acceptance, Ptah Prime-native integration, or runtime authority expansion.

## Phase 8A proof checkpoint

Exact-head workflows on `108c4fef...`:

```text
Origins Daemon Foundation         PASS  run 33625215701
Origins Contract Spine            PASS  run 33625215702
Origins Phase 3 Workspace         PASS  run 33625215693
Stage-2 Authority Containment     PASS  run 33625215669
Phase 8 Portable Release          PASS  run 33625215653
```

The Phase 8 lane passed exact-head assertion, canonical/adversarial tests, deterministic double-build, independent unpack/runtime/restart proof, and clean-source verification. Stage-2 containment passed on Ubuntu and Windows.

Fresh independent CodeRabbit review against exact head `108c4fef...` reported **no blocking issues** and no unresolved inline threads.

Tenfold Gen1 disposition:

```text
campaign = origins-phase8a-runtime-metadata-integrity-v2
freeze_binding_sha256 = dce6325c287c14c98bb0ca43cd9f4155b37f10740b07930d240c0738ff200c85
state = SHIPPED
```

Full record: `proof/phase8a-portable-release-freeze.md`.

## Merge-history note

The GitHub provider's ready-for-review GraphQL mutation failed before merge, leaving the PR's historical `draft` flag set. The exact proven tree was merged through an authorised two-parent no-ff merge commit, and GitHub records PR #21 as merged at `df0bbcef...`. The stale draft bit is historical metadata only.

## Phase 7 authority retained

Phase 7 remains shipped/proven and owns the canonical controlled capability-evolution vertical. Its exact owner bindings, AgentOps/CodeOps/Sergeant proof, canary Generation, rollback and Mission-resume evidence remain frozen in `proof/phase7-capability-evolution-freeze.md`.

Do not reopen Phase 7 unless new reproducible evidence proves a regression.

## Preserved truthful nonclaims

### AgentOps ↔ Huawei Gateway durable link

```text
available = false
reason = AGENTOPS_GATEWAY_LINK_CONTRACT_UNAVAILABLE
```

No shadow mapping database or inferred IDs are authorized.

### Device write execution

```text
available = false
reason = PHASE6_DEVICE_WRITE_NOT_AUTHORIZED
```

Capability evolution and release packaging do not grant physical-device write authority.

### Ptah runtime

```text
available = false
reason = PTAH_RUNTIME_NOT_AUTHORIZED
```

Phase 8 may consume accepted Ptah vocabulary and later replace interim Providers only where separately authorized and proven. Origins and the custom OS must not silently rebuild Ptah runtime.

## Exact next action

Continue with **Phase 8B — custom-OS consumption of the pinned Origins release**:

1. recover the canonical custom-OS repository, current branch/checkpoint and release/packaging authority;
2. inspect existing installation, launcher, update, health and rollback contracts before adding anything;
3. consume the exact pinned Origins release through `origins.release.v1` without copying Origins source into the OS;
4. preserve exact Origins version/provenance, external persistent data, restart health and rollback;
5. keep THETECHGUY Software Builder as final packaging/signing/release authority;
6. keep Ptah runtime unavailable until a separate authorized/proven Provider replacement exists.

Do not reopen Phases 1–8A unless new reproducible evidence proves a regression.
