pub mod auth;
pub mod control;
pub mod events;
pub mod http;
pub mod live;
pub mod output_live;
pub mod process;
pub mod repository;
pub mod sessions;
pub mod store;
pub mod workspace_roots;

use crate::auth::load_or_create_token;
use crate::http::{router, AppState};
use crate::process::{ProcessPolicy, ProcessSupervisor};
use crate::repository::initialize as initialize_repository_store;
use crate::store::Store;
use crate::workspace_roots::WorkspaceRootPolicy;
use chrono::{SecondsFormat, Utc};
use std::env;
use std::fmt::{Display, Formatter};
use std::fs;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::net::TcpListener;

pub const DEFAULT_BIND: &str = "127.0.0.1:48700";
pub const DATABASE_FILE: &str = "origins.sqlite3";

#[derive(Debug)]
pub enum RuntimeError {
    Config(String),
    Io(String),
    Store(String),
    Server(String),
}

impl Display for RuntimeError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Config(message) => write!(formatter, "configuration error: {message}"),
            Self::Io(message) => write!(formatter, "I/O error: {message}"),
            Self::Store(message) => write!(formatter, "store error: {message}"),
            Self::Server(message) => write!(formatter, "server error: {message}"),
        }
    }
}

impl std::error::Error for RuntimeError {}

#[derive(Debug, Clone)]
pub struct RuntimeConfig {
    pub bind: SocketAddr,
    pub data_dir: PathBuf,
}

impl RuntimeConfig {
    pub fn from_env() -> Result<Self, RuntimeError> {
        let bind_text = env::var("ORIGINS_BIND").unwrap_or_else(|_| DEFAULT_BIND.to_owned());
        let bind: SocketAddr = bind_text.parse().map_err(|error| {
            RuntimeError::Config(format!("invalid ORIGINS_BIND {bind_text:?}: {error}"))
        })?;
        let bind = require_loopback(bind)?;

        let data_dir = env::var_os("ORIGINS_DATA_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(".origins"));
        Ok(Self { bind, data_dir })
    }
}

fn require_loopback(bind: SocketAddr) -> Result<SocketAddr, RuntimeError> {
    if !bind.ip().is_loopback() {
        return Err(RuntimeError::Config(
            "originsd v1 refuses non-loopback bind addresses".to_owned(),
        ));
    }
    Ok(bind)
}

pub async fn run_from_env() -> Result<(), RuntimeError> {
    run(RuntimeConfig::from_env()?).await
}

pub async fn run(config: RuntimeConfig) -> Result<(), RuntimeError> {
    fs::create_dir_all(&config.data_dir).map_err(|error| RuntimeError::Io(error.to_string()))?;
    let token = load_or_create_token(&config.data_dir)
        .map_err(|error| RuntimeError::Io(error.to_string()))?;
    let process_policy = ProcessPolicy::from_env().map_err(RuntimeError::Config)?;
    let repository_policy = WorkspaceRootPolicy::from_env().map_err(RuntimeError::Config)?;
    let store = Store::open(config.data_dir.join(DATABASE_FILE))
        .map_err(|error| RuntimeError::Store(error.to_string()))?;
    initialize_repository_store(&store).map_err(|error| RuntimeError::Store(error.to_string()))?;
    let state = AppState {
        store,
        process_policy,
        process_supervisor: ProcessSupervisor::default(),
        repository_policy,
        local_token: Arc::<str>::from(token),
        started_at: Arc::<str>::from(now_rfc3339()),
    };

    let listener = TcpListener::bind(config.bind)
        .await
        .map_err(|error| RuntimeError::Server(error.to_string()))?;
    let local_addr = listener
        .local_addr()
        .map_err(|error| RuntimeError::Server(error.to_string()))?;
    println!("originsd ready on http://{local_addr}");

    axum::serve(listener, router(state))
        .with_graceful_shutdown(shutdown_signal())
        .await
        .map_err(|error| RuntimeError::Server(error.to_string()))
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut terminate = signal(SignalKind::terminate()).expect("SIGTERM handler must install");
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {},
            _ = terminate.recv() => {},
        }
    }

    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_bind_is_accepted() {
        let bind: SocketAddr = "127.0.0.1:48700".parse().unwrap();
        assert_eq!(require_loopback(bind).unwrap(), bind);
    }

    #[test]
    fn non_loopback_bind_is_refused() {
        let bind: SocketAddr = "0.0.0.0:48700".parse().unwrap();
        let error = require_loopback(bind).expect_err("non-loopback bind must fail");
        assert!(matches!(error, RuntimeError::Config(_)));
    }
}
