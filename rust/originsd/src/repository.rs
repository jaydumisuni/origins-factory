use crate::store::{append_event, now_rfc3339, verify_stored_contract, Store, StoreError};
use crate::workspace_roots::WorkspaceRootPolicy;
use origins_contracts::{canonical_json, contract_sha256, validate_contract};
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::io::{AsyncRead, AsyncReadExt};
use tokio::process::Command;
use uuid::Uuid;

const REPOSITORY_SCHEMA_VERSION: i64 = 1;
const METADATA_RETAIN_BYTES: usize = 128 * 1024;
const MAX_STATUS_BYTES: usize = 8 * 1024 * 1024;
pub const DEFAULT_DIFF_RETAIN_BYTES: usize = 512 * 1024;
pub const MAX_DIFF_RETAIN_BYTES: usize = 8 * 1024 * 1024;

#[derive(Debug, Clone)]
pub struct RepositoryDiff {
    pub repository: Value,
    pub kind: String,
    pub retained: Vec<u8>,
    pub complete_bytes: u64,
    pub sha256: String,
    pub truncated: bool,
}

#[derive(Debug)]
struct GitCapture {
    success: bool,
    stdout: CapturedStream,
    stderr: CapturedStream,
}

#[derive(Debug)]
struct CapturedStream {
    retained: Vec<u8>,
    total_bytes: u64,
    sha256: String,
    truncated: bool,
}

pub fn initialize(store: &Store) -> Result<(), StoreError> {
    let connection = store.connection()?;
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS repository_meta (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS repositories (
            repository_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            worktree_root TEXT NOT NULL,
            projection_json TEXT NOT NULL,
            projection_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            UNIQUE (workspace_id, worktree_root),
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
         );",
    )?;
    let current: Option<String> = connection
        .query_row(
            "SELECT value FROM repository_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    let version = match current {
        Some(value) => value.parse::<i64>().map_err(|_| {
            StoreError::Corrupt("invalid repository subsystem schema version".to_owned())
        })?,
        None => 0,
    };
    if version > REPOSITORY_SCHEMA_VERSION {
        return Err(StoreError::Corrupt(format!(
            "unsupported newer repository subsystem schema version {version}; current is {REPOSITORY_SCHEMA_VERSION}"
        )));
    }
    if version != REPOSITORY_SCHEMA_VERSION {
        connection.execute(
            "INSERT INTO repository_meta (key, value) VALUES ('schema_version', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [REPOSITORY_SCHEMA_VERSION.to_string()],
        )?;
    }
    Ok(())
}

impl Store {
    pub fn repository_schema_version(&self) -> Result<i64, StoreError> {
        let connection = self.connection()?;
        let value: String = connection.query_row(
            "SELECT value FROM repository_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )?;
        value.parse().map_err(|_| {
            StoreError::Corrupt("invalid repository subsystem schema version".to_owned())
        })
    }

    pub fn repository_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM repositories", [], |row| row.get(0))?;
        u64::try_from(count)
            .map_err(|_| StoreError::Corrupt("negative repository count".to_owned()))
    }

    pub fn get_repository(&self, repository_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        let stored: Option<(String, String)> = connection
            .query_row(
                "SELECT projection_json, projection_sha256 FROM repositories WHERE repository_id = ?1",
                [repository_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (canonical, digest) = stored
            .ok_or_else(|| StoreError::NotFound(format!("repository {repository_id}")))?;
        verify_stored_contract("repository", repository_id, &canonical, &digest)
    }

    pub fn list_repositories(&self, workspace_id: Option<&str>) -> Result<Vec<Value>, StoreError> {
        let connection = self.connection()?;
        let sql = if workspace_id.is_some() {
            "SELECT repository_id, projection_json, projection_sha256 FROM repositories
             WHERE workspace_id = ?1 ORDER BY worktree_root"
        } else {
            "SELECT repository_id, projection_json, projection_sha256 FROM repositories
             ORDER BY workspace_id, worktree_root"
        };
        let mut statement = connection.prepare(sql)?;
        let mut result = Vec::new();
        if let Some(workspace_id) = workspace_id {
            let rows = statement.query_map([workspace_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })?;
            for row in rows {
                let (repository_id, canonical, digest) = row?;
                result.push(verify_stored_contract(
                    "repository",
                    &repository_id,
                    &canonical,
                    &digest,
                )?);
            }
        } else {
            let rows = statement.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })?;
            for row in rows {
                let (repository_id, canonical, digest) = row?;
                result.push(verify_stored_contract(
                    "repository",
                    &repository_id,
                    &canonical,
                    &digest,
                )?);
            }
        }
        Ok(result)
    }

    fn upsert_repository_observation(
        &self,
        workspace_id: &str,
        observation: RepositoryObservation,
    ) -> Result<Value, StoreError> {
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let existing: Option<(String, i64)> = transaction
            .query_row(
                "SELECT repository_id, revision FROM repositories
                 WHERE workspace_id = ?1 AND worktree_root = ?2",
                params![workspace_id, observation.worktree_root],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let (repository_id, revision) = match existing {
            Some((repository_id, revision)) => (repository_id, revision + 1),
            None => (Uuid::new_v4().hyphenated().to_string(), 1),
        };
        let revision_u64 = u64::try_from(revision)
            .map_err(|_| StoreError::Corrupt("invalid repository revision".to_owned()))?;
        let observed_at = now_rfc3339();
        let projection = json!({
            "contract_type": "repository_projection",
            "schema_version": "1.0.0",
            "repository_id": repository_id,
            "workspace_id": workspace_id,
            "revision": revision_u64,
            "worktree_root": observation.worktree_root,
            "git_dir": observation.git_dir,
            "common_dir": observation.common_dir,
            "head_oid": observation.head_oid,
            "head_ref": observation.head_ref,
            "branch": observation.branch,
            "detached": observation.detached,
            "unborn": observation.unborn,
            "staged_count": observation.staged_count,
            "unstaged_count": observation.unstaged_count,
            "untracked_count": observation.untracked_count,
            "status_sha256": observation.status_sha256,
            "observed_at": observed_at,
        });
        validate_contract(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let canonical =
            canonical_json(&projection).map_err(|error| StoreError::Contract(error.to_string()))?;
        let digest = contract_sha256(&projection)
            .map_err(|error| StoreError::Contract(error.to_string()))?;
        transaction.execute(
            "INSERT INTO repositories (
                repository_id, workspace_id, worktree_root, projection_json,
                projection_sha256, revision, observed_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
             ON CONFLICT(workspace_id, worktree_root) DO UPDATE SET
                projection_json = excluded.projection_json,
                projection_sha256 = excluded.projection_sha256,
                revision = excluded.revision,
                observed_at = excluded.observed_at",
            params![
                projection["repository_id"].as_str(),
                workspace_id,
                projection["worktree_root"].as_str(),
                canonical,
                digest,
                revision,
                observed_at,
            ],
        )?;
        append_event(
            &transaction,
            workspace_id,
            "repository.observed",
            json!({
                "repository_id": projection["repository_id"],
                "revision": revision_u64,
                "head_oid": projection["head_oid"],
                "status_sha256": projection["status_sha256"],
                "staged_count": projection["staged_count"],
                "unstaged_count": projection["unstaged_count"],
                "untracked_count": projection["untracked_count"],
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(projection)
    }

    fn record_repository_diff(
        &self,
        repository: &Value,
        kind: &str,
        complete_bytes: u64,
        sha256: &str,
        truncated: bool,
    ) -> Result<(), StoreError> {
        let workspace_id = required_projection_string(repository, "workspace_id")?;
        let repository_id = required_projection_string(repository, "repository_id")?;
        let mut connection = self.connection()?;
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        append_event(
            &transaction,
            workspace_id,
            "repository.diff_observed",
            json!({
                "repository_id": repository_id,
                "kind": kind,
                "complete_bytes": complete_bytes,
                "sha256": sha256,
                "truncated": truncated,
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        Ok(())
    }
}

#[derive(Debug)]
struct RepositoryObservation {
    worktree_root: String,
    git_dir: String,
    common_dir: String,
    head_oid: String,
    head_ref: String,
    branch: String,
    detached: bool,
    unborn: bool,
    staged_count: u64,
    unstaged_count: u64,
    untracked_count: u64,
    status_sha256: String,
}

pub async fn inspect_repository(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    workspace_id: &str,
    requested_path: &str,
) -> Result<Value, StoreError> {
    if !store.workspace_exists(workspace_id)? {
        return Err(StoreError::NotFound(format!("workspace {workspace_id}")));
    }
    let requested = policy
        .authorize_existing_dir(requested_path)
        .map_err(StoreError::InvalidInput)?;
    let worktree_text = git_text(&requested, &["rev-parse", "--show-toplevel"]).await?;
    let worktree = policy
        .authorize_existing_dir(&worktree_text)
        .map_err(StoreError::InvalidInput)?;
    let git_dir_text = git_text(&worktree, &["rev-parse", "--absolute-git-dir"]).await?;
    let git_dir = canonical_git_path(&worktree, &git_dir_text)?;
    let common_dir_text = git_text(&worktree, &["rev-parse", "--git-common-dir"]).await?;
    let common_dir = canonical_git_path(&worktree, &common_dir_text)?;

    let head_run = run_git(&worktree, &["rev-parse", "--verify", "HEAD"], METADATA_RETAIN_BYTES).await?;
    let head_oid = if head_run.success {
        capture_text(&head_run.stdout, "HEAD oid")?
    } else {
        String::new()
    };
    let head_ref_run = run_git(&worktree, &["symbolic-ref", "-q", "HEAD"], METADATA_RETAIN_BYTES).await?;
    let head_ref = if head_ref_run.success {
        capture_text(&head_ref_run.stdout, "HEAD ref")?
    } else {
        String::new()
    };
    let unborn = head_oid.is_empty();
    if unborn && head_ref.is_empty() {
        return Err(StoreError::InvalidInput(
            "repository HEAD cannot be resolved as either an unborn symbolic ref or a commit"
                .to_owned(),
        ));
    }
    let detached = !unborn && head_ref.is_empty();
    let branch = head_ref
        .strip_prefix("refs/heads/")
        .unwrap_or("")
        .to_owned();

    let status = run_git(
        &worktree,
        &["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        MAX_STATUS_BYTES,
    )
    .await?;
    require_git_success(&status, "git status")?;
    if status.stdout.truncated {
        return Err(StoreError::InvalidInput(format!(
            "repository status exceeds the {MAX_STATUS_BYTES}-byte v1 inspection bound"
        )));
    }
    let (staged_count, unstaged_count, untracked_count) = parse_porcelain_status(&status.stdout.retained)?;

    let observation = RepositoryObservation {
        worktree_root: path_text(&worktree, "worktree root")?,
        git_dir: path_text(&git_dir, "git directory")?,
        common_dir: path_text(&common_dir, "git common directory")?,
        head_oid,
        head_ref,
        branch,
        detached,
        unborn,
        staged_count,
        unstaged_count,
        untracked_count,
        status_sha256: status.stdout.sha256,
    };
    store.upsert_repository_observation(workspace_id, observation)
}

pub async fn refresh_repository(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
) -> Result<Value, StoreError> {
    let stored = store.get_repository(repository_id)?;
    let workspace_id = required_projection_string(&stored, "workspace_id")?.to_owned();
    let worktree_root = required_projection_string(&stored, "worktree_root")?.to_owned();
    inspect_repository(store, policy, &workspace_id, &worktree_root).await
}

pub async fn repository_diff(
    store: &Store,
    policy: &WorkspaceRootPolicy,
    repository_id: &str,
    kind: &str,
    retain_limit: usize,
) -> Result<RepositoryDiff, StoreError> {
    if retain_limit == 0 || retain_limit > MAX_DIFF_RETAIN_BYTES {
        return Err(StoreError::InvalidInput(format!(
            "diff limit must be between 1 and {MAX_DIFF_RETAIN_BYTES} bytes"
        )));
    }
    let repository = refresh_repository(store, policy, repository_id).await?;
    let worktree = PathBuf::from(required_projection_string(&repository, "worktree_root")?);
    let args: &[&str] = match kind {
        "unstaged" => &["diff", "--no-ext-diff", "--binary", "--no-color", "--full-index", "--"],
        "staged" => &[
            "diff",
            "--cached",
            "--no-ext-diff",
            "--binary",
            "--no-color",
            "--full-index",
            "--",
        ],
        _ => {
            return Err(StoreError::InvalidInput(
                "diff kind must be staged or unstaged".to_owned(),
            ))
        }
    };
    let capture = run_git(&worktree, args, retain_limit).await?;
    require_git_success(&capture, "git diff")?;
    let diff = RepositoryDiff {
        repository,
        kind: kind.to_owned(),
        retained: capture.stdout.retained,
        complete_bytes: capture.stdout.total_bytes,
        sha256: capture.stdout.sha256,
        truncated: capture.stdout.truncated,
    };
    store.record_repository_diff(
        &diff.repository,
        &diff.kind,
        diff.complete_bytes,
        &diff.sha256,
        diff.truncated,
    )?;
    Ok(diff)
}

fn parse_porcelain_status(bytes: &[u8]) -> Result<(u64, u64, u64), StoreError> {
    let mut staged = 0_u64;
    let mut unstaged = 0_u64;
    let mut untracked = 0_u64;
    let mut index = 0_usize;
    while index < bytes.len() {
        if index + 3 > bytes.len() || bytes[index + 2] != b' ' {
            return Err(StoreError::Corrupt(
                "Git porcelain v1 status record is malformed".to_owned(),
            ));
        }
        let x = bytes[index];
        let y = bytes[index + 1];
        let end = bytes[index + 3..]
            .iter()
            .position(|byte| *byte == 0)
            .map(|offset| index + 3 + offset)
            .ok_or_else(|| StoreError::Corrupt("Git status record lacks NUL terminator".to_owned()))?;
        if x == b'?' && y == b'?' {
            untracked += 1;
        } else {
            if x != b' ' {
                staged += 1;
            }
            if y != b' ' {
                unstaged += 1;
            }
        }
        index = end + 1;
        if matches!(x, b'R' | b'C') || matches!(y, b'R' | b'C') {
            let second_end = bytes[index..]
                .iter()
                .position(|byte| *byte == 0)
                .map(|offset| index + offset)
                .ok_or_else(|| {
                    StoreError::Corrupt("Git rename/copy status lacks second NUL path".to_owned())
                })?;
            index = second_end + 1;
        }
    }
    Ok((staged, unstaged, untracked))
}

async fn git_text(cwd: &Path, args: &[&str]) -> Result<String, StoreError> {
    let run = run_git(cwd, args, METADATA_RETAIN_BYTES).await?;
    require_git_success(&run, "git metadata read")?;
    capture_text(&run.stdout, "git metadata")
}

fn capture_text(capture: &CapturedStream, label: &str) -> Result<String, StoreError> {
    if capture.truncated {
        return Err(StoreError::InvalidInput(format!(
            "{label} exceeds the metadata capture bound"
        )));
    }
    let text = std::str::from_utf8(&capture.retained)
        .map_err(|_| StoreError::InvalidInput(format!("{label} is not valid UTF-8")))?;
    Ok(text.trim_end_matches(['\r', '\n']).to_owned())
}

fn require_git_success(run: &GitCapture, label: &str) -> Result<(), StoreError> {
    if run.success {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&run.stderr.retained);
    Err(StoreError::InvalidInput(format!(
        "{label} failed: {}",
        stderr.trim()
    )))
}

async fn run_git(cwd: &Path, args: &[&str], retain_limit: usize) -> Result<GitCapture, StoreError> {
    let mut command = Command::new("git");
    command
        .arg("--no-pager")
        .arg("-c")
        .arg("core.fsmonitor=false")
        .arg("-c")
        .arg("diff.external=")
        .arg("-C")
        .arg(cwd)
        .args(args)
        .env_clear()
        .env("GIT_OPTIONAL_LOCKS", "0")
        .env("GIT_TERMINAL_PROMPT", "0")
        .env("GIT_PAGER", "cat")
        .env("LC_ALL", "C")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    for key in [
        "HOME",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    ] {
        if let Some(value) = env::var_os(key) {
            command.env(key, value);
        }
    }
    let mut child = command
        .spawn()
        .map_err(|error| StoreError::Io(format!("cannot start git: {error}")))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| StoreError::Io("git stdout pipe missing".to_owned()))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| StoreError::Io("git stderr pipe missing".to_owned()))?;
    let stdout_task = tokio::spawn(capture_stream(stdout, retain_limit));
    let stderr_task = tokio::spawn(capture_stream(stderr, METADATA_RETAIN_BYTES));
    let status = child
        .wait()
        .await
        .map_err(|error| StoreError::Io(format!("cannot wait for git: {error}")))?;
    let stdout = stdout_task
        .await
        .map_err(|error| StoreError::Io(format!("git stdout task failed: {error}")))??;
    let stderr = stderr_task
        .await
        .map_err(|error| StoreError::Io(format!("git stderr task failed: {error}")))??;
    Ok(GitCapture {
        success: status.success(),
        stdout,
        stderr,
    })
}

async fn capture_stream<R: AsyncRead + Unpin>(
    mut reader: R,
    retain_limit: usize,
) -> Result<CapturedStream, StoreError> {
    let mut retained = Vec::new();
    let mut total_bytes = 0_u64;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let read = reader
            .read(&mut buffer)
            .await
            .map_err(|error| StoreError::Io(format!("Git output read failed: {error}")))?;
        if read == 0 {
            break;
        }
        total_bytes = total_bytes
            .checked_add(read as u64)
            .ok_or_else(|| StoreError::Corrupt("Git output byte count overflow".to_owned()))?;
        hasher.update(&buffer[..read]);
        if retained.len() < retain_limit {
            let available = retain_limit - retained.len();
            retained.extend_from_slice(&buffer[..read.min(available)]);
        }
    }
    let truncated = total_bytes > retained.len() as u64;
    Ok(CapturedStream {
        retained,
        total_bytes,
        sha256: hex::encode(hasher.finalize()),
        truncated,
    })
}

fn canonical_git_path(worktree: &Path, value: &str) -> Result<PathBuf, StoreError> {
    let path = PathBuf::from(value);
    let candidate = if path.is_absolute() {
        path
    } else {
        worktree.join(path)
    };
    std::fs::canonicalize(&candidate).map_err(|error| {
        StoreError::InvalidInput(format!("Git path {:?} cannot be resolved: {error}", candidate))
    })
}

fn path_text(path: &Path, label: &str) -> Result<String, StoreError> {
    path.to_str()
        .map(str::to_owned)
        .ok_or_else(|| StoreError::InvalidInput(format!("{label} must be valid Unicode")))
}

fn required_projection_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| StoreError::Corrupt(format!("repository projection field {field} invalid")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn porcelain_counts_untracked_and_modified_records() {
        let bytes = b"M  staged.txt\0 M unstaged.txt\0?? new.txt\0MM both.txt\0";
        assert_eq!(parse_porcelain_status(bytes).unwrap(), (2, 2, 1));
    }

    #[test]
    fn porcelain_rejects_malformed_record() {
        assert!(parse_porcelain_status(b"broken\0").is_err());
    }
}
