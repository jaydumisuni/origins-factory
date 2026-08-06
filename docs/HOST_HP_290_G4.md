# Origins Factory — HP 290 G4 Host Record

**Status:** VERIFIED from live Ubuntu hardware inventory supplied by the owner  
**Recorded:** 2026-08-07  
**Intended role:** first complete-system host, Origins development/validation Node, and portable-drive test host

## 1. Verified hardware

```text
Machine family:       HP 290 G4 Microtower
Regulatory model:     TPC-F123-MT
System board:         HP 8948, revision A (SMVB)
Chipset:              Intel H470
BIOS vendor/version:  AMI F.40
BIOS release date:    2023-02-13

CPU:                  Intel Core i7-10700 @ 2.90 GHz
Architecture:         x86_64
Cores / threads:      8 / 16
Maximum frequency:    4.80 GHz reported
Virtualization:       Intel VT-x
Cache:                16 MiB L3

Memory total:         8 GB installed (7.5 GiB visible)
Slot/module 1:        4 GB Micron 4ATF51264AZ-3G2R1
Slot/module 2:        4 GB Samsung M378A5244CB0-CWE
Module rating:        DDR4-3200
Configured speed:     2933 MT/s
Swap in live session: none

Integrated graphics: Intel UHD Graphics 630
Graphics driver:      i915

Primary NVMe:         Samsung MZVL81T0 / PM9C1a controller
Reported capacity:    953.9 GiB (nominal 1 TB)
NVMe driver:          Linux nvme

Secondary SATA SSD:   Crucial CT500BX500SSD1
Reported capacity:    465.8 GiB (nominal 500 GB)

Ethernet:             Realtek RTL8111/8168/8211/8411 Gigabit Ethernet
Linux driver:         r8169
Optical drive:        HP/HLDS DVDRW
```

## 2. Current observed storage state

The live Ubuntu session showed:

```text
nvme0n1p1  953.9 GiB  NTFS  label/mount: CCCOMA_X64FRE_EN-US_DV9
nvme0n1p2  1 MiB      VFAT  label/mount: UEFI_NTFS

sdb1       200 MiB    VFAT
sdb2       465.6 GiB  exFAT label/mount: Untitled

sda        231.1 GiB  USB Flash Drive used as the live Ubuntu medium
```

The NVMe partition labels strongly indicate that the 1 TB NVMe is currently written as Windows installation media. This is a storage-state inference, not a hardware fault.

Do not treat either SSD as empty. Inventory and preserve any needed data before repartitioning.

## 3. Origins role

This host is materially stronger than the earlier sticker-based assumptions.

It is capable of running:

- the Origins React/TypeScript workspace;
- the persistent Rust native service;
- Python Hunter/AgentOps/CodeOps integration;
- several repositories and terminal sessions;
- normal Rust, Python, TypeScript, and packaging builds;
- Oracle and Lumi services;
- local storage and Artifact coordination;
- containers and lightweight local models;
- remote Node and hosted-model coordination.

The installed 8 GB RAM is enough to begin because Athena, VPS workers, Cloudflare, Fireworks, and later Nodes can carry heavy builds or inference.

No RAM purchase is required to start Origins architecture, contract, and initial runtime work.

## 4. Recommended storage roles for the HP stage

The exact disk to become the portable system drive remains an owner decision after data review.

A practical arrangement is:

```text
1 TB NVMe
→ custom OS/system installation later
→ Origins, Hunter control services, durable workspace metadata
→ portable drive intended for later compatible mini-PC migration

500 GB Crucial SATA SSD
→ active build scratch
→ worktrees and package/build caches
→ temporary recovery staging
→ disposable intermediates with sanitation rules
```

A second copy on the same physical machine is not a complete backup. Important system and mission state requires a separate verified recovery copy.

## 5. Portability requirements

When the custom OS is built onto the movable system drive:

- GPT/UEFI boot;
- bootloader on the movable drive;
- generic x86-64 kernel/initramfs;
- filesystems mounted by UUID or stable logical identity;
- no hard-coded HP network interface or MAC address;
- no hard-coded UHD 630 dependency;
- no secrets irreversibly bound to the HP TPM;
- storage identity separate from Node identity;
- hardware/capability discovery rerun on migration;
- destination mini PC enrolled as a new Node/Generation;
- backup and restore proven before physical migration.

Physical-host proof does not migrate merely because the drive moves. Ptah or other host-specific authorization evidence must be collected against the final accepted host.

## 6. Resource strategy

For the HP’s 8 GB stage:

- use zram or reviewed compressed swap in the installed system;
- bound service memory explicitly;
- isolate build workers;
- avoid several heavy local models at once;
- route GPU-heavy work to Athena;
- route suitable reasoning to hosted providers;
- place caches and build scratch on the secondary SSD where practical;
- expose honest memory, storage-pressure, and Provider-health views in Origins.

## 7. Firmware/security observations

The supplied `lscpu` output reported current Linux mitigations for several speculative-execution classes and reported Gather Data Sampling as vulnerable. This record does not prescribe a firmware update. BIOS/microcode update decisions require a separate HP-specific evidence and recovery review.

The SATA controller was reported as Intel RAID mode while Linux used the `ahci` driver. Do not change firmware storage mode without checking the installed-system consequences and recovery path.

## 8. Remaining hardware checks

Before installing the permanent custom OS image or migrating the drive:

- confirm current SSD health and SMART/NVMe health data;
- confirm the mini PC accepts the same physical NVMe form factor and interface;
- confirm HP boot order and Secure Boot policy;
- confirm whether firmware updates are required and safely recoverable;
- test suspend/restart, Ethernet, graphics, USB, audio, and thermal behavior;
- create a verified backup of any existing data;
- record the final disk identity chosen for migration.

## 9. Canonical conclusion

The HP 290 G4 is a valid first full-system and Origins host:

```text
Intel Core i7-10700
8 cores / 16 threads
8 GB DDR4-2933 installed
1 TB Samsung NVMe
500 GB Crucial SATA SSD
Intel UHD 630
Gigabit Ethernet
```

It does not need to be the final high-memory or GPU machine. Origins is designed to coordinate Athena, hosted inference, rented workers, and later Nodes while preserving the same Mission and Workspace state.
