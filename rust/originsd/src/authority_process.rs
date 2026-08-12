use crate::authority_runtime::{InvocationRequest, ResourceGrant};
use crate::containment::{ContainmentPlan, ContainmentPlatform};
use crate::process::{validate_executable, ProcessPolicy};
use crate::store::{Store, StoreError};
use origins_native_sandbox::{SandboxPathRule, SandboxSpec};
use serde_json::Value;
use std::collections::BTreeMap;
use std::env;
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone)]
pub struct NativeProcessRequest {
    pub invocation: InvocationRequest,
    pub executable: String,
    pub args: Vec<String>,
    pub cwd_resource_id: String,
    pub cwd_relative: String,
}

#[derive(Debug, Clone)]
pub struct NativeProcessAdmission {
    pub lease_id: String,
    pub scope_id: String,
    pub sandbox: SandboxSpec,
    pub runtime_authority_activated: bool,
}

pub fn prepare_native_process(
    store: &Store,
    process_policy: &ProcessPolicy,
    request: &NativeProcessRequest,
) -> Result<NativeProcessAdmission, StoreError> {
    let decision = store.authorize_invocation(&request.invocation)?;
    if !decision.authorized {
        return Err(StoreError::Conflict(format!(
            "native process admission denied: {}",
            decision.code
        )));
    }
    if decision.runtime_authority_activated {
        return Err(StoreError::Corrupt(
            "dormant Stage-2 admission unexpectedly reported runtime activation".to_owned(),
        ));
    }

    validate_executable(&request.executable)?;
    validate_args(&request.args)?;
    let executable = resolve_executable(&request.executable)?;
    let lease = store.get_capability_lease(&request.invocation.handle.lease_id)?;
    let platform = current_platform()?;
    let plan = ContainmentPlan::from_lease(&lease, platform)?;
    if plan.network_mode != "deny" || !request.invocation.network_endpoints.is_empty() {
        return Err(StoreError::Conflict(
            "native containment v1 refuses network-capable leases; exact endpoint broker is not implemented"
                .to_owned(),
        ));
    }
    if plan.runtime_authority_activated {
        return Err(StoreError::Corrupt(
            "containment plan must remain dormant before Stage-2 activation".to_owned(),
        ));
    }

    let workspace_id = required_string(&lease, "workspace_id")?;
    let roots = resolve_resource_roots(store, process_policy, workspace_id, &lease)?;
    let cwd_root = roots.get(&request.cwd_resource_id).ok_or_else(|| {
        StoreError::InvalidInput(format!(
            "cwd resource {} is not bound to a durable Origins repository",
            request.cwd_resource_id
        ))
    })?;
    let cwd_relative = normalize_relative(&request.cwd_relative)?;
    if !plan.allows_resource_path(&request.cwd_resource_id, &cwd_relative, false)? {
        return Err(StoreError::Conflict(
            "cwd is outside current lease read authority".to_owned(),
        ));
    }
    let cwd = canonical_existing(cwd_root, &cwd_relative, true)?;

    let mut path_rules = BTreeMap::<PathBuf, bool>::new();
    for grant in grants(&lease, "resource_reads")? {
        let path = resolve_grant_path(&roots, &grant)?;
        path_rules.entry(path).or_insert(false);
    }
    for grant in grants(&lease, "resource_writes")? {
        let path = resolve_grant_path(&roots, &grant)?;
        path_rules.insert(path, true);
    }
    let deny_paths = grants(&lease, "resource_denies")?
        .into_iter()
        .map(|grant| resolve_grant_path(&roots, &grant))
        .collect::<Result<Vec<_>, _>>()?;

    let environment = request
        .invocation
        .environment_names
        .iter()
        .map(|name| {
            let value = env::var(name).map_err(|_| {
                StoreError::Conflict(format!(
                    "granted environment variable {name} is not present as UTF-8 on the host"
                ))
            })?;
            Ok((name.clone(), value))
        })
        .collect::<Result<BTreeMap<_, _>, StoreError>>()?;

    let sandbox = SandboxSpec {
        executable: executable.clone(),
        args: request.args.clone(),
        cwd,
        environment,
        runtime_read_paths: runtime_read_paths(&executable),
        resource_paths: path_rules
            .into_iter()
            .map(|(path, writable)| SandboxPathRule { path, writable })
            .collect(),
        deny_paths,
        network_mode: "deny".to_owned(),
    };
    sandbox
        .validate()
        .map_err(|error| StoreError::Conflict(error.to_string()))?;

    Ok(NativeProcessAdmission {
        lease_id: decision.lease_id,
        scope_id: decision.scope_id,
        sandbox,
        runtime_authority_activated: false,
    })
}

#[cfg(target_os = "linux")]
fn current_platform() -> Result<ContainmentPlatform, StoreError> {
    Ok(ContainmentPlatform::Linux)
}

#[cfg(windows)]
fn current_platform() -> Result<ContainmentPlatform, StoreError> {
    Ok(ContainmentPlatform::Windows)
}

#[cfg(not(any(target_os = "linux", windows)))]
fn current_platform() -> Result<ContainmentPlatform, StoreError> {
    Err(StoreError::Conflict(
        "native Stage-2 process admission is supported only on Linux and Windows".to_owned(),
    ))
}

fn resolve_resource_roots(
    store: &Store,
    process_policy: &ProcessPolicy,
    workspace_id: &str,
    lease: &Value,
) -> Result<BTreeMap<String, PathBuf>, StoreError> {
    let mut roots = BTreeMap::new();
    for field in ["resource_reads", "resource_writes", "resource_denies"] {
        for grant in grants(lease, field)? {
            if roots.contains_key(&grant.resource_id) {
                continue;
            }
            let repository_id = grant.resource_id.strip_prefix("worktree:").ok_or_else(|| {
                StoreError::Conflict(format!(
                    "native containment v1 supports durable worktree resources only: {}",
                    grant.resource_id
                ))
            })?;
            if repository_id.is_empty() {
                return Err(StoreError::InvalidInput(
                    "worktree resource id is missing repository id".to_owned(),
                ));
            }
            let repository = store.get_repository(repository_id)?;
            if required_string(&repository, "workspace_id")? != workspace_id {
                return Err(StoreError::Conflict(format!(
                    "repository {repository_id} belongs to a different workspace"
                )));
            }
            let root = std::fs::canonicalize(required_string(&repository, "worktree_root")?)
                .map_err(|error| {
                    StoreError::Conflict(format!(
                        "durable repository {repository_id} worktree root is unavailable: {error}"
                    ))
                })?;
            if !root.is_dir() || !process_policy.allows(&root) {
                return Err(StoreError::Conflict(format!(
                    "durable repository {repository_id} is outside Origins process policy"
                )));
            }
            roots.insert(grant.resource_id, root);
        }
    }
    Ok(roots)
}

fn resolve_grant_path(
    roots: &BTreeMap<String, PathBuf>,
    grant: &ResourceGrant,
) -> Result<PathBuf, StoreError> {
    let root = roots.get(&grant.resource_id).ok_or_else(|| {
        StoreError::Corrupt(format!("missing resolved root for {}", grant.resource_id))
    })?;
    canonical_existing(root, &normalize_relative(&grant.prefix)?, false)
}

fn canonical_existing(root: &Path, relative: &str, require_dir: bool) -> Result<PathBuf, StoreError> {
    let candidate = if relative.is_empty() {
        root.to_path_buf()
    } else {
        root.join(relative)
    };
    let canonical = std::fs::canonicalize(&candidate).map_err(|error| {
        StoreError::Conflict(format!(
            "native containment requires existing grant path {}: {error}",
            candidate.display()
        ))
    })?;
    if !canonical.starts_with(root) {
        return Err(StoreError::Conflict(
            "grant path escapes durable worktree root".to_owned(),
        ));
    }
    if require_dir && !canonical.is_dir() {
        return Err(StoreError::InvalidInput(
            "native process cwd must resolve to a directory".to_owned(),
        ));
    }
    Ok(canonical)
}

fn normalize_relative(value: &str) -> Result<String, StoreError> {
    if value.starts_with('/') || value.starts_with('\\') || value.contains('\\') {
        return Err(StoreError::InvalidInput(
            "native process paths must use relative slash form".to_owned(),
        ));
    }
    let mut parts = Vec::new();
    for component in Path::new(value).components() {
        match component {
            Component::Normal(part) => {
                let text = part.to_str().ok_or_else(|| {
                    StoreError::InvalidInput("native process path must be UTF-8".to_owned())
                })?;
                if text.contains(':') {
                    return Err(StoreError::InvalidInput(
                        "native process path contains a platform prefix".to_owned(),
                    ));
                }
                parts.push(text);
            }
            Component::CurDir => {}
            _ => {
                return Err(StoreError::InvalidInput(
                    "native process path traversal is forbidden".to_owned(),
                ))
            }
        }
    }
    Ok(parts.join("/"))
}

fn resolve_executable(executable: &str) -> Result<PathBuf, StoreError> {
    let path = env::var_os("PATH")
        .ok_or_else(|| StoreError::Conflict("host PATH is unavailable".to_owned()))?;
    for directory in env::split_paths(&path) {
        let direct = directory.join(executable);
        if let Some(path) = executable_candidate(&direct)? {
            return Ok(path);
        }
        #[cfg(windows)]
        if Path::new(executable).extension().is_none() {
            let candidate = directory.join(format!("{executable}.exe"));
            if let Some(path) = executable_candidate(&candidate)? {
                return Ok(path);
            }
        }
    }
    Err(StoreError::NotFound(format!(
        "allowed executable {executable} was not found on host PATH"
    )))
}

fn executable_candidate(candidate: &Path) -> Result<Option<PathBuf>, StoreError> {
    if !candidate.is_file() {
        return Ok(None);
    }
    let canonical = std::fs::canonicalize(candidate).map_err(|error| {
        StoreError::Conflict(format!(
            "host executable {} cannot be canonicalized: {error}",
            candidate.display()
        ))
    })?;
    Ok(Some(canonical))
}

fn runtime_read_paths(executable: &Path) -> Vec<PathBuf> {
    #[cfg(target_os = "linux")]
    {
        [
            "/lib",
            "/lib64",
            "/usr/lib",
            "/usr/lib64",
            "/etc/ld.so.cache",
            "/etc/ld.so.preload",
        ]
        .into_iter()
        .map(PathBuf::from)
        .filter(|path| path.exists())
        .collect()
    }
    #[cfg(windows)]
    {
        executable
            .parent()
            .map(Path::to_path_buf)
            .into_iter()
            .collect()
    }
    #[cfg(not(any(target_os = "linux", windows)))]
    {
        let _ = executable;
        Vec::new()
    }
}

fn validate_args(args: &[String]) -> Result<(), StoreError> {
    if args.len() > 256 {
        return Err(StoreError::InvalidInput(
            "native process args cannot contain more than 256 entries".to_owned(),
        ));
    }
    if args.iter().any(|arg| arg.chars().count() > 32_768) {
        return Err(StoreError::InvalidInput(
            "native process argument exceeds 32768 characters".to_owned(),
        ));
    }
    Ok(())
}

fn grants(value: &Value, field: &str) -> Result<Vec<ResourceGrant>, StoreError> {
    value[field]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt(format!("lease field {field} invalid")))?
        .iter()
        .map(|item| {
            serde_json::from_value::<ResourceGrant>(item.clone())
                .map_err(|error| StoreError::Corrupt(error.to_string()))
        })
        .collect()
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value[field]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| StoreError::Corrupt(format!("field {field} must be a non-empty string")))
}
