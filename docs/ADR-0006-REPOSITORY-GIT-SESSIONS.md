# ADR-0006 — Repository/Git Sessions v1

**Status:** FROZEN — mechanically proven
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0005
**External owner consulted:** `jaydumisuni/hunter-codeops`

## Purpose

Give Origins a durable read-first Git repository identity that CodeOps can consume without duplicating CodeOps' semantic repository recovery, planning, patch, proof, rollback, cross-repository coordination, or Sergeant handoff engine.

Origins owns mechanical Git observations. CodeOps continues to own engineering decisions and mutation workflows.

## Repository projection

Contract Spine v1.2 adds `repository_projection` with exact Rust/Python/TypeScript validation and cross-runtime canonical JSON/SHA equivalence.

The projection records:

- Origins repository ID;
- owning Origins Workspace ID;
- monotonically increasing repository projection revision;
- canonical worktree root;
- canonical Git directory;
- canonical Git common directory;
- exact HEAD object ID when one exists;
- full symbolic HEAD ref when one exists;
- short local branch name when attached;
- detached state;
- unborn state;
- staged, unstaged, and untracked counts;
- SHA-256 of the complete raw Git porcelain status stream;
- observation timestamp.

An initialized repository with no commit may have an empty HEAD object ID while still carrying its symbolic branch ref. Attached, detached, and unborn combinations fail closed when internally contradictory.

## Durable repository store

Repository projections are stored in Origins-owned SQLite state keyed by `repository_id` and unique `(workspace_id, canonical worktree root)` identity.

The Repository/Git subsystem has its own schema-generation record. The core daemon schema remains version 2 while the repository subsystem reports schema version 1.

Opening the same canonical worktree root in the same Workspace refreshes the existing Repository projection rather than creating duplicate identities. A linked Git worktree is a separate Origins Repository identity because its worktree/Git directory differs, while its shared Git common directory remains visible.

Repository projection reads verify canonical contract validity and stored SHA-256. Deliberate projection tampering therefore fails closed.

## Capability ownership

The three core built-in capability descriptors remain owned by the core store. Repository/Git registers its own two descriptors from `capabilities/repository.json` into the same durable capability table during subsystem initialization:

```text
origins.repository.inspect
origins.repository.diff
```

Both are model-free `observe`/`verify` capabilities. No repository mutation capability is introduced.

This preserves subsystem ownership instead of inflating the core capability manifest whenever a new Origins organ is added.

## Read-first Git execution

Repository inspection uses a dedicated deterministic Git reader, not a shell string and not CodeOps mutation logic.

The reader:

- accepts only existing directories beneath configured `ORIGINS_WORKSPACE_ROOTS`;
- resolves the actual Git worktree root and rechecks it against the authorized roots;
- resolves canonical Git directory and common directory identity;
- invokes Git directly with argv, no generic shell;
- clears inherited environment and forwards only a bounded reviewed host set;
- sets `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat`, and `LC_ALL=C`;
- disables optional fsmonitor and external diff behavior on the read path;
- bounds metadata/status/diff retention while hashing complete observed streams;
- does not expose Origins credentials to Git;
- does not run Git mutation commands in this generation.

Once this dedicated authority is active, the public generic `origins.process.run` command surface rejects `git` and `git.exe` with `DEDICATED_CAPABILITY_REQUIRED`. That prevents two public mechanical Git truth paths.

## Status truth

Origins derives staged, unstaged, and untracked counts from `git status --porcelain=v1 -z --untracked-files=all` and records SHA-256 over the complete status stream.

Status inspection is bounded to 8 MiB in v1; exceeding that inspection boundary fails rather than silently presenting partial counts as complete truth.

CodeOps may perform richer semantic repository analysis independently, but Origins' mechanical repository state comes from refreshed Git evidence, not from a model summary.

## Diff evidence

Authenticated staged and unstaged diff reads use deterministic direct-Git argv with external diff disabled, binary/full-index output, and no color.

Each response includes:

- refreshed repository projection;
- diff kind (`staged` or `unstaged`);
- retained bytes as hex and UTF-8 text when valid;
- retained byte count;
- complete observed byte count;
- SHA-256 of the complete observed diff stream;
- truncation flag.

Default retained diff bound is 512 KiB and the v1 maximum is 8 MiB. Complete stream hashing continues beyond retained bytes.

Raw diff content is not copied into the permanent hash-chained journal. The journal records only `repository.diff_observed` metadata and digests.

## Authenticated API surface

```text
POST /v1/repositories/inspect
GET  /v1/repositories?workspace_id=<workspace-id>
GET  /v1/repositories/{repository_id}
GET  /v1/repositories/{repository_id}/diff?kind=staged|unstaged&limit=<bytes>
```

Inspection payload:

```json
{
  "workspace_id": "<uuid>",
  "path": "/authorized/path/inside/repository"
}
```

Diff internally refreshes repository state before reading evidence; v1 does not expose a separate public refresh mutation-shaped endpoint.

Health additionally reports:

```text
repository_schema_version
repositories
```

## CodeOps integration boundary

Recovered CodeOps authority already provides repository recovery/analysis, provider/model routing, bounded patch generation, controlled apply, proof discovery, correction, rollback, cross-repository engineering, and Sergeant handoff through its CLI/JSON surfaces.

Origins therefore supplies CodeOps with durable repository IDs, canonical roots, exact revisions, status observations, mechanical Sessions, and evidence references. It must not copy the CodeOps orchestrator or patch engine into Origins.

## Challenge evidence

The challenged candidate passed:

1. Python contract corpus including repository valid/invalid states;
2. TypeScript contract corpus;
3. Rust contract corpus;
4. exact Rust/Python/TypeScript canonical JSON, SHA-256, validity, and error-code equivalence across 15 cases;
5. Clippy with warnings denied under Rust 1.75;
6. all Rust daemon/session/event/output/repository tests;
7. originsd build;
8. all inherited ADR-0002 through ADR-0005 hosted proofs;
9. authorized-root and non-Git-directory rejection;
10. clean attached-branch worktree/HEAD/ref/status identity;
11. repeated observation preserving Repository identity while advancing projection revision;
12. staged, unstaged, and untracked status counts plus complete-status SHA proof;
13. exact staged and unstaged diff complete-byte/SHA truth with deliberately small retention bounds and truncation;
14. proof that raw staged/unstaged diff content does not enter the permanent journal;
15. public generic `origins.process.run` rejection for Git after dedicated authority activation;
16. detached-HEAD representation;
17. linked-worktree proof with distinct Repository/Git directories and shared common directory;
18. two Repository projections surviving daemon restart;
19. deliberate repository-projection SQLite tampering returning `CORRUPT_STATE`;
20. token/log sanitation and repository whitespace proof.

Challenge also corrected capability ownership: Repository/Git descriptors moved out of the core built-in manifest and are initialized by the Repository/Git subsystem into the same capability table. The existing core `Store::open` invariant therefore remains three core capabilities while a running originsd with Repository/Git initialized exposes five total capabilities.

The substantive proof ran before formatting normalization. The proof-gated normalizer then applied the exact Rust formatting/dependency state. Final promotion still requires a fresh exact-head proof after this frozen documentation update.

## Explicit non-claims

This generation does not provide or claim:

- Git add/commit/reset/checkout/rebase/merge/push/pull;
- CodeOps planning or patch application;
- AgentOps lifecycle ownership;
- Sergeant review ownership;
- remote Git hosting/authentication management;
- repository filesystem editing;
- PTY/interactive terminal behavior;
- React repository UI.
