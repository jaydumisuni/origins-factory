# Origins Factory — Phase 7 Capability Evolution Freeze

**Status:** SHIPPED / PROVEN  
**Phase:** 7 — Capability evolution  
**PR:** #19  
**Frozen candidate:** `2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e`  
**Merge checkpoint:** `2f93f79f78502959fd09b50350b878ab659fee84`  
**Construction archive:** `archive/phase7-capability-evolution-construction`  
**Execution standard:** `ttg.tenfold.v1`

## Authority preserved

Phase 7 coordinates existing owners rather than absorbing them:

- **Hunter-AgentOps** owns durable approval truth and the external capability-upgrade Operation lifecycle.
- **Hunter CodeOps** owns bounded repository engineering and real candidate plan application.
- **Sergeant** owns the independent engineering verdict.
- **Origins/originsd** owns Workspace, Repository, Session, canary, Generation, rollback and Mission-resume mechanical truth.

Origins exposes no AgentOps approval-decision tool. The AgentOps MCP bearer credential authenticates the local service caller only and is explicitly **not** owner authorization.

## Gate semantics

Capability synthesis uses:

```text
owner_approval_required
```

The approval creates/permits an undispatched semantic capability-upgrade lifecycle. It does not itself execute CodeOps or activate runtime authority.

Isolated/reversible CodeOps candidate construction uses:

```text
review_required
candidate_only = true
runtime_authority_expansion = false
```

The exact engineering subject is stored in the durable Origins approval binding and is reused for execution; clients cannot reassert a changed subject after approval.

Promotion/rollback remains a separate Origins Generation decision after real CodeOps application, Sergeant review and canary evidence. Phase 7 grants no production/runtime authority expansion.

## Owner revisions used by exact-host proof

```text
Hunter-AgentOps
0eeb69027aec9d70303e724129ebf5585f373ca1

hunter-codeops
348f133cb72ab6d18a7959d4a954158f7b881068

Sergeant
22879a8c47df379d19fb8537c79b745750df4077
```

Exact-host proof used detached owner worktrees and provenance-aware disposable launchers so CodeOps and Sergeant execution came from those pinned source revisions rather than stale globally installed console scripts.

## Hosted frozen-SHA proof

All existing hosted Origins regression lanes passed against exact frozen candidate `2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e`:

```text
Origins Contract Spine              PASS
Origins Daemon Foundation           PASS
Stage-2 Authority Containment       PASS
Origins Phase 3 Workspace           PASS
Phase 4 Intelligence Plane          PASS
Phase 5 Oracle Lumi Applications    PASS
Phase 6 Device Read-Only Integration PASS
Phase 7 Capability Evolution        PASS
```

Phase 7 workflow run: `32014148821`.

## Independent adversarial Pass B

A separate proof branch was created directly from the frozen candidate:

```text
proof/phase7-adversarial-2a4489e
```

Its complete diff from the frozen source was exactly one tests-only file:

```text
python/tests/test_phase7_adversarial_pass.py
```

KRATOS result:

```text
12 passed in 0.10s
```

The adversarial matrix attacked:

- non-loopback / malformed AgentOps MCP endpoints;
- short service credentials and service-token-as-owner-authority confusion;
- client attempts to reassert approval IDs or engineering subjects at execution time;
- counterfeit capability approval evidence;
- engineering gate substitution;
- candidate-only/runtime-authority-expansion tampering;
- mutated external-operation approval bindings;
- replay of an approved engineering record against a changed subject.

All failed closed as required.

## Frozen exact-host proof

Oracle Live was used only as reviewed transport to KRATOS. The Origins proof itself executed against frozen candidate `2a4489e6a64c62a3db42dbbd4aab8fca3ea4560e` and the pinned owner worktrees above.

Oracle result record:

```text
jaydumisuni/Oracle-
oracle_control/live_results/0000-origins-phase7-freeze-proof-20260817-092326z.json
```

Result:

```text
PHASE7_LIVE_OWNER_MCP_OK
exitCode = 0
```

The exact-host proof established:

```text
agentops_transport = mcp/rpc
agentops_decision_tools_exposed_by_origins = false
capability_gate = owner_approval_required
engineering_gate = review_required
engineering_candidate_only = true
agentops_child_operation_undispatched = true
codeops_real_plan_applied = true
sergeant_promote_verdict = PASS
sergeant_rollback_verdict = PASS
canary_sessions_recovered = true
mission_resume_exact = true
runtime_authority_expansion = false
model_self_approval = false
production_credentials_used = false
strict = true
```

It proved both promotion and rollback paths, retained/recovered canary Sessions across originsd restart, preserved the exact pre-upgrade Mission resume token/state, and kept the rollback candidate inactive.

## Tenfold disposition

```text
Understand  PASS
Build       PASS
Review      PASS
Freeze      PASS
Prove       PASS
Ship        PASS
```

Phase 7 must not be reopened as unfinished capability-evolution work unless new reproducible evidence proves a regression.

## Next canonical phase

Per `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`:

```text
Phase 8 — Custom OS consumption and later Ptah
```

The immediate Phase-8 responsibility is to package/consume Origins in the custom OS as a pinned release without source duplication. Ptah runtime remains a later replacement boundary only where its Providers are separately authorised and proven.
