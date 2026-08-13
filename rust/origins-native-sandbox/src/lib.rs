use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fmt::{Display, Formatter};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SandboxPathRule {
    pub path: PathBuf,
    pub writable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct SandboxSpec {
    pub executable: PathBuf,
    pub args: Vec<String>,
    pub cwd: PathBuf,
    pub environment: BTreeMap<String, String>,
    pub runtime_read_paths: Vec<PathBuf>,
    pub resource_paths: Vec<SandboxPathRule>,
    pub deny_paths: Vec<PathBuf>,
    pub network_mode: String,
}

impl SandboxSpec {
    pub fn validate(&self) -> Result<(), SandboxError> {
        if self.network_mode != "deny" {
            return Err(SandboxError::Unsupported(
                "native containment v1 only supports network_mode=deny".to_owned(),
            ));
        }
        require_file(&self.executable, "executable")?;
        require_dir(&self.cwd, "cwd")?;
        if self.resource_paths.is_empty() {
            return Err(SandboxError::Invalid(
                "at least one resource path is required".to_owned(),
            ));
        }
        for path in &self.runtime_read_paths {
            require_existing(path, "runtime_read_path")?;
        }
        for rule in &self.resource_paths {
            require_existing(&rule.path, "resource_path")?;
        }
        for deny in &self.deny_paths {
            require_existing(deny, "deny_path")?;
            for rule in &self.resource_paths {
                if deny.starts_with(&rule.path) || rule.path.starts_with(deny) {
                    return Err(SandboxError::Unsupported(format!(
                        "overlapping allow/deny paths cannot be represented safely: allow={} deny={}",
                        rule.path.display(), deny.display()
                    )));
                }
            }
        }
        if !self
            .resource_paths
            .iter()
            .any(|rule| self.cwd.starts_with(&rule.path))
        {
            return Err(SandboxError::Invalid(
                "cwd must be inside a granted resource path".to_owned(),
            ));
        }
        if self.environment.iter().any(|(name, value)| {
            name.is_empty() || name.contains('=') || name.contains('\0') || value.contains('\0')
        }) {
            return Err(SandboxError::Invalid(
                "environment contains an invalid name or value".to_owned(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug)]
pub enum SandboxError {
    Invalid(String),
    Unsupported(String),
    Os(String),
    Io(String),
}

impl Display for SandboxError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid(message) => write!(formatter, "invalid sandbox spec: {message}"),
            Self::Unsupported(message) => {
                write!(formatter, "unsupported sandbox request: {message}")
            }
            Self::Os(message) => write!(formatter, "sandbox OS error: {message}"),
            Self::Io(message) => write!(formatter, "sandbox I/O error: {message}"),
        }
    }
}

impl std::error::Error for SandboxError {}

pub fn run(spec: SandboxSpec) -> Result<i32, SandboxError> {
    spec.validate()?;
    platform::run(spec)
}

#[cfg(windows)]
pub fn recover_windows_cleanup() -> Result<(), SandboxError> {
    windows_cleanup::recover_stale()
}

#[cfg(windows)]
pub fn watch_windows_cleanup(owner_pid: u32, manifest_path: &Path) -> Result<(), SandboxError> {
    windows_cleanup::watch_owner(owner_pid, manifest_path)
}

fn require_existing(path: &Path, label: &str) -> Result<(), SandboxError> {
    if !path.is_absolute() || !path.exists() {
        return Err(SandboxError::Invalid(format!(
            "{label} must be an existing absolute path: {}",
            path.display()
        )));
    }
    Ok(())
}

fn require_file(path: &Path, label: &str) -> Result<(), SandboxError> {
    require_existing(path, label)?;
    if !path.is_file() {
        return Err(SandboxError::Invalid(format!(
            "{label} must be a file: {}",
            path.display()
        )));
    }
    Ok(())
}

fn require_dir(path: &Path, label: &str) -> Result<(), SandboxError> {
    require_existing(path, label)?;
    if !path.is_dir() {
        return Err(SandboxError::Invalid(format!(
            "{label} must be a directory: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
#[path = "platform_linux.rs"]
mod platform;

#[cfg(windows)]
mod windows_cleanup;

#[cfg(windows)]
#[path = "platform_windows.rs"]
mod platform;

#[cfg(not(any(target_os = "linux", windows)))]
mod platform {
    use super::{SandboxError, SandboxSpec};

    pub fn run(_spec: SandboxSpec) -> Result<i32, SandboxError> {
        Err(SandboxError::Unsupported(
            "native containment is implemented only for Linux and Windows".to_owned(),
        ))
    }
}
