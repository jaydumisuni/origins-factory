# Origins Factory — Integration Recovery Matrix

**Status:** FROZEN implementation input for Contract Spine v1
**Branch:** `impl/contract-spine-v1`
**Architecture authority:** `docs/ORIGINS_FACTORY_PRODUCT_PLAN.md`

## Purpose

This matrix records only interfaces recovered from owning repositories. It prevents Origins from rebuilding capabilities that already exist, inventing APIs from memory, or confusing product ownership with integration convenience.

`VERIFIED` means a callable or typed surface was recovered from current repository evidence. `PARTIAL` means the ownership boundary is clear but the production mount still needs an adapter or exact current route recovery. `DEFERRED` means the architecture may target the contract but runtime use is not authorized.

## Matrix

| Capability | Owner | Recovered callable/typed surface | Truth owned by | Origins integration | Status |
|---|---|---|---|---|---|
| Hunter intelligence | `jaydumisuni/hunter` | Existing Hunter runtime/API is the intelligence authority; exact current production client contract still requires a focused mount recovery because the repository has evolved independently | Hunter | Python intelligence adapter; Origins never stores a second Hunter brain | PARTIAL |
| AgentOps lifecycle | `jaydumisuni/Hunter-AgentOps` | `CodeOpsOperationPacket`; `run_route`; `run_apply_plan`; `run_sergeant_packet`; approval enum and evidence-return adapter in `hunter_agentops/code_ops_switcher_runner.py` | AgentOps | Python adapter; Origins binds and projects Operation IDs, approvals, blockers and results | VERIFIED foundation / production lifecycle wiring pending |
| CodeOps engineering | `jaydumisuni/hunter-codeops` | `hunter-codeops-code`; `hunter-codeops-ui`; `hunter-codeops-switcher route|bridge|apply-plan|sergeant-command|ingest-sergeant`; structured JSON evidence | CodeOps for coding work, AgentOps for lifecycle | Python worker adapter + native workspace/process supervision | VERIFIED |
| Sergeant assurance | `jaydumisuni/Sergeant` | `sergeant review`, `pr-review`, `app-review`, `v2-mission`, `proof-suite`, `final-proof`, `verify-standard`, `battle-tests`; verdicts `PASS`, `NEEDS WORK`, `BLOCK` | Sergeant | Independent review provider; Origins may display but not rewrite verdicts | VERIFIED |
| Oracle browser | `jaydumisuni/Oracle-` | HTTP routes `/api/browser/status`, `/start`, `/stop`, `/control`, `/snapshot`, `/screenshot`, `/action`; private MCP; retained browser session and authority modes | Oracle | Browser session projection and control adapter | VERIFIED |
| Oracle OS control | `jaydumisuni/Oracle-` + future reviewed Node work | Architecture accepted; current repository proves browser control, not yet the complete cross-platform OS-control/remote-session agent | Oracle | Keep behind capability manifest until Node Agent contract is implemented | PARTIAL |
| Lumi download control | `jaydumisuni/Lumi-DM` | Loopback API at `127.0.0.1:7000`; `/api/v4/security/me`, `/api/settings`, `/api/v3/media/info`, `/api/v5/browser/capture`, `/api/v5/browser/handoffs/{id}`, `/api/v5/desktop/command`; browser handoff IDs | Lumi | Origins/Oracle hand downloads to Lumi and project returned handoff/task state | VERIFIED |
| Device X-Ray | `jaydumisuni/TTG-Device-X-Ray` | `ttg-xray doctor`; `ttg-xray scan --output`; sealed evidence bundle, manifests, certification, profile match and read-only helper contracts | X-Ray | Device evidence provider before and after specialist execution | VERIFIED |
| Huawei shared contracts | `jaydumisuni/TECHGUYTOOL-Huawei` | 17 frozen Python/Rust contract types; canonical JSON; SHA-256 identity; fail-closed registry and context validation | Huawei specialist architecture | Donor for Origins canonicalization and cross-language equivalence, not copied domain policy | VERIFIED |
| Huawei persistent Gateway | `jaydumisuni/TECHGUYTOOL-Huawei` | Loopback `127.0.0.1:49321`; UTF-8 JSON request/response per line; SQLite state; snapshots; journal; recovery; reconnect-safe Python client | Huawei Gateway | Specialist session adapter; Origins remains a client | VERIFIED device-inert control plane |
| Software Builder | `jaydumisuni/thetechguy-software-builder` | Repository history proves branded build hardening, primary-artifact validation, installer enforcement, completion hardening and packaging ownership; exact public CLI/API contract must be recovered before mounting | Software Builder | Later productization/release adapter; no packaging logic duplicated in Origins | PARTIAL |
| Ptah | `jaydumisuni/ptah-roadmap-`, `jaydumisuni/Ptah-space` | Frozen vocabulary and roadmap: Workspace, Activity, Operation, Attempt, Objects/Revisions/Views/Artifacts, Nodes, Providers, Grants/Leases/Fences/Receipts/Evidence | Ptah after authorization | Origins designs compatible IDs/bindings but does not call a runtime yet | DEFERRED — runtime not authorized |

## Cross-cutting donor evidence

### Huawei contract theorem

Origins adopts the proven cross-language rules from Huawei Phase 2:

- UTF-8 JSON;
- object keys sorted lexicographically;
- no insignificant whitespace;
- array order preserved;
- integers only; floating point rejected;
- deterministic SHA-256 over canonical UTF-8 bytes;
- unknown fields rejected for authority contracts;
- schema and registry versions explicit;
- Python and Rust must produce identical canonical bytes and digests.

Origins does **not** copy Huawei device contract types into its own generic registry. It borrows the theorem and validation discipline.

### Persistent-runtime theorem

Huawei Phase 3 proves that the UI can be disposable while work remains durable:

```text
UI closes
→ persistent Rust control plane remains alive
→ durable state and journal remain authoritative
→ a new client reconnects
```

Origins generalizes this pattern to repository terminals, processes, capability sessions and workspace projections.

### Assurance theorem

Sergeant proves that implementation and review must remain independent. A CodeOps result does not become completion until the configured assurance path returns an accepted result and AgentOps records the lifecycle outcome.

## Missing interfaces that must not be guessed

1. Current production Hunter client/API contract and auth boundary.
2. Final AgentOps persistent operation backend and production lifecycle call surface.
3. Oracle cross-platform Node Agent / remote-session protocol.
4. Software Builder's current stable machine-callable packaging contract.
5. Ptah runtime API until explicit runtime authorization closes.

These gaps are integration work, not permission to create competing engines in Origins.

## First implementation consequences

The first runnable Origins vertical slice may safely use:

- Origins-owned contract/reference types;
- local Rust process/session supervision;
- AgentOps CodeOps runner contract;
- CodeOps CLI/JSON surfaces;
- Sergeant CLI/JSON result ingestion;
- Git repository state;
- deterministic evidence references.

It must not block on Oracle OS control, Software Builder packaging, physical-device writes or Ptah runtime.
