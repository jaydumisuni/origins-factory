# ADR-0006 — Repository/Git Sessions v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0005
**External owner consulted:** `jaydumisuni/hunter-codeops`

## Purpose

Give Origins a durable read-first Git repository identity that CodeOps can consume without duplicating CodeOps' semantic repository recovery, planning, patch, proof, or Sergeant handoff engine.

Origins owns mechanical Git observations. CodeOps continues to own engineering decisions and mutation workflows.

## Repository projection

Contract Spine v1 adds `repository_projection` with exact Rust/Python/TypeScript validation.

The projection records:

- Origins repository ID;
- owning Origins Workspace ID;
- canonical worktree root;
- canonical Git directory;
- canonical Git common directory;
- exact HEAD object ID when one exists;
- full symbolic HEAD ref when one exists;
- short branch name when attached to a local branch;
- detached state;
- dirty state;
- staged, unstaged, and untracked counts;
- observation timestamp.

An initialized repository with no commit may have an empty HEAD object ID while still carrying its symbolic branch ref.

## Durable repository store

Repository projections are stored in an Origins-owned SQLite extension table keyed by `repository_id` and unique `(workspace_id, canonical_root)` identity.

The repository extension has its own schema-generation key so the existing core SQLite schema version does not pretend unrelated table additions are invisible.

Opening the same canonical root in the same Workspace refreshes the existing Repository rather than creating duplicate identities.

## Read-first Git execution

Repository inspection uses a dedicated deterministic Git reader, not a shell string and not CodeOps mutation logic.

The reader:

- accepts only paths beneath configured `ORIGINS_WORKSPACE_ROOTS`;
- resolves the actual Git worktree root;
- rechecks that root against the authorized path set;
- invokes Git directly with argv, no shell;
- disables optional Git locks for read-only observation;
- captures bounded command output;
- does not expose Origins credentials to Git;
- does not run Git mutation commands in this generation.

## Status truth

Origins derives staged, unstaged, and untracked counts from Git porcelain output and records only counts in the durable repository projection.

CodeOps may perform richer repository analysis independently, but Origins' displayed mechanical repository state must come from refreshed Git evidence, not from a model summary.

## Diff evidence

Authenticated diff reads are derived from the current repository identity and produce separate staged and unstaged evidence.

Each diff side records:

- retained text/bytes up to the requested bound;
- complete observed byte count;
- SHA-256 of the complete observed diff stream;
- truncation flag;
- HEAD revision used for correlation.

Diff commands disable external diff/text conversion and do not mutate the repository.

The bounded diff response is a view/evidence projection, not a second source repository or CodeOps patch plan.

## API surface

```text
POST /v1/repositories
GET  /v1/repositories
GET  /v1/repositories/{repository_id}
POST /v1/repositories/{repository_id}/refresh
GET  /v1/repositories/{repository_id}/diff?max_bytes=<n>
```

All require local authentication.

## Capability registry

Origins advertises read-only capabilities only:

```text
origins.repository.inspect
origins.repository.diff
```

No repository mutation capability is introduced in this slice.

## CodeOps integration boundary

Recovered CodeOps authority already provides repository recovery/analysis, bounded patching, controlled apply, proof discovery, rollback, cross-repository work, and Sergeant handoff through its CLI/JSON surfaces.

Origins therefore supplies CodeOps with repository IDs, canonical roots, exact revisions, status observations, Sessions, and evidence references. It must not copy the CodeOps orchestrator into Origins.

## Proof requirements

Before promotion the exact head must prove:

1. opening a Git repository from a nested path resolves one canonical worktree identity;
2. repeated open in the same Workspace refreshes rather than duplicates;
3. a path outside `ORIGINS_WORKSPACE_ROOTS` is rejected;
4. non-Git directories are rejected cleanly;
5. clean repository projection records exact HEAD/ref/branch state;
6. staged, unstaged, and untracked counts match real Git state;
7. detached HEAD is represented truthfully;
8. linked-worktree Git/common directory identity is preserved when supported by hosted Git;
9. bounded staged/unstaged diffs return complete-stream counts/SHA plus truncation truth;
10. external diff/text conversion cannot replace the deterministic diff path;
11. Repository projections survive daemon restart;
12. Repository projection tampering fails closed;
13. no repository mutation command is exposed;
14. all ADR-0002 through ADR-0005 and three-language Contract Spine proofs remain green.

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
