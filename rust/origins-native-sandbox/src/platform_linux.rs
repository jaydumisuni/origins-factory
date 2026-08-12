use crate::{SandboxError, SandboxSpec};
use landlock::{
    Access, AccessFs, CompatLevel, Compatible, PathBeneath, PathFd, Ruleset, RulesetAttr,
    RulesetCreatedAttr, RulesetStatus, ABI,
};
use nix::unistd::setsid;
use seccompiler::{BpfProgram, SeccompAction, SeccompFilter};
use std::collections::BTreeMap;
use std::convert::TryInto;
use std::os::unix::process::CommandExt;
use std::process::Command;

pub fn run(spec: SandboxSpec) -> Result<i32, SandboxError> {
    setsid().map_err(|error| SandboxError::Os(format!("setsid failed: {error}")))?;
    apply_filesystem(&spec)?;
    apply_network_and_escape_filter()?;

    let mut command = Command::new(&spec.executable);
    command.args(&spec.args);
    command.current_dir(&spec.cwd);
    command.env_clear();
    command.envs(&spec.environment);
    let error = command.exec();
    Err(SandboxError::Io(format!(
        "sandboxed exec failed for {}: {error}",
        spec.executable.display()
    )))
}

fn apply_filesystem(spec: &SandboxSpec) -> Result<(), SandboxError> {
    let abi = ABI::V3;
    let access_all = AccessFs::from_all(abi);
    let access_read = AccessFs::from_read(abi);
    let mut ruleset = Ruleset::default()
        .set_compatibility(CompatLevel::HardRequirement)
        .handle_access(access_all)
        .map_err(map_landlock)?
        .create()
        .map_err(map_landlock)?;

    for path in &spec.runtime_read_paths {
        ruleset = ruleset
            .add_rule(
                PathBeneath::new(PathFd::new(path).map_err(map_landlock)?, access_read)
                    .set_compatibility(CompatLevel::HardRequirement),
            )
            .map_err(map_landlock)?;
    }
    ruleset = ruleset
        .add_rule(
            PathBeneath::new(
                PathFd::new(&spec.executable).map_err(map_landlock)?,
                access_read,
            )
            .set_compatibility(CompatLevel::HardRequirement),
        )
        .map_err(map_landlock)?;
    for rule in &spec.resource_paths {
        let access = if rule.writable {
            access_all
        } else {
            access_read
        };
        ruleset = ruleset
            .add_rule(
                PathBeneath::new(PathFd::new(&rule.path).map_err(map_landlock)?, access)
                    .set_compatibility(CompatLevel::HardRequirement),
            )
            .map_err(map_landlock)?;
    }

    let status = ruleset.restrict_self().map_err(map_landlock)?;
    if status.ruleset != RulesetStatus::FullyEnforced || !status.no_new_privs {
        return Err(SandboxError::Os(format!(
            "Landlock did not fully enforce requested filesystem boundary: {status:?}"
        )));
    }
    Ok(())
}

fn apply_network_and_escape_filter() -> Result<(), SandboxError> {
    let blocked = [
        libc::SYS_socket,
        libc::SYS_socketpair,
        libc::SYS_connect,
        libc::SYS_bind,
        libc::SYS_listen,
        libc::SYS_accept,
        libc::SYS_accept4,
        libc::SYS_sendto,
        libc::SYS_sendmsg,
        libc::SYS_recvfrom,
        libc::SYS_recvmsg,
        libc::SYS_shutdown,
        libc::SYS_setsockopt,
        libc::SYS_getsockopt,
        libc::SYS_setsid,
        libc::SYS_setpgid,
        libc::SYS_unshare,
    ];
    let rules = blocked
        .into_iter()
        .map(|syscall| (syscall, Vec::new()))
        .collect::<BTreeMap<_, _>>();
    let filter = SeccompFilter::new(
        rules,
        SeccompAction::Allow,
        SeccompAction::Errno(libc::EPERM as u32),
        std::env::consts::ARCH
            .try_into()
            .map_err(|error| SandboxError::Os(format!("unsupported seccomp architecture: {error}")))?,
    )
    .map_err(|error| SandboxError::Os(format!("seccomp filter invalid: {error}")))?;
    let program: BpfProgram = filter
        .try_into()
        .map_err(|error| SandboxError::Os(format!("seccomp compile failed: {error}")))?;
    seccompiler::apply_filter(&program)
        .map_err(|error| SandboxError::Os(format!("seccomp install failed: {error}")))
}

fn map_landlock(error: impl std::fmt::Display) -> SandboxError {
    SandboxError::Os(format!("Landlock containment failed: {error}"))
}
