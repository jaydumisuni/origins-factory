# Origins Factory — Product and Implementation Authority

**Status:** Candidate product authority  
**Recovered authority:** Hunter architecture, TECHGUYTOOL Huawei `FULL_PLAN.md`, TTG Device Gateway, TTG Device X-Ray, AgentOps, CodeOps, Oracle, Lumi, Sergeant, and Ptah boundaries

## 1. Product definition

Origins Factory is the portable, conversation-first Hunter workspace for the THETECHGUY ecosystem.

It is intended to exceed the useful combined experience of VS Code, Cursor, Codex, and ChatGPT Work by joining persistent project context, repository engineering, model choice, parallel operations, browser work, downloads, applications, device evidence, real hardware, proof, and recovery in one workspace.

Origins Factory is not the custom operating system. It runs inside that future OS and also ships independently for Windows, Linux, and later macOS.

Origins Factory is also not the canonical runtime database for every system it displays. It is a client, workspace surface, and coordinator over existing authorities.

## 2. Primary experience

The owner normally opens Origins Factory and speaks to Hunter.

```text
Owner
  ↓
Origins Factory
  ↓
Hunter
  ↓
AgentOps Operation
  ↓
CodeOps / Oracle / Lumi / Sergeant / specialist Gateways / Nodes
```

Conversation remains central. Code, terminal, browser, downloads, applications, devices, evidence, storage, and recovery surfaces open when required.

## 3. Permanent authority boundaries

- **Hunter** — intelligence, conversation, memory, context recovery, planning, capability selection, routing, reconciliation, contradiction detection, and upgrade proposals.
- **Hunter AgentOps** — durable semantic Operation identity, attempts, approvals, blockers, evidence bindings, correction loops, resume state, and sanitation state.
- **Hunter CodeOps** — repository recovery, editing, build/test proof, correction, rollback, and engineering handoff.
- **Sergeant** — independent review and challenge.
- **Oracle** — browser and authorised operating-system vision/control sessions, remote view, human takeover, and file/control capability.
- **Lumi DM** — downloads, queues, resume, integrity verification, and download history.
- **TTG Device X-Ray and specialist X-Rays** — read-first device evidence, correlation, diagnosis, prediction, certification, verification, and sealed evidence.
- **Specialist Device Gateways** — persistent physical-device sessions, domain operation sessions, typed journal truth, provider/worker supervision, deterministic policy, leases, bounded execution, and crash recovery.
- **Ptah Space** — future general mechanical Workspace and execution substrate after its existing authorization gates close.
- **Specialist applications** — approved domain interfaces and deterministic domain behavior.

Origins Factory presents and coordinates these capabilities without duplicating their engines or canonical state.

## 4. Workspace and operation hierarchy

A general Origins Workspace binds references to:

- project purpose and instructions;
- canonical repositories and accepted documents;
- locked decisions and current status;
- conversations;
- AgentOps Operations and Attempts;
- models, providers, and Nodes;
- editor, terminal, browser, download, application, and device sessions;
- Artifacts, evidence, and recovery state.

The Workspace belongs to Hunter/AgentOps, not to one model. Changing providers must not lose project or Operation state.

For a specialist hardware operation, Origins must preserve the distinction between the broader semantic mission and the domain control plane:

```text
Hunter / AgentOps Operation
└── Specialist Gateway Operation Session
    ├── Physical Device Session
    ├── Endpoint Observations
    ├── X-Ray Device Evidence
    ├── pre-operation Device Twin
    ├── Decision Verdicts
    ├── Mode Lease
    ├── bounded Execution Lease
    ├── Executor Result
    ├── post-operation Device Twin
    ├── Verification Result
    ├── Recovery Plan
    ├── Artifact Manifests
    └── Knowledge Gaps and Learning Proposals
```

Origins links and displays these records. It does not flatten them into one invented database or substitute an AgentOps approval for a domain execution lease.

## 5. Engineering experience

Origins Factory must provide, directly or through mounted capabilities:

- repository explorer and search;
- code editor and diff review;
- Git status, branches, worktrees, and checkpoints;
- terminal and process sessions;
- build, lint, test, and proof output;
- model/provider selection and automatic routing;
- multiple bounded child Operations;
- browser research through Oracle;
- downloads through Lumi;
- application and device sessions;
- evidence and recovery views;
- interruption, reassignment, continuation, and cross-client resume.

It is not an editor with an AI sidebar. Hunter conversation and durable Operations coordinate the complete workspace.

## 6. Runtime composition

Rust and Python are both required, but exact framework and IPC choices remain unapproved until implementation review is complete.

### 6.1 Rust responsibilities

- native process and PTY supervision;
- filesystem and Git authority;
- local application discovery and launching;
- Node capability discovery;
- secure native IPC boundary;
- resource limits and cancellation;
- terminal, window, and local session attachment;
- high-performance event transport;
- reconnect-safe native session handling;
- specialist Gateway and later Ptah integration.

TECHGUYTOOL Huawei already proves important donor patterns: an always-running Rust Gateway, SQLite durable state, typed event bus, append-only hash-chained journal, worker supervision, crash recovery, loopback protocol, diagnostics, consistent snapshots, and UI reconnection.

Origins should reuse or generalize proven contracts and client patterns where authority permits. It must not copy Huawei-specific repair policy into a generic runtime.

### 6.2 Python responsibilities

- Hunter intelligence integration;
- AgentOps and CodeOps mounting;
- model/provider adapters;
- planning, reconciliation, and capability selection;
- repository and evidence intelligence;
- skills and specialist adapters;
- reconnect-safe clients for Rust control planes;
- capability-gap diagnosis and evolution proposals.

### 6.3 Workspace UI responsibilities

- Hunter conversation;
- Project Twin views;
- AgentOps Operations and Attempts;
- specialist Gateway operation views;
- editor, terminal, browser, Lumi, application, device, evidence, storage, and recovery surfaces;
- approval and takeover controls;
- cross-client status and notifications.

React, Tauri, Qt, Monaco, xterm, and the exact Rust–Python protocol remain candidate choices, not frozen decisions.

## 7. Huawei and X-Ray integration

TECHGUYTOOL Huawei is the first concrete authority demonstrating how Origins must handle real hardware work.

### 7.1 Recovery order

Before presenting or continuing a Huawei operation, Origins recovers in this order:

1. `TECHGUYTOOL-Huawei/FULL_PLAN.md` and current repository evidence;
2. the active specialist Gateway snapshot and journal, when available;
3. referenced Artifact Manifests and Recovery Plan;
4. the Google Drive Huawei plan mirror and case handovers for recovery context;
5. chat history only as non-authoritative context.

The P30 Pro `VOG-L29-recovery-chat-and-handoff-2026-07-30.txt` is a valuable recovery Artifact. It is not the normal live source of operation truth and must not override current repository, Gateway, or fresh X-Ray evidence.

### 7.2 Origins is a Gateway client

The Huawei UI is already defined as a client of the always-running TTG Device Gateway. Origins follows the same rule.

```text
Origins closes, crashes, or moves to another client
→ Huawei Gateway remains alive
→ physical-device identity remains pinned
→ endpoint observations remain journaled
→ operation stage remains known
→ X-Ray/provider state remains known
→ Origins reconnects to the same operation
```

Origins may open the approved Huawei QML application, embed an authorised session/view, or present a general operation summary. It does not replace the Huawei Gateway or redesign the approved domain UI without separate authority.

### 7.3 X-Ray is the read-first evidence provider

X-Ray does not own the persistent operation session. The specialist Gateway owns the session and accepts validated typed X-Ray contracts.

For device work:

1. the Gateway establishes or recovers the `PhysicalDeviceSession`;
2. transport changes are recorded as `EndpointObservation` records;
3. specialist X-Ray runs read-only on the Node carrying the physical device;
4. X-Ray publishes `DeviceEvidence` and a `pre_operation` `DeviceTwin`;
5. the Gateway validates producer, authority, session, expiry, and evidence hashes;
6. Origins displays the accepted evidence and contradictions;
7. deterministic governors decide whether a recipe stage is eligible;
8. only a valid bounded execution lease can reach an executor;
9. post-operation X-Ray publishes a new `DeviceTwin` and verification evidence;
10. Origins presents the before/after delta and current recovery state.

X-Ray remains strictly read-only. Origins, Hunter, AgentOps, models, and the UI cannot convert a profile match, recommendation, or certification into permission to write.

### 7.4 Device view

Origins displays views over accepted contracts and Gateway state:

- physical-session identity and continuity;
- candidate endpoints grouped into the same physical device;
- current transport and mode;
- identity, firmware, storage, partition, security, branding, and version evidence;
- evidence freshness and hashes;
- `certified`, `investigate`, or `unsafe` Device Twin status;
- selected profile and recipe candidates;
- blockers and deterministic decision verdicts;
- mode and execution lease state;
- raw executor result;
- pre/post/final Device Twin comparison;
- journal integrity and exact recovery action.

When multiple physical candidates exist, Origins preserves each candidate's evidence and respects the unsafe workstation-level state.

### 7.5 Hunter and model boundary

Hunter and models may:

- explain accepted evidence;
- compare repository, firmware, and device records;
- help the technician understand blockers;
- propose additional registered read-only probes;
- prepare implementation or capability-improvement work outside the active device authority path.

They may not:

- make the deterministic repair verdict;
- override a safety veto;
- issue a device execution lease;
- alter a sealed contract or journal;
- declare the device repaired because a command returned success;
- authorize premature reboot or restoration of stock Fastboot.

The Huawei plan explicitly records that GPT temporarily filled a missing reasoning role during investigation, but that role must become deterministic Decision Corps and Repair Governor software.

### 7.6 Inquiry and capability evolution

Huawei already defines the domain learning loop Origins should expose:

```text
X-Ray predicted outcome
vs
Executor raw result
vs
X-Ray post-operation evidence
```

Disagreement produces a typed `KnowledgeGap`, not a silent retry or prompt adjustment.

```text
observed
→ questioned
→ candidate
→ replay_supported
→ hardware_supported
→ specialist_approved
→ ttg_promoted
```

Origins surfaces the gap, linked evidence, requested read-only probes, replay results, hardware proof, review, and promotion state. The Inquiry Governor and specialist authority own the domain verdict. Origins does not auto-promote write targets, offsets, destructive recipes, or expanded authority.

This is the device-specific proof of the wider Hunter capability-evolution concept.

### 7.7 Recovery and handover

Origins can import or generate a portable device-case handover containing references to:

- canonical repository, branch, and commit;
- AgentOps Operation;
- specialist Gateway operation and physical session;
- journal digest;
- Recovery Plan and exact next action code;
- X-Ray contract IDs and Device Twin hashes;
- Artifact Manifests and custody locations;
- confirmed facts, unresolved contradictions, and blockers;
- approved continuation conditions.

The handover is a recovery projection over canonical records. It is not a second mutable operation database.

### 7.8 Remote Nodes

A Huawei device may remain physically connected to Athena, the custom-OS host, or another enrolled Windows/Linux Node. Specialist X-Ray and the Gateway-side worker run where physical access exists. Origins can reconnect from elsewhere and receive contract references, journal events, evidence views, and approval requests without copying uncontrolled device state between machines.

## 8. Oracle and Lumi relationship

Oracle discovers and interacts; Lumi downloads.

```text
Hunter request
→ Oracle locates and validates the source
→ Lumi accepts the download
→ Lumi resumes and verifies content
→ storage checks content identity
→ accepted Artifact is registered once
```

Oracle also provides authorised OS/file/application control and later remote-view or forwarding capabilities. Origins presents Oracle sessions without duplicating their execution truth.

## 9. Compute model

Origins Factory can coordinate local and remote resources:

- the current host;
- Athena for heavy builds, NVIDIA work, tests, Windows device tooling, and local models;
- VPS or rented workers;
- Cloudflare, Fireworks, and other approved providers;
- Windows, Linux, macOS, mini-PC, and GPU Nodes.

The HP 290 G4 can run the complete first system with 8 GB RAM because heavy compute may be routed elsewhere. Workspace and AgentOps identity remain stable while compute moves. Physical-device and domain operation identity remain with the specialist Gateway on the Node carrying the device.

## 10. Clean-core rules

- one canonical owner per durable fact;
- references preferred over copies;
- exact duplicate bytes stored once per authorised scope;
- AgentOps and specialist Gateway Operations remain distinct and linked;
- failed Attempts and executor results remain visible;
- temporary work is isolated by Workspace, Operation, and Attempt;
- accepted outputs are promoted explicitly;
- obsolete plans and generated material are removed during sanitation;
- completion requires proof and a clean sanitation result;
- no capability approves or activates its own upgrade;
- Drive handovers are recovery projections, not competing live truth.

## 11. First repository-engineering vertical slice

The first Origins implementation proof should use a real repository mission and demonstrate:

1. open a Workspace;
2. converse with Hunter;
3. recover canonical project authority;
4. create a durable AgentOps Operation;
5. open the repository and editor view;
6. invoke CodeOps through Python;
7. supervise terminal/process work through Rust;
8. use at least two approved model providers;
9. retain patches, proof, and failed Attempts;
10. run Sergeant review;
11. close and reopen Origins Factory;
12. resume the exact Operation;
13. complete sanitation without duplicate state.

## 12. First device vertical slice

The Huawei P30 Pro/VOG case should prove the specialist integration:

1. recover Huawei repository authority and the historical Drive handover;
2. connect Origins to the persistent Huawei Gateway;
3. create or recover the `PhysicalDeviceSession`;
4. record current endpoints and continuity;
5. run specialist X-Ray and ingest accepted read-only contracts;
6. produce and display the pre-operation Device Twin;
7. link the broader AgentOps objective to the Gateway operation;
8. route through deterministic recipe selection and governor gates;
9. execute only one bounded approved stage after the executor exists and is authorised;
10. ingest the raw executor result;
11. run post-operation X-Ray;
12. compare pre/post twins and verification result;
13. raise a Knowledge Gap when prediction and observation disagree;
14. retain Recovery Plan, journal digest, and exact continuation state;
15. block clean completion when proof is insufficient.

The current Huawei repository has not yet authorised a production executor, so early Origins integration must remain device-inert and prove reconnection, evidence, journal, and recovery views first.

## 13. Current implementation gate

Before continuing Origins source implementation, recover and review:

- existing Hunter UI and APIs;
- AgentOps and CodeOps callable boundaries;
- the Huawei Gateway protocol, Python reconnect client, snapshots, and journal;
- Huawei shared contract registry and fixtures;
- Oracle and Lumi integration contracts;
- X-Ray bundle and helper contracts;
- Ptah vocabulary and authorization boundary;
- specialist application session contracts;
- candidate desktop host and editor technologies.

Only then freeze the repository layout, frontend framework, native host, Rust–Python IPC, editor, terminal, and packaging choices.

The exploratory `build/initial-workspace` scaffold is not accepted implementation authority and must not be merged as-is.
