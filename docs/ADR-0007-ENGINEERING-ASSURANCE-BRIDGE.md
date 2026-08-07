# ADR-0007 — Engineering Assurance Bridge v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0006
**External authorities recovered:** `jaydumisuni/Hunter-AgentOps`, `jaydumisuni/hunter-codeops`, `jaydumisuni/Sergeant`

## Purpose

Mount the first semantic engineering + independent-assurance loop into Origins without copying AgentOps lifecycle, CodeOps engineering, or Sergeant review authority.

The bridge connects the already-proven Origins mechanical substrate to the current owning contracts:

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

This is the first Origins integration slice where semantic work and assurance cross the native mechanical substrate.

## Recovered authority

### AgentOps

Current `hunter_agentops.code_ops_switcher_runner` proves:

- `CodeOpsOperationPacket` owns `operation_id`, task, workspace, files, plan, apply intent, and approval state;
- unsafe operation file escapes are rejected by the owning packet;
- applying a plan requires `ApprovalState.APPROVED`;
- AgentOps owns operation state, approval, evidence transport, loop control, and completion;
- production lifecycle/audit backend wiring is still explicitly pending in AgentOps.

Origins therefore must not create a competing semantic operation database and must not claim AgentOps completion persistence in this generation.

### CodeOps

Current CodeOps CLI exposes machine-facing JSON commands:

- `route`;
- `apply-plan`;
- `sergeant-command`;
- `ingest-sergeant`.

Current SRG contracts define CodeOps as builder/router/patch/proof/correction authority while Sergeant remains independent. Canonical review actions are:

```text
PASS       → complete candidate / verified evidence
NEEDS WORK → correct / failed verification
BLOCK      → block / failed verification
UNKNOWN    → unresolved / partial evidence
```

Origins must not replace this mapping with substring parsing or its own reviewer semantics.

### Sergeant

Sergeant remains model-free by default and independently returns canonical:

```text
PASS
NEEDS WORK
BLOCK
```

Sergeant does not auto-modify or auto-merge project code. Optional model support is not required for this bridge.

## Runtime boundary

The bridge lives in the Origins Python plane.

It may:

- recover an Origins Repository projection through authenticated originsd HTTP;
- construct/validate the owning AgentOps `CodeOpsOperationPacket` when the AgentOps package is installed;
- submit CodeOps and Sergeant executables through `origins.process.run` only;
- wait for durable Origins Sessions and read their retained output through originsd;
- use CodeOps' owning Sergeant result-ingestion function in-process for semantic normalization;
- return a structured attempt result to AgentOps/Hunter.

It may not:

- use Python `subprocess` for CodeOps or Sergeant mechanical execution;
- edit project files directly;
- create a second Git execution path;
- invent AgentOps approval/completion state;
- parse a Sergeant verdict with Origins-owned substring rules;
- mark PASS as AgentOps-complete by itself.

## Restart honesty

AgentOps' production persistent lifecycle wiring is not yet accepted in its owning repository. Therefore Engineering Assurance Bridge v1 is restart-honest:

- Origins mechanical Sessions/Repository evidence remain durable;
- the bridge returns operation ID + mechanical Session IDs + normalized review result to AgentOps;
- Origins does not claim durable semantic loop resumption from its own database;
- full semantic resume waits for the owning AgentOps lifecycle backend or a later accepted contract from that repository.

No shadow operation store is introduced merely to make the demo look persistent.

## Attempt model

One bridge call is one bounded engineering attempt.

Input references:

- AgentOps `operation_id`;
- Origins `repository_id`;
- task;
- CodeOps config path;
- optional relative changed-file list;
- optional relative CodeOps edit-plan path;
- apply intent + AgentOps approval state;
- CodeOps route settings.

Output contains:

- operation ID;
- Repository ID and exact repository projection revision observed before work;
- CodeOps route Session/result;
- optional CodeOps dry-run/apply Session/result;
- Sergeant-command Session/result;
- Sergeant review Session/result digest;
- CodeOps-normalized verdict, `needs_loop`, `blocked`, and summary;
- recommended AgentOps action: `complete_candidate`, `correct`, `block`, or `unresolved`.

The action is advice to the AgentOps lifecycle owner, not Origins completion authority.

## Correction loop

A full loop is repeated bounded attempts under the same AgentOps operation ID:

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

A `BLOCK` never silently enters correction. `UNKNOWN` never becomes PASS.

## Plan and path rules

Origins adds no new file mutation engine.

For v1:

- changed files must remain relative and are validated by AgentOps' owning packet;
- optional plan path must be relative to the Repository worktree and must not contain parent/root/drive escape semantics;
- `apply-plan` is never sent with `--apply` unless AgentOps approval is `approved`;
- route-only and dry-run paths do not imply mutation approval;
- provider execution is outside this first bridge slice; this avoids silently bypassing paid/external-provider approval policy.

## Mechanical command routing

All CodeOps/Sergeant processes are submitted as typed Origins command envelopes against the durable Repository worktree:

```text
hunter-codeops-switcher ...
sergeant ...
```

They therefore inherit originsd's current mechanical controls:

- executable allowlist;
- argv rather than shell strings;
- authorized Workspace root;
- bounded Session output;
- durable Session identity;
- cancellation/observation;
- exact command replay binding;
- no generic Git path.

## External package mount

Production mode dynamically imports the current owning packages:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

Missing or incompatible owning packages fail closed with an explicit integration-unavailable error.

Origins does not vendor copies of these authorities.

CI may use protocol fixtures to prove the Origins bridge independently of private-repository installation. Such fixture proof demonstrates Origins routing/loop behavior only; it must not be reported as live production AgentOps/CodeOps/Sergeant package proof.

## Proof requirements

Before promotion the exact head must prove:

1. no Python subprocess use in the Origins engineering bridge;
2. Repository identity/worktree comes from originsd, not caller-supplied mechanical truth;
3. AgentOps packet validation is invoked through the owning adapter interface;
4. unsafe relative plan paths fail before mechanical execution;
5. unapproved apply intent fails before mechanical execution;
6. CodeOps route command executes only through an originsd Session;
7. CodeOps `sergeant-command` executes only through an originsd Session;
8. returned Sergeant command is constrained to the expected `sergeant` executable and Repository worktree;
9. Sergeant review executes only through originsd;
10. review output digest is preserved;
11. verdict normalization is delegated to the CodeOps ingest interface;
12. `PASS`, `NEEDS WORK`, `BLOCK`, and `UNKNOWN` map to distinct AgentOps recommendations without promotion by substring;
13. a two-attempt fixture proves `NEEDS WORK → correction → fresh PASS` while keeping the same external operation ID and distinct mechanical Sessions;
14. plan apply is absent without approved AgentOps state;
15. all ADR-0002 through ADR-0006 Origins runtime/contract proofs remain green;
16. documentation never claims the AgentOps production lifecycle backend is already mounted.

## Explicit non-claims

This generation does not provide or claim:

- production AgentOps persistent lifecycle/completion backend;
- autonomous approval;
- provider/model execution through paid/external routes;
- Origins-owned patch planning or file mutation;
- Origins-owned Sergeant verdict semantics;
- automatic AgentOps completion after PASS;
- semantic loop restart recovery before AgentOps persistence exists;
- React engineering UI;
- PTY interaction.
