# ADR-0008 — Production Engineering Mount v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0007
**Owning systems:** `jaydumisuni/Hunter-AgentOps`, `jaydumisuni/hunter-codeops`, `jaydumisuni/Sergeant`

## Purpose

Close the gap between ADR-0007's protocol-proven bridge and an actual host capable of mounting the current AgentOps, CodeOps, and Sergeant owners.

This generation begins with a **read-only integration doctor**. It does not install, upgrade, modify, vendor, or repair external repositories automatically.

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
→ a later controlled live Engineering Assurance attempt using the actual owner stack has passed
```

The doctor itself can promote only as far as `compatible`. `proven` requires a separate live smoke/attempt receipt; presence or `--help` output is not proof of an engineering loop.

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

Compatibility probe constructs a harmless packet bound to the current Origins Repository worktree with:

- non-empty operation ID/task;
- no files;
- no plan;
- `apply_plan=false`;
- `ApprovalState.NOT_REQUIRED`.

The packet must preserve the supplied operation ID, task, and canonical Repository worktree. This checks the actual current constructor/validation behavior rather than symbol presence alone.

### CodeOps semantic ingest

Production module:

```text
hunter_codeops.code_ops_sergeant_ingest
```

Required symbol:

```text
ingest_sergeant_result_text
```

Compatibility probe submits canonical JSON verdicts without executing project work:

```text
PASS
NEEDS WORK
BLOCK
```

The owning function must preserve the expected verdict/loop/block semantics. Origins does not parse or repair the result itself.

## CLI probes

CLI compatibility is tested mechanically through originsd Sessions against an authorized Repository worktree:

```text
hunter-codeops-switcher --help
sergeant --help
```

The doctor never uses Python `subprocess`.

Classification:

- spawn/interruption because executable cannot start → `missing`;
- executable starts but returns non-zero/times out/truncates required probe output → `available`;
- completed exit 0 with non-truncated output → `compatible`.

A successful help probe proves command availability/shape only. It does not become `proven` engineering integration.

## Package metadata

When available, the doctor records installed distribution versions through Python package metadata:

```text
hunter-agentops
hunter-codeops
sergeant-reviewer
```

Missing metadata does not by itself override a successful imported contract probe, but it is reported explicitly. Compatibility comes from behavior, not merely version strings.

## Mechanical authority

The doctor receives an Origins `repository_id` and obtains:

- Workspace ID;
- canonical Repository worktree;
- Repository revision/HEAD;

from originsd.

All CLI probes therefore inherit the same mechanical controls as ADR-0007:

- loopback authenticated originsd;
- authorized Workspace root;
- typed process command envelope;
- durable Session identity;
- bounded output;
- no Python subprocess;
- no generic Git path.

## No automatic repair

A failed doctor may recommend exact next actions but does not:

- pip-install packages;
- alter PATH;
- clone/pull owner repositories;
- modify pyproject files;
- rewrite AgentOps/CodeOps/Sergeant APIs;
- silently substitute fixtures for missing production owners.

Capability installation or owner-repository upgrades are separate approved engineering operations.

## Doctor result

The result records:

- Repository ID/revision/HEAD used for the probe;
- each Python owner module status/version/detail;
- each CLI status/version/detail + mechanical Session ID;
- overall status;
- whether live engineering proof exists (false in doctor-only generation);
- blockers/recommendations.

No raw CLI output is copied into the permanent Origins journal by the doctor. Mechanical Session output remains under the existing Session evidence model.

## Live proof boundary

ADR-0008 doctor proof uses controlled fixtures in CI to prove doctor classification logic and Origins mechanical routing.

That fixture proof does not claim a user's machine currently has the private owner packages installed.

A later controlled host smoke using the actual installed owners is required before any doctor result may be labeled `proven`.

## Proof requirements

Before promotion the exact head must prove:

1. doctor code contains no Python subprocess use;
2. Repository/worktree identity comes from originsd;
3. exact production module/distribution/executable names are pinned by tests;
4. missing AgentOps import → `missing` without fallback schema creation;
5. present AgentOps symbols with incompatible packet behavior → `available`, not `compatible`;
6. compatible AgentOps packet behavior → `compatible`;
7. CodeOps ingest compatibility delegates to the owning function and checks PASS/NEEDS WORK/BLOCK semantics;
8. missing CodeOps ingest module → `missing`;
9. missing CLI spawn through originsd → `missing`;
10. non-zero CLI probe → `available`;
11. successful non-truncated CLI probe → `compatible`;
12. doctor overall status is the weakest required surface;
13. doctor never outputs `proven` without a separate live proof receipt;
14. fixture host proves all-compatible classification using real originsd durable Sessions;
15. a second fixture scenario proves one missing owner keeps overall status `missing` even when others are compatible;
16. all ADR-0002 through ADR-0007 proofs remain green;
17. documentation never upgrades fixture compatibility to live production proof.

## Explicit non-claims

This generation does not provide or claim:

- automatic installation or repair of owner packages;
- actual live private-package proof on the user's target host;
- AgentOps persistent lifecycle backend;
- provider/model execution;
- Hunter production mount;
- React UI;
- PTY interaction.
