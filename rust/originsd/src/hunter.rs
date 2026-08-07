use crate::store::{append_event, now_rfc3339, Store, StoreError};
use axum::extract::State;
use axum::http::{header::AUTHORIZATION, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use reqwest::{Client, Method, Url};
use rusqlite::TransactionBehavior;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::fmt::{Display, Formatter};
use std::sync::Arc;
use std::time::Duration;
use uuid::Uuid;

pub const HUNTER_URL_ENV: &str = "ORIGINS_HUNTER_URL";
pub const HUNTER_TOKEN_ENV: &str = "ORIGINS_HUNTER_TOKEN";
const MAX_REQUEST_BYTES: usize = 512 * 1024;
const MAX_RESPONSE_BYTES: usize = 2 * 1024 * 1024;
const DEFAULT_TIMEOUT_SECONDS: u64 = 45;

#[derive(Clone)]
pub struct HunterTransport {
    client: Client,
    base_url: Url,
    token: Arc<str>,
}

#[derive(Clone)]
pub struct HunterState {
    pub store: Store,
    pub transport: Option<HunterTransport>,
    pub local_token: Arc<str>,
}

#[derive(Debug, Deserialize)]
pub struct HunterTransportRequest {
    pub workspace_id: String,
    pub operation: String,
    #[serde(default)]
    pub payload: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HunterOperation {
    Version,
    Session,
    CoreStatus,
    ProvidersStatus,
    ChatList,
    ChatLoad,
    ChatSave,
    CoreChat,
}

impl HunterOperation {
    fn parse(value: &str) -> Result<Self, HunterError> {
        match value {
            "version" => Ok(Self::Version),
            "session" => Ok(Self::Session),
            "core_status" => Ok(Self::CoreStatus),
            "providers_status" => Ok(Self::ProvidersStatus),
            "chat_list" => Ok(Self::ChatList),
            "chat_load" => Ok(Self::ChatLoad),
            "chat_save" => Ok(Self::ChatSave),
            "core_chat" => Ok(Self::CoreChat),
            _ => Err(HunterError::InvalidInput(format!(
                "unsupported Hunter operation {value:?}"
            ))),
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Version => "version",
            Self::Session => "session",
            Self::CoreStatus => "core_status",
            Self::ProvidersStatus => "providers_status",
            Self::ChatList => "chat_list",
            Self::ChatLoad => "chat_load",
            Self::ChatSave => "chat_save",
            Self::CoreChat => "core_chat",
        }
    }

    fn authenticated(self) -> bool {
        !matches!(self, Self::Version)
    }
}

#[derive(Debug)]
pub enum HunterError {
    Config(String),
    InvalidInput(String),
    NotConfigured,
    Unavailable(String),
    InvalidResponse(String),
    Store(StoreError),
}

impl Display for HunterError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Config(message) => write!(formatter, "Hunter configuration error: {message}"),
            Self::InvalidInput(message) => write!(formatter, "Hunter request error: {message}"),
            Self::NotConfigured => write!(formatter, "Hunter transport is not configured"),
            Self::Unavailable(message) => {
                write!(formatter, "Hunter transport unavailable: {message}")
            }
            Self::InvalidResponse(message) => write!(formatter, "Hunter response error: {message}"),
            Self::Store(error) => write!(formatter, "Hunter evidence store error: {error}"),
        }
    }
}

impl std::error::Error for HunterError {}

impl From<StoreError> for HunterError {
    fn from(error: StoreError) -> Self {
        Self::Store(error)
    }
}

impl HunterTransport {
    pub fn from_env() -> Result<Option<Self>, HunterError> {
        let raw_url = env::var(HUNTER_URL_ENV).unwrap_or_default();
        let raw_token = env::var(HUNTER_TOKEN_ENV).unwrap_or_default();
        let url = raw_url.trim();
        let token = raw_token.trim();

        if url.is_empty() || token.is_empty() {
            return Ok(None);
        }

        let mut base_url = Url::parse(url)
            .map_err(|error| HunterError::Config(format!("invalid {HUNTER_URL_ENV}: {error}")))?;
        validate_base_url(&base_url)?;
        base_url.set_query(None);
        base_url.set_fragment(None);
        if !base_url.path().ends_with('/') {
            base_url.set_path("/");
        }

        let client = Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(DEFAULT_TIMEOUT_SECONDS))
            .user_agent("Origins-Factory/0.1 HunterTransport/1")
            .build()
            .map_err(|error| HunterError::Config(format!("Hunter HTTP client: {error}")))?;

        Ok(Some(Self {
            client,
            base_url,
            token: Arc::<str>::from(token.to_owned()),
        }))
    }

    pub fn base_origin(&self) -> String {
        self.base_url.origin().ascii_serialization()
    }

    pub async fn execute(
        &self,
        store: &Store,
        request: HunterTransportRequest,
    ) -> Result<Value, HunterError> {
        if !store.workspace_exists(&request.workspace_id)? {
            return Err(HunterError::InvalidInput(format!(
                "workspace {} does not exist",
                request.workspace_id
            )));
        }

        let operation = HunterOperation::parse(request.operation.trim())?;
        let request_id = Uuid::new_v4().hyphenated().to_string();
        let request_value = json!({
            "operation": operation.name(),
            "payload": request.payload,
        });
        let request_bytes = serde_json::to_vec(&request_value)
            .map_err(|error| HunterError::InvalidInput(format!("request JSON: {error}")))?;
        if request_bytes.len() > MAX_REQUEST_BYTES {
            return Err(HunterError::InvalidInput(format!(
                "Hunter request exceeds {MAX_REQUEST_BYTES} bytes"
            )));
        }
        let request_sha256 = sha256_bytes(&request_bytes);

        let (method, url, body) = build_remote_request(&self.base_url, operation, &request_value)?;
        let mut builder = self
            .client
            .request(method, url)
            .header("accept", "application/json");
        if operation.authenticated() {
            builder = builder.bearer_auth(self.token.as_ref());
        }
        if let Some(body) = body {
            builder = builder
                .header("content-type", "application/json")
                .json(&body);
        }

        let remote = match builder.send().await {
            Ok(response) => response,
            Err(error) => {
                record_transport_event(
                    store,
                    &request.workspace_id,
                    "hunter.transport.failed",
                    json!({
                        "request_id": request_id,
                        "operation": operation.name(),
                        "request_sha256": request_sha256,
                        "failure_class": "network_or_timeout"
                    }),
                )?;
                return Err(HunterError::Unavailable(error.to_string()));
            }
        };

        let status = remote.status().as_u16();
        if remote.status().is_redirection() {
            record_transport_event(
                store,
                &request.workspace_id,
                "hunter.transport.failed",
                json!({
                    "request_id": request_id,
                    "operation": operation.name(),
                    "request_sha256": request_sha256,
                    "http_status": status,
                    "failure_class": "redirect_refused"
                }),
            )?;
            return Err(HunterError::Unavailable(format!(
                "Hunter returned redirect HTTP {status}; redirects are disabled"
            )));
        }

        if remote
            .content_length()
            .is_some_and(|length| length > MAX_RESPONSE_BYTES as u64)
        {
            record_transport_event(
                store,
                &request.workspace_id,
                "hunter.transport.failed",
                json!({
                    "request_id": request_id,
                    "operation": operation.name(),
                    "request_sha256": request_sha256,
                    "http_status": status,
                    "failure_class": "response_too_large"
                }),
            )?;
            return Err(HunterError::InvalidResponse(format!(
                "Hunter response exceeds {MAX_RESPONSE_BYTES} bytes"
            )));
        }

        let body_bytes = match read_bounded_body(remote).await {
            Ok(bytes) => bytes,
            Err(error) => {
                let failure_class = match error {
                    HunterError::InvalidResponse(_) => "response_too_large",
                    _ => "response_read_failed",
                };
                record_transport_event(
                    store,
                    &request.workspace_id,
                    "hunter.transport.failed",
                    json!({
                        "request_id": request_id,
                        "operation": operation.name(),
                        "request_sha256": request_sha256,
                        "http_status": status,
                        "failure_class": failure_class
                    }),
                )?;
                return Err(error);
            }
        };
        let response_sha256 = sha256_bytes(&body_bytes);
        let response_body: Value = match serde_json::from_slice(&body_bytes) {
            Ok(body) => body,
            Err(error) => {
                record_transport_event(
                    store,
                    &request.workspace_id,
                    "hunter.transport.failed",
                    json!({
                        "request_id": request_id,
                        "operation": operation.name(),
                        "request_sha256": request_sha256,
                        "http_status": status,
                        "response_bytes": body_bytes.len(),
                        "response_sha256": response_sha256,
                        "failure_class": "invalid_json"
                    }),
                )?;
                return Err(HunterError::InvalidResponse(format!(
                    "non-JSON body: {error}"
                )));
            }
        };
        let completed_at = now_rfc3339();

        record_transport_event(
            store,
            &request.workspace_id,
            "hunter.transport.completed",
            json!({
                "request_id": request_id,
                "operation": operation.name(),
                "request_sha256": request_sha256,
                "http_status": status,
                "response_bytes": body_bytes.len(),
                "response_sha256": response_sha256
            }),
        )?;

        Ok(json!({
            "ok": (200..300).contains(&status),
            "transport": {
                "request_id": request_id,
                "operation": operation.name(),
                "http_status": status,
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
                "response_bytes": body_bytes.len(),
                "completed_at": completed_at
            },
            "body": response_body
        }))
    }
}

fn validate_base_url(url: &Url) -> Result<(), HunterError> {
    if !url.username().is_empty() || url.password().is_some() {
        return Err(HunterError::Config(
            "Hunter URL must not contain credentials".to_owned(),
        ));
    }
    if url.fragment().is_some() || url.query().is_some() {
        return Err(HunterError::Config(
            "Hunter URL must not contain query or fragment".to_owned(),
        ));
    }
    if !matches!(url.path(), "" | "/") {
        return Err(HunterError::Config(
            "Hunter URL must identify an origin, not a path".to_owned(),
        ));
    }
    let host = url
        .host_str()
        .ok_or_else(|| HunterError::Config("Hunter URL host is required".to_owned()))?;
    match url.scheme() {
        "https" => Ok(()),
        "http" if is_loopback_host(host) => Ok(()),
        "http" => Err(HunterError::Config(
            "plain HTTP Hunter URL is allowed only on loopback".to_owned(),
        )),
        other => Err(HunterError::Config(format!(
            "unsupported Hunter URL scheme {other:?}"
        ))),
    }
}

fn is_loopback_host(host: &str) -> bool {
    matches!(host, "localhost" | "127.0.0.1" | "::1")
}

fn build_remote_request(
    base: &Url,
    operation: HunterOperation,
    request: &Value,
) -> Result<(Method, Url, Option<Value>), HunterError> {
    let payload = request.get("payload").cloned().unwrap_or(Value::Null);
    match operation {
        HunterOperation::Version => Ok((Method::GET, joined(base, "api/system/version")?, None)),
        HunterOperation::Session => Ok((Method::GET, joined(base, "api/auth/v2/session")?, None)),
        HunterOperation::CoreStatus => Ok((Method::GET, joined(base, "core/status")?, None)),
        HunterOperation::ProvidersStatus => {
            Ok((Method::GET, joined(base, "core/providers/status")?, None))
        }
        HunterOperation::ChatList => {
            let limit = payload
                .get("limit")
                .and_then(Value::as_u64)
                .unwrap_or(200)
                .clamp(1, 300);
            let mut url = joined(base, "chat/list")?;
            url.query_pairs_mut()
                .append_pair("limit", &limit.to_string());
            Ok((Method::GET, url, None))
        }
        HunterOperation::ChatLoad => {
            let id = safe_chat_id(required_string(&payload, "id")?)?;
            let mut url = joined(base, "chat/load")?;
            url.query_pairs_mut().append_pair("id", &id);
            Ok((Method::GET, url, None))
        }
        HunterOperation::ChatSave => {
            let session = payload.get("session").cloned().ok_or_else(|| {
                HunterError::InvalidInput("chat_save payload.session is required".to_owned())
            })?;
            if !session.is_object() {
                return Err(HunterError::InvalidInput(
                    "chat_save payload.session must be an object".to_owned(),
                ));
            }
            let id = required_string(&session, "id")?;
            safe_chat_id(id)?;
            Ok((
                Method::POST,
                joined(base, "chat/save")?,
                Some(json!({"session": session})),
            ))
        }
        HunterOperation::CoreChat => {
            if !payload.is_object() {
                return Err(HunterError::InvalidInput(
                    "core_chat payload must be an object".to_owned(),
                ));
            }
            let messages = payload
                .get("messages")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    HunterError::InvalidInput("core_chat payload.messages is required".to_owned())
                })?;
            if messages.is_empty() || messages.len() > 12 {
                return Err(HunterError::InvalidInput(
                    "core_chat messages must contain between 1 and 12 entries".to_owned(),
                ));
            }
            Ok((Method::POST, joined(base, "core/chat")?, Some(payload)))
        }
    }
}

fn joined(base: &Url, path: &str) -> Result<Url, HunterError> {
    base.join(path)
        .map_err(|error| HunterError::Config(format!("Hunter route URL: {error}")))
}

fn required_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, HunterError> {
    value
        .get(field)
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .ok_or_else(|| HunterError::InvalidInput(format!("required string field {field} missing")))
}

fn safe_chat_id(value: &str) -> Result<String, HunterError> {
    if value.is_empty() || value.len() > 140 {
        return Err(HunterError::InvalidInput(
            "Hunter chat id must contain 1..140 bytes".to_owned(),
        ));
    }
    if !value.chars().all(|character| {
        character.is_ascii_alphanumeric() || matches!(character, '_' | '-' | '.' | ':')
    }) {
        return Err(HunterError::InvalidInput(
            "Hunter chat id contains unsupported characters".to_owned(),
        ));
    }
    Ok(value.to_owned())
}

async fn read_bounded_body(mut response: reqwest::Response) -> Result<Vec<u8>, HunterError> {
    let mut bytes = Vec::new();
    loop {
        let chunk = response
            .chunk()
            .await
            .map_err(|error| HunterError::Unavailable(error.to_string()))?;
        let Some(chunk) = chunk else {
            break;
        };
        if bytes.len().saturating_add(chunk.len()) > MAX_RESPONSE_BYTES {
            return Err(HunterError::InvalidResponse(format!(
                "Hunter response exceeds {MAX_RESPONSE_BYTES} bytes"
            )));
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}

fn record_transport_event(
    store: &Store,
    workspace_id: &str,
    event_kind: &str,
    payload: Value,
) -> Result<(), StoreError> {
    let mut connection = store.connection()?;
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    append_event(&transaction, workspace_id, event_kind, payload, Vec::new())?;
    transaction.commit()?;
    Ok(())
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

pub fn router(state: HunterState) -> Router {
    Router::new()
        .route("/v1/hunter/status", get(status))
        .route("/v1/hunter/request", post(request))
        .with_state(state)
}

async fn status(
    State(state): State<HunterState>,
    headers: HeaderMap,
) -> Result<Json<Value>, HunterApiError> {
    require_local_auth(&headers, &state.local_token)?;
    Ok(Json(json!({
        "ok": true,
        "capability_id": "origins.hunter.transport",
        "configured": state.transport.is_some(),
        "base_origin": state.transport.as_ref().map(HunterTransport::base_origin),
        "token_exposed": false
    })))
}

async fn request(
    State(state): State<HunterState>,
    headers: HeaderMap,
    Json(request): Json<HunterTransportRequest>,
) -> Result<Json<Value>, HunterApiError> {
    require_local_auth(&headers, &state.local_token)?;
    let transport = state
        .transport
        .as_ref()
        .ok_or(HunterApiError::not_configured())?;
    let result = transport
        .execute(&state.store, request)
        .await
        .map_err(HunterApiError::from_hunter)?;
    Ok(Json(result))
}

fn require_local_auth(headers: &HeaderMap, expected: &str) -> Result<(), HunterApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(HunterApiError::new(
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
pub struct HunterApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl HunterApiError {
    fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
        }
    }

    fn not_configured() -> Self {
        Self::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "HUNTER_NOT_CONFIGURED",
            "Hunter transport is optional and not configured",
        )
    }

    fn from_hunter(error: HunterError) -> Self {
        match error {
            HunterError::InvalidInput(message) | HunterError::Config(message) => {
                Self::new(StatusCode::BAD_REQUEST, "HUNTER_INVALID_REQUEST", message)
            }
            HunterError::NotConfigured => Self::not_configured(),
            HunterError::Unavailable(message) => {
                Self::new(StatusCode::BAD_GATEWAY, "HUNTER_UNAVAILABLE", message)
            }
            HunterError::InvalidResponse(message) => {
                Self::new(StatusCode::BAD_GATEWAY, "HUNTER_INVALID_RESPONSE", message)
            }
            HunterError::Store(error) => Self::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "HUNTER_EVIDENCE_UNAVAILABLE",
                error.to_string(),
            ),
        }
    }
}

impl IntoResponse for HunterApiError {
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
    fn production_requires_https() {
        let url = Url::parse("http://hunter.example.com/").unwrap();
        assert!(validate_base_url(&url).is_err());
        let secure = Url::parse("https://hunter.example.com/").unwrap();
        assert!(validate_base_url(&secure).is_ok());
    }

    #[test]
    fn loopback_http_is_allowed_for_controlled_fixtures() {
        let url = Url::parse("http://127.0.0.1:9999/").unwrap();
        assert!(validate_base_url(&url).is_ok());
    }

    #[test]
    fn arbitrary_operations_are_rejected() {
        assert!(HunterOperation::parse("github_write").is_err());
        assert!(HunterOperation::parse("whatsapp_send").is_err());
        assert!(HunterOperation::parse("login").is_err());
    }

    #[test]
    fn chat_ids_are_bounded_and_safe() {
        assert!(safe_chat_id("origins-workspace-main").is_ok());
        assert!(safe_chat_id("../../escape").is_err());
        assert!(safe_chat_id(&"x".repeat(141)).is_err());
    }
}
