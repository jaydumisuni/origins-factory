# Origins Stage-2 Sec-Ops Implementation Red-Team Packet

Status: **review packet prepared; runtime authority remains inactive**

This packet is for the mandatory Stage-2 security review of the **implemented** authority/enforcement boundary. It is not a re-review of the Stage-1 v1.1 contract model.

Canonical implementation description: `docs/ADR-0014-STAGE2-AUTHORITY-RUNTIME.md`.

## Review target

Review the real implementation of:

- durable production lease issuance/persistence;
- invocation-time authority evaluation;
- lease/scope revocation and fencing;
- Origins-native process admission;
- Linux Landlock + seccomp containment;
- Windows AppContainer + ACL + Job Object containment;
- Windows normal/crash cleanup and stale-manifest recovery.

## Locked authority chain

```text
approved and authenticated preflight evidence
        ↓
current durable scope/provider/host/resource revalidation
        ↓
atomic single-use lease issuance
        ↓
current lease/scope revalidation for every invocation
        ↓
durable Repository projection only
        ↓
ProcessPolicy
        ↓
SandboxSpec
        ↓
native OS containment
```

No security layer may silently substitute a broader source of authority for the layer above it.

## Required hostile review areas

### 1. Issuance TOCTOU / replay

Attempt to:

- reuse an eligible preflight receipt;
- change scope revision/fence after preflight;
- substitute provider manifest/generation;
- substitute host-policy generation/digest;
- substitute resource generation/digest;
- change the proposal/approval/issuance binding;
- race concurrent issuance using the same receipt;
- exploit rollback/restart to make a consumed receipt usable again.

Determine whether single-use enforcement is atomic under concurrent writers and restart.

### 2. Durable authority tamper / rollback

Attack the SQLite authority records and their metadata independently:

- canonical contract JSON;
- contract SHA-256;
- preflight JSON/digest;
- provider metadata;
- host-policy metadata;
- resource-generation rows;
- lease/scope state, revision and fence.

Test deletion, partial replacement, stale-copy rollback and cross-record substitution. The runtime must fail closed rather than reconstructing authority from attacker-controlled fragments.

### 3. Stale handles and revocation races

Attempt invocation:

- immediately before and after lease revocation;
- immediately before and after scope revocation;
- while scope revocation cascades across multiple leases;
- with stale revision/fence handles;
- after daemon restart;
- while a native process is being admitted/started.

Check whether any already-obtained handle can survive the intended fence transition.

### 4. Confused deputy / holder substitution

Try to use a valid lease through a different:

- holder UUID;
- holder generation;
- capability;
- effect;
- provider;
- Workspace;
- Repository projection.

Origins must not become a privileged deputy for an otherwise unauthorized caller.

### 5. Repository/root substitution

Native admission accepts only `worktree:<repository_id>` resources resolved through durable Origins Repository projections.

Attack:

- arbitrary absolute host paths;
- repository IDs from another Workspace;
- changed/stale Repository projection roots;
- symlink/junction/reparse traversal;
- path replacement between validation and use;
- nested mount/reparse tricks;
- deleted/recreated grant paths;
- special filesystem objects.

Explicitly distinguish attacks closed by the resource-id abstraction from attacks that still require runtime path-resolution enforcement.

### 6. Linux containment escape

Against the actual Landlock/seccomp/setsid implementation, attempt:

- filesystem access outside granted rules;
- write under read-only grants;
- deny-path bypass;
- inherited file-descriptor abuse;
- `/proc` or runtime-loader abuse;
- socket creation/use;
- inherited socket/fd abuse;
- namespace creation;
- process-group/session escape;
- descendant survival after fencing;
- kernel/ABI compatibility downgrade behavior.

Landlock is configured as a hard requirement; verify unsupported/partial enforcement fails closed.

### 7. Windows containment escape

Against the actual AppContainer/ACL/Job implementation, attempt:

- ACL inheritance escape;
- reparse-point escape;
- child process outside the AppContainer;
- child process outside the Job Object;
- duplicate/escaped Job handles;
- network access without capabilities;
- access through pre-opened/inherited handles;
- executable/runtime DLL path substitution;
- profile/SID collision or reuse.

### 8. Windows cleanup/recovery

The helper may be terminated without Rust destructors. Attack:

- abrupt helper termination before profile creation;
- termination during ACL application;
- termination after process creation;
- watchdog termination;
- simultaneous sandboxes;
- stale manifest replay/tamper;
- PID reuse;
- cleanup directory substitution;
- path deletion/recreation before recovery;
- ACL changes by another principal while the sandbox is running.

Verify cleanup removes only the unique ephemeral AppContainer SID and never restores/overwrites an unrelated principal's concurrent ACL change.

### 9. Network fail-closed boundary

Native v1 intentionally supports only `network_mode=deny`.

Attempt to pass:

- allowlist leases;
- endpoints with otherwise valid leases;
- delegated remote authority;
- redirect-policy variations.

The system must refuse these rather than silently mapping them to weaker containment.

### 10. Environment authority

Attempt to inject or inherit ungranted environment data, especially credentials and authority/configuration variables. Confirm only names granted by the current lease can be selected for the native sandbox and that missing/invalid host values fail closed.

### 11. Self-disable / activation

Search for every path that could:

- set `RUNTIME_AUTHORITY_ACTIVATED` true;
- expose issuer/evaluator/native admission over HTTP/model routes;
- bypass `authorize_invocation()`;
- invoke native containment from a broader legacy process route;
- edit policy/authority state to widen its own cage.

The reviewed candidate must remain dormant. No Sec-Ops PASS on this packet should be interpreted as permission to enable a surface that was absent from the reviewed code.

## Proof evidence expected with review

Review the exact candidate head only. Evidence should include:

- Stage-2 Ubuntu Rust 1.75 `clippy -D warnings` PASS;
- Stage-2 Windows Rust 1.75 `clippy -D warnings` PASS;
- authority runtime tests PASS on both hosts;
- native sandbox compiler PASS on both hosts;
- Linux behavioral filesystem/network/process-tree PASS;
- Windows behavioral filesystem/network/process-tree PASS;
- Windows abrupt-helper-death cleanup PASS with unique SID absent from touched ACLs;
- `originsd` build PASS on both hosts;
- complete inherited Origins Daemon Foundation PASS;
- Contract Spine PASS on the PR head;
- no-activation/source review evidence.

## Verdict boundary

Requested verdicts:

- `PASS` — implemented dormant boundary is acceptable to proceed to a separately controlled activation decision;
- `NEEDS_WORK` — concrete findings must be corrected and exact-head proof rerun;
- `BLOCK` — boundary is structurally unsafe and activation work must stop.

Even a Stage-2 `PASS` does **not** itself activate runtime authority. Activation must be a distinct reviewed change with explicit owner approval and proof of the exact surfaces being enabled.
