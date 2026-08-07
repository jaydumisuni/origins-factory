use crate::sessions::{ProcessSessionStart, SessionOutputRecord};
use crate::store::{Store, StoreError};
use origins_contracts::{contract_sha256, validate_contract};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::env;
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::io::{AsyncRead, AsyncReadExt};
use tokio::process::Command;
use tokio::sync::oneshot;
use tokio::time::sleep;

const MAX_TIMEOUT_SECONDS: u64 = 3_600;
const MAX_OUTPUT_BYTES: u64 = 8 * 1024 * 1024;
const MAX_ARGUMENTS: usize = 256;
const MAX_ARGUMENT_CHARS: usize = 32_768;
const SHELL_EXECUTABLES: &[&str] = &[
    "bash",
    "cmd",
    "cmd.exe",
    "fish",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "sh",
    "zsh",
];
const ALLOWED_EXECUTABLES: &[&str] = &[
    "cargo",
    "cargo.exe",
    "git",
    "git.exe",
    "hunter-codeops-code",
    "hunter-codeops-code.exe",
    "hunter-codeops-switcher",
    "hunter-codeops-switcher.exe",
    "node",
    "node.exe",
    "npm",
    "npm.cmd",
    "npx",
    "npx.cmd",
    "py",
    "py.exe",
    "pytest",
    "pytest.exe",
    "python",
    "python.exe",
    "python3",
    "rustc",
    "rustc.exe",
    "sergeant",
    "sergeant.exe",
];
const SAFE_ENV_KEYS: &[&str] = &[
    "CARGO_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "RUSTUP_HOME",
    "RUSTUP_TOOLCHAIN",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WINDIR",
];

#[derive(Debug, Clone)]
pub struct ProcessPolicy {
    allowed_roots: Arc<[PathBuf]>,
}

impl ProcessPolicy {
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

    fn allows(&self, path: &Path) -> bool {
        self.allowed_roots.iter().any(|root| path.starts_with(root))
    }
}

#[derive(Clone, Default)]
pub struct ProcessSupervisor {
    controls: Arc<Mutex<HashMap<String, oneshot::Sender<()>>>>,
}

impl ProcessSupervisor {
    fn register(&self, session_id: &str, sender: oneshot::Sender<()>) -> Result<(), StoreError> {
        let mut controls = self
            .controls
            .lock()
            .map_err(|_| StoreError::Corrupt("process supervisor lock poisoned".to_owned()))?;
        if controls.insert(session_id.to_owned(), sender).is_some() {
            return Err(StoreError::Conflict(format!(
                "session {session_id} already has a live process control"
            )));
        }
        Ok(())
    }

    fn remove(&self, session_id: &str) {
        if let Ok(mut controls) = self.controls.lock() {
            controls.remove(session_id);
        }
    }

    pub fn cancel(&self, session_id: &str) -> Result<(), StoreError> {
        let sender = self
            .controls
            .lock()
            .map_err(|_| StoreError::Corrupt("process supervisor lock poisoned".to_owned()))?
            .remove(session_id)
            .ok_or_else(|| {
                StoreError::Conflict(format!(
                    "session {session_id} is not controlled by this daemon generation"
                ))
            })?;
        sender.send(()).map_err(|_| {
            StoreError::Conflict(format!(
                "session {session_id} finished before cancellation was delivered"
            ))
        })
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProcessPayload {
    workspace_root: String,
    executable: String,
    args: Vec<String>,
    cwd: String,
    timeout_seconds: u64,
    max_output_bytes: u64,
}

#[derive(Debug, Clone)]
pub struct ProcessAcceptanceResult {
    pub session: Value,
    pub replayed: bool,
}

pub fn accept_command(
    store: Store,
    policy: ProcessPolicy,
    supervisor: ProcessSupervisor,
    envelope: Value,
) -> Result<ProcessAcceptanceResult, StoreError> {
    validate_contract(&envelope).map_err(|error| StoreError::InvalidInput(error.to_string()))?;
    if envelope["contract_type"] != "command_envelope" {
        return Err(StoreError::InvalidInput(
            "POST /v1/commands accepts command_envelope contracts only".to_owned(),
        ));
    }
    if envelope["capability_id"] != "origins.process.run" || envelope["effect"] != "execute" {
        return Err(StoreError::InvalidInput(
            "only origins.process.run with execute effect is available in this slice".to_owned(),
        ));
    }

    let command_id = required_string(&envelope, "command_id")?;
    let command_sha256 = contract_sha256(&envelope)
        .map_err(|error| StoreError::InvalidInput(format!("command digest failed: {error}")))?;
    if let Some(session) = store.get_session_for_command(command_id, &command_sha256)? {
        return Ok(ProcessAcceptanceResult {
            session,
            replayed: true,
        });
    }

    let workspace_id = required_string(&envelope, "workspace_id")?;
    if !store.workspace_exists(workspace_id)? {
        return Err(StoreError::NotFound(format!("workspace {workspace_id}")));
    }
    let payload: ProcessPayload = serde_json::from_value(envelope["payload"].clone())
        .map_err(|error| StoreError::InvalidInput(format!("invalid process payload: {error}")))?;
    let prepared = prepare_process(payload, &policy)?;
    let args_value = Value::Array(prepared.args.iter().cloned().map(Value::String).collect());
    let args_sha256 = contract_sha256(&args_value)
        .map_err(|error| StoreError::InvalidInput(format!("argument digest failed: {error}")))?;

    let starting = match store.create_process_session(ProcessSessionStart {
        workspace_id,
        command_id,
        command_sha256: &command_sha256,
        workspace_root: &prepared.workspace_root,
        executable: &prepared.executable,
        cwd: &prepared.cwd,
        args_sha256: &args_sha256,
    }) {
        Ok(session) => session,
        Err(StoreError::Conflict(_)) => {
            if let Some(session) = store.get_session_for_command(command_id, &command_sha256)? {
                return Ok(ProcessAcceptanceResult {
                    session,
                    replayed: true,
                });
            }
            return Err(StoreError::Conflict(format!(
                "command {command_id} raced with another request"
            )));
        }
        Err(error) => return Err(error),
    };
    let session_id = required_string(&starting, "session_id")?.to_owned();
    let (cancel_sender, cancel_receiver) = oneshot::channel();
    if let Err(error) = supervisor.register(&session_id, cancel_sender) {
        let output = output_from_error("process supervisor registration failed", 1024);
        let _ = store.finish_process_session(
            &session_id,
            "interrupted",
            None,
            false,
            output,
            "supervisor_registration_failed",
        );
        return Err(error);
    }

    let run_store = store.clone();
    let cleanup_store = store.clone();
    let cleanup_supervisor = supervisor.clone();
    let cleanup_session_id = session_id.clone();
    tokio::spawn(async move {
        if run_process(run_store, &cleanup_session_id, prepared, cancel_receiver)
            .await
            .is_err()
        {
            let _ = cleanup_store.interrupt_process_session(&cleanup_session_id);
        }
        cleanup_supervisor.remove(&cleanup_session_id);
    });

    Ok(ProcessAcceptanceResult {
        session: starting,
        replayed: false,
    })
}

async fn run_process(
    store: Store,
    session_id: &str,
    prepared: PreparedProcess,
    mut cancel_receiver: oneshot::Receiver<()>,
) -> Result<(), StoreError> {
    let mut command = Command::new(&prepared.executable);
    command
        .args(&prepared.args)
        .current_dir(&prepared.cwd_path)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    apply_safe_environment(&mut command);

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            let output = output_from_error(&error.to_string(), prepared.max_output_bytes as usize);
            store.finish_process_session(
                session_id,
                "interrupted",
                None,
                false,
                output,
                "spawn_failed",
            )?;
            return Ok(());
        }
    };

    let pid = match child.id() {
        Some(pid) => pid,
        None => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            let output = output_from_error(
                "spawned process did not expose a process identifier",
                prepared.max_output_bytes as usize,
            );
            store.finish_process_session(
                session_id,
                "interrupted",
                None,
                false,
                output,
                "missing_process_id",
            )?;
            return Ok(());
        }
    };
    store.mark_process_running(session_id, pid)?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| StoreError::Corrupt("spawned process stdout pipe missing".to_owned()))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| StoreError::Corrupt("spawned process stderr pipe missing".to_owned()))?;
    let output_limit = prepared.max_output_bytes as usize;
    let stdout_task = tokio::spawn(capture_stream(stdout, output_limit));
    let stderr_task = tokio::spawn(capture_stream(stderr, output_limit));
    let timeout_sleep = sleep(Duration::from_secs(prepared.timeout_seconds));
    tokio::pin!(timeout_sleep);

    let wait_outcome = tokio::select! {
        status = child.wait() => {
            match status {
                Ok(status) if status.success() => ("completed", Some(0), false, "exit_zero"),
                Ok(status) => match status.code() {
                    Some(code) => ("failed", Some(code), false, "nonzero_exit"),
                    None => ("interrupted", None, false, "terminated_without_exit_code"),
                },
                Err(_) => ("interrupted", None, false, "wait_failed"),
            }
        }
        _ = &mut cancel_receiver => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            ("interrupted", None, false, "cancelled_by_client")
        }
        _ = &mut timeout_sleep => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            ("timed_out", None, true, "timeout")
        }
    };

    let stdout_capture = match stdout_task.await {
        Ok(Ok(capture)) => capture,
        _ => CapturedStream::failed("stdout capture failed", output_limit),
    };
    let stderr_capture = match stderr_task.await {
        Ok(Ok(capture)) => capture,
        _ => CapturedStream::failed("stderr capture failed", output_limit),
    };
    let capture_failed = stdout_capture.capture_failed || stderr_capture.capture_failed;
    let output = SessionOutputRecord {
        stdout: stdout_capture.retained,
        stderr: stderr_capture.retained,
        stdout_bytes: stdout_capture.total_bytes,
        stderr_bytes: stderr_capture.total_bytes,
        stdout_sha256: stdout_capture.sha256,
        stderr_sha256: stderr_capture.sha256,
        output_truncated: stdout_capture.truncated || stderr_capture.truncated,
    };

    let (state, exit_code, timed_out, reason) = if capture_failed {
        ("interrupted", None, false, "output_capture_failed")
    } else {
        wait_outcome
    };
    store.finish_process_session(session_id, state, exit_code, timed_out, output, reason)?;
    Ok(())
}

struct PreparedProcess {
    workspace_root: String,
    cwd: String,
    cwd_path: PathBuf,
    executable: String,
    args: Vec<String>,
    timeout_seconds: u64,
    max_output_bytes: u64,
}

fn prepare_process(
    payload: ProcessPayload,
    policy: &ProcessPolicy,
) -> Result<PreparedProcess, StoreError> {
    if !(1..=MAX_TIMEOUT_SECONDS).contains(&payload.timeout_seconds) {
        return Err(StoreError::InvalidInput(format!(
            "timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}"
        )));
    }
    if !(1..=MAX_OUTPUT_BYTES).contains(&payload.max_output_bytes) {
        return Err(StoreError::InvalidInput(format!(
            "max_output_bytes must be between 1 and {MAX_OUTPUT_BYTES}"
        )));
    }
    validate_executable(&payload.executable)?;
    if payload.args.len() > MAX_ARGUMENTS {
        return Err(StoreError::InvalidInput(format!(
            "args cannot contain more than {MAX_ARGUMENTS} entries"
        )));
    }
    if payload
        .args
        .iter()
        .any(|arg| arg.chars().count() > MAX_ARGUMENT_CHARS)
    {
        return Err(StoreError::InvalidInput(format!(
            "each argument must be at most {MAX_ARGUMENT_CHARS} characters"
        )));
    }

    let root = std::fs::canonicalize(&payload.workspace_root).map_err(|error| {
        StoreError::InvalidInput(format!("workspace_root cannot be resolved: {error}"))
    })?;
    if !root.is_dir() {
        return Err(StoreError::InvalidInput(
            "workspace_root must resolve to a directory".to_owned(),
        ));
    }
    if !policy.allows(&root) {
        return Err(StoreError::InvalidInput(
            "workspace_root is outside the configured Origins workspace roots".to_owned(),
        ));
    }
    let relative_cwd = validate_relative_cwd(&payload.cwd)?;
    let cwd_path = std::fs::canonicalize(root.join(relative_cwd))
        .map_err(|error| StoreError::InvalidInput(format!("cwd cannot be resolved: {error}")))?;
    if !cwd_path.is_dir() || !cwd_path.starts_with(&root) {
        return Err(StoreError::InvalidInput(
            "cwd must resolve to a directory inside workspace_root".to_owned(),
        ));
    }
    let workspace_root = root
        .to_str()
        .ok_or_else(|| StoreError::InvalidInput("workspace_root must be valid Unicode".to_owned()))?
        .to_owned();
    let cwd = cwd_path
        .strip_prefix(&root)
        .ok()
        .and_then(Path::to_str)
        .filter(|value| !value.is_empty())
        .unwrap_or(".")
        .to_owned();

    Ok(PreparedProcess {
        workspace_root,
        cwd,
        cwd_path,
        executable: payload.executable,
        args: payload.args,
        timeout_seconds: payload.timeout_seconds,
        max_output_bytes: payload.max_output_bytes,
    })
}

fn validate_executable(executable: &str) -> Result<(), StoreError> {
    if executable.is_empty()
        || executable.len() > 128
        || executable.contains('/')
        || executable.contains('\\')
        || executable.chars().any(char::is_whitespace)
    {
        return Err(StoreError::InvalidInput(
            "executable must be a bounded program name without path separators or whitespace"
                .to_owned(),
        ));
    }
    let normalized = executable.to_ascii_lowercase();
    if SHELL_EXECUTABLES.contains(&normalized.as_str()) {
        return Err(StoreError::InvalidInput(
            "generic process capability does not execute shell interpreters".to_owned(),
        ));
    }
    if !ALLOWED_EXECUTABLES.contains(&normalized.as_str()) {
        return Err(StoreError::InvalidInput(format!(
            "executable {executable:?} is not registered for origins.process.run"
        )));
    }
    Ok(())
}

fn validate_relative_cwd(cwd: &str) -> Result<PathBuf, StoreError> {
    let path = if cwd.is_empty() {
        Path::new(".")
    } else {
        Path::new(cwd)
    };
    for component in path.components() {
        if !matches!(component, Component::Normal(_) | Component::CurDir) {
            return Err(StoreError::InvalidInput(
                "cwd must be relative and cannot contain parent/root/prefix components".to_owned(),
            ));
        }
    }
    Ok(path.to_path_buf())
}

fn apply_safe_environment(command: &mut Command) {
    for key in SAFE_ENV_KEYS {
        if let Some(value) = env::var_os(key) {
            command.env(key, value);
        }
    }
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, StoreError> {
    value[field]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| StoreError::InvalidInput(format!("{field} is required")))
}

struct CapturedStream {
    retained: Vec<u8>,
    total_bytes: u64,
    sha256: String,
    truncated: bool,
    capture_failed: bool,
}

impl CapturedStream {
    fn failed(message: &str, limit: usize) -> Self {
        let bytes = message.as_bytes();
        let retained = bytes[..bytes.len().min(limit)].to_vec();
        Self {
            retained,
            total_bytes: bytes.len() as u64,
            sha256: hex::encode(Sha256::digest(bytes)),
            truncated: bytes.len() > limit,
            capture_failed: true,
        }
    }
}

async fn capture_stream<R>(mut reader: R, limit: usize) -> std::io::Result<CapturedStream>
where
    R: AsyncRead + Unpin,
{
    let mut retained = Vec::with_capacity(limit.min(64 * 1024));
    let mut total_bytes = 0_u64;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let read = reader.read(&mut buffer).await?;
        if read == 0 {
            break;
        }
        total_bytes = total_bytes.saturating_add(read as u64);
        hasher.update(&buffer[..read]);
        let remaining = limit.saturating_sub(retained.len());
        if remaining > 0 {
            retained.extend_from_slice(&buffer[..read.min(remaining)]);
        }
    }
    Ok(CapturedStream {
        truncated: total_bytes > retained.len() as u64,
        retained,
        total_bytes,
        sha256: hex::encode(hasher.finalize()),
        capture_failed: false,
    })
}

fn output_from_error(message: &str, limit: usize) -> SessionOutputRecord {
    let capture = CapturedStream::failed(message, limit);
    SessionOutputRecord {
        stdout: Vec::new(),
        stderr: capture.retained,
        stdout_bytes: 0,
        stderr_bytes: capture.total_bytes,
        stdout_sha256: hex::encode(Sha256::digest([])),
        stderr_sha256: capture.sha256,
        output_truncated: capture.truncated,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shell_programs_are_rejected() {
        let error = validate_executable("bash").expect_err("shell must fail");
        assert!(matches!(error, StoreError::InvalidInput(_)));
    }

    #[test]
    fn parent_cwd_escape_is_rejected() {
        let error = validate_relative_cwd("../outside").expect_err("parent path must fail");
        assert!(matches!(error, StoreError::InvalidInput(_)));
    }
}
