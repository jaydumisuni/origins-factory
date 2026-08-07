use crate::live::{journal_stream, output_stream, LiveStream};
use crate::process::{accept_command as accept_process_command, ProcessPolicy, ProcessSupervisor};
use crate::sessions::SessionOutputRecord;
use crate::store::{Store, StoreError};
use axum::extract::{Path, Query, State};
use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub store: Store,
    pub process_policy: ProcessPolicy,
    pub process_supervisor: ProcessSupervisor,
    pub local_token: Arc<str>,
    pub started_at: Arc<str>,
}

#[derive(Debug, Deserialize)]
pub struct CreateWorkspaceRequest {
    pub name: String,
    #[serde(default)]
    pub authority_refs: Vec<Value>,
    #[serde(default)]
    pub session_refs: Vec<Value>,
}

#[derive(Debug, Deserialize)]
pub struct EventQuery {
    #[serde(default)]
    pub after_sequence: u64,
    #[serde(default = "default_event_limit")]
    pub limit: u64,
}

#[derive(Debug, Deserialize)]
pub struct LiveEventQuery {
    #[serde(default)]
    pub after_sequence: u64,
}

#[derive(Debug, Deserialize)]
pub struct OutputDeltaQuery {
    #[serde(default)]
    pub stdout_after: u64,
    #[serde(default)]
    pub stderr_after: u64,
    #[serde(default = "default_output_delta_limit")]
    pub limit: u64,
}

#[derive(Debug, Deserialize)]
pub struct OutputLiveQuery {
    #[serde(default)]
    pub stdout_after: u64,
    #[serde(default)]
    pub stderr_after: u64,
}

fn default_event_limit() -> u64 {
    100
}

fn default_output_delta_limit() -> u64 {
    64 * 1024
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(health))
        .route("/v1/capabilities", get(capabilities))
        .route("/v1/workspaces", post(create_workspace))
        .route("/v1/workspaces/:workspace_id", get(get_workspace))
        .route("/v1/commands", post(run_command))
        .route("/v1/events", get(list_events))
        .route("/v1/events/live", get(live_events))
        .route("/v1/sessions", get(list_sessions))
        .route("/v1/sessions/:session_id", get(get_session))
        .route("/v1/sessions/:session_id/output", get(get_session_output))
        .route(
            "/v1/sessions/:session_id/output/delta",
            get(get_session_output_delta),
        )
        .route(
            "/v1/sessions/:session_id/output/live",
            get(live_session_output),
        )
        .route("/v1/sessions/:session_id/cancel", post(cancel_session))
        .with_state(state)
}

async fn health(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let journal = state.store.verify_journal().map_err(ApiError::from_store)?;
    Ok(Json(json!({
        "ok": true,
        "service": "originsd",
        "api_version": "v1",
        "database_schema_version": state.store.schema_version().map_err(ApiError::from_store)?,
        "started_at": state.started_at.as_ref(),
        "workspaces": state.store.workspace_count().map_err(ApiError::from_store)?,
        "sessions": state.store.session_count().map_err(ApiError::from_store)?,
        "capabilities": state.store.capability_count().map_err(ApiError::from_store)?,
        "journal": {
            "ok": journal.ok,
            "entries": journal.entries,
            "head_hash": journal.head_hash,
        }
    })))
}

async fn capabilities(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let capabilities = state
        .store
        .list_capabilities()
        .map_err(ApiError::from_store)?;
    Ok(Json(json!({"capabilities": capabilities})))
}

async fn create_workspace(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<CreateWorkspaceRequest>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    require_auth(&headers, &state.local_token)?;
    let workspace = state
        .store
        .create_workspace(&request.name, request.authority_refs, request.session_refs)
        .map_err(ApiError::from_store)?;
    Ok((StatusCode::CREATED, Json(workspace)))
}

async fn get_workspace(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(workspace_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let workspace = state
        .store
        .get_workspace(&workspace_id)
        .map_err(ApiError::from_store)?;
    Ok(Json(workspace))
}

async fn run_command(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(envelope): Json<Value>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    require_auth(&headers, &state.local_token)?;
    let result = accept_process_command(
        state.store,
        state.process_policy,
        state.process_supervisor,
        envelope,
    )
    .map_err(ApiError::from_store)?;
    Ok((
        StatusCode::ACCEPTED,
        Json(json!({
            "replayed": result.replayed,
            "session": result.session
        })),
    ))
}

async fn list_events(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<EventQuery>,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let page = state
        .store
        .list_events_after(query.after_sequence, query.limit)
        .map_err(ApiError::from_store)?;
    Ok(Json(json!({
        "events": page.events,
        "after_sequence": page.after_sequence,
        "next_sequence": page.next_sequence,
        "head_sequence": page.head_sequence,
        "head_hash": page.head_hash
    })))
}

async fn live_events(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<LiveEventQuery>,
) -> Result<LiveStream, ApiError> {
    require_auth(&headers, &state.local_token)?;
    state
        .store
        .list_events_after(query.after_sequence, 1)
        .map_err(ApiError::from_store)?;
    Ok(journal_stream(state.store, query.after_sequence))
}

async fn list_sessions(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let sessions = state.store.list_sessions().map_err(ApiError::from_store)?;
    Ok(Json(json!({"sessions": sessions})))
}

async fn get_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let session = state
        .store
        .get_session(&session_id)
        .map_err(ApiError::from_store)?;
    Ok(Json(session))
}

async fn get_session_output(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let output = state
        .store
        .get_session_output(&session_id)
        .map_err(ApiError::from_store)?;
    Ok(Json(output_json(&session_id, output)))
}

async fn get_session_output_delta(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
    Query(query): Query<OutputDeltaQuery>,
) -> Result<Json<Value>, ApiError> {
    require_auth(&headers, &state.local_token)?;
    let delta = state
        .store
        .read_output_delta(
            &session_id,
            query.stdout_after,
            query.stderr_after,
            query.limit,
        )
        .map_err(ApiError::from_store)?;
    Ok(Json(delta))
}

async fn live_session_output(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
    Query(query): Query<OutputLiveQuery>,
) -> Result<LiveStream, ApiError> {
    require_auth(&headers, &state.local_token)?;
    state
        .store
        .read_output_delta(
            &session_id,
            query.stdout_after,
            query.stderr_after,
            1,
        )
        .map_err(ApiError::from_store)?;
    Ok(output_stream(
        state.store,
        session_id,
        query.stdout_after,
        query.stderr_after,
    ))
}

async fn cancel_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    require_auth(&headers, &state.local_token)?;
    let event = state
        .store
        .record_process_cancel_requested(&session_id)
        .map_err(ApiError::from_store)?;
    state
        .process_supervisor
        .cancel(&session_id)
        .map_err(ApiError::from_store)?;
    Ok((
        StatusCode::ACCEPTED,
        Json(json!({
            "accepted": true,
            "session_id": session_id,
            "event": event
        })),
    ))
}

fn output_json(session_id: &str, output: SessionOutputRecord) -> Value {
    let stdout_text = String::from_utf8(output.stdout.clone()).ok();
    let stderr_text = String::from_utf8(output.stderr.clone()).ok();
    json!({
        "session_id": session_id,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_hex": hex::encode(&output.stdout),
        "stderr_hex": hex::encode(&output.stderr),
        "stdout_retained_bytes": output.stdout.len(),
        "stderr_retained_bytes": output.stderr.len(),
        "stdout_bytes": output.stdout_bytes,
        "stderr_bytes": output.stderr_bytes,
        "stdout_sha256": output.stdout_sha256,
        "stderr_sha256": output.stderr_sha256,
        "output_truncated": output.output_truncated,
    })
}

fn require_auth(headers: &HeaderMap, expected: &str) -> Result<(), ApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(ApiError::new(
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
pub struct ApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl ApiError {
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

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({
                "ok": false,
                "error_code": self.code,
                "error": self.message,
            })),
        )
            .into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_compare_requires_exact_bytes() {
        assert!(constant_time_eq(b"origins_secret", b"origins_secret"));
        assert!(!constant_time_eq(b"origins_secret", b"origins_secreu"));
        assert!(!constant_time_eq(b"short", b"longer"));
    }
}
