# ADR-0009 — Live Engineering Mount v1

**Status:** FROZEN — implementation and fixture-hosted proof accepted; actual target-host live-owner receipt pending
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0008
**Corrects:** ADR-0007 CodeOps-config path ownership

## Purpose

Provide the controlled smoke path that can promote an engineering mount from `compatible` to `proven` only when the actual AgentOps/CodeOps/Sergeant owners are installed and the complete read-only integration path succeeds.

This slice also corrects one pre-live assumption: CodeOps configuration is an integration resource, not a project edit artifact.

## Authority correction

Project files and edit plans remain Repository-scoped. CodeOps `--config` is an engineering-stack integration reference and may be absolute or relative.

Origins therefore:

- validates config as non-empty and NUL-free;
- does not treat config as permission to edit outside the Repository;
- does not copy the config into every project;
- does not read, persist, or rewrite config contents merely because the bridge references it;
- keeps edit-plan references Repository-relative and escape-resistant.

ADR-0007 was corrected in place to reflect this split.

## Fresh Repository theorem

Doctor and bridge work must begin from fresh mechanical Git truth.

```text
Repository ID
→ read durable Workspace/worktree identity
→ originsd Repository inspect
→ require same Repository ID
→ use refreshed revision + HEAD
→ semantic engineering / assurance work
```

A stored projection alone is not sufficient evidence for a new engineering Attempt.

## Live smoke theorem

A mount may become `proven` only through:

```text
Production Engineering Mount doctor
→ every required surface compatible
→ production ExternalContracts loader
→ AgentOps packet validation
→ CodeOps route Session through originsd
→ CodeOps Sergeant-command Session through originsd
→ Sergeant review Session through originsd
→ CodeOps verdict ingestion
→ canonical non-UNKNOWN verdict
→ bounded integrity-addressed receipt
```

No project mutation is required or allowed by the smoke.

## Smoke behavior

The smoke uses:

- an existing durable Origins `repository_id`;
- an explicit CodeOps config reference;
- a generated external operation ID;
- optional read-only review file scope;
- no edit plan;
- `apply_plan=false`;
- `ApprovalState.NOT_REQUIRED`;
- no provider/model execution.

The Engineering Assurance Bridge remains the semantic path. All CodeOps/Sergeant mechanical processes remain originsd Sessions.

## Project verdict versus mount proof

Canonical review results are:

```text
PASS
NEEDS WORK
BLOCK
```

Any of those may prove that the actual owner stack communicated end-to-end. They describe project quality, not mount quality.

`UNKNOWN` never proves the mount.

Exact recommendation semantics remain:

```text
PASS       → complete_candidate
NEEDS WORK → correct
BLOCK      → block
UNKNOWN    → unresolved
```

`complete_candidate` remains advice to AgentOps, not Origins completion authority.

## Proof scopes

```text
fixture
→ controlled CI owner fixtures
→ may prove Origins routing/protocol behavior
→ can never set live_engineering_proven=true

live_owner
→ production constructor + actual installed owners
→ may set live_engineering_proven=true after full successful smoke
```

The proof-scope token is internal. A display string cannot promote fixture evidence into live-owner proof.

## Receipt

A smoke receipt contains:

- proof scope;
- mount status;
- `live_engineering_proven`;
- Repository ID/revision/HEAD;
- generated operation ID;
- doctor surface status/version/Session evidence;
- CodeOps route Session ID;
- CodeOps Sergeant-command Session ID;
- Sergeant review Session ID;
- review stdout SHA-256;
- canonical project verdict;
- recommended AgentOps action;
- canonical receipt SHA-256.

The receipt excludes raw CodeOps config, provider credentials, raw review text, and stdout/stderr bodies.

The receipt SHA-256 is computed over canonical Origins JSON for the compact receipt body. Identical bodies produce identical digests; changed evidence changes the digest.

The receipt is returned to the caller in v1. Origins does not invent a shadow AgentOps lifecycle database to persist semantic completion.

## Mechanical authority

Every executable probe/review remains under originsd. The smoke module contains no Python subprocess execution.

The smoke adds no new mutation route and does not restore generic Git execution.

## Challenge evidence

The first strengthened doctor run failed for a valid reason in the **fixture environment**, not production code: the missing-Sergeant restart replaced `PATH` with the CodeOps fixture directory only. After Repository freshness became mandatory, that accidentally removed Git as well.

The proof was corrected so the restart PATH contains only:

```text
CodeOps fixture directory
+ system Git directory
```

and explicitly asserts Sergeant remains absent. The same correction was applied to the hosted live-mount smoke.

A second challenge found that `tools/prove_live_engineering_mount.py` existed but was not yet wired into the daemon workflow. The existing runtime workflow was corrected in place so this proof is compiled and executed; no parallel CI island was created.

On exact implementation head `8fa5e096e81fa70226ccc65b30dd7d9a1638aad6`, both required suites passed:

- **Origins Contract Spine** — success;
- **Origins Daemon Foundation** — success.

The daemon proof included successful execution of:

1. originsd auth/persistence/journal/restart recovery;
2. supervised Process Sessions;
3. active Session control/event replay;
4. live Session observation/cursor reconnect;
5. Repository/Git Sessions;
6. Engineering Assurance Bridge protocol;
7. Production Engineering Mount doctor;
8. Live Engineering Mount hosted smoke;
9. repository whitespace gate.

The hosted live smoke proves, against real originsd and controlled exact-name owner fixtures:

- external CodeOps config outside the target Repository;
- fresh Repository inspection before doctor/bridge work;
- doctor compatibility gate;
- durable CodeOps route and Sergeant-command Sessions;
- durable Sergeant review Session;
- CodeOps-owned verdict normalization;
- fixture `NEEDS WORK → correct` routing;
- fixture scope cannot self-promote;
- compact canonical receipt SHA-256;
- no raw config/token leakage into permanent journal evidence;
- missing Sergeant blocks before bridge work after restart;
- Git remains available during that missing-owner check;
- no automatic repair or owner substitution.

## Operator surface

A thin operator-facing smoke command exists for the production constructor. It consumes originsd loopback auth through the existing environment contract and emits the compact JSON receipt. It does not install owners, execute providers, apply plans, or mutate project files.

## Explicit non-claims

This generation does **not** claim:

- that the user's actual target host has compatible AgentOps/CodeOps/Sergeant installations;
- an actual `live_owner` receipt from that host;
- automatic package installation or repair;
- AgentOps production persistent lifecycle/completion backend;
- provider/model execution;
- project mutation during smoke;
- production Hunter mount;
- React Workspace UI;
- PTY interaction.

Actual target-host proof is a deployment verification step, not something CI fixtures may impersonate.
