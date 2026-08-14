use crate::store::{append_event, Store, StoreError};
use crate::workspace_roots::WorkspaceRootPolicy;
use rusqlite::TransactionBehavior;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Component, Path, PathBuf};

pub const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024;
pub const MAX_LIST_ENTRIES: usize = 2_000;

#[derive(Debug, Clone)]
pub struct WorkspaceFileError {
    pub code: &'static str,
    pub message: String,
}

impl WorkspaceFileError {
    fn invalid(message: impl Into<String>) -> Self {
        Self { code: "INVALID_PATH", message: message.into() }
    }

    fn too_large(message: impl Into<String>) -> Self {
        Self { code: "FILE_TOO_LARGE", message: message.into() }
    }

    fn unsupported(message: impl Into<String>) -> Self {
        Self { code: "UNSUPPORTED_FILE", message: message.into() }
    }

    fn io(message: impl Into<String>) -> Self {
        Self { code: "FILE_IO_ERROR", message: message.into() }
    }

    fn store(error: StoreError) -> Self {
        Self { code: "STORE_ERROR", message: error.to_string() }
    }
}

pub fn list_repository_files(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
    relative_dir: &str,
) -> Result<Value, WorkspaceFileError> {
    let root = repository_root(store, policy, repository_id)?;
    let requested = existing_path_under_root(&root, relative_dir)?;
    if !requested.is_dir() {
        return Err(WorkspaceFileError::invalid("requested repository path is not a directory"));
    }

    let mut entries = Vec::new();
    for item in fs::read_dir(&requested).map_err(|error| WorkspaceFileError::io(error.to_string()))? {
        if entries.len() >= MAX_LIST_ENTRIES {
            break;
        }
        let item = item.map_err(|error| WorkspaceFileError::io(error.to_string()))?;
        let name = item.file_name().to_string_lossy().to_string();
        if ignored_name(&name) {
            continue;
        }
        let file_type = item.file_type().map_err(|error| WorkspaceFileError::io(error.to_string()))?;
        if file_type.is_symlink() {
            continue;
        }
        let path = item.path();
        let relative = path.strip_prefix(&root)
            .map_err(|_| WorkspaceFileError::invalid("repository entry escaped root"))?
            .to_string_lossy()
            .replace('\\', "/");
        let metadata = item.metadata().map_err(|error| WorkspaceFileError::io(error.to_string()))?;
        entries.push(json!({
            "name": name,
            "path": relative,
            "kind": if file_type.is_dir() { "directory" } else if file_type.is_file() { "file" } else { "other" },
            "bytes": if file_type.is_file() { Some(metadata.len()) } else { None },
        }));
    }
    entries.sort_by(|left, right| {
        let left_kind = left["kind"].as_str().unwrap_or("other");
        let right_kind = right["kind"].as_str().unwrap_or("other");
        let rank = |kind: &str| if kind == "directory" { 0 } else { 1 };
        rank(left_kind).cmp(&rank(right_kind)).then_with(|| {
            left["name"].as_str().unwrap_or("").cmp(right["name"].as_str().unwrap_or(""))
        })
    });

    Ok(json!({
        "repository_id": repository_id,
        "path": normalize_relative(relative_dir)?,
        "entries": entries,
        "truncated": entries.len() >= MAX_LIST_ENTRIES,
        "max_entries": MAX_LIST_ENTRIES,
    }))
}

pub fn read_repository_file(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
    relative_path: &str,
) -> Result<Value, WorkspaceFileError> {
    let root = repository_root(store, policy, repository_id)?;
    let path = existing_path_under_root(&root, relative_path)?;
    let metadata = fs::symlink_metadata(&path).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(WorkspaceFileError::unsupported("editor reads regular non-symlink files only"));
    }
    if metadata.len() > MAX_FILE_BYTES {
        return Err(WorkspaceFileError::too_large(format!(
            "file is {} bytes; editor limit is {MAX_FILE_BYTES}", metadata.len()
        )));
    }
    let bytes = fs::read(&path).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
    let sha256 = sha256_bytes(&bytes);
    let text = String::from_utf8(bytes).ok();
    Ok(json!({
        "repository_id": repository_id,
        "path": normalize_relative(relative_path)?,
        "bytes": metadata.len(),
        "sha256": sha256,
        "utf8": text.is_some(),
        "text": text,
        "editable": text.is_some(),
        "max_bytes": MAX_FILE_BYTES,
    }))
}

pub fn write_repository_file(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
    relative_path: &str,
    text: &str,
    expected_sha256: Option<&str>,
) -> Result<Value, WorkspaceFileError> {
    let bytes = text.as_bytes();
    if bytes.len() as u64 > MAX_FILE_BYTES {
        return Err(WorkspaceFileError::too_large(format!(
            "content is {} bytes; editor limit is {MAX_FILE_BYTES}", bytes.len()
        )));
    }
    let root = repository_root(store, policy, repository_id)?;
    let normalized = normalize_relative(relative_path)?;
    if normalized.is_empty() {
        return Err(WorkspaceFileError::invalid("file path is required"));
    }
    let candidate = root.join(Path::new(&normalized));
    let parent = candidate.parent().ok_or_else(|| WorkspaceFileError::invalid("file parent is required"))?;
    let canonical_parent = fs::canonicalize(parent).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
    if !canonical_parent.starts_with(&root) {
        return Err(WorkspaceFileError::invalid("file parent escaped repository root"));
    }

    if candidate.exists() {
        let metadata = fs::symlink_metadata(&candidate).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(WorkspaceFileError::unsupported("editor writes regular non-symlink files only"));
        }
        let canonical = fs::canonicalize(&candidate).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
        if !canonical.starts_with(&root) {
            return Err(WorkspaceFileError::invalid("file escaped repository root"));
        }
        if let Some(expected) = expected_sha256.filter(|value| !value.trim().is_empty()) {
            let current = fs::read(&candidate).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
            let actual = sha256_bytes(&current);
            if actual != expected {
                return Err(WorkspaceFileError {
                    code: "FILE_CHANGED",
                    message: "file changed since it was opened; reload before overwriting".to_owned(),
                });
            }
        }
    } else if expected_sha256.is_some_and(|value| !value.trim().is_empty()) {
        return Err(WorkspaceFileError {
            code: "FILE_CHANGED",
            message: "file no longer exists; reload before writing".to_owned(),
        });
    }

    fs::write(&candidate, bytes).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
    let sha256 = sha256_bytes(bytes);
    let repository = store.get_repository(repository_id).map_err(WorkspaceFileError::store)?;
    let workspace_id = repository["workspace_id"]
        .as_str()
        .ok_or_else(|| WorkspaceFileError::store(StoreError::Corrupt("repository workspace_id missing".to_owned())))?;
    let mut connection = store.connection().map_err(WorkspaceFileError::store)?;
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate).map_err(StoreError::from).map_err(WorkspaceFileError::store)?;
    let event = append_event(
        &transaction,
        workspace_id,
        "workspace.file_written",
        json!({
            "repository_id": repository_id,
            "path": normalized,
            "bytes": bytes.len(),
            "sha256": sha256,
        }),
        Vec::new(),
    ).map_err(WorkspaceFileError::store)?;
    transaction.commit().map_err(StoreError::from).map_err(WorkspaceFileError::store)?;

    Ok(json!({
        "repository_id": repository_id,
        "path": normalized,
        "bytes": bytes.len(),
        "sha256": sha256,
        "event": event,
    }))
}

fn repository_root(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
) -> Result<PathBuf, WorkspaceFileError> {
    let repository = store.get_repository(repository_id).map_err(WorkspaceFileError::store)?;
    let root = repository["worktree_root"].as_str()
        .ok_or_else(|| WorkspaceFileError::store(StoreError::Corrupt("repository worktree_root missing".to_owned())))?;
    let canonical = policy.authorize_existing_dir(root).map_err(WorkspaceFileError::invalid)?;
    Ok(canonical)
}

fn existing_path_under_root(root: &Path, relative: &str) -> Result<PathBuf, WorkspaceFileError> {
    let normalized = normalize_relative(relative)?;
    let candidate = if normalized.is_empty() { root.to_path_buf() } else { root.join(Path::new(&normalized)) };
    let canonical = fs::canonicalize(&candidate).map_err(|error| WorkspaceFileError::io(error.to_string()))?;
    if !canonical.starts_with(root) {
        return Err(WorkspaceFileError::invalid("path escaped repository root"));
    }
    Ok(canonical)
}

fn normalize_relative(value: &str) -> Result<String, WorkspaceFileError> {
    let path = Path::new(value.trim());
    if path.is_absolute() {
        return Err(WorkspaceFileError::invalid("absolute paths are not accepted"));
    }
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(value) => parts.push(value.to_string_lossy().to_string()),
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(WorkspaceFileError::invalid("parent/root/prefix path components are not accepted"));
            }
        }
    }
    Ok(parts.join("/"))
}

fn ignored_name(name: &str) -> bool {
    matches!(name, ".git" | ".origins" | "node_modules" | "target")
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_normalization_rejects_escape() {
        assert_eq!(normalize_relative("src/main.rs").unwrap(), "src/main.rs");
        assert_eq!(normalize_relative("./src/main.rs").unwrap(), "src/main.rs");
        assert!(normalize_relative("../outside").is_err());
    }

    #[test]
    fn ignored_heavy_or_internal_directories_are_explicit() {
        assert!(ignored_name(".git"));
        assert!(ignored_name("node_modules"));
        assert!(!ignored_name("src"));
    }
}
