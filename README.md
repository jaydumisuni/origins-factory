# Origins Factory OS

Origins Factory is the custom Linux-based operating system for the THETECHGUY ecosystem.

It is not an application running on Ubuntu Desktop. It owns the bootable system image, the visible workspace shell, the service composition, the application model, updates, recovery, hardware discovery, and the clean integration of Hunter capabilities into one operating environment.

Linux provides the kernel and low-level hardware/runtime foundation. Origins Factory provides the product identity and operating experience.

## Product role

Origins Factory is the system the owner boots into and works through.

It presents one coherent environment for:

- Hunter conversation, memory, context recovery, and orchestration;
- AgentOps Operations, approvals, blockers, attempts, evidence, and sanitation;
- CodeOps repository engineering;
- Sergeant independent review;
- Oracle browser and authorised operating-system vision/control;
- Lumi DM downloads, queues, resume, integrity verification, and history;
- models and provider selection;
- repositories, terminals, editors, builds, files, artifacts, and recovery;
- registered THETECHGUY applications;
- local and remote Nodes, devices, and specialist gateways;
- Ptah Workspaces and mechanical execution after Ptah authorization.

Origins Factory does not duplicate the engines it presents. Each capability remains authoritative in its owning repository and is integrated through versioned packages, services, contracts, and manifests.

## System architecture

```text
Origins Factory OS
├── boot, hardware discovery, networking, identity, update, and recovery
├── Origins Factory workspace shell
├── Hunter core services
├── AgentOps
├── capability and application registry
├── Oracle Node Agent and live-control surfaces
├── Lumi DM
├── CodeOps and Sergeant adapters
├── local storage and artifact services
├── Ptah runtime later, after authorization
└── registered local or remote THETECHGUY applications
```

“All in one” means one bootable, coherent operating environment. It does not mean collapsing every subsystem into one process or copying every repository into this repository.

## Repository ownership

This repository owns:

- reproducible bootable image construction;
- the Origins Factory workspace shell;
- system package and service manifests;
- application and capability registry;
- native bridge and local OS integration;
- hardware profile and discovery policy;
- installer and first-boot flow;
- system updates, rollback, and recovery;
- Windows/Linux client packaging where the workspace is used outside the full OS;
- OS-level acceptance and portability tests.

This repository does not own:

- Hunter intelligence or memory implementation;
- AgentOps lifecycle implementation;
- CodeOps engineering implementation;
- Sergeant review implementation;
- Oracle or Lumi engines;
- specialist application source;
- Device Gateway journals;
- duplicated project documentation or artifact stores.

The complete ecosystem architecture remains canonical in `jaydumisuni/hunter`. This repository contains only Origins Factory OS implementation authority.

## Build and host roles

### Athena

Athena is the heavy development, compilation, packaging, model, and test machine.

### HP 290 G4

The HP 290 G4 is the temporary bootstrap and compatibility host:

- 10th-generation Intel platform, exact CPU pending inventory;
- 8 GB installed RAM;
- 1 TB movable system drive;
- boot, driver, installer, service, shell, update, and recovery validation.

The HP is not the final performance target and does not require a major RAM upgrade for this role.

### Final mini PC

The completed 1 TB Origins Factory system drive is intended to move to the properly provisioned mini PC. The mini PC becomes the permanent always-on host and receives a new final Node identity and hardware capability inventory.

The final Ptah physical-host proof must be collected against the final accepted mini-PC host. Evidence collected on the HP must not be reused as proof for different hardware.

## Portable-drive requirements

The bootable installation must remain portable across compatible x86-64 UEFI systems:

- bootloader installed on the movable drive;
- GPT and UEFI boot;
- generic Linux kernel and initramfs with required hardware support;
- filesystems mounted by UUID or stable logical identity;
- no hard-coded motherboard, GPU, MAC address, or network-interface assumptions;
- storage/content identity separate from Node identity;
- secrets not irreversibly bound to the HP TPM;
- destination hardware discovery and Node enrolment after migration;
- recovery and restore proof before physical drive migration.

Ubuntu Desktop or Windows may be booted temporarily only to inspect hardware. They are not the Origins Factory product base or user experience.

## Clean system rule

Origins Factory must remain sanitary:

- one canonical owner per fact;
- one deliberate location per artifact;
- references instead of unnecessary copies;
- temporary work isolated and expired;
- applications integrated as packages/services, not pasted source trees;
- updates replace obsolete generations cleanly;
- every accepted update includes rollback and sanitation evidence.

## Current state

The custom-OS boundary is now established. No complete operating-system image, installer, workspace shell, or runtime release is yet claimed as implemented or proven.
