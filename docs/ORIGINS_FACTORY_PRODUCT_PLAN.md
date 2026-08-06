# Origins Factory — Product and Implementation Authority

**Status:** Candidate product authority

## 1. Product definition

Origins Factory is the portable, conversation-first Hunter workspace for the THETECHGUY ecosystem.

It is intended to exceed the useful combined experience of VS Code, Cursor, Codex, and ChatGPT Work by joining persistent project context, repository engineering, model choice, parallel operations, browser work, downloads, applications, device evidence, real hardware, proof, and recovery in one workspace.

Origins Factory is not the custom operating system. It runs inside that future OS and also ships independently for Windows, Linux, and later macOS.

## 2. Primary experience

The owner should normally open Origins Factory and speak to Hunter.

```text
Owner
  ↓
Origins Factory
  ↓
Hunter
  ↓
AgentOps Operation
  ↓
CodeOps / Oracle / Lumi / X-Ray / Sergeant / specialist applications / Nodes
```

The conversation remains central. Code, terminal, browser, downloads, applications, devices, evidence, and recovery surfaces open when required.

## 3. Permanent authority boundaries

- **Hunter** — intelligence, conversation, memory, context recovery, planning, capability selection, routing, reconciliation, contradiction detection, and upgrade proposals.
- **Hunter AgentOps** — durable Operation identity, attempts, approvals, blockers, evidence bindings, correction loops, resume state, and sanitation state.
- **Hunter CodeOps** — repository recovery, editing, build/test proof, correction, rollback, and engineering handoff.
- **Sergeant** — independent review and challenge.
- **Oracle** — browser and authorised operating-system vision/control sessions, remote view, human takeover, and file/control capability.
- **Lumi DM** — downloads, queues, resume, integrity verification, and download history.
- **TTG Device X-Ray** — read-first device identification, transport evidence, identity correlation, firmware/storage intelligence, challenge, certification, profile resolution, recommendation, and sealed evidence.
- **Ptah Space** — future persistent mechanical Workspace and execution substrate after its existing authorization gates close.
- **Specialist applications and Device Gateways** — deterministic domain execution and final domain-specific operation truth.

Origins Factory presents and coordinates these capabilities without duplicating their engines or canonical state.

## 4. Workspace model

A Workspace binds references to:

- project purpose and instructions;
- canonical repositories and accepted documents;
- locked decisions and current status;
- conversations;
- AgentOps Operations and Attempts;
- models, providers, and Nodes;
- editor, terminal, browser, download, application, and device sessions;
- Artifacts, evidence, and recovery state.

The Workspace belongs to Hunter/AgentOps, not to one model. Changing providers must not lose project or Operation state.

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

## 6. Runtime roles

Rust and Python are both required, but exact framework and IPC choices remain unapproved until the implementation review is complete.

### Rust responsibilities

- native process and PTY supervision;
- filesystem and Git authority;
- local application discovery and launching;
- Node capability discovery;
- secure native IPC boundary;
- resource limits and cancellation;
- terminal, window, and local session attachment;
- high-performance event transport;
- later Ptah and device-gateway integration.

### Python responsibilities

- Hunter intelligence integration;
- AgentOps and CodeOps mounting;
- model/provider adapters;
- planning, reconciliation, and capability selection;
- repository and evidence intelligence;
- skills and specialist adapters;
- capability-gap diagnosis and evolution proposals.

### Workspace UI responsibilities

- Hunter conversation;
- Project Twin views;
- Operations and Attempts;
- editor, terminal, browser, Lumi, application, device, evidence, storage, and recovery surfaces;
- approval and takeover controls;
- cross-client status and notifications.

React, Tauri, Qt, Monaco, xterm, and the exact Rust–Python protocol are candidate choices, not yet frozen decisions.

## 7. X-Ray integration

TTG Device X-Ray is not a normal launcher tile. It is Origins Factory's authoritative read-first device context engine.

### 7.1 Device discovery and scan

When device work begins, Origins Factory:

1. identifies the Node and physical transport carrying the device;
2. requests a read-only X-Ray scan on that Node;
3. receives the sealed evidence bundle and manifest digest;
4. binds that exact bundle to the AgentOps Operation and Attempt;
5. presents candidate topology and certification by dimension.

X-Ray's pipeline remains:

```text
PROBE
→ NORMALIZE
→ GROUP PHYSICAL DEVICES
→ CORRELATE IDENTITY
→ BUILD FIRMWARE FINGERPRINT
→ BUILD STORAGE SUMMARY
→ CHALLENGE
→ CERTIFY BY DIMENSION
→ RESOLVE REVIEWED PROFILE
→ PLAN
→ SEAL EVIDENCE BUNDLE
```

### 7.2 Origins device view

Origins Factory displays:

- physical-device candidates and endpoint grouping;
- current transport and mode;
- identity confidence;
- firmware fingerprint;
- storage and partition evidence;
- contradictions and challenger findings;
- matched reviewed profile;
- freshness and expiry;
- `CERTIFIED`, `INVESTIGATE`, or `UNSAFE` state;
- recommended route;
- bundle integrity and signer state.

When multiple physical-device candidates are present, Origins must preserve the separate evidence while respecting X-Ray's workstation-level `UNSAFE` result.

### 7.3 Hunter and model use

Hunter and assigned models may:

- explain the evidence;
- compare it with project and firmware records;
- recommend a specialist route;
- identify missing evidence;
- propose new read-only probes or profile improvements.

They may not:

- convert a profile match into write authority;
- override X-Ray certification;
- hide contradictions;
- change the sealed bundle;
- declare a repair successful without required post-operation verification.

### 7.4 Specialist execution

After evidence and approvals are satisfied, Origins opens or binds the correct specialist application or Device Gateway, such as Huawei or CHECKM8.

The specialist system consumes the exact X-Ray evidence reference, establishes its own deterministic policy and leases, and performs only its authorised bounded operation. Origins does not execute device writes directly.

### 7.5 Post-operation proof

After a device stage, Origins requests a fresh X-Ray scan and shows a before/after evidence comparison.

An Operation cannot become `COMPLETED_CLEAN` when required post-X-Ray evidence is missing, stale, contradictory, or `UNSAFE`.

### 7.6 Remote Nodes

A device may remain physically connected to Athena, a Mac, the custom-OS host, or another enrolled Node. X-Ray runs where the device is physically attached. Origins receives the signed/sealed evidence and live status by reference rather than copying uncontrolled device state between machines.

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
- Athena for heavy builds, NVIDIA work, tests, and local models;
- VPS or rented workers;
- Cloudflare, Fireworks, and other approved providers;
- Windows, Linux, macOS, mini-PC, and GPU Nodes.

The HP 290 G4 can run the complete first system with 8 GB RAM because heavy compute may be routed elsewhere. The Workspace and Operation identity remain stable while compute moves.

## 10. Clean-core rules

- one canonical owner per durable fact;
- references preferred over copies;
- exact duplicate bytes stored once per authorised scope;
- failed Attempts retained honestly;
- temporary work isolated by Workspace/Operation/Attempt;
- accepted outputs promoted explicitly;
- obsolete plans and generated material removed during sanitation;
- completion requires proof and a clean sanitation result;
- no capability approves or activates its own upgrade.

## 11. First vertical slice

The first implementation proof should use a real repository mission and demonstrate:

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

A later device vertical slice must add:

1. attach a device to a Node;
2. run X-Ray;
3. bind the sealed bundle;
4. route to the correct specialist Gateway;
5. execute one bounded approved stage;
6. run post-X-Ray;
7. present the evidence delta;
8. block clean completion when proof is insufficient.

## 12. Current implementation gate

Before continuing source implementation, recover and review:

- existing Hunter UI and APIs;
- AgentOps and CodeOps callable boundaries;
- Oracle and Lumi integration contracts;
- X-Ray bundle and helper contracts;
- Ptah vocabulary and authorization boundary;
- specialist application session contracts;
- candidate desktop host and editor technologies.

Only then freeze the repository layout, frontend framework, native host, Rust–Python IPC, editor, terminal, and packaging choices.

The exploratory `build/initial-workspace` scaffold is not accepted implementation authority and must not be merged as-is.
