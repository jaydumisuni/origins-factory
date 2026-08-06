# Origins Factory

Origins Factory is the portable, cross-platform Hunter workspace for the THETECHGUY ecosystem.

It is **not the operating system itself**. It is the primary workspace and interaction surface that can run:

- inside the future custom THETECHGUY/Hunter operating system;
- as a Windows application;
- as a Linux application;
- as a macOS application later;
- through other supported clients where appropriate.

## Role

Origins Factory is the application the owner opens to work with Hunter across projects, operations, models, browsers, downloads, applications, Nodes, devices, evidence, storage, and recovery.

It presents and coordinates capabilities without duplicating their engines.

- Hunter owns intelligence, conversation, memory, context selection, planning, and orchestration.
- Hunter AgentOps owns durable Operation lifecycle, attempts, approvals, blockers, evidence, and sanitation state.
- Hunter CodeOps owns repository engineering.
- Sergeant owns independent review.
- Oracle owns browser and authorised operating-system vision/control sessions.
- Lumi DM owns downloads, queues, resume, integrity verification, and download history.
- Ptah Space is the future mechanical Workspace and execution substrate after its existing authorization gates close.
- Specialist applications and Device Gateways retain their own authority.

## Relationship to the main custom OS

The main custom OS is a separate product and deployment layer. Its final name and canonical repository have not yet been frozen.

The custom OS will provide the complete integrated machine environment, including:

- Linux kernel and hardware support;
- boot, login, system services, updates, rollback, and recovery;
- Origins Factory as the main workspace;
- Hunter and AgentOps services;
- Oracle Node Agent and optional remote-view/control capability;
- Lumi DM;
- local storage and artifact services;
- application installation and registration;
- local and remote compute routing;
- Ptah after authorization;
- selected TechGuy applications and specialist capabilities.

Origins Factory remains usable outside that OS. The OS consumes a pinned Origins Factory release rather than absorbing or duplicating its source.

## Compute model

The system does not require all intelligence or build power to exist inside the machine running Origins Factory.

A host may use:

- its own CPU, RAM, storage, and optional GPU;
- Athena for heavy local builds, testing, NVIDIA workloads, and local models;
- VPS or rented compute workers;
- Cloudflare, Fireworks, and other approved hosted providers;
- additional Windows, Linux, macOS, mini-PC, and GPU Nodes.

The workspace, Operation identity, evidence, and recovery state remain stable while compute is routed elsewhere.

## Initial hardware path

The HP 290 G4 Microtower can run the complete first custom-OS system with its current 8 GB RAM and 1 TB system drive because heavy compute can be routed to Athena or remote providers.

The HP is both:

- a valid first full-system host;
- a hardware and portability test host.

The 1 TB system drive may later move to the properly provisioned mini PC. The installation must therefore remain portable between compatible x86-64 UEFI machines:

- bootloader installed on the movable system drive;
- GPT/UEFI boot;
- generic Linux kernel and initramfs;
- filesystems mounted by UUID or stable logical identity;
- no hard-coded network interface, MAC address, GPU, or motherboard assumptions;
- no secrets irreversibly tied to the HP TPM;
- storage identity separated from Node identity;
- hardware capability discovery rerun after migration;
- destination Node re-enrolled after migration;
- backup and restore proven before moving the drive.

The final Ptah physical-host proof must be collected against whichever physical machine is ultimately accepted as the Ptah host. Moving the drive does not transfer physical-host proof automatically.

## Repository boundary

This repository owns:

- the Origins Factory workspace application;
- conversation-first workspace UI;
- Project and Operation views;
- model, provider, and Node controls;
- Oracle and Lumi client surfaces;
- application registry and launcher;
- native client bridge;
- local cache and offline/reconnect behaviour;
- Windows, Linux, and later macOS packaging;
- integration contracts consumed by the custom OS.

This repository does not own:

- the Linux distribution or OS image;
- Hunter intelligence;
- AgentOps operation truth;
- CodeOps;
- Oracle's execution engine;
- Lumi's download engine;
- Ptah;
- specialist application engines;
- duplicated copies of artifacts or project truth.

The complete Hunter architecture remains canonical in `jaydumisuni/hunter`. Specialist source remains in its owning repository and is integrated through versioned contracts and manifests.

## Current state

Product boundary corrected and recorded. Origins Factory is the portable workspace, while the main custom OS remains a separate integrated system whose name and repository are still to be frozen. No application or OS implementation is yet claimed as complete or proven.
