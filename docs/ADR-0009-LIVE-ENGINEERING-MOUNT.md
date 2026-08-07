# ADR-0009 — Live Engineering Mount v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0008
**Corrects:** ADR-0007 CodeOps-config path ownership

## Purpose

Provide the controlled live-owner smoke path that can promote an engineering mount from `compatible` to `proven` **only when the actual AgentOps/CodeOps/Sergeant owners are installed and the complete read-only integration path succeeds**.

This slice also corrects one pre-live assumption: the CodeOps configuration is an integration resource, not a project edit artifact.

## Config authority correction

ADR-0007 correctly keeps changed files and edit plans inside the target Repository. It was too strict in requiring the CodeOps `--config` reference to be Repository-relative.

Recovered owning contracts show:

- AgentOps carries `config: Path("config/code_ops_switcher.example.json")` independently from `workspace`;
- CodeOps CLI accepts `--config` as its own integration/provider configuration input;
- project file/plan containment is enforced separately.

Therefore:

```text
project files / edit plan
→ remain Repository-scoped

CodeOps config
→ explicit integration configuration reference
→ may be relative to the process working directory or absolute
→ never treated as permission to edit outside the Repository
```

Origins validates a config reference as non-empty and NUL-free but does not falsely bind it to the target Repository. It does not read, copy, persist, or rewrite the config contents.

The operator/host is responsible for mounting a valid CodeOps config path. A later configuration-object capability may replace raw paths, but v1 does not invent one before evidence requires it.

## Live smoke theorem

A live engineering mount may become `proven` only through:

```text
Production Engineering Mount doctor
→ every required surface compatible
→ actual ExternalContracts loader
→ actual AgentOps packet validation
→ actual CodeOps route Session through originsd
→ actual CodeOps Sergeant-command Session through originsd
→ actual Sergeant review Session through originsd
→ actual CodeOps verdict ingestion
→ canonical non-UNKNOWN verdict
→ bounded smoke receipt
```

No project mutation is required or allowed by the smoke.

## Smoke behavior

The smoke uses:

- an existing durable Origins `repository_id`;
- explicit CodeOps config reference;
- a generated external operation ID for the smoke;
- no files unless explicitly requested for read-only review scope;
- no edit plan;
- `apply_plan=false`;
- `ApprovalState.NOT_REQUIRED`;
- no provider execution.

Task intent is read-only integration verification.

The existing Engineering Assurance Bridge performs:

1. AgentOps packet validation;
2. CodeOps `route` through originsd;
3. CodeOps `sergeant-command` through originsd;
4. Sergeant review through originsd;
5. CodeOps verdict ingestion.

The smoke does not call CodeOps provider execution or patch application.

## Proven verdict requirement

A live smoke is successful only when CodeOps normalizes actual Sergeant output to one of:

```text
PASS
NEEDS WORK
BLOCK
```

All three prove the owner stack can communicate end-to-end; they describe project review quality, not mount quality.

`UNKNOWN` does **not** prove the mount because actual Sergeant output was not canonically understood by the owning CodeOps ingestion contract.

The smoke receipt records the project verdict separately from mount proof.

## Doctor gate

Before any smoke process is launched:

- doctor overall status must equal `compatible`;
- every required surface must be compatible;
- doctor `live_engineering_proven` remains false;
- any missing/available owner blocks the smoke before new mechanical Sessions are created.

The smoke does not repair a failed doctor.

## Proof scope

Two proof scopes are explicit:

```text
fixture
→ CI protocol/logic proof using controlled owner fixtures
→ can never set live_engineering_proven=true

live_owner
→ actual installed owner packages/binaries via production loaders
→ may set live_engineering_proven=true after full successful smoke
```

Fixture proof cannot be relabeled as live proof by changing a display string. Production construction creates the `live_owner` scope internally; fixture construction is test-only.

## Receipt

A successful smoke receipt contains:

- proof scope;
- Repository ID/revision/HEAD;
- generated operation ID;
- doctor surface statuses/versions and doctor Session IDs;
- CodeOps route Session ID;
- CodeOps Sergeant-command Session ID;
- Sergeant review Session ID;
- review stdout SHA-256;
- normalized project verdict;
- recommended AgentOps action;
- `live_engineering_proven`.

It contains no raw CodeOps config contents, no provider credentials, and no raw review output.

In v1 the receipt is returned to the caller. It is not stored in a shadow AgentOps lifecycle database. Durable semantic receipt ownership remains an AgentOps concern until its production backend exists.

## Mechanical authority

Every executable probe/review remains under originsd. The smoke module contains no Python subprocess execution.

The smoke does not add new originsd mutation routes and does not restore generic Git execution.

## Proof requirements

Before promotion the exact head must prove:

1. ADR-0007 config-path rule is corrected in place while edit-plan containment remains unchanged;
2. config references may be absolute or relative but reject empty/NUL values;
3. plan references remain Repository-relative and escape-resistant;
4. smoke code contains no Python subprocess use;
5. incompatible doctor blocks smoke before bridge attempt;
6. fixture scope can never produce `live_engineering_proven=true`;
7. production construction is the only path to `live_owner` scope;
8. fixture PASS/NEEDS WORK/BLOCK can prove fixture end-to-end mount communication but remain `live_engineering_proven=false`;
9. fixture UNKNOWN fails mount proof;
10. smoke uses no plan/apply/provider execution;
11. all CodeOps/Sergeant mechanical work continues through originsd Sessions;
12. receipt contains IDs/digests/verdict/status only, not raw review/config contents;
13. hosted fixture proof runs doctor gate + bridge over real originsd/Repository/Sessions;
14. a missing-owner doctor fixture blocks before any smoke bridge Sessions are added;
15. all ADR-0002 through ADR-0008 proofs remain green;
16. documentation states that CI fixture proof is not actual target-host proof.

## Explicit non-claims

This generation does not provide or claim:

- actual live proof until run on a host with the real owner packages/binaries;
- automatic installation/repair;
- AgentOps persistent lifecycle backend;
- provider/model execution;
- project mutation during smoke;
- Hunter production mount;
- React UI;
- PTY interaction.
