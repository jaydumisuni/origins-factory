# Origins Factory

Origins Factory is the cross-platform Hunter workspace application and future visible Linux workspace shell for the THETECHGUY ecosystem.

## Role

Origins Factory is the application the owner opens to work with Hunter across projects, operations, models, browsers, downloads, applications, Nodes, devices, evidence, and recovery.

It does not duplicate the engines it presents.

- Hunter owns intelligence, conversation, memory, context selection, and orchestration.
- Hunter AgentOps owns durable Operation lifecycle, attempts, approvals, blockers, evidence, and sanitation state.
- Hunter CodeOps owns repository engineering.
- Sergeant owns independent review.
- Oracle owns browser and authorised operating-system vision/control sessions.
- Lumi DM owns downloads, queues, resume, integrity verification, and download history.
- Ptah Space is the future mechanical Workspace and execution substrate after its existing authorization gates close.
- Specialist applications and Device Gateways retain their own authority.

## Deployment direction

Origins Factory is intended to ship as:

- a Windows application;
- a Linux desktop application;
- a macOS application later;
- the full-screen visible shell of the future Hunter Linux appliance.

The first Linux installation will be developed and exercised on an HP 290 G4 Microtower using an 8 GB RAM / 1 TB system drive configuration. That HP is a bootstrap and compatibility host, not the final performance target. Heavy building, testing, and model work remains available on Athena. The system drive is intended to move later to the properly provisioned mini PC, which becomes the permanent always-on host.

The final Ptah physical-host proof must be collected on the final accepted host after the drive migration. Proof collected on the HP must not be silently reused as proof for the mini PC.

## Portability requirements

The Linux installation and Origins Factory shell must remain portable between compatible x86-64 UEFI hosts:

- bootloader installed on the movable system drive;
- GPT/UEFI boot;
- generic Linux kernel and initramfs;
- filesystems mounted by UUID or stable logical identity;
- no hard-coded network interface, MAC address, GPU, or motherboard assumptions;
- no secrets or disk unlock policy irreversibly bound to the HP TPM;
- Node identity separated from disk/content identity;
- mini-PC enrolment performed after migration;
- hardware inventory and capability discovery rerun on the destination host;
- backup and restore proof completed before physical migration.

## Repository boundary

This repository owns the Origins Factory application, workspace UI, native client bridge, application registry, packaging configuration, offline/reconnect behaviour, and Linux shell integration.

The complete Hunter architecture remains canonical in `jaydumisuni/hunter`. Specialist source remains in its owning repository and is integrated through versioned contracts and manifests.

## Current state

Initial product boundary recorded. Application implementation has not yet been claimed or proven.
