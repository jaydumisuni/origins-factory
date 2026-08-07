# ADR-0007 — Engineering Assurance Bridge v1

**Status:** FROZEN — protocol bridge mechanically proven; live private-package mount pending
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0006
**External authorities recovered:** `jaydumisuni/Hunter-AgentOps`, `jaydumisuni/hunter-codeops`, `jaydumisuni/Sergeant`

## Purpose

Mount the first semantic engineering + independent-assurance loop into Origins without copying AgentOps lifecycle, CodeOps engineering, or Sergeant review authority.

```text
AgentOps operation packet / approval
→ Origins Repository identity
→ CodeOps route / plan command
→ originsd mechanical Session
→ CodeOps Sergeant command packet
→ originsd mechanical Sergeant Session
→ CodeOps canonical Sergeant-result ingestion
→ exact action returned to AgentOps
```

This is the first Origins integration slice where semantic engineering work and independent assurance cross the native mechanical substrate.

## Recovered authority

### AgentOps

Current `hunter_agentops.code_ops_switcher_runner` proves:

- `CodeOpsOperationPacket` owns `operation_id`, task, workspace, files, plan, apply intent, and approval state;
- unsafe operation file escapes are rejected by the owning packet;
- applying a plan requires `ApprovalState.APPROVED`;
- AgentOps owns operation state, approval, evidence transport, loop control, and completion;
- production lifecycle/audit backend wiring is still explicitly pending in AgentOps.

Origins therefore does not create a competing semantic operation database and does not claim AgentOps completion persistence in this generation.

### CodeOps

Current CodeOps machine-facing interfaces expose:

- `route`;
- `apply-plan`;
- `sergeant-command`;
- `ingest-sergeant`.

Current CodeOps SRG contracts keep CodeOps as builder/router/patch/proof/correction authority while Sergeant remains independent. Canonical review routing is:

```text
PASS       → complete candidate
NEEDS WORK → correct
BLOCK      → block
UNKNOWN    → unresolved
```

Origins does not replace CodeOps' verdict ingestion with substring parsing or its own review semantics.

### Sergeant

Sergeant remains model-free by default and independently returns canonical:

```text
PASS
NEEDS WORK
BLOCK
```

Sergeant does not auto-modify or auto-merge project code. Optional model support is not required by this bridge.

## Runtime boundary

The bridge lives in the Origins Python plane.

It may:

- recover an Origins Repository projection through authenticated originsd HTTP;
- construct/validate the owning AgentOps `CodeOpsOperationPacket` when the AgentOps package is installed;
- submit CodeOps and Sergeant executables through `origins.process.run` only;
- wait for durable Origins Sessions and read retained output through originsd;
- use CodeOps' owning Sergeant result-ingestion function in-process for semantic normalization;
- return a structured attempt result to AgentOps/Hunter.

It may not:

- use Python `subprocess` for CodeOps or Sergeant mechanical execution;
- edit project files directly;
- create a second Git execution path;
- invent AgentOps approval/completion state;
- parse a Sergeant verdict with Origins-owned substring rules;
- mark PASS as AgentOps-complete by itself.

## External package mount

Production mode dynamically imports exactly:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

It expects the owning `ApprovalState`, `CodeOpsOperationPacket`, and `ingest_sergeant_result_text` interfaces. Missing or incompatible owning packages fail closed with `IntegrationUnavailable`.

Origins does not vendor copies of these authorities.

The production loader itself is unit-proven to target those exact module names. **The current CI does not install or execute the user's private AgentOps/CodeOps packages, so live production-package compatibility is not yet claimed.**

## Restart honesty

AgentOps' production persistent lifecycle wiring is not yet accepted in its owning repository. Therefore Engineering Assurance Bridge v1 is restart-honest:

- Origins Repository and mechanical Session evidence remain durable;
- the bridge returns operation ID, Session IDs, review digest, normalized verdict, and recommended action;
- Origins does not claim durable semantic loop resumption from its own database;
- full semantic resume waits for the owning AgentOps lifecycle backend or a later accepted AgentOps contract.

No shadow operation store is introduced merely to simulate persistence.

## Attempt model

One bridge call is one bounded engineering Attempt.

Input references include:

- AgentOps `operation_id`;
- Origins `repository_id`;
- task;
- CodeOps config path;
- optional relative changed-file list;
- optional relative CodeOps edit-plan path;
- apply intent + AgentOps approval state;
- CodeOps route settings.

Output includes:

- operation ID;
- Repository ID and observed repository projection revision/HEAD;
- CodeOps route Session/result;
- optional CodeOps dry-run/apply Session/result;
- Sergeant-command Session/result;
- Sergeant review Session and stdout SHA-256;
- CodeOps-normalized verdict, `needs_loop`, `blocked`, and summary;
- recommended AgentOps action: `complete_candidate`, `correct`, `block`, or `unresolved`.

The recommendation is advice to the AgentOps lifecycle owner, not Origins completion authority.

## Correction loop

A full loop is repeated bounded Attempts under the same AgentOps operation ID:

```text
Attempt 1
→ CodeOps work
→ Sergeant NEEDS WORK
→ bridge returns action=correct
→ AgentOps decides/approves next correction Attempt

Attempt 2
→ CodeOps correction
→ fresh Sergeant review
→ PASS
→ bridge returns action=complete_candidate
→ AgentOps decides completion
```

`BLOCK` does not silently enter correction. `UNKNOWN` does not become PASS.

## Plan and path rules

Origins adds no new file mutation engine.

For v1:

- changed files remain relative and are validated by the AgentOps packet interface;
- config and optional plan paths must remain relative to the Repository worktree and reject parent/root/drive escape semantics;
- `apply-plan --apply` is never submitted unless AgentOps packet validation accepts the approved apply intent;
- route-only and dry-run paths do not imply mutation approval;
- provider execution is outside this first bridge slice, avoiding unreviewed paid/external-provider policy bypass.

## Mechanical command routing

All CodeOps/Sergeant processes are submitted as typed Origins command envelopes against the durable Repository worktree:

```text
hunter-codeops-switcher ...
sergeant ...
```

They therefore inherit originsd controls: executable allowlist, argv rather than shell strings, authorized Workspace root, bounded output, durable Session identity, cancellation/observation, exact replay binding, and no generic Git path.

The CodeOps-produced Sergeant argv is constrained before execution to the recovered contract:

```text
sergeant app-review <repository-worktree> --mode <review-mode> [--files <exact-scope>] [--pretty]
```

A changed executable, worktree, file scope, or unsupported flag fails before Sergeant execution.

Sergeant semantic ingestion requires a successful, non-truncated mechanical Session so incomplete review output cannot be normalized as a verdict.

## Protocol-fixture proof boundary

CI uses protocol fixtures for the private AgentOps/CodeOps package surfaces. The fixture proof demonstrates the **Origins bridge routing, approval, mechanical Session, evidence, and loop behavior** independently of private-package installation.

It does not prove that the private packages are installed on a target machine, that their current executable packaging is available there, or that AgentOps' production lifecycle backend exists.

## Challenge evidence

The challenged exact candidate passed:

1. Python bridge source contains no Python `subprocess` import/use;
2. unsafe config/plan paths are rejected;
3. exact AgentOps/CodeOps production import module names are pinned by test;
4. canonical review recommendation map is exact and non-promoting;
5. CodeOps-produced Sergeant command shape is constrained before execution;
6. all CodeOps and Sergeant fixture processes execute through real durable `originsd` Sessions;
7. a real Origins Workspace + Repository projection anchors the hosted proof;
8. Attempt 1 returns canonical `NEEDS WORK` and recommendation `correct`;
9. review stdout SHA-256 matches the durable Session evidence;
10. the compact bridge evidence record keeps normalized verdict/IDs/digests without duplicating raw review summary/output;
11. unapproved `apply_plan=True` is rejected by the AgentOps adapter before any new mechanical Session is created;
12. unsafe plan escape is rejected before mechanical execution;
13. Attempt 2 uses the same external AgentOps operation ID but distinct CodeOps dry-run/apply/review Sessions;
14. approved correction mutates only through the CodeOps fixture command routed by originsd;
15. a fresh independent review returns canonical `PASS` and recommendation `complete_candidate`;
16. separate fixture states prove `BLOCK → block` and ambiguous/noncanonical review text → `UNKNOWN → unresolved`;
17. raw corrected file content and Origins token do not enter the permanent journal;
18. all Sessions in the hosted loop are mechanical `origins.process.run` Sessions;
19. every inherited ADR-0002 through ADR-0006 runtime proof remains green;
20. Contract Spine Python/TypeScript/Rust tests, exact three-runtime equivalence, Clippy, Rust tests/build, whitespace, and rustfmt remain green.

The first hosted bridge challenge failed because the **proof contained a contradictory assertion**: it simultaneously prohibited `NEEDS WORK` from the compact evidence record and required the normalized verdict field to equal `NEEDS WORK`. Only the proof was corrected. The actual sanitation rule is that raw review summary/output is not duplicated; the normalized canonical verdict is retained.

After that correction and an additional ownership-loader test, both the Origins Daemon Foundation and Contract Spine suites passed on exact head `8906cf184c57d7c4e0e1fbffcbf1f87350518c0f`.

## Explicit non-claims

This generation does not provide or claim:

- live production installation/compatibility proof of the private AgentOps/CodeOps Python packages or their CLIs;
- production AgentOps persistent lifecycle/completion backend;
- autonomous approval;
- provider/model execution through paid/external routes;
- Origins-owned patch planning or file mutation;
- Origins-owned Sergeant verdict semantics;
- automatic AgentOps completion after PASS;
- semantic loop restart recovery before AgentOps persistence exists;
- production Hunter mount;
- React engineering UI;
- PTY interaction.
