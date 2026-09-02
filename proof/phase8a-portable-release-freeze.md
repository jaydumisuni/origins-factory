# Origins Factory — Phase 8A Portable Release Freeze

**Status:** SHIPPED / PROVEN  
**Phase:** 8A — Portable pinned release contract  
**PR:** #21  
**Frozen exact product head:** `108c4fef9777bb8c1d25d39f372423ded6159ced`  
**Frozen product tree:** `48a682ea212fcefa4bfff61a9fcafca28577cb3d`  
**Merge checkpoint:** `df0bbcef9da640d93518be87356733851ae8451e`  
**Release contract:** `origins.release.v1`  
**Execution standard:** `ttg.tenfold.v1`

## Authority delivered

Phase 8A creates the first bounded Origins distribution contract without turning Origins into the custom OS or granting downstream systems new runtime authority.

The shipped product lane provides:

- a Linux x86_64 candidate release contract;
- aligned `0.1.0` component versions across `originsd`, Python integration and Workspace UI;
- deterministic candidate assembly with exact source commit and build-environment provenance;
- immutable SHA-256 and size records for the native daemon, Python wheel and Workspace bundle;
- a release archive plus checksum sidecar;
- external persistent runtime data, separate from the immutable release root;
- independent archive, manifest, artifact, wheel, Workspace and runtime verification;
- `/v1/health`, restart and persistence proof;
- source-derived Python runtime metadata from `python/pyproject.toml` with fail-closed pinned-contract validation;
- independent wheel `Requires-Python` / `Requires-Dist` verification against the release manifest.

## Preserved claim boundary

The Phase 8A manifest remains candidate-only. These claims remain false:

```text
prime_component_format_claimed = false
prime_installation_claimed = false
builder_final_release_proven = false
ptah_prime_native_proven = false
production_release_accepted = false
runtime_authority_expansion = false
```

Ownership remains separated:

- Origins owns the candidate release contract and artifact identity.
- THETECHGUY Software Builder remains final packaging/signing/release authority.
- The custom OS remains the consumer and must not copy Origins source into the OS tree.
- Ptah remains a later separately authorised/proven mechanical Provider boundary.

## Exact-head hosted proof

All five workflows associated with exact product head `108c4fef9777bb8c1d25d39f372423ded6159ced` completed successfully:

```text
Origins Daemon Foundation         run 33625215701  PASS
Origins Contract Spine            run 33625215702  PASS
Origins Phase 3 Workspace         run 33625215693  PASS
Stage-2 Authority Containment     run 33625215669  PASS
Phase 8 Portable Release          run 33625215653  PASS
```

The Phase 8 Portable Release lane additionally proved:

```text
Assert exact reviewed revision                    PASS
Compile release tooling and tests                 PASS
Run canonical release contract/adversarial tests PASS
Build exact-head portable candidate twice         PASS
Independently unpack and prove released runtime   PASS
Prove release construction left checkout clean    PASS
```

Stage-2 containment passed on both Ubuntu and Windows.

## Independent review

A fresh CodeRabbit review was requested against exact head:

```text
108c4fef9777bb8c1d25d39f372423ded6159ced
```

Review response: **no blocking issues**.

It confirmed the requested HEAD and specifically validated the Python runtime metadata chain across:

```text
python/pyproject.toml
→ release builder
→ origins.release.v1 manifest
→ manifest verifier
→ wheel METADATA verifier
```

All earlier actionable inline review threads were already resolved/outdated; no unresolved inline thread remained.

## Tenfold disposition

The product milestone was executed through the real Tenfold Gen1 Foreman in the workspace before repository promotion.

```text
campaign = origins-phase8a-runtime-metadata-integrity-v2
freeze_binding_sha256 = dce6325c287c14c98bb0ca43cd9f4155b37f10740b07930d240c0738ff200c85
promoted_product_head = 108c4fef9777bb8c1d25d39f372423ded6159ced
merge_checkpoint = df0bbcef9da640d93518be87356733851ae8451e

Understand  PASS
Build       PASS
Review      PASS
Freeze      PASS
Prove       PASS
Ship        PASS
```

## Merge lineage

The GitHub ready-for-review connector mutation failed on a provider GraphQL response-schema field before merge. GitHub's normal merge endpoint therefore refused the still-draft PR.

The authorised fallback preserved PR provenance rather than rewriting the branch:

- verified `main` was still `590c03170a234b523650fc19992d25c9e5ed6e89`;
- verified product head `108c4fef...` was 11 commits ahead and 0 behind;
- constructed a two-parent no-ff merge commit using the exact proven tree `48a682ea...`;
- parents are the previous `main` and exact proven PR head;
- fast-forwarded `main` to `df0bbcef9da640d93518be87356733851ae8451e` without force;
- GitHub then recorded PR #21 as `merged=true` with that merge SHA.

The historical PR object still reports `draft=true`. That is metadata from the failed ready-for-review transition, not an engineering or shipping blocker.

## Earlier authority retained

Phases 1–7 remain merged authority. Their existing freeze records remain canonical for their respective surfaces:

- `proof/phase5-workspace-ui-freeze.md`
- `proof/phase6-device-readonly-freeze.md`
- `proof/phase7-capability-evolution-freeze.md`

Phase 8A does not reopen those phases.

## Next canonical slice

Continue Phase 8 with **custom-OS consumption of the pinned Origins release**:

1. recover the canonical custom-OS repository and current release/integration authority;
2. consume a pinned `origins.release.v1` candidate/release artifact without copying Origins source;
3. preserve Origins version/provenance, external data, health, restart and rollback boundaries;
4. keep final packaging/signing/release ownership with THETECHGUY Software Builder;
5. keep Ptah runtime unavailable until a separate authorised/proven Provider replacement exists.

Do not rebuild Phase 8A unless new reproducible evidence proves a regression.
