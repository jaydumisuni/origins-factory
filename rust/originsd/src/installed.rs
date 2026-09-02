use axum::body::{to_bytes, Body};
use axum::extract::{Json, State};
use axum::http::{header, HeaderMap, HeaderValue, Request, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use axum::routing::{any, get, post};
use axum::Router;
use reqwest::{Client, Method, Url};
use serde::Deserialize;
use serde_json::json;
use std::env;
use std::fs;
use std::future::IntoFuture;
use std::net::{SocketAddr, TcpListener as StdTcpListener};
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tokio::time::{sleep, Instant};
use uuid::Uuid;

const LAUNCHER_EXE: &str = "Origins Factory.exe";
const DAEMON_EXE: &str = "originsd.exe";
const TOKEN_FILE: &str = "local-token.txt";
const DEFAULT_DAEMON_BIND: &str = "127.0.0.1:48700";
const DEFAULT_UI_BIND: &str = "127.0.0.1:48750";
const MAX_PROXY_BODY: usize = 8 * 1024 * 1024;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(20);
const SESSION_COOKIE: &str = "origins_installed_session";

#[derive(Clone)]
struct LauncherState {
    client: Client,
    workspace_root: Arc<PathBuf>,
    daemon_base: Url,
    bootstrap_nonce: Arc<Mutex<Option<String>>>,
    session_id: Arc<str>,
    local_token: Arc<str>,
}

#[derive(Debug, Deserialize)]
struct BootstrapRequest {
    nonce: String,
}

pub fn is_launcher_entrypoint() -> bool {
    if env::var("ORIGINS_INSTALLED_LAUNCHER").ok().as_deref() == Some("1") {
        return true;
    }
    env::current_exe()
        .ok()
        .and_then(|path| {
            path.file_name()
                .map(|name| name.to_string_lossy().into_owned())
        })
        .is_some_and(|name| name.eq_ignore_ascii_case(LAUNCHER_EXE))
}

pub async fn run() -> Result<(), String> {
    let probe = env::args().any(|arg| arg == "--probe");
    if probe {
        return run_probe().await;
    }

    let exe_dir = executable_dir()?;
    let workspace_root = exe_dir.join("workspace");
    require_workspace(&workspace_root)?;
    let data_dir = installed_data_dir()?;
    require_external_data_dir(&exe_dir, &data_dir)?;
    fs::create_dir_all(&data_dir).map_err(|error| format!("create data directory: {error}"))?;
    require_external_data_dir(&exe_dir, &data_dir)?;

    let daemon_bind = env::var("ORIGINS_INSTALLED_DAEMON_BIND")
        .unwrap_or_else(|_| DEFAULT_DAEMON_BIND.to_owned());
    let daemon_addr: SocketAddr = daemon_bind
        .parse()
        .map_err(|error| format!("invalid installed daemon bind {daemon_bind:?}: {error}"))?;
    if !daemon_addr.ip().is_loopback() {
        return Err("installed daemon bind must remain loopback-only".to_owned());
    }

    let client = local_client()?;
    let daemon_base = Url::parse(&format!("http://{daemon_addr}/"))
        .map_err(|error| format!("daemon URL: {error}"))?;
    let mut child = ensure_daemon(&client, &exe_dir, &data_dir, daemon_addr).await?;
    let token = read_local_token(&data_dir)?;

    let nonce = Uuid::new_v4().simple().to_string();
    let state = LauncherState {
        client,
        workspace_root: Arc::new(workspace_root),
        daemon_base,
        bootstrap_nonce: Arc::new(Mutex::new(Some(nonce.clone()))),
        session_id: Arc::<str>::from(Uuid::new_v4().simple().to_string()),
        local_token: Arc::<str>::from(token),
    };

    let requested_ui =
        env::var("ORIGINS_INSTALLED_UI_BIND").unwrap_or_else(|_| DEFAULT_UI_BIND.to_owned());
    let requested_addr: SocketAddr = requested_ui
        .parse()
        .map_err(|error| format!("invalid installed UI bind {requested_ui:?}: {error}"))?;
    if !requested_addr.ip().is_loopback() {
        return Err("installed UI bind must remain loopback-only".to_owned());
    }
    let listener = TcpListener::bind(requested_addr)
        .await
        .map_err(|error| format!("bind installed UI: {error}"))?;
    let local_addr = listener
        .local_addr()
        .map_err(|error| format!("UI address: {error}"))?;
    let app = launcher_router(state);
    let url = format!("http://{local_addr}/#bootstrap={nonce}");
    open_browser(&url).await;

    let server = axum::serve(listener, app).into_future();
    tokio::pin!(server);

    if let Some(ref mut owned_child) = child {
        tokio::select! {
            result = &mut server => result.map_err(|error| format!("installed UI server: {error}"))?,
            status = owned_child.wait() => {
                let status = status.map_err(|error| format!("wait for originsd: {error}"))?;
                return Err(format!("originsd exited while installed launcher was active: {status}"));
            }
        }
    } else {
        server
            .await
            .map_err(|error| format!("installed UI server: {error}"))?;
    }
    Ok(())
}

fn launcher_router(state: LauncherState) -> Router {
    Router::new()
        .route("/origins-bootstrap", post(bootstrap))
        .route("/origins-bootstrap/status", get(bootstrap_status))
        .route("/origins-api", any(proxy_originsd_root))
        .route("/origins-api/*path", any(proxy_originsd))
        .route("/origins-intelligence", any(proxy_intelligence_root))
        .route("/origins-intelligence/*path", any(proxy_intelligence))
        .route("/origins-phase5", any(proxy_phase5_root))
        .route("/origins-phase5/*path", any(proxy_phase5))
        .route("/origins-phase6", any(proxy_phase6_root))
        .route("/origins-phase6/*path", any(proxy_phase6))
        .route("/origins-phase7", any(proxy_phase7_root))
        .route("/origins-phase7/*path", any(proxy_phase7))
        .fallback(serve_static)
        .with_state(state)
}

async fn bootstrap(
    State(state): State<LauncherState>,
    Json(request): Json<BootstrapRequest>,
) -> Response {
    let mut expected = state.bootstrap_nonce.lock().await;
    let valid = expected
        .as_deref()
        .is_some_and(|nonce| constant_time_eq(nonce.as_bytes(), request.nonce.trim().as_bytes()));
    if !valid {
        return (StatusCode::UNAUTHORIZED, Json(json!({"ok": false, "error": "invalid_bootstrap_nonce", "installed_proxy": true, "authenticated": false}))).into_response();
    }
    *expected = None;
    let cookie = format!(
        "{SESSION_COOKIE}={}; Path=/; HttpOnly; SameSite=Strict",
        state.session_id
    );
    let mut response =
        Json(json!({"ok": true, "installed_proxy": true, "authenticated": true})).into_response();
    match HeaderValue::from_str(&cookie) {
        Ok(value) => {
            response.headers_mut().insert(header::SET_COOKIE, value);
            response
        }
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"ok": false, "error": "cookie_encoding_failed", "installed_proxy": true, "authenticated": false}))).into_response(),
    }
}

async fn bootstrap_status(State(state): State<LauncherState>, headers: HeaderMap) -> Response {
    let authenticated = session_matches(&headers, state.session_id.as_ref());
    let status = if authenticated {
        StatusCode::OK
    } else {
        StatusCode::UNAUTHORIZED
    };
    (
        status,
        Json(json!({"ok": authenticated, "installed_proxy": true, "authenticated": authenticated})),
    )
        .into_response()
}

async fn proxy_originsd_root(
    State(state): State<LauncherState>,
    request: Request<Body>,
) -> Response {
    let base = state.daemon_base.clone();
    proxy_request(state, request, "originsd", base, "").await
}

async fn proxy_originsd(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    let path = request
        .uri()
        .path()
        .strip_prefix("/origins-api")
        .unwrap_or("")
        .to_owned();
    let base = state.daemon_base.clone();
    proxy_request(state, request, "originsd", base, &path).await
}

async fn proxy_intelligence_root(
    State(state): State<LauncherState>,
    request: Request<Body>,
) -> Response {
    proxy_optional(
        state,
        request,
        "intelligence",
        "http://127.0.0.1:48710/",
        "",
    )
    .await
}
async fn proxy_intelligence(
    State(state): State<LauncherState>,
    request: Request<Body>,
) -> Response {
    let path = request
        .uri()
        .path()
        .strip_prefix("/origins-intelligence")
        .unwrap_or("")
        .to_owned();
    proxy_optional(
        state,
        request,
        "intelligence",
        "http://127.0.0.1:48710/",
        &path,
    )
    .await
}
async fn proxy_phase5_root(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    proxy_optional(state, request, "phase5", "http://127.0.0.1:48720/", "").await
}
async fn proxy_phase5(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    let path = request
        .uri()
        .path()
        .strip_prefix("/origins-phase5")
        .unwrap_or("")
        .to_owned();
    proxy_optional(state, request, "phase5", "http://127.0.0.1:48720/", &path).await
}
async fn proxy_phase6_root(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    proxy_optional(state, request, "phase6", "http://127.0.0.1:48730/", "").await
}
async fn proxy_phase6(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    let path = request
        .uri()
        .path()
        .strip_prefix("/origins-phase6")
        .unwrap_or("")
        .to_owned();
    proxy_optional(state, request, "phase6", "http://127.0.0.1:48730/", &path).await
}
async fn proxy_phase7_root(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    proxy_optional(state, request, "phase7", "http://127.0.0.1:49327/", "").await
}
async fn proxy_phase7(State(state): State<LauncherState>, request: Request<Body>) -> Response {
    let path = request
        .uri()
        .path()
        .strip_prefix("/origins-phase7")
        .unwrap_or("")
        .to_owned();
    proxy_optional(state, request, "phase7", "http://127.0.0.1:49327/", &path).await
}

async fn proxy_optional(
    state: LauncherState,
    request: Request<Body>,
    service: &'static str,
    base: &'static str,
    path: &str,
) -> Response {
    let base = match Url::parse(base) {
        Ok(value) => value,
        Err(error) => return proxy_failure(service, format!("invalid local target: {error}")),
    };
    proxy_request(state, request, service, base, path).await
}

async fn proxy_request(
    state: LauncherState,
    request: Request<Body>,
    service: &'static str,
    base: Url,
    path: &str,
) -> Response {
    let authenticated = session_matches(request.headers(), state.session_id.as_ref());
    let method = match Method::from_bytes(request.method().as_str().as_bytes()) {
        Ok(method) => method,
        Err(error) => return proxy_failure(service, format!("unsupported method: {error}")),
    };
    let query = request.uri().query().map(str::to_owned);
    let target = match proxy_url(base, path, query.as_deref()) {
        Ok(url) => url,
        Err(error) => return proxy_failure(service, error),
    };
    let content_type = request
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let accept = request
        .headers()
        .get(header::ACCEPT)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let body = match to_bytes(request.into_body(), MAX_PROXY_BODY).await {
        Ok(bytes) => bytes,
        Err(error) => return proxy_failure(service, format!("request body rejected: {error}")),
    };
    let mut outbound = state.client.request(method, target);
    if let Some(value) = content_type {
        outbound = outbound.header("content-type", value);
    }
    if let Some(value) = accept {
        outbound = outbound.header("accept", value);
    }
    if authenticated {
        outbound = outbound.bearer_auth(state.local_token.as_ref());
    }
    if !body.is_empty() {
        outbound = outbound.body(body.to_vec());
    }

    let upstream = match outbound.send().await {
        Ok(response) => response,
        Err(error) => return proxy_failure(service, error.to_string()),
    };
    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let content_type = upstream
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let bytes = match upstream.bytes().await {
        Ok(bytes) if bytes.len() <= MAX_PROXY_BODY => bytes,
        Ok(_) => {
            return proxy_failure(
                service,
                "upstream response exceeded installed proxy limit".to_owned(),
            )
        }
        Err(error) => {
            return proxy_failure(service, format!("upstream response read failed: {error}"))
        }
    };
    let mut response = Response::new(Body::from(bytes));
    *response.status_mut() = status;
    if let Some(value) = content_type.and_then(|value| HeaderValue::from_str(&value).ok()) {
        response.headers_mut().insert(header::CONTENT_TYPE, value);
    }
    response
}

fn proxy_failure(service: &str, detail: String) -> Response {
    let error = if service == "originsd" {
        "core_service_unavailable"
    } else {
        "optional_service_unavailable"
    };
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({
            "ok": false,
            "error": error,
            "service": service,
            "detail": detail,
        })),
    )
        .into_response()
}

async fn serve_static(State(state): State<LauncherState>, uri: Uri) -> Response {
    let relative = match safe_static_path(uri.path()) {
        Ok(path) => path,
        Err(message) => return (StatusCode::BAD_REQUEST, message).into_response(),
    };
    let mut candidate = state.workspace_root.join(&relative);
    if relative.as_os_str().is_empty() || !candidate.is_file() {
        if candidate.extension().is_none() {
            candidate = state.workspace_root.join("index.html");
        }
    }
    if !candidate.is_file() {
        return StatusCode::NOT_FOUND.into_response();
    }
    let bytes = match fs::read(&candidate) {
        Ok(bytes) => bytes,
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    };
    let mut response = Response::new(Body::from(bytes));
    if let Ok(value) = HeaderValue::from_str(content_type_for(&candidate)) {
        response.headers_mut().insert(header::CONTENT_TYPE, value);
    }
    response
}

fn safe_static_path(raw: &str) -> Result<PathBuf, &'static str> {
    let decoded = percent_decode_path(raw)?;
    let mut output = PathBuf::new();
    for component in Path::new(decoded.trim_start_matches('/')).components() {
        match component {
            Component::Normal(part) => output.push(part),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("invalid static path")
            }
        }
    }
    Ok(output)
}

fn percent_decode_path(raw: &str) -> Result<String, &'static str> {
    let bytes = raw.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            if index + 2 >= bytes.len() {
                return Err("invalid percent encoding");
            }
            let high = hex_value(bytes[index + 1]).ok_or("invalid percent encoding")?;
            let low = hex_value(bytes[index + 2]).ok_or("invalid percent encoding")?;
            output.push((high << 4) | low);
            index += 3;
        } else {
            output.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(output).map_err(|_| "static path is not UTF-8")
}

fn hex_value(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn content_type_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "ico" => "image/x-icon",
        "woff2" => "font/woff2",
        _ => "application/octet-stream",
    }
}

fn proxy_url(mut base: Url, path: &str, query: Option<&str>) -> Result<Url, String> {
    let relative = path.trim_start_matches('/');
    if relative.split('/').any(|part| part == "..") {
        return Err("proxy path traversal refused".to_owned());
    }
    let target_path = if relative.is_empty() {
        "/".to_owned()
    } else {
        format!("/{relative}")
    };
    base.set_path(&target_path);
    base.set_query(query);
    Ok(base)
}

fn session_matches(headers: &HeaderMap, expected: &str) -> bool {
    headers
        .get(header::COOKIE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| {
            value.split(';').find_map(|entry| {
                let (name, value) = entry.trim().split_once('=')?;
                (name == SESSION_COOKIE).then_some(value)
            })
        })
        .is_some_and(|value| constant_time_eq(value.as_bytes(), expected.as_bytes()))
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut diff = 0u8;
    for (a, b) in left.iter().zip(right.iter()) {
        diff |= a ^ b;
    }
    diff == 0
}

fn executable_dir() -> Result<PathBuf, String> {
    let exe = env::current_exe().map_err(|error| format!("current executable: {error}"))?;
    exe.parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| "installed executable has no parent directory".to_owned())
}

fn require_workspace(root: &Path) -> Result<(), String> {
    if root.is_symlink() || !root.join("index.html").is_file() {
        return Err(format!(
            "installed Workspace missing index.html: {}",
            root.display()
        ));
    }
    Ok(())
}

fn require_external_data_dir(exe_dir: &Path, data_dir: &Path) -> Result<(), String> {
    if !data_dir.is_absolute() {
        return Err(
            "installed Origins data directory must be absolute and external to the payload"
                .to_owned(),
        );
    }
    if data_dir.starts_with(exe_dir) {
        return Err(
            "installed Origins data directory must remain external to the application payload"
                .to_owned(),
        );
    }
    if data_dir.exists() {
        let resolved_exe = fs::canonicalize(exe_dir)
            .map_err(|error| format!("resolve installed payload directory: {error}"))?;
        let resolved_data = fs::canonicalize(data_dir)
            .map_err(|error| format!("resolve installed data directory: {error}"))?;
        if resolved_data.starts_with(&resolved_exe) {
            return Err(
                "installed Origins data directory resolves inside the application payload"
                    .to_owned(),
            );
        }
    }
    Ok(())
}

fn installed_data_dir() -> Result<PathBuf, String> {
    if let Some(value) = env::var_os("ORIGINS_DATA_DIR") {
        let path = PathBuf::from(value);
        if path.as_os_str().is_empty() {
            return Err("ORIGINS_DATA_DIR is empty".to_owned());
        }
        return Ok(path);
    }
    let base = env::var_os("LOCALAPPDATA")
        .or_else(|| env::var_os("APPDATA"))
        .ok_or_else(|| {
            "LOCALAPPDATA/APPDATA is unavailable for installed Origins state".to_owned()
        })?;
    Ok(PathBuf::from(base)
        .join("THETECHGUY")
        .join("Origins Factory"))
}

fn local_client() -> Result<Client, String> {
    Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|error| format!("local HTTP client: {error}"))
}

async fn ensure_daemon(
    client: &Client,
    exe_dir: &Path,
    data_dir: &Path,
    daemon_addr: SocketAddr,
) -> Result<Option<Child>, String> {
    let health_url = format!("http://{daemon_addr}/v1/health");
    if health_ok(client, &health_url).await {
        let token = read_local_token(data_dir).map_err(|error| {
            format!(
                "healthy originsd already occupies {daemon_addr}, but it cannot be bound to the intended data root {}: {error}",
                data_dir.display()
            )
        })?;
        if daemon_matches_data_root(client, daemon_addr, &token).await {
            return Ok(None);
        }
        return Err(format!(
            "healthy originsd already occupies {daemon_addr}, but it does not belong to the intended data root {}",
            data_dir.display()
        ));
    }
    let daemon = exe_dir.join(DAEMON_EXE);
    if daemon.is_symlink() || !daemon.is_file() {
        return Err(format!("installed daemon missing: {}", daemon.display()));
    }
    let mut command = Command::new(&daemon);
    command
        .env("ORIGINS_BIND", daemon_addr.to_string())
        .env("ORIGINS_DATA_DIR", data_dir)
        .env_remove("ORIGINS_INSTALLED_LAUNCHER")
        .kill_on_drop(true)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let mut child = command
        .spawn()
        .map_err(|error| format!("start originsd: {error}"))?;
    if let Err(error) = wait_for_health(client, &health_url).await {
        let _ = child.kill().await;
        let _ = child.wait().await;
        return Err(error);
    }
    let token = match read_local_token(data_dir) {
        Ok(token) => token,
        Err(error) => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            return Err(error);
        }
    };
    if !daemon_matches_data_root(client, daemon_addr, &token).await {
        let _ = child.kill().await;
        let _ = child.wait().await;
        return Err(format!(
            "started originsd at {daemon_addr}, but protected state did not bind to {}",
            data_dir.display()
        ));
    }
    Ok(Some(child))
}

async fn wait_for_health(client: &Client, url: &str) -> Result<(), String> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    loop {
        if health_ok(client, url).await {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(format!(
                "originsd did not become healthy within {:?}",
                STARTUP_TIMEOUT
            ));
        }
        sleep(Duration::from_millis(150)).await;
    }
}

async fn health_ok(client: &Client, url: &str) -> bool {
    match client.get(url).send().await {
        Ok(response) if response.status().is_success() => response
            .json::<serde_json::Value>()
            .await
            .ok()
            .is_some_and(|value| {
                value.get("ok") == Some(&serde_json::Value::Bool(true))
                    && value.get("service")
                        == Some(&serde_json::Value::String("originsd".to_owned()))
            }),
        _ => false,
    }
}

async fn daemon_matches_data_root(client: &Client, daemon_addr: SocketAddr, token: &str) -> bool {
    let url = format!("http://{daemon_addr}/v1/capabilities");
    match client.get(url).bearer_auth(token).send().await {
        Ok(response) if response.status().is_success() => response
            .json::<serde_json::Value>()
            .await
            .ok()
            .and_then(|value| {
                value
                    .get("capabilities")
                    .and_then(serde_json::Value::as_array)
                    .map(|_| ())
            })
            .is_some(),
        _ => false,
    }
}

fn read_local_token(data_dir: &Path) -> Result<String, String> {
    let value = fs::read_to_string(data_dir.join(TOKEN_FILE))
        .map_err(|error| format!("read installed token: {error}"))?;
    let token = value.trim().to_owned();
    if token.is_empty() {
        return Err("installed token file is empty".to_owned());
    }
    Ok(token)
}

async fn open_browser(url: &str) {
    #[cfg(windows)]
    {
        let _ = Command::new("cmd")
            .args(["/C", "start", "", url])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn();
    }
    #[cfg(not(windows))]
    {
        println!("Origins installed UI: {url}");
    }
}

fn reserve_loopback_port() -> Result<u16, String> {
    let listener = StdTcpListener::bind("127.0.0.1:0")
        .map_err(|error| format!("reserve loopback port: {error}"))?;
    listener
        .local_addr()
        .map(|addr| addr.port())
        .map_err(|error| format!("reserved port address: {error}"))
}

async fn run_probe() -> Result<(), String> {
    let exe_dir = executable_dir()?;
    let workspace_root = exe_dir.join("workspace");
    require_workspace(&workspace_root)?;
    let probe_root = env::temp_dir().join(format!(
        "origins-installed-probe-{}",
        Uuid::new_v4().simple()
    ));
    fs::create_dir_all(&probe_root).map_err(|error| format!("create probe root: {error}"))?;
    let client = local_client()?;

    let first_port = reserve_loopback_port()?;
    let first_addr: SocketAddr = format!("127.0.0.1:{first_port}")
        .parse()
        .map_err(|error| format!("probe bind: {error}"))?;
    let mut first = ensure_daemon(&client, &exe_dir, &probe_root, first_addr)
        .await?
        .ok_or_else(|| "probe unexpectedly reused an existing daemon".to_owned())?;
    let token_before = read_local_token(&probe_root)?;
    exercise_installed_proxy(&client, &workspace_root, first_addr, token_before.clone()).await?;

    let mismatched_root = env::temp_dir().join(format!(
        "origins-installed-mismatch-{}",
        Uuid::new_v4().simple()
    ));
    fs::create_dir_all(&mismatched_root)
        .map_err(|error| format!("create mismatch probe root: {error}"))?;
    match ensure_daemon(&client, &exe_dir, &mismatched_root, first_addr).await {
        Err(error)
            if error.contains("cannot be bound to the intended data root")
                || error.contains("does not belong to the intended data root") => {}
        Ok(Some(mut unexpected)) => {
            let _ = unexpected.kill().await;
            let _ = first.kill().await;
            let _ = fs::remove_dir_all(&mismatched_root);
            return Err("installed Origins reused an occupied daemon without proving the intended data root".to_owned());
        }
        Ok(None) => {
            let _ = first.kill().await;
            let _ = fs::remove_dir_all(&mismatched_root);
            return Err(
                "installed Origins reused an occupied daemon with the wrong data root".to_owned(),
            );
        }
        Err(error) => {
            let _ = first.kill().await;
            let _ = fs::remove_dir_all(&mismatched_root);
            return Err(format!("unexpected occupied-daemon refusal: {error}"));
        }
    }
    let _ = fs::remove_dir_all(&mismatched_root);

    first
        .kill()
        .await
        .map_err(|error| format!("stop first probe daemon: {error}"))?;
    let _ = first.wait().await;

    let second_port = reserve_loopback_port()?;
    let second_addr: SocketAddr = format!("127.0.0.1:{second_port}")
        .parse()
        .map_err(|error| format!("probe bind: {error}"))?;
    let mut second = ensure_daemon(&client, &exe_dir, &probe_root, second_addr)
        .await?
        .ok_or_else(|| "probe unexpectedly reused an existing daemon on restart".to_owned())?;
    let token_after = read_local_token(&probe_root)?;
    if token_before != token_after {
        let _ = second.kill().await;
        return Err("installed Origins token did not survive daemon restart".to_owned());
    }
    let health_url = format!("http://{second_addr}/v1/health");
    if !health_ok(&client, &health_url).await {
        let _ = second.kill().await;
        return Err("installed Origins restart health proof failed".to_owned());
    }
    second
        .kill()
        .await
        .map_err(|error| format!("stop second probe daemon: {error}"))?;
    let _ = second.wait().await;
    let _ = fs::remove_dir_all(&probe_root);
    println!("ORIGINS_WINDOWS_INSTALLED_PROBE=PASS");
    Ok(())
}

async fn exercise_installed_proxy(
    client: &Client,
    workspace_root: &Path,
    daemon_addr: SocketAddr,
    token: String,
) -> Result<(), String> {
    let daemon_base = Url::parse(&format!("http://{daemon_addr}/"))
        .map_err(|error| format!("probe daemon URL: {error}"))?;
    let nonce = Uuid::new_v4().simple().to_string();
    let session_id = Uuid::new_v4().simple().to_string();
    let state = LauncherState {
        client: client.clone(),
        workspace_root: Arc::new(workspace_root.to_path_buf()),
        daemon_base,
        bootstrap_nonce: Arc::new(Mutex::new(Some(nonce.clone()))),
        session_id: Arc::<str>::from(session_id.clone()),
        local_token: Arc::<str>::from(token),
    };
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|error| format!("bind probe UI: {error}"))?;
    let addr = listener
        .local_addr()
        .map_err(|error| format!("probe UI address: {error}"))?;
    let server = tokio::spawn(async move { axum::serve(listener, launcher_router(state)).await });
    let base = format!("http://{addr}");

    let index = client
        .get(format!("{base}/"))
        .send()
        .await
        .map_err(|error| format!("probe UI index: {error}"))?;
    if !index.status().is_success() {
        server.abort();
        return Err("installed Workspace index is not servable".to_owned());
    }

    let unauth = client
        .get(format!("{base}/origins-bootstrap/status"))
        .send()
        .await
        .map_err(|error| format!("probe bootstrap status: {error}"))?;
    if unauth.status() != reqwest::StatusCode::UNAUTHORIZED {
        server.abort();
        return Err("bootstrap status must reject an unauthenticated browser".to_owned());
    }

    let bootstrap = client
        .post(format!("{base}/origins-bootstrap"))
        .json(&json!({"nonce": nonce}))
        .send()
        .await
        .map_err(|error| format!("probe bootstrap: {error}"))?;
    if !bootstrap.status().is_success() {
        server.abort();
        return Err("installed bootstrap exchange failed".to_owned());
    }
    let cookie = bootstrap
        .headers()
        .get(reqwest::header::SET_COOKIE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(';').next())
        .ok_or_else(|| "bootstrap did not issue session cookie".to_owned())?
        .to_owned();

    let replay = client
        .post(format!("{base}/origins-bootstrap"))
        .json(&json!({"nonce": "replay"}))
        .send()
        .await
        .map_err(|error| format!("probe bootstrap replay: {error}"))?;
    if replay.status() != reqwest::StatusCode::UNAUTHORIZED {
        server.abort();
        return Err("bootstrap nonce replay was not refused".to_owned());
    }

    let protected = client
        .get(format!("{base}/origins-api/v1/capabilities"))
        .header(reqwest::header::COOKIE, cookie)
        .send()
        .await
        .map_err(|error| format!("probe authenticated proxy: {error}"))?;
    if !protected.status().is_success() {
        server.abort();
        return Err(format!(
            "installed authenticated proxy failed: {}",
            protected.status()
        ));
    }

    server.abort();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn launcher_name_is_canonical() {
        assert_eq!(LAUNCHER_EXE, "Origins Factory.exe");
    }

    #[test]
    fn static_path_rejects_parent_traversal() {
        assert!(safe_static_path("/../secret").is_err());
        assert!(safe_static_path("/%2e%2e/secret").is_err());
    }

    #[test]
    fn static_path_accepts_assets() {
        assert_eq!(
            safe_static_path("/assets/app.js").unwrap(),
            PathBuf::from("assets").join("app.js")
        );
    }

    #[test]
    fn proxy_path_refuses_parent_segment() {
        let base = Url::parse("http://127.0.0.1:48700/").unwrap();
        assert!(proxy_url(base, "/v1/../secret", None).is_err());
    }

    #[test]
    fn constant_time_equality_is_exact() {
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd"));
        assert!(!constant_time_eq(b"abc", b"abcd"));
    }
}
