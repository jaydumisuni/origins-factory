use crate::store::Store;
use crate::workspace_files::{
    list_repository_files, read_repository_file, write_repository_file, WorkspaceFileError,
};
use crate::workspace_roots::WorkspaceRootPolicy;
use axum::extract::{Path, Query, State};
use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

#[derive(Clone)]
pub struct WorkspaceFileState {
    pub store: Store,
    pub policy: WorkspaceRootPolicy,
    pub local_token: Arc<str>,
}

#[derive(Debug, Deserialize, Default)]
pub struct FilePathQuery {
    #[serde(default)]
    pub path: String,
}

#[derive(Debug, Deserialize)]
pub struct WriteFileRequest {
    pub path: String,
    pub text: String,
    pub expected_sha256: Option<String>,
}

pub fn router(state: WorkspaceFileState) -> Router {
    Router::new()
        .route(
            "/v1/repositories/:repository_id/files",
            get(list_files),
        )
        .route(
            "/v1/repositories/:repository_id/file",
            get(read_file).post(write_file),
        )
        .with_state(state)
}

async fn list_files(
    State(state): State<WorkspaceFileState>,
    headers: HeaderMap,
    Path(repository_id): Path<String>,
    Query(query): Query<FilePathQuery>,
) -> Result<Json<Value>, FileApiError> {
    require_auth(&headers, &state.local_token)?;
    Ok(Json(
        list_repository_files(&state.store, &state.policy, &repository_id, &query.path)
            .map_err(FileApiError::from_file)?,
    ))
}

async fn read_file(
    State(state): State<WorkspaceFileState>,
    headers: HeaderMap,
    Path(repository_id): Path<String>,
    Query(query): Query<FilePathQuery>,
) -> Result<Json<Value>, FileApiError> {
    require_auth(&headers, &state.local_token)?;
    if query.path.trim().is_empty() {
        return Err(FileApiError::new(
            StatusCode::BAD_REQUEST,
            "INVALID_PATH",
            "file path is required",
        ));
    }
    Ok(Json(
        read_repository_file(&state.store, &state.policy, &repository_id, &query.path)
            .map_err(FileApiError::from_file)?,
    ))
}

async fn write_file(
    State(state): State<WorkspaceFileState>,
    headers: HeaderMap,
    Path(repository_id): Path<String>,
    Json(request): Json<WriteFileRequest>,
) -> Result<Json<Value>, FileApiError> {
    require_auth(&headers, &state.local_token)?;
    Ok(Json(
        write_repository_file(
            &state.store,
            &state.policy,
            &repository_id,
            &request.path,
            &request.text,
            request.expected_sha256.as_deref(),
        )
        .map_err(FileApiError::from_file)?,
    ))
}

fn require_auth(headers: &HeaderMap, expected: &str) -> Result<(), FileApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(FileApiError::new(
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
struct FileApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl FileApiError {
    fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
        }
    }

    fn from_file(error: WorkspaceFileError) -> Self {
        let status = match error.code {
            "INVALID_PATH" => StatusCode::BAD_REQUEST,
            "RESOURCE_NOT_FOUND" => StatusCode::NOT_FOUND,
            "FILE_TOO_LARGE" => StatusCode::PAYLOAD_TOO_LARGE,
            "UNSUPPORTED_FILE" => StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "FILE_CHANGED" => StatusCode::CONFLICT,
            _ => StatusCode::SERVICE_UNAVAILABLE,
        };
        Self::new(status, error.code, error.message)
    }
}

impl IntoResponse for FileApiError {
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
    fn auth_compare_requires_exact_bytes() {
        assert!(constant_time_eq(b"alpha", b"alpha"));
        assert!(!constant_time_eq(b"alpha", b"alphb"));
        assert!(!constant_time_eq(b"alpha", b"alpha2"));
    }
}
