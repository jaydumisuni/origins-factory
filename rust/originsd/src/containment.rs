use crate::authority_runtime::{NetworkEndpoint, ResourceGrant};
use crate::store::StoreError;
use origins_authority_contracts::validate_authority_contract;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ContainmentPlatform {
    Linux,
    Windows,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContainmentPlan {
    pub platform: ContainmentPlatform,
    pub lease_id: String,
    pub lease_fence: u64,
    pub scope_id: String,
    pub filesystem_driver: String,
    pub process_tree_driver: String,
    pub network_driver: String,
    pub read_grants: Vec<ResourceGrant>,
    pub write_grants: Vec<ResourceGrant>,
    pub deny_grants: Vec<ResourceGrant>,
    pub network_mode: String,
    pub network_endpoints: Vec<NetworkEndpoint>,
    pub environment_names: Vec<String>,
    pub persistent_process_allowed: bool,
    pub fail_closed: bool,
    pub runtime_authority_activated: bool,
}

impl ContainmentPlan {
    pub fn from_lease(lease: &Value, platform: ContainmentPlatform) -> Result<Self, StoreError> {
        validate_authority_contract(lease)
            .map_err(|error| StoreError::InvalidInput(error.to_string()))?;
        if lease["contract_type"] != "capability_lease" {
            return Err(StoreError::InvalidInput(
                "containment plan requires capability_lease".to_owned(),
            ));
        }
        if lease["state"] != "active" {
            return Err(StoreError::Conflict(
                "containment plan requires active lease".to_owned(),
            ));
        }
        if lease["delegated_remote_authority"].as_bool() == Some(true)
            || lease["network_mode"] == "delegated_remote"
        {
            return Err(StoreError::Conflict(
                "local OS containment cannot represent delegated remote authority".to_owned(),
            ));
        }

        let network_mode = required_string(lease, "network_mode")?.to_owned();
        if network_mode != "deny" {
            return Err(StoreError::Conflict(
                "native containment v1 refuses network-capable leases; exact endpoint broker is not implemented"
                    .to_owned(),
            ));
        }
        let (filesystem_driver, process_tree_driver, network_driver) = match platform {
            ContainmentPlatform::Linux => (
                "linux.landlock.v1",
                "linux.setsid-process-group-fence.v1",
                "linux.seccomp-network-deny.v1",
            ),
            ContainmentPlatform::Windows => (
                "windows.appcontainer-acl.v1",
                "windows.job-object-kill-on-close.v1",
                "windows.appcontainer-network-deny.v1",
            ),
        };

        Ok(Self {
            platform,
            lease_id: required_string(lease, "lease_id")?.to_owned(),
            lease_fence: required_u64(lease, "fence")?,
            scope_id: required_string(lease, "scope_id")?.to_owned(),
            filesystem_driver: filesystem_driver.to_owned(),
            process_tree_driver: process_tree_driver.to_owned(),
            network_driver: network_driver.to_owned(),
            read_grants: grants(lease, "resource_reads")?,
            write_grants: grants(lease, "resource_writes")?,
            deny_grants: grants(lease, "resource_denies")?,
            network_mode,
            network_endpoints: endpoints(lease)?,
            environment_names: strings(lease, "environment_names")?,
            persistent_process_allowed: lease["persistent_process_allowed"]
                .as_bool()
                .ok_or_else(|| StoreError::Corrupt("lease persistent flag invalid".to_owned()))?,
            fail_closed: true,
            runtime_authority_activated: false,
        })
    }

    pub fn allows_resource_path(
        &self,
        resource_id: &str,
        relative_path: &str,
        write: bool,
    ) -> Result<bool, StoreError> {
        let path = normalize_relative_path(relative_path)?;
        if self
            .deny_grants
            .iter()
            .any(|grant| grant.resource_id == resource_id && prefix_covers(&grant.prefix, &path))
        {
            return Ok(false);
        }
        let grants = if write {
            &self.write_grants
        } else {
            &self.read_grants
        };
        Ok(grants
            .iter()
            .any(|grant| grant.resource_id == resource_id && prefix_covers(&grant.prefix, &path)))
    }

    pub fn allows_endpoint(&self, endpoint: &NetworkEndpoint) -> bool {
        match self.network_mode.as_str() {
            "deny" => false,
            "allowlist" => self.network_endpoints.contains(endpoint),
            _ => false,
        }
    }
}

pub fn validate_host_path(
    plan: &ContainmentPlan,
    resource_id: &str,
    resource_root: impl AsRef<Path>,
    relative_path: &str,
    write: bool,
) -> Result<PathBuf, StoreError> {
    if !plan.allows_resource_path(resource_id, relative_path, write)? {
        return Err(StoreError::Conflict(
            "resource path is outside lease containment grants".to_owned(),
        ));
    }
    let relative = normalize_relative_path(relative_path)?;
    let root = std::fs::canonicalize(resource_root.as_ref()).map_err(|error| {
        StoreError::InvalidInput(format!("resource root cannot be canonicalized: {error}"))
    })?;
    if !root.is_dir() {
        return Err(StoreError::InvalidInput(
            "resource root must be a directory".to_owned(),
        ));
    }
    let target = if relative.is_empty() {
        root.clone()
    } else {
        root.join(&relative)
    };

    // Existing parents are inspected without following symbolic links. For a write target that does
    // not yet exist, the nearest existing parent must still remain inside the canonical resource root.
    let mut cursor = root.clone();
    for component in Path::new(&relative).components() {
        let Component::Normal(part) = component else {
            return Err(StoreError::InvalidInput(
                "resource path contains non-normal component".to_owned(),
            ));
        };
        cursor.push(part);
        match std::fs::symlink_metadata(&cursor) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink() {
                    return Err(StoreError::Conflict(
                        "symbolic-link/reparse traversal is forbidden by containment".to_owned(),
                    ));
                }
                if !metadata.is_dir() && !metadata.is_file() {
                    return Err(StoreError::Conflict(
                        "special filesystem objects are forbidden by containment".to_owned(),
                    ));
                }
                let canonical = std::fs::canonicalize(&cursor).map_err(|error| {
                    StoreError::InvalidInput(format!(
                        "resource path cannot be canonicalized: {error}"
                    ))
                })?;
                if !canonical.starts_with(&root) {
                    return Err(StoreError::Conflict(
                        "resource path escapes canonical resource root".to_owned(),
                    ));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound && write => break,
            Err(error) => {
                return Err(StoreError::InvalidInput(format!(
                    "resource path cannot be inspected: {error}"
                )))
            }
        }
    }
    if target.exists() {
        let canonical = std::fs::canonicalize(&target).map_err(|error| {
            StoreError::InvalidInput(format!("resource target cannot be canonicalized: {error}"))
        })?;
        if !canonical.starts_with(&root) {
            return Err(StoreError::Conflict(
                "resource target escapes canonical resource root".to_owned(),
            ));
        }
        Ok(canonical)
    } else if write {
        Ok(target)
    } else {
        Err(StoreError::NotFound(format!(
            "resource path {}",
            target.display()
        )))
    }
}

pub trait ProcessTreeFence: Send + Sync {
    fn terminate(&self) -> Result<(), String>;
}

#[derive(Clone, Default)]
pub struct RevocationCoordinator {
    inner: Arc<Mutex<BTreeMap<String, Vec<BoundProcessTree>>>>,
}

#[derive(Clone)]
struct BoundProcessTree {
    scope_id: String,
    fence: Arc<dyn ProcessTreeFence>,
}

impl RevocationCoordinator {
    pub fn register(
        &self,
        lease_id: &str,
        scope_id: &str,
        fence: Arc<dyn ProcessTreeFence>,
    ) -> Result<(), StoreError> {
        if lease_id.is_empty() || scope_id.is_empty() {
            return Err(StoreError::InvalidInput(
                "lease_id and scope_id are required for process containment".to_owned(),
            ));
        }
        let mut inner = self
            .inner
            .lock()
            .map_err(|_| StoreError::Corrupt("revocation coordinator lock poisoned".to_owned()))?;
        inner
            .entry(lease_id.to_owned())
            .or_default()
            .push(BoundProcessTree {
                scope_id: scope_id.to_owned(),
                fence,
            });
        Ok(())
    }

    pub fn revoke_lease(&self, lease_id: &str) -> Result<u64, StoreError> {
        let targets = self
            .inner
            .lock()
            .map_err(|_| StoreError::Corrupt("revocation coordinator lock poisoned".to_owned()))?
            .remove(lease_id)
            .unwrap_or_default();
        terminate_targets(targets)
    }

    pub fn revoke_scope(&self, scope_id: &str) -> Result<u64, StoreError> {
        let targets = {
            let mut inner = self.inner.lock().map_err(|_| {
                StoreError::Corrupt("revocation coordinator lock poisoned".to_owned())
            })?;
            let keys = inner
                .iter()
                .filter(|(_, targets)| targets.iter().any(|target| target.scope_id == scope_id))
                .map(|(lease_id, _)| lease_id.clone())
                .collect::<Vec<_>>();
            let mut collected = Vec::new();
            for key in keys {
                if let Some(mut values) = inner.remove(&key) {
                    collected.append(&mut values);
                }
            }
            collected
        };
        terminate_targets(targets)
    }
}

fn terminate_targets(targets: Vec<BoundProcessTree>) -> Result<u64, StoreError> {
    let mut terminated = 0_u64;
    let mut failures = Vec::new();
    for target in targets {
        match target.fence.terminate() {
            Ok(()) => terminated += 1,
            Err(error) => failures.push(error),
        }
    }
    if failures.is_empty() {
        Ok(terminated)
    } else {
        Err(StoreError::Conflict(format!(
            "process-tree revocation failed closed: {}",
            failures.join("; ")
        )))
    }
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

fn endpoints(value: &Value) -> Result<Vec<NetworkEndpoint>, StoreError> {
    value["network_endpoints"]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt("lease network_endpoints invalid".to_owned()))?
        .iter()
        .map(|item| {
            serde_json::from_value::<NetworkEndpoint>(item.clone())
                .map_err(|error| StoreError::Corrupt(error.to_string()))
        })
        .collect()
}

fn strings(value: &Value, field: &str) -> Result<Vec<String>, StoreError> {
    value[field]
        .as_array()
        .ok_or_else(|| StoreError::Corrupt(format!("lease field {field} invalid")))?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_owned)
                .ok_or_else(|| StoreError::Corrupt(format!("lease field {field} invalid")))
        })
        .collect()
}

fn normalize_relative_path(path: &str) -> Result<String, StoreError> {
    if path.starts_with('/') || path.starts_with('\\') || path.contains('\\') {
        return Err(StoreError::InvalidInput(
            "resource path must be canonical relative slash form".to_owned(),
        ));
    }
    let mut parts = Vec::new();
    for part in path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." || part.contains(':') {
            return Err(StoreError::InvalidInput(
                "resource path traversal/prefix is forbidden".to_owned(),
            ));
        }
        parts.push(part);
    }
    Ok(parts.join("/"))
}

fn prefix_covers(prefix: &str, path: &str) -> bool {
    if prefix.is_empty() {
        return true;
    }
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value[field]
        .as_str()
        .ok_or_else(|| StoreError::Corrupt(format!("lease field {field} invalid")))
}

fn required_u64(value: &Value, field: &str) -> Result<u64, StoreError> {
    value[field]
        .as_u64()
        .ok_or_else(|| StoreError::Corrupt(format!("lease field {field} invalid")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicU64, Ordering};

    fn lease() -> Value {
        json!({
            "contract_type":"capability_lease","schema_version":"1.1.0",
            "lease_id":"44444444-4444-4444-8444-444444444444",
            "scope_id":"22222222-2222-4222-8222-222222222222",
            "workspace_id":"11111111-1111-4111-8111-111111111111",
            "capability_id":"origins.process.run",
            "provider_id":"origins.process.local",
            "provider_manifest_digest":"2222222222222222222222222222222222222222222222222222222222222222",
            "provider_generation":1,
            "holder_kind":"session","holder_id":"55555555-5555-4555-8555-555555555555","holder_generation":1,
            "effects":["execute","observe"],
            "resource_reads":[{"resource_id":"worktree:33333333-3333-4333-8333-333333333333","prefix":"src"}],
            "resource_writes":[],
            "resource_denies":[{"resource_id":"worktree:33333333-3333-4333-8333-333333333333","prefix":"src/private"}],
            "network_mode":"deny","network_endpoints":[],"network_redirect_policy":"deny_outside_endpoints",
            "environment_names":["LANG"],"persistent_process_allowed":false,"delegated_remote_authority":false,
            "approval_authority":"jaydumisuni/Hunter-AgentOps","approval_id":"approval-42",
            "approval_digest":"0000000000000000000000000000000000000000000000000000000000000000",
            "proposal_digest":"1111111111111111111111111111111111111111111111111111111111111111",
            "state":"active","fence":1,"issued_at":"2026-08-09T12:05:00Z","updated_at":"2026-08-09T12:05:00Z",
            "expires_at":"2026-08-09T13:00:00Z","revision":1
        })
    }

    #[test]
    fn linux_and_windows_plans_are_fail_closed() {
        let lease = lease();
        let linux = ContainmentPlan::from_lease(&lease, ContainmentPlatform::Linux).unwrap();
        let windows = ContainmentPlan::from_lease(&lease, ContainmentPlatform::Windows).unwrap();
        assert!(linux.fail_closed && windows.fail_closed);
        assert_eq!(linux.filesystem_driver, "linux.landlock.v1");
        assert_eq!(linux.process_tree_driver, "linux.setsid-process-group-fence.v1");
        assert_eq!(linux.network_driver, "linux.seccomp-network-deny.v1");
        assert_eq!(
            windows.network_driver,
            "windows.appcontainer-network-deny.v1"
        );
        assert!(!linux.runtime_authority_activated && !windows.runtime_authority_activated);
        assert!(linux
            .allows_resource_path(
                "worktree:33333333-3333-4333-8333-333333333333",
                "src/main.rs",
                false
            )
            .unwrap());
        assert!(!linux
            .allows_resource_path(
                "worktree:33333333-3333-4333-8333-333333333333",
                "src/private/key",
                false
            )
            .unwrap());
    }

    struct FakeFence(Arc<AtomicU64>);
    impl ProcessTreeFence for FakeFence {
        fn terminate(&self) -> Result<(), String> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    #[test]
    fn scope_revocation_terminates_registered_process_trees() {
        let counter = Arc::new(AtomicU64::new(0));
        let coordinator = RevocationCoordinator::default();
        coordinator
            .register("lease-a", "scope-a", Arc::new(FakeFence(counter.clone())))
            .unwrap();
        coordinator
            .register("lease-b", "scope-a", Arc::new(FakeFence(counter.clone())))
            .unwrap();
        assert_eq!(coordinator.revoke_scope("scope-a").unwrap(), 2);
        assert_eq!(counter.load(Ordering::SeqCst), 2);
        assert_eq!(coordinator.revoke_scope("scope-a").unwrap(), 0);
    }
}
