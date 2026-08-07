use crate::store::{Store, StoreError};
use axum::extract::{Path, State};
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

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(health))
        .route("/v1/capabilities", get(capabilities))
        .route("/v1/workspaces", post(create_workspace))
        .route("/v1/workspaces/:workspace_id", get(get_workspace))
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
    let capabilities = state.store.list_capabilities().map_err(ApiError::from_store)?;
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
            StoreError::NotFound(message) => {
                Self::new(StatusCode::NOT_FOUND, "NOT_FOUND", message)
            }
            StoreError::Corrupt(message) => Self::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "CORRUPT_STATE",
                message,
            ),
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
