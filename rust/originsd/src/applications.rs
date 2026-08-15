use crate::store::{append_event, now_rfc3339, Store, StoreError};
use axum::extract::{Path, State};
use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use origins_contracts::contract_sha256;
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::env;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use tokio::process::Command;
use uuid::Uuid;

const APPLICATION_SCHEMA_VERSION: i64 = 1;
const MAX_APPLICATIONS: usize = 512;
const MAX_ARGUMENTS: usize = 128;
const MAX_ARGUMENT_CHARS: usize = 16_384;
const MAX_LAUNCH_ERROR_CHARS: usize = 2_048;
const SHELL_NAMES: &[&str] = &[
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
const SAFE_APPLICATION_ENV_KEYS: &[&str] = &[
    "APPDATA",
    "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)",
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WAYLAND_DISPLAY",
    "WINDIR",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
];

#[derive(Debug, Clone)]
pub struct ApplicationDescriptor {
    pub id: String,
    pub name: String,
    executable: PathBuf,
    args: Arc<[String]>,
    cwd: Option<PathBuf>,
}

impl ApplicationDescriptor {
    fn projection(&self) -> Value {
        json!({
            "application_id": self.id,
            "name": self.name,
            "launchable": true,
            "source": "origins.application-registry.v1",
            "executable_name": self.executable.file_name().and_then(|value| value.to_str()).unwrap_or(""),
        })
    }

    fn fingerprint(&self) -> Result<String, StoreError> {
        contract_sha256(&json!({
            "application_id": self.id,
            "name": self.name,
            "executable": self.executable.to_string_lossy(),
            "args": self.args.as_ref(),
            "cwd": self.cwd.as_ref().map(|value| value.to_string_lossy()),
        }))
        .map_err(|error| {
            StoreError::InvalidInput(format!("application descriptor digest failed: {error}"))
        })
    }
}

#[derive(Debug, Clone, Default)]
pub struct ApplicationRegistry {
    applications: Arc<BTreeMap<String, ApplicationDescriptor>>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistryFile {
    #[serde(default)]
    applications: Vec<RegistryApplication>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistryApplication {
    id: String,
    name: String,
    executable: String,
    #[serde(default)]
    args: Vec<String>,
    #[serde(default)]
    cwd: String,
}

impl ApplicationRegistry {
    pub fn from_env() -> Result<Self, String> {
        match env::var("ORIGINS_APPLICATIONS_JSON") {
            Ok(raw) if !raw.trim().is_empty() => Self::from_json(&raw),
            _ => Ok(Self::default()),
        }
    }

    pub fn from_json(raw: &str) -> Result<Self, String> {
        let parsed: RegistryFile = serde_json::from_str(raw)
            .map_err(|error| format!("invalid ORIGINS_APPLICATIONS_JSON: {error}"))?;
        if parsed.applications.len() > MAX_APPLICATIONS {
            return Err(format!(
                "application registry exceeds {MAX_APPLICATIONS} entries"
            ));
        }
        let mut applications = BTreeMap::new();
        for candidate in parsed.applications {
            let descriptor = prepare(candidate)?;
            if applications
                .insert(descriptor.id.clone(), descriptor)
                .is_some()
            {
                return Err("duplicate application ID in registry".to_owned());
            }
        }
        Ok(Self {
            applications: Arc::new(applications),
        })
    }

    fn get(&self, id: &str) -> Option<ApplicationDescriptor> {
        self.applications.get(id).cloned()
    }

    fn projections(&self) -> Vec<Value> {
        self.applications
            .values()
            .map(ApplicationDescriptor::projection)
            .collect()
    }
}

fn prepare(candidate: RegistryApplication) -> Result<ApplicationDescriptor, String> {
    let id = candidate.id.trim().to_owned();
    if id.is_empty()
        || id.len() > 128
        || !id
            .bytes()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, b'-' | b'_' | b'.'))
    {
        return Err(
            "application ID must use 1-128 ASCII letters, numbers, '.', '_' or '-'".to_owned(),
        );
    }
    let name = candidate.name.trim().to_owned();
    if name.is_empty() || name.chars().count() > 200 {
        return Err(format!("application {id} has an invalid display name"));
    }
    if candidate.args.len() > MAX_ARGUMENTS
        || candidate
            .args
            .iter()
            .map(|value| value.chars().count())
            .sum::<usize>()
            > MAX_ARGUMENT_CHARS
    {
        return Err(format!("application {id} exceeds fixed argument limits"));
    }
    if candidate.args.iter().any(|value| value.contains('\0')) {
        return Err(format!("application {id} contains a NUL argument"));
    }

    let configured = PathBuf::from(candidate.executable.trim());
    if !configured.is_absolute() {
        return Err(format!(
            "application {id} executable must be an absolute path"
        ));
    }
    let executable = std::fs::canonicalize(&configured)
        .map_err(|error| format!("application {id} executable cannot be resolved: {error}"))?;
    if !executable.is_file() {
        return Err(format!("application {id} executable is not a file"));
    }
    let executable_name = executable
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if SHELL_NAMES.contains(&executable_name.as_str()) {
        return Err(format!(
            "application {id} cannot register a shell executable"
        ));
    }

    let cwd = if candidate.cwd.trim().is_empty() {
        None
    } else {
        let configured_cwd = PathBuf::from(candidate.cwd.trim());
        if !configured_cwd.is_absolute() {
            return Err(format!("application {id} cwd must be absolute"));
        }
        let canonical = std::fs::canonicalize(&configured_cwd)
            .map_err(|error| format!("application {id} cwd cannot be resolved: {error}"))?;
        if !canonical.is_dir() {
            return Err(format!("application {id} cwd is not a directory"));
        }
        Some(canonical)
    };

    Ok(ApplicationDescriptor {
        id,
        name,
        executable,
        args: Arc::from(candidate.args),
        cwd,
    })
}

pub fn initialize(store: &Store) -> Result<(), StoreError> {
    let connection = store.connection()?;
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS application_meta (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS application_launches (
            launch_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            application_id TEXT NOT NULL,
            descriptor_sha256 TEXT NOT NULL,
            state TEXT NOT NULL,
            pid INTEGER,
            error TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
         );",
    )?;
    let current: Option<String> = connection
        .query_row(
            "SELECT value FROM application_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    let version = match current {
        Some(value) => value.parse::<i64>().map_err(|_| {
            StoreError::Corrupt("invalid application subsystem schema version".to_owned())
        })?,
        None => 0,
    };
    if version > APPLICATION_SCHEMA_VERSION {
        return Err(StoreError::Corrupt(format!(
            "unsupported newer application subsystem schema version {version}; current is {APPLICATION_SCHEMA_VERSION}"
        )));
    }
    if version != APPLICATION_SCHEMA_VERSION {
        connection.execute(
            "INSERT INTO application_meta (key, value) VALUES ('schema_version', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [APPLICATION_SCHEMA_VERSION.to_string()],
        )?;
    }
    Ok(())
}

impl Store {
    pub fn application_schema_version(&self) -> Result<i64, StoreError> {
        let connection = self.connection()?;
        let value: String = connection.query_row(
            "SELECT value FROM application_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )?;
        value.parse().map_err(|_| {
            StoreError::Corrupt("invalid application subsystem schema version".to_owned())
        })
    }

    pub fn application_launch_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM application_launches", [], |row| {
                row.get(0)
            })?;
        u64::try_from(count)
            .map_err(|_| StoreError::Corrupt("negative application launch count".to_owned()))
    }

    fn get_application_launch(&self, launch_id: &str) -> Result<Value, StoreError> {
        let connection = self.connection()?;
        load_launch(&connection, launch_id)?
            .map(|launch| launch.projection())
            .ok_or_else(|| StoreError::NotFound(format!("application launch {launch_id}")))
    }
}

#[derive(Clone)]
pub struct ApplicationState {
    pub store: Store,
    pub registry: ApplicationRegistry,
    pub local_token: Arc<str>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LaunchRequest {
    launch_id: String,
    workspace_id: String,
}

#[derive(Debug, Clone)]
struct StoredLaunch {
    launch_id: String,
    workspace_id: String,
    application_id: String,
    descriptor_sha256: String,
    state: String,
    pid: Option<i64>,
    error: String,
    created_at: String,
    updated_at: String,
}

impl StoredLaunch {
    fn projection(&self) -> Value {
        json!({
            "launch_id": self.launch_id,
            "workspace_id": self.workspace_id,
            "application_id": self.application_id,
            "descriptor_sha256": self.descriptor_sha256,
            "state": self.state,
            "pid": self.pid,
            "error": self.error,
            "node_id": "local",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "liveness": "untracked",
        })
    }
}

pub fn router(state: ApplicationState) -> Router {
    Router::new()
        .route("/v1/applications", get(list_applications))
        .route(
            "/v1/applications/:application_id/launch",
            post(launch_application),
        )
        .route(
            "/v1/application-launches/:launch_id",
            get(get_application_launch),
        )
        .with_state(state)
}

async fn list_applications(
    State(state): State<ApplicationState>,
    headers: HeaderMap,
) -> Result<Json<Value>, AppApiError> {
    require_auth(&headers, &state.local_token)?;
    Ok(Json(json!({"applications": state.registry.projections()})))
}

async fn get_application_launch(
    State(state): State<ApplicationState>,
    headers: HeaderMap,
    Path(launch_id): Path<String>,
) -> Result<Json<Value>, AppApiError> {
    require_auth(&headers, &state.local_token)?;
    let launch_id = normalize_launch_id(&launch_id).map_err(AppApiError::from_store)?;
    Ok(Json(
        state
            .store
            .get_application_launch(&launch_id)
            .map_err(AppApiError::from_store)?,
    ))
}

async fn launch_application(
    State(state): State<ApplicationState>,
    headers: HeaderMap,
    Path(application_id): Path<String>,
    Json(request): Json<LaunchRequest>,
) -> Result<Response, AppApiError> {
    require_auth(&headers, &state.local_token)?;
    let launch_id = normalize_launch_id(&request.launch_id).map_err(AppApiError::from_store)?;
    if !state
        .store
        .workspace_exists(&request.workspace_id)
        .map_err(AppApiError::from_store)?
    {
        return Err(AppApiError::new(
            StatusCode::NOT_FOUND,
            "WORKSPACE_NOT_FOUND",
            "workspace not found",
        ));
    }
    let application = state.registry.get(&application_id).ok_or_else(|| {
        AppApiError::new(
            StatusCode::NOT_FOUND,
            "APPLICATION_NOT_FOUND",
            "application not found",
        )
    })?;
    let descriptor_sha256 = application.fingerprint().map_err(AppApiError::from_store)?;

    match reserve_launch(
        &state.store,
        &launch_id,
        &request.workspace_id,
        &application,
        &descriptor_sha256,
    )
    .map_err(AppApiError::from_store)?
    {
        LaunchReservation::Replayed(launch) => {
            return Ok((
                StatusCode::ACCEPTED,
                Json(json!({
                    "accepted": true,
                    "replayed": true,
                    "application": application.projection(),
                    "launch": launch.projection(),
                })),
            )
                .into_response());
        }
        LaunchReservation::New => {}
    }

    let mut command = Command::new(&application.executable);
    command.args(application.args.iter().map(String::as_str));
    if let Some(cwd) = application.cwd.as_ref() {
        command.current_dir(cwd);
    }
    apply_safe_environment(&mut command);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    match command.spawn() {
        Ok(child) => {
            let pid = child.id().ok_or_else(|| {
                AppApiError::new(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "APPLICATION_LAUNCH_FAILED",
                    "launched application exposed no process ID",
                )
            })?;
            drop(child);
            let launch = finish_launch(
                &state.store,
                &launch_id,
                &request.workspace_id,
                &application.id,
                &descriptor_sha256,
                "spawned",
                Some(i64::from(pid)),
                "",
            )
            .map_err(AppApiError::from_store)?;
            Ok((
                StatusCode::ACCEPTED,
                Json(json!({
                    "accepted": true,
                    "replayed": false,
                    "application": application.projection(),
                    "launch": launch.projection(),
                })),
            )
                .into_response())
        }
        Err(error) => {
            let message = bounded_error(&error.to_string());
            let launch = finish_launch(
                &state.store,
                &launch_id,
                &request.workspace_id,
                &application.id,
                &descriptor_sha256,
                "failed",
                None,
                &message,
            )
            .map_err(AppApiError::from_store)?;
            Ok((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({
                    "accepted": false,
                    "replayed": false,
                    "error_code": "APPLICATION_LAUNCH_FAILED",
                    "error": message,
                    "application": application.projection(),
                    "launch": launch.projection(),
                })),
            )
                .into_response())
        }
    }
}

#[derive(Debug)]
enum LaunchReservation {
    New,
    Replayed(Box<StoredLaunch>),
}

fn reserve_launch(
    store: &Store,
    launch_id: &str,
    workspace_id: &str,
    application: &ApplicationDescriptor,
    descriptor_sha256: &str,
) -> Result<LaunchReservation, StoreError> {
    let mut connection = store.connection()?;
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    if let Some(existing) = load_launch(&transaction, launch_id)? {
        if existing.workspace_id != workspace_id
            || existing.application_id != application.id
            || existing.descriptor_sha256 != descriptor_sha256
        {
            return Err(StoreError::Conflict(format!(
                "launch ID {launch_id} is already bound to a different application request"
            )));
        }
        transaction.commit()?;
        return Ok(LaunchReservation::Replayed(Box::new(existing)));
    }

    let now = now_rfc3339();
    transaction.execute(
        "INSERT INTO application_launches (
            launch_id, workspace_id, application_id, descriptor_sha256, state,
            pid, error, created_at, updated_at
         ) VALUES (?1, ?2, ?3, ?4, 'requested', NULL, '', ?5, ?5)",
        params![
            launch_id,
            workspace_id,
            application.id,
            descriptor_sha256,
            now
        ],
    )?;
    append_event(
        &transaction,
        workspace_id,
        "application.launch.requested",
        json!({
            "launch_id": launch_id,
            "application_id": application.id,
            "descriptor_sha256": descriptor_sha256,
            "node_id": "local",
        }),
        Vec::new(),
    )?;
    transaction.commit()?;
    Ok(LaunchReservation::New)
}

#[allow(clippy::too_many_arguments)]
fn finish_launch(
    store: &Store,
    launch_id: &str,
    workspace_id: &str,
    application_id: &str,
    descriptor_sha256: &str,
    state: &str,
    pid: Option<i64>,
    error: &str,
) -> Result<StoredLaunch, StoreError> {
    if !matches!(state, "spawned" | "failed") {
        return Err(StoreError::InvalidInput(format!(
            "invalid application launch terminal state {state}"
        )));
    }
    let mut connection = store.connection()?;
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let existing = load_launch(&transaction, launch_id)?.ok_or_else(|| {
        StoreError::Corrupt(format!("application launch {launch_id} disappeared"))
    })?;
    if existing.workspace_id != workspace_id
        || existing.application_id != application_id
        || existing.descriptor_sha256 != descriptor_sha256
    {
        return Err(StoreError::Conflict(format!(
            "launch ID {launch_id} changed ownership during execution"
        )));
    }
    if existing.state != "requested" {
        transaction.commit()?;
        return Ok(existing);
    }
    let now = now_rfc3339();
    transaction.execute(
        "UPDATE application_launches
         SET state = ?2, pid = ?3, error = ?4, updated_at = ?5
         WHERE launch_id = ?1 AND state = 'requested'",
        params![launch_id, state, pid, error, now],
    )?;
    append_event(
        &transaction,
        workspace_id,
        if state == "spawned" {
            "application.launch.spawned"
        } else {
            "application.launch.failed"
        },
        json!({
            "launch_id": launch_id,
            "application_id": application_id,
            "descriptor_sha256": descriptor_sha256,
            "state": state,
            "pid": pid,
            "error": error,
            "node_id": "local",
        }),
        Vec::new(),
    )?;
    let updated = load_launch(&transaction, launch_id)?.ok_or_else(|| {
        StoreError::Corrupt(format!(
            "application launch {launch_id} disappeared after update"
        ))
    })?;
    transaction.commit()?;
    Ok(updated)
}

fn load_launch(
    connection: &rusqlite::Connection,
    launch_id: &str,
) -> Result<Option<StoredLaunch>, StoreError> {
    connection
        .query_row(
            "SELECT launch_id, workspace_id, application_id, descriptor_sha256,
                    state, pid, error, created_at, updated_at
             FROM application_launches WHERE launch_id = ?1",
            [launch_id],
            |row| {
                Ok(StoredLaunch {
                    launch_id: row.get(0)?,
                    workspace_id: row.get(1)?,
                    application_id: row.get(2)?,
                    descriptor_sha256: row.get(3)?,
                    state: row.get(4)?,
                    pid: row.get(5)?,
                    error: row.get(6)?,
                    created_at: row.get(7)?,
                    updated_at: row.get(8)?,
                })
            },
        )
        .optional()
        .map_err(StoreError::from)
}

fn normalize_launch_id(value: &str) -> Result<String, StoreError> {
    let parsed = Uuid::parse_str(value.trim())
        .map_err(|_| StoreError::InvalidInput("launch_id must be a UUID".to_owned()))?;
    Ok(parsed.hyphenated().to_string())
}

fn apply_safe_environment(command: &mut Command) {
    command.env_clear();
    for key in SAFE_APPLICATION_ENV_KEYS {
        if let Some(value) = env::var_os(key) {
            command.env(key, value);
        }
    }
}

fn bounded_error(value: &str) -> String {
    value.chars().take(MAX_LAUNCH_ERROR_CHARS).collect()
}

fn require_auth(headers: &HeaderMap, expected: &str) -> Result<(), AppApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(AppApiError::new(
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "valid Origins local bearer token required",
        ));
    }
    Ok(())
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut difference = 0_u8;
    for (left, right) in left.iter().zip(right.iter()) {
        difference |= left ^ right;
    }
    difference == 0
}

#[derive(Debug)]
struct AppApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl AppApiError {
    fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
        }
    }

    fn from_store(error: StoreError) -> Self {
        match error {
            StoreError::InvalidInput(message) | StoreError::Contract(message) => {
                Self::new(StatusCode::BAD_REQUEST, "INVALID_REQUEST", message)
            }
            StoreError::NotFound(message) => Self::new(StatusCode::NOT_FOUND, "NOT_FOUND", message),
            StoreError::Conflict(message) => Self::new(StatusCode::CONFLICT, "CONFLICT", message),
            StoreError::Corrupt(message) => {
                Self::new(StatusCode::SERVICE_UNAVAILABLE, "CORRUPT_STATE", message)
            }
            StoreError::Io(message) | StoreError::Database(message) => Self::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "STORAGE_UNAVAILABLE",
                message,
            ),
        }
    }
}

impl IntoResponse for AppApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({
                "ok": false,
                "error_code": self.code,
                "error": self.message
            })),
        )
            .into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn existing_file() -> PathBuf {
        std::env::current_exe().expect("test executable path")
    }

    #[test]
    fn configured_registry_never_accepts_caller_command_text() {
        let executable = existing_file();
        let raw = json!({
            "applications": [{
                "id": "proof-app",
                "name": "Proof App",
                "executable": executable,
                "args": ["--fixed"],
                "cwd": ""
            }]
        })
        .to_string();
        let registry = ApplicationRegistry::from_json(&raw).expect("registry accepted");
        let app = registry.get("proof-app").expect("app exists");
        assert_eq!(app.args.as_ref(), &["--fixed".to_owned()]);
    }

    #[test]
    fn relative_executable_is_rejected() {
        let raw = r#"{"applications":[{"id":"bad","name":"Bad","executable":"relative.exe"}]}"#;
        let error = ApplicationRegistry::from_json(raw).expect_err("relative executable must fail");
        assert!(error.contains("absolute path"));
    }

    #[test]
    fn duplicate_id_is_rejected() {
        let executable = existing_file();
        let raw = json!({
            "applications": [
                {"id":"same","name":"One","executable":executable},
                {"id":"same","name":"Two","executable":executable}
            ]
        })
        .to_string();
        assert!(ApplicationRegistry::from_json(&raw).is_err());
    }

    #[test]
    fn application_ids_are_bounded() {
        let executable = existing_file();
        let raw = json!({
            "applications":[{"id":"bad/id","name":"Bad","executable":executable}]
        })
        .to_string();
        assert!(ApplicationRegistry::from_json(&raw).is_err());
    }

    #[test]
    fn shell_executable_is_rejected_when_resolved_name_is_shell() {
        assert!(SHELL_NAMES.contains(&"sh"));
        assert!(SHELL_NAMES.contains(&"powershell.exe"));
    }

    #[test]
    fn unsafe_environment_keys_are_not_allowlisted() {
        assert!(!SAFE_APPLICATION_ENV_KEYS.contains(&"ORIGINS_LOCAL_TOKEN"));
        assert!(!SAFE_APPLICATION_ENV_KEYS.contains(&"OPENAI_API_KEY"));
        assert!(!SAFE_APPLICATION_ENV_KEYS.contains(&"ORACLE_PAIRING_TOKEN"));
    }

    #[test]
    fn launch_id_is_canonicalized() {
        let value = "550E8400-E29B-41D4-A716-446655440000";
        assert_eq!(
            normalize_launch_id(value).unwrap(),
            "550e8400-e29b-41d4-a716-446655440000"
        );
    }

    #[test]
    fn bearer_compare_is_exact() {
        assert!(constant_time_eq(b"same", b"same"));
        assert!(!constant_time_eq(b"same", b"diff"));
        assert!(!constant_time_eq(b"short", b"longer"));
    }
}
