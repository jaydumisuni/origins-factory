# ADR-0008 — Production Engineering Mount v1

**Status:** FROZEN — compatibility doctor mechanically proven; live target-host proof pending
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0007
**Owning systems:** `jaydumisuni/Hunter-AgentOps`, `jaydumisuni/hunter-codeops`, `jaydumisuni/Sergeant`

## Purpose

Close the gap between ADR-0007's protocol-proven bridge and an actual host capable of mounting the current AgentOps, CodeOps, and Sergeant owners.

This generation adds a **read-only integration doctor**. It does not install, upgrade, modify, vendor, or repair external repositories automatically.

## Status vocabulary

Every owner surface is classified independently:

```text
missing
→ required package/module/executable cannot be found or started

available
→ owner is present, but required contract behavior is not yet proven compatible

compatible
→ current required contract behavior passes non-mutating compatibility probes

proven
→ a separate controlled live Engineering Assurance attempt using the actual owner stack has passed
```

The doctor itself promotes only as far as `compatible`. Presence or `--help` output never becomes `proven` engineering integration.

Overall doctor status is the weakest required owner surface. No average/majority logic may hide one missing authority.

## Current recovered owner identities

Evidence recovered from current owning repositories:

```text
hunter-agentops       0.3.0
hunter-codeops        0.3.0
sergeant-reviewer     0.4.1
```

Current executable contracts:

```text
hunter-codeops-switcher
sergeant
```

Versions are observations, not permanent compatibility locks. Compatibility is determined by required contract behavior, while installed versions are recorded for recovery and diagnosis.

## Python contract probes

### AgentOps

Production module:

```text
hunter_agentops.code_ops_switcher_runner
```

Required symbols:

```text
ApprovalState
CodeOpsOperationPacket
```

Compatibility constructs a harmless packet bound to the current Origins Repository worktree with no files, no plan, `apply_plan=false`, and `ApprovalState.NOT_REQUIRED`. The packet must preserve operation ID, task, Repository worktree, and non-apply intent.

### CodeOps semantic ingest

Production module:

```text
hunter_codeops.code_ops_sergeant_ingest
```

Required symbol:

```text
ingest_sergeant_result_text
```

Compatibility delegates canonical JSON verdicts to the owner and requires:

```text
PASS       → needs_loop=false, blocked=false
NEEDS WORK → needs_loop=true,  blocked=false
BLOCK      → needs_loop=true,  blocked=true
```

Origins does not parse or repair those semantics itself.

## CLI probes

CLI compatibility is tested mechanically through originsd Sessions against an authorized Repository worktree:

```text
hunter-codeops-switcher --help
sergeant --help
```

The doctor never uses Python `subprocess`.

Classification:

- interrupted/no-code start failure → `missing`;
- executable starts but exits non-zero, times out, or truncates required probe output → `available`;
- completed exit 0 with non-truncated output → `compatible`.

CLI Session ID and stdout SHA-256 are retained in the doctor result. Raw help output remains under the existing mechanical Session evidence model rather than being duplicated into a new doctor log store.

## Package metadata

When available, the doctor records installed distribution versions through Python package metadata:

```text
hunter-agentops
hunter-codeops
sergeant-reviewer
```

Missing metadata does not by itself override successful behavioral compatibility. Compatibility comes from behavior, not merely version strings.

## Mechanical authority

The doctor receives an Origins `repository_id` and obtains Workspace ID, canonical Repository worktree, Repository revision, and HEAD from originsd.

All CLI probes inherit loopback authentication, authorized Workspace roots, typed command envelopes, durable Sessions, bounded output, and the no-generic-Git rule.

## No automatic repair

A failed doctor may report blockers but does not:

- pip-install packages;
- alter PATH;
- clone/pull owner repositories;
- modify pyproject files;
- rewrite AgentOps/CodeOps/Sergeant APIs;
- silently substitute fixtures for missing production owners.

Capability installation or owner upgrades are separate approved engineering operations.

## Doctor result

`EngineeringMountDoctorResult` records:

- Repository ID/revision/HEAD used for the probe;
- `agentops_python` status/version/detail;
- `codeops_python` status/version/detail;
- `codeops_cli` status/version/detail/Session/digest;
- `sergeant_cli` status/version/detail/Session/digest;
- weakest-link overall status;
- `live_engineering_proven=false` in this doctor-only generation;
- blockers for any surface below compatible.

## Live proof boundary

ADR-0008 CI proof uses controlled owner fixtures with the exact recovered module/distribution/executable identities while using **real originsd, a real durable Repository, and real durable process Sessions**.

That fixture proof does not claim the user's target host currently has the private owner packages installed.

A separate controlled host smoke using the actual installed owners is required before the engineering mount may be labeled `proven`.

## Challenge evidence

The challenged candidate passed:

1. doctor source contains no Python `subprocess` import/use;
2. exact AgentOps/CodeOps module, distribution, and executable names are pinned by tests;
3. all-compatible Python/CLI fixtures produce overall `compatible`, never `proven`;
4. missing AgentOps import keeps overall status `missing` without fallback schema creation;
5. incompatible AgentOps packet behavior is classified `available`, not compatible;
6. changed CodeOps Sergeant-ingest semantics are classified `available`;
7. CLI interruption is classified `missing`;
8. CLI non-zero and truncated-help probes are classified `available`;
9. compatible CLI probes are submitted only through originsd Sessions;
10. hosted fixture packages report recovered observations `hunter-agentops 0.3.0`, `hunter-codeops 0.3.0`, and `sergeant-reviewer 0.4.1`;
11. hosted all-compatible fixture proves two CLI probe Sessions are durable `origins.process.run` Sessions;
12. hosted restart with Sergeant deliberately absent from PATH keeps AgentOps, CodeOps Python, and CodeOps CLI compatible while `sergeant_cli=missing` forces overall `missing`;
13. the doctor does not recreate the missing Sergeant executable or alter the fixture PATH directory;
14. `live_engineering_proven` remains false in both compatible and missing scenarios;
15. all ADR-0002 through ADR-0007 hosted runtime proofs remain green;
16. Python/TypeScript/Rust Contract Spine proofs, exact three-runtime equivalence, Clippy, all Rust tests/build, whitespace, and rustfmt remain green.

Both proof suites passed on candidate head `46f31faf9ca3df3b26f7199ec0c5a77ba2e251e8` before this documentation freeze. Final promotion still requires a fresh exact-head proof after the documentation updates.

## Explicit non-claims

This generation does not provide or claim:

- automatic installation or repair of owner packages;
- actual live private-package proof on the user's target host;
- a `proven` engineering mount result from the doctor alone;
- AgentOps persistent lifecycle backend;
- provider/model execution;
- Hunter production mount;
- React UI;
- PTY interaction.
