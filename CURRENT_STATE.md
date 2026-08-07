# Origins Factory — Current State

**Recorded:** 2026-08-07
**Architecture version:** 1.0.0 — accepted product and architecture authority
**Implementation status:** Mechanical foundation through Repository/Git proven; Engineering Assurance Bridge protocol-proven; production-mount doctor proven; Live Engineering Mount mechanism proven with non-promoting fixtures; actual target-host live-owner receipt still pending

## Contribution status

Current work contributes **New implementation + Correction + Verification**.

Origins Factory is not yet the complete workspace. The accepted foundation now provides cross-language contracts, persistent Rust mechanical state, bounded process execution, active control, reconnectable observation, read-first Repository/Git truth, an AgentOps/CodeOps/Sergeant assurance bridge, a production compatibility doctor, and a controlled live-owner smoke path with integrity-addressed receipts.

## Proven implementation sequence

1. **Contract Spine v1.2** — Rust/Python/TypeScript canonical contracts and exact equivalence.
2. **originsd persistence foundation** — loopback auth, SQLite durability, Workspace/capability state, hash-chained journal, tamper detection, restart recovery.
3. **Supervised Process Sessions v1** — bounded argv execution, durable Sessions, environment/root policy, replay binding, output evidence.
4. **Active Session Control v1** — async acceptance, running-session cancellation, durable event replay.
5. **Live Session Observation v1** — one-copy retained output, byte/event cursors, authenticated SSE projections.
6. **Repository/Git Sessions v1** — read-first durable Repository identity, HEAD/worktree/status/diff evidence, no generic Git mutation path.
7. **Engineering Assurance Bridge v1** — AgentOps-gated CodeOps work and independent Sergeant review through originsd; protocol-proven.
8. **Production Engineering Mount v1 doctor** — compatible/missing/available classification for current AgentOps/CodeOps Python contracts and CodeOps/Sergeant CLI surfaces.
9. **Live Engineering Mount v1** — doctor-gated read-only owner-stack smoke, internal proof scopes, fresh Repository observation, bounded receipt and canonical receipt SHA-256.

## Engineering ownership lock

Production dynamic imports remain:

```text
hunter_agentops.code_ops_switcher_runner
hunter_codeops.code_ops_sergeant_ingest
```

Mechanical flow remains:

```text
AgentOps packet / approval
→ fresh Origins Repository projection
→ CodeOps command
→ originsd Session
→ CodeOps Sergeant-command
→ originsd Sergeant Session
→ CodeOps verdict ingestion
→ recommendation back to AgentOps
```

Exact recommendations remain:

```text
PASS       → complete_candidate
NEEDS WORK → correct
BLOCK      → block
UNKNOWN    → unresolved
```

`complete_candidate` is advice to AgentOps, not Origins completion authority.

## Fresh Repository rule

The doctor and Engineering Assurance Bridge no longer trust only the last stored Repository projection. They recover the durable Workspace/worktree identity, run the dedicated Repository inspect surface, require the same Repository ID, and bind the current revision/HEAD to the attempt/receipt.

## Production Engineering Mount doctor

Observed current owner identities remain compatibility observations rather than eternal version locks:

```text
hunter-agentops       0.3.0
hunter-codeops        0.3.0
sergeant-reviewer     0.4.1
hunter-codeops-switcher
sergeant
```

Required surfaces:

```text
agentops_python
codeops_python
codeops_cli
sergeant_cli
```

Status semantics:

```text
missing    → owner cannot be found or started
available  → present but required contract behavior is not compatible
compatible → required non-mutating behavior passes
proven     → reserved for a successful actual live-owner smoke receipt
```

The doctor never self-installs or repairs an owner and can never promote itself to `proven`.

## Live Engineering Mount v1

The smoke is read-only with respect to project engineering:

- doctor must report every required surface `compatible`;
- production construction is the only path to internal `live_owner` scope;
- fixture construction is permanently non-promoting;
- CodeOps config may be an external integration path;
- edit plans/files remain Repository-scoped;
- no edit plan is used by smoke;
- `apply_plan=false`;
- no provider/model execution;
- all CodeOps/Sergeant processes remain originsd Sessions;
- Sergeant normalization remains owned by CodeOps;
- `UNKNOWN` cannot prove the mount.

The compact receipt records proof scope, Repository revision/HEAD, operation/Session IDs, doctor evidence, review SHA, canonical project verdict, recommended AgentOps action, and a canonical receipt SHA-256. It excludes raw config, raw review output, provider credentials, and process bodies.

CI fixture proof demonstrates the routing/proof theorem on real originsd. It **does not** prove that the user's actual target host currently has compatible owner packages/binaries.

## Current authenticated originsd routes

```text
GET  /v1/health
GET  /v1/capabilities
POST /v1/workspaces
GET  /v1/workspaces/{workspace_id}
POST /v1/repositories/inspect
GET  /v1/repositories?workspace_id=<workspace_id>
GET  /v1/repositories/{repository_id}
GET  /v1/repositories/{repository_id}/diff?kind=staged|unstaged&limit=<bytes>
POST /v1/commands
GET  /v1/events
GET  /v1/events/live
GET  /v1/sessions
GET  /v1/sessions/{session_id}
GET  /v1/sessions/{session_id}/output
GET  /v1/sessions/{session_id}/output/delta
GET  /v1/sessions/{session_id}/output/live
POST /v1/sessions/{session_id}/cancel
```

## Proof state

The fully integrated pre-freeze implementation head `8fa5e096e81fa70226ccc65b30dd7d9a1638aad6` passed both required suites:

- **Origins Contract Spine** — success;
- **Origins Daemon Foundation** — success.

The runtime gate now explicitly executes `tools/prove_live_engineering_mount.py`; the live-mount proof is not merely present in the repository.

The same gate proved every earlier hosted runtime slice, the Production Engineering Mount doctor, Live Engineering Mount hosted smoke, and repository whitespace.

The strengthened missing-Sergeant proofs preserve system Git while excluding Sergeant so Repository freshness remains valid. No proof disables a required mechanical authority to simulate an owner gap.

This state/handoff freeze is documentation-only after the green implementation head. PR promotion still requires both suites to remain green on the final documentation-adjusted head.

## Canonical repository authority

Recovery order:

1. `AI_HANDOFF.md`;
2. this `CURRENT_STATE.md`;
3. `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`;
4. implementation ADRs, current source, PRs, and proof;
5. owning repositories for mounted capabilities.

Implementation ADRs now run through `docs/ADR-0009-LIVE-ENGINEERING-MOUNT.md`.

The exploratory `build/initial-workspace` branch remains non-authoritative.

## Explicit current limitations

Not production-proven yet:

- actual target-host AgentOps/CodeOps Python package installation/compatibility;
- actual target-host `hunter-codeops-switcher` / `sergeant` CLI compatibility;
- an actual `live_owner` smoke receipt from that host;
- AgentOps production persistent lifecycle/audit/completion backend;
- semantic restart recovery owned by AgentOps;
- provider/model execution through the engineering bridge;
- production Hunter mount;
- PTY/interactive terminal Sessions, stdin, resize, or process reattachment;
- stronger OS-level resource isolation;
- React Workspace shell;
- Oracle/Lumi/specialist Gateway clients;
- Ptah runtime integration;
- Windows/Linux desktop package/release proof.

## Next valid work

Do not block Origins development on a target host that is not connected to this build environment, and do not fake that host proof.

1. when a controlled Origins host with the actual owner stack is available, run the production live-mount smoke and retain its receipt;
2. in parallel, recover and freeze Hunter's current production client/API/session/auth boundary;
3. build the thinnest model-optional Hunter intelligence mount over the existing Origins/AgentOps mechanical foundation without copying Hunter's controller;
4. keep broad React Workspace work behind the same durable projections rather than making the UI the runtime;
5. preserve the option to prioritize PTY or UI only if evidence from the Hunter mount requires it.

## Blocking rule

Do not let UI, Python workers, models, CodeOps, Hunter, or external adapters bypass originsd or specialist authority because direct subprocess/network access would be easier. Mechanical truth and independent assurance are product boundaries, not implementation decoration.
