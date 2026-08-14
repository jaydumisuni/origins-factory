use crate::store::{append_event, Store, StoreError};
use axum::extract::{Path, State};
use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use rusqlite::TransactionBehavior;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::env;
use std::path::{Path as FsPath, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use tokio::process::Command;

const MAX_APPLICATIONS: usize = 512;
const MAX_ARGUMENTS: usize = 128;
const MAX_ARGUMENT_CHARS: usize = 16_384;
const SHELL_NAMES: &[&str] = &[
    "bash", "cmd", "cmd.exe", "fish", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "sh", "zsh",
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
        let parsed: RegistryFile =
            serde_json::from_str(raw).map_err(|error| format!("invalid ORIGINS_APPLICATIONS_JSON: {error}"))?;
        if parsed.applications.len() > MAX_APPLICATIONS {
            return Err(format!("application registry exceeds {MAX_APPLICATIONS} entries"));
        }
        let mut applications = BTreeMap::new();
        for candidate in parsed.applications {
            let descriptor = prepare(candidate)?;
            if applications.insert(descriptor.id.clone(), descriptor).is_some() {
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
        self.applications.values().map(ApplicationDescriptor::projection).collect()
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
        return Err("application ID must use 1-128 ASCII letters, numbers, '.', '_' or '-'".to_owned());
    }
    let name = candidate.name.trim().to_owned();
    if name.is_empty() || name.chars().count() > 200 {
        return Err(format!("application {id} has an invalid display name"));
    }
    if candidate.args.len() > MAX_ARGUMENTS
        || candidate.args.iter().map(|value| value.chars().count()).sum::<usize>() > MAX_ARGUMENT_CHARS
    {
        return Err(format!("application {id} exceeds fixed argument limits"));
    }
    if candidate.args.iter().any(|value| value.contains('\0')) {
        return Err(format!("application {id} contains a NUL argument"));
    }

    let configured = PathBuf::from(candidate.executable.trim());
    if !configured.is_absolute() {
        return Err(format!("application {id} executable must be an absolute path"));
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
        return Err(format!("application {id} cannot register a shell executable"));
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

#[derive(Clone)]
pub struct ApplicationState {
    pub store: Store,
    pub registry: ApplicationRegistry,
    pub local_token: Arc<str>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LaunchRequest {
    workspace_id: String,
}

pub fn router(state: ApplicationState) -> Router {
    Router::new()
        .route("/v1/applications", get(list_applications))
        .route("/v1/applications/:application_id/launch", post(launch_application))
        .with_state(state)
}

async fn list_applications(
    State(state): State<ApplicationState>,
    headers: HeaderMap,
) -> Result<Json<Value>, AppApiError> {
    require_auth(&headers, &state.local_token)?;
    Ok(Json(json!({"applications": state.registry.projections()})))
}

async fn launch_application(
    State(state): State<ApplicationState>,
    headers: HeaderMap,
    Path(application_id): Path<String>,
    Json(request): Json<LaunchRequest>,
) -> Result<(StatusCode, Json<Value>), AppApiError> {
    require_auth(&headers, &state.local_token)?;
    if !state
        .store
        .workspace_exists(&request.workspace_id)
        .map_err(AppApiError::from_store)?
    {
        return Err(AppApiError::new(StatusCode::NOT_FOUND, "WORKSPACE_NOT_FOUND", "workspace not found"));
    }
    let application = state
        .registry
        .get(&application_id)
        .ok_or_else(|| AppApiError::new(StatusCode::NOT_FOUND, "APPLICATION_NOT_FOUND", "application not found"))?;

    let mut command = Command::new(&application.executable);
    command.args(application.args.iter().map(String::as_str));
    if let Some(cwd) = application.cwd.as_ref() {
        command.current_dir(cwd);
    }
    command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    let child = command
        .spawn()
        .map_err(|error| AppApiError::new(StatusCode::SERVICE_UNAVAILABLE, "APPLICATION_LAUNCH_FAILED", error.to_string()))?;
    let pid = child
        .id()
        .ok_or_else(|| AppApiError::new(StatusCode::SERVICE_UNAVAILABLE, "APPLICATION_LAUNCH_FAILED", "launched application exposed no process ID"))?;
    drop(child);

    let mut connection = state.store.connection().map_err(AppApiError::from_store)?;
    let transaction = connection
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(StoreError::from)
        .map_err(AppApiError::from_store)?;
    let event = append_event(
        &transaction,
        &request.workspace_id,
        "application.launched",
        json!({
            "application_id": application.id,
            "name": application.name,
            "pid": pid,
            "node_id": "local",
        }),
        Vec::new(),
    )
    .map_err(AppApiError::from_store)?;
    transaction.commit().map_err(StoreError::from).map_err(AppApiError::from_store)?;

    Ok((
        StatusCode::ACCEPTED,
        Json(json!({
            "accepted": true,
            "application": application.projection(),
            "pid": pid,
            "node_id": "local",
            "event": event,
        })),
    ))
}

fn require_auth(headers: &HeaderMap, expected: &str) -> Result<(), AppApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(AppApiError::new(StatusCode::UNAUTHORIZED, "UNAUTHORIZED", "valid Origins local bearer token required"));
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
        Self { status, code, message: message.into() }
    }

    fn from_store(error: StoreError) -> Self {
        match error {
            StoreError::InvalidInput(message) | StoreError::Contract(message) => Self::new(StatusCode::BAD_REQUEST, "INVALID_REQUEST", message),
            StoreError::NotFound(message) => Self::new(StatusCode::NOT_FOUND, "NOT_FOUND", message),
            StoreError::Conflict(message) => Self::new(StatusCode::CONFLICT, "CONFLICT", message),
            StoreError::Corrupt(message) => Self::new(StatusCode::SERVICE_UNAVAILABLE, "CORRUPT_STATE", message),
            StoreError::Io(message) | StoreError::Database(message) => Self::new(StatusCode::SERVICE_UNAVAILABLE, "STORAGE_UNAVAILABLE", message),
        }
    }
}

impl IntoResponse for AppApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({"ok": false, "error_code": self.code, "error": self.message}))).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

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
        let raw = json!({"applications":[{"id":"bad/id","name":"Bad","executable":executable}]}).to_string();
        assert!(ApplicationRegistry::from_json(&raw).is_err());
        let _unused = Uuid::new_v4();
    }

    #[test]
    fn bearer_compare_is_exact() {
        assert!(constant_time_eq(b"same", b"same"));
        assert!(!constant_time_eq(b"same", b"diff"));
        assert!(!constant_time_eq(b"short", b"longer"));
    }
}
