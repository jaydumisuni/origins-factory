use std::env;
use std::path::{Path, PathBuf};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct WorkspaceRootPolicy {
    allowed_roots: Arc<[PathBuf]>,
}

impl WorkspaceRootPolicy {
    pub fn from_env() -> Result<Self, String> {
        let candidates = match env::var_os("ORIGINS_WORKSPACE_ROOTS") {
            Some(raw) => env::split_paths(&raw).collect::<Vec<_>>(),
            None => vec![env::current_dir().map_err(|error| {
                format!("cannot determine default Origins workspace root: {error}")
            })?],
        };
        if candidates.is_empty() {
            return Err("ORIGINS_WORKSPACE_ROOTS must contain at least one path".to_owned());
        }

        let mut roots = Vec::new();
        for candidate in candidates {
            if candidate.as_os_str().is_empty() {
                continue;
            }
            let canonical = std::fs::canonicalize(&candidate).map_err(|error| {
                format!(
                    "configured Origins workspace root {:?} cannot be resolved: {error}",
                    candidate
                )
            })?;
            if !canonical.is_dir() {
                return Err(format!(
                    "configured Origins workspace root {:?} is not a directory",
                    canonical
                ));
            }
            roots.push(canonical);
        }
        roots.sort();
        roots.dedup();
        if roots.is_empty() {
            return Err("ORIGINS_WORKSPACE_ROOTS resolved to no usable directories".to_owned());
        }
        Ok(Self {
            allowed_roots: Arc::from(roots),
        })
    }

    pub fn allows(&self, path: &Path) -> bool {
        self.allowed_roots.iter().any(|root| path.starts_with(root))
    }

    pub fn authorize_existing_dir(&self, path: impl AsRef<Path>) -> Result<PathBuf, String> {
        let canonical = std::fs::canonicalize(path.as_ref()).map_err(|error| {
            format!("Workspace path {:?} cannot be resolved: {error}", path.as_ref())
        })?;
        if !canonical.is_dir() {
            return Err(format!("Workspace path {:?} is not a directory", canonical));
        }
        if !self.allows(&canonical) {
            return Err(format!(
                "Workspace path {:?} is outside configured ORIGINS_WORKSPACE_ROOTS",
                canonical
            ));
        }
        Ok(canonical)
    }
}
