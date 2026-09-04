use crate::store::{append_event, now_rfc3339, Store, StoreError};
use axum::body::Body;
use axum::extract::{Path, Query, State};
use axum::http::{
    header::{AUTHORIZATION, CONTENT_DISPOSITION, CONTENT_LENGTH, CONTENT_TYPE},
    HeaderMap, HeaderValue, StatusCode,
};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use origins_contracts::{canonical_json, contract_sha256};
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path as FsPath, PathBuf};
use std::sync::Arc;
use tokio::io::AsyncReadExt;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use uuid::Uuid;

const ARTIFACT_SCHEMA_VERSION: i64 = 1;
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;
const COPY_BUFFER_BYTES: usize = 256 * 1024;
const STREAM_BUFFER_BYTES: usize = 256 * 1024;
const MAX_OWNER_REF_CHARS: usize = 512;
const MAX_FILENAME_CHARS: usize = 255;
const MAX_MEDIA_TYPE_CHARS: usize = 200;

#[derive(Debug, Clone, Default)]
pub struct ArtifactRootPolicy {
    roots: Vec<PathBuf>,
}

impl ArtifactRootPolicy {
    pub fn from_env() -> Result<Self, String> {
        let Some(raw) = env::var_os("ORIGINS_ARTIFACT_ROOTS") else {
            return Ok(Self::default());
        };
        let mut roots = Vec::new();
        for candidate in env::split_paths(&raw) {
            if candidate.as_os_str().is_empty() {
                continue;
            }
            let canonical = fs::canonicalize(&candidate).map_err(|error| {
                format!(
                    "configured Artifact source root {:?} cannot be resolved: {error}",
                    candidate
                )
            })?;
            if !canonical.is_dir() {
                return Err(format!(
                    "configured Artifact source root {:?} is not a directory",
                    canonical
                ));
            }
            roots.push(canonical);
        }
        roots.sort();
        roots.dedup();
        Ok(Self { roots })
    }

    fn require_source(&self, value: &str) -> Result<PathBuf, StoreError> {
        if self.roots.is_empty() {
            return Err(StoreError::Conflict(
                "Artifact registration is unavailable until ORIGINS_ARTIFACT_ROOTS is configured"
                    .to_owned(),
            ));
        }
        let configured = PathBuf::from(value.trim());
        if !configured.is_absolute() {
            return Err(StoreError::InvalidInput(
                "Artifact source path must be absolute".to_owned(),
            ));
        }
        let canonical = fs::canonicalize(&configured).map_err(|error| {
            StoreError::InvalidInput(format!("Artifact source cannot be resolved: {error}"))
        })?;
        if !canonical.is_file() {
            return Err(StoreError::InvalidInput(
                "Artifact source must be a regular file".to_owned(),
            ));
        }
        if !self.roots.iter().any(|root| canonical.starts_with(root)) {
            return Err(StoreError::InvalidInput(
                "Artifact source is outside configured Artifact roots".to_owned(),
            ));
        }
        Ok(canonical)
    }
}

#[derive(Clone)]
pub struct ArtifactState {
    pub store: Store,
    pub policy: ArtifactRootPolicy,
    pub object_root: PathBuf,
    pub local_token: Arc<str>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RegisterArtifactRequest {
    workspace_id: String,
    owner: String,
    owner_ref: String,
    path: String,
    #[serde(default)]
    filename: String,
    #[serde(default)]
    media_type: String,
}

#[derive(Debug, Deserialize)]
struct ArtifactListQuery {
    workspace_id: Option<String>,
}

#[derive(Debug, Clone)]
struct StoredArtifact {
    artifact_id: String,
    workspace_id: String,
    projection_json: String,
    projection_sha256: String,
    object_path: String,
}

impl StoredArtifact {
    fn projection(&self) -> Result<Value, StoreError> {
        let value: Value = serde_json::from_str(&self.projection_json)
            .map_err(|error| StoreError::Corrupt(format!("Artifact JSON: {error}")))?;
        validate_projection_shape(&value)?;
        let actual = contract_sha256(&value)
            .map_err(|error| StoreError::Corrupt(format!("Artifact digest: {error}")))?;
        if actual != self.projection_sha256 {
            return Err(StoreError::Corrupt(format!(
                "Artifact {} projection digest mismatch",
                self.artifact_id
            )));
        }
        Ok(value)
    }
}

pub fn initialize(store: &Store, object_root: &FsPath) -> Result<(), StoreError> {
    fs::create_dir_all(object_root).map_err(|error| StoreError::Io(error.to_string()))?;
    fs::create_dir_all(object_root.join("tmp"))
        .map_err(|error| StoreError::Io(error.to_string()))?;
    let connection = store.connection()?;
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS artifact_meta (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            object_path TEXT NOT NULL,
            projection_json TEXT NOT NULL,
            projection_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (workspace_id, content_sha256),
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
         );
         CREATE TABLE IF NOT EXISTS artifact_sources (
            source_id TEXT PRIMARY KEY NOT NULL,
            workspace_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            owner_ref TEXT NOT NULL,
            source_path TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            UNIQUE (workspace_id, owner, owner_ref),
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
         );",
    )?;
    let current: Option<String> = connection
        .query_row(
            "SELECT value FROM artifact_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    let version = match current {
        Some(value) => value.parse::<i64>().map_err(|_| {
            StoreError::Corrupt("invalid Artifact subsystem schema version".to_owned())
        })?,
        None => 0,
    };
    if version > ARTIFACT_SCHEMA_VERSION {
        return Err(StoreError::Corrupt(format!(
            "unsupported newer Artifact subsystem schema version {version}; current is {ARTIFACT_SCHEMA_VERSION}"
        )));
    }
    if version != ARTIFACT_SCHEMA_VERSION {
        connection.execute(
            "INSERT INTO artifact_meta (key, value) VALUES ('schema_version', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [ARTIFACT_SCHEMA_VERSION.to_string()],
        )?;
    }
    Ok(())
}

impl Store {
    pub fn artifact_schema_version(&self) -> Result<i64, StoreError> {
        let connection = self.connection()?;
        let value: String = connection.query_row(
            "SELECT value FROM artifact_meta WHERE key = 'schema_version'",
            [],
            |row| row.get(0),
        )?;
        value.parse().map_err(|_| {
            StoreError::Corrupt("invalid Artifact subsystem schema version".to_owned())
        })
    }

    pub fn artifact_count(&self) -> Result<u64, StoreError> {
        let connection = self.connection()?;
        let count: i64 =
            connection.query_row("SELECT COUNT(*) FROM artifacts", [], |row| row.get(0))?;
        u64::try_from(count).map_err(|_| StoreError::Corrupt("negative Artifact count".to_owned()))
    }
}

pub fn router(state: ArtifactState) -> Router {
    Router::new()
        .route("/v1/artifacts", get(list_artifacts).post(register_artifact))
        .route("/v1/artifacts/:artifact_id", get(get_artifact))
        .route(
            "/v1/artifacts/:artifact_id/content",
            get(get_artifact_content),
        )
        .with_state(state)
}

async fn list_artifacts(
    State(state): State<ArtifactState>,
    headers: HeaderMap,
    Query(query): Query<ArtifactListQuery>,
) -> Result<Json<Value>, ArtifactApiError> {
    require_auth(&headers, &state.local_token)?;
    if let Some(workspace_id) = query.workspace_id.as_deref() {
        if !state
            .store
            .workspace_exists(workspace_id)
            .map_err(ArtifactApiError::from_store)?
        {
            return Err(ArtifactApiError::new(
                StatusCode::NOT_FOUND,
                "WORKSPACE_NOT_FOUND",
                "workspace not found",
            ));
        }
    }
    let artifacts = list_stored_artifacts(&state.store, query.workspace_id.as_deref())
        .map_err(ArtifactApiError::from_store)?
        .into_iter()
        .map(|artifact| artifact.projection())
        .collect::<Result<Vec<_>, _>>()
        .map_err(ArtifactApiError::from_store)?;
    Ok(Json(json!({"artifacts": artifacts})))
}

async fn get_artifact(
    State(state): State<ArtifactState>,
    headers: HeaderMap,
    Path(artifact_id): Path<String>,
) -> Result<Json<Value>, ArtifactApiError> {
    require_auth(&headers, &state.local_token)?;
    let artifact_id =
        normalize_uuid(&artifact_id, "artifact_id").map_err(ArtifactApiError::from_store)?;
    let artifact = load_artifact(&state.store, &artifact_id)
        .map_err(ArtifactApiError::from_store)?
        .ok_or_else(|| {
            ArtifactApiError::new(
                StatusCode::NOT_FOUND,
                "ARTIFACT_NOT_FOUND",
                "Artifact not found",
            )
        })?;
    Ok(Json(
        artifact
            .projection()
            .map_err(ArtifactApiError::from_store)?,
    ))
}

async fn register_artifact(
    State(state): State<ArtifactState>,
    headers: HeaderMap,
    Json(request): Json<RegisterArtifactRequest>,
) -> Result<(StatusCode, Json<Value>), ArtifactApiError> {
    require_auth(&headers, &state.local_token)?;
    let workspace_id = normalize_uuid(&request.workspace_id, "workspace_id")
        .map_err(ArtifactApiError::from_store)?;
    if !state
        .store
        .workspace_exists(&workspace_id)
        .map_err(ArtifactApiError::from_store)?
    {
        return Err(ArtifactApiError::new(
            StatusCode::NOT_FOUND,
            "WORKSPACE_NOT_FOUND",
            "workspace not found",
        ));
    }
    let owner = normalize_owner(&request.owner).map_err(ArtifactApiError::from_store)?;
    let owner_ref = bounded_nonempty(&request.owner_ref, MAX_OWNER_REF_CHARS, "owner_ref")
        .map_err(ArtifactApiError::from_store)?;
    let source_path = state
        .policy
        .require_source(&request.path)
        .map_err(ArtifactApiError::from_store)?;
    let filename =
        artifact_filename(&request.filename, &source_path).map_err(ArtifactApiError::from_store)?;
    let media_type = bounded_text(&request.media_type, MAX_MEDIA_TYPE_CHARS, "media_type")
        .map_err(ArtifactApiError::from_store)?;

    let materialized = materialize(source_path.clone(), state.object_root.clone())
        .await
        .map_err(ArtifactApiError::from_store)?;
    let result = register_materialized(
        &state.store,
        &workspace_id,
        &owner,
        &owner_ref,
        &source_path,
        &filename,
        &media_type,
        materialized,
    )
    .map_err(ArtifactApiError::from_store)?;
    Ok((
        if result.reused {
            StatusCode::OK
        } else {
            StatusCode::CREATED
        },
        Json(json!({
            "registered": true,
            "reused": result.reused,
            "artifact": result.artifact.projection().map_err(ArtifactApiError::from_store)?,
        })),
    ))
}

async fn get_artifact_content(
    State(state): State<ArtifactState>,
    headers: HeaderMap,
    Path(artifact_id): Path<String>,
) -> Result<Response, ArtifactApiError> {
    require_auth(&headers, &state.local_token)?;
    let artifact_id =
        normalize_uuid(&artifact_id, "artifact_id").map_err(ArtifactApiError::from_store)?;
    let artifact = load_artifact(&state.store, &artifact_id)
        .map_err(ArtifactApiError::from_store)?
        .ok_or_else(|| {
            ArtifactApiError::new(
                StatusCode::NOT_FOUND,
                "ARTIFACT_NOT_FOUND",
                "Artifact not found",
            )
        })?;
    let projection = artifact
        .projection()
        .map_err(ArtifactApiError::from_store)?;
    let canonical_object = fs::canonicalize(&artifact.object_path).map_err(|error| {
        ArtifactApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "ARTIFACT_CONTENT_UNAVAILABLE",
            format!("Artifact object cannot be resolved: {error}"),
        )
    })?;
    let canonical_root = fs::canonicalize(&state.object_root).map_err(|error| {
        ArtifactApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "ARTIFACT_CONTENT_UNAVAILABLE",
            format!("Artifact store cannot be resolved: {error}"),
        )
    })?;
    if !canonical_object.starts_with(&canonical_root) || !canonical_object.is_file() {
        return Err(ArtifactApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "ARTIFACT_CONTENT_UNAVAILABLE",
            "Artifact object escaped the managed content store",
        ));
    }
    let expected_size = projection
        .get("size_bytes")
        .and_then(Value::as_u64)
        .ok_or_else(|| {
            ArtifactApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "CORRUPT_STATE",
                "Artifact size missing",
            )
        })?;
    let metadata = fs::metadata(&canonical_object).map_err(|error| {
        ArtifactApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "ARTIFACT_CONTENT_UNAVAILABLE",
            error.to_string(),
        )
    })?;
    if metadata.len() != expected_size {
        return Err(ArtifactApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "ARTIFACT_CONTENT_CORRUPT",
            "Artifact object size no longer matches its registered projection",
        ));
    }

    let mut file = tokio::fs::File::open(canonical_object)
        .await
        .map_err(|error| {
            ArtifactApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "ARTIFACT_CONTENT_UNAVAILABLE",
                error.to_string(),
            )
        })?;
    let (sender, receiver) = mpsc::channel::<Result<Vec<u8>, std::io::Error>>(4);
    tokio::spawn(async move {
        loop {
            let mut buffer = vec![0_u8; STREAM_BUFFER_BYTES];
            match file.read(&mut buffer).await {
                Ok(0) => break,
                Ok(read) => {
                    buffer.truncate(read);
                    if sender.send(Ok(buffer)).await.is_err() {
                        break;
                    }
                }
                Err(error) => {
                    let _ = sender.send(Err(error)).await;
                    break;
                }
            }
        }
    });
    let body = Body::from_stream(ReceiverStream::new(receiver));
    let filename = projection
        .get("filename")
        .and_then(Value::as_str)
        .unwrap_or("artifact.bin");
    let media_type = projection
        .get("media_type")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .unwrap_or("application/octet-stream");
    let safe_filename = filename.replace(['\\', '"'], "_");
    let disposition = format!("attachment; filename=\"{safe_filename}\"");
    let mut response = Response::new(body);
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        CONTENT_LENGTH,
        HeaderValue::from_str(&expected_size.to_string()).map_err(|error| {
            ArtifactApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "CORRUPT_STATE",
                error.to_string(),
            )
        })?,
    );
    response.headers_mut().insert(
        CONTENT_TYPE,
        HeaderValue::from_str(media_type).map_err(|_| {
            ArtifactApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "CORRUPT_STATE",
                "invalid Artifact media type",
            )
        })?,
    );
    response.headers_mut().insert(
        CONTENT_DISPOSITION,
        HeaderValue::from_str(&disposition).map_err(|_| {
            ArtifactApiError::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "CORRUPT_STATE",
                "invalid Artifact filename",
            )
        })?,
    );
    Ok(response)
}

#[derive(Debug)]
struct MaterializedObject {
    sha256: String,
    size_bytes: u64,
    object_path: PathBuf,
}

async fn materialize(
    source: PathBuf,
    object_root: PathBuf,
) -> Result<MaterializedObject, StoreError> {
    tokio::task::spawn_blocking(move || materialize_blocking(&source, &object_root))
        .await
        .map_err(|error| StoreError::Io(format!("Artifact worker failed: {error}")))?
}

fn materialize_blocking(
    source: &FsPath,
    object_root: &FsPath,
) -> Result<MaterializedObject, StoreError> {
    let temp_path = object_root
        .join("tmp")
        .join(format!("{}.partial", Uuid::new_v4().hyphenated()));
    let result = (|| {
        let mut input = File::open(source)
            .map_err(|error| StoreError::Io(format!("Artifact source open failed: {error}")))?;
        let mut output = File::create(&temp_path)
            .map_err(|error| StoreError::Io(format!("Artifact staging create failed: {error}")))?;
        let mut hasher = Sha256::new();
        let mut size_bytes = 0_u64;
        let mut buffer = vec![0_u8; COPY_BUFFER_BYTES];
        loop {
            let read = input
                .read(&mut buffer)
                .map_err(|error| StoreError::Io(format!("Artifact source read failed: {error}")))?;
            if read == 0 {
                break;
            }
            hasher.update(&buffer[..read]);
            size_bytes = size_bytes
                .checked_add(read as u64)
                .ok_or_else(|| StoreError::InvalidInput("Artifact size overflow".to_owned()))?;
            if size_bytes > MAX_SAFE_INTEGER {
                return Err(StoreError::InvalidInput(
                    "Artifact exceeds cross-language safe byte-count range".to_owned(),
                ));
            }
            output.write_all(&buffer[..read]).map_err(|error| {
                StoreError::Io(format!("Artifact staging write failed: {error}"))
            })?;
        }
        output
            .flush()
            .map_err(|error| StoreError::Io(format!("Artifact staging flush failed: {error}")))?;
        output
            .sync_all()
            .map_err(|error| StoreError::Io(format!("Artifact staging sync failed: {error}")))?;
        drop(output);

        let sha256 = hex::encode(hasher.finalize());
        let destination_dir = object_root.join(&sha256[..2]);
        fs::create_dir_all(&destination_dir).map_err(|error| {
            StoreError::Io(format!("Artifact object directory failed: {error}"))
        })?;
        let object_path = destination_dir.join(&sha256);
        if object_path.exists() {
            verify_object_blocking(&object_path, &sha256, size_bytes)?;
            let _ = fs::remove_file(&temp_path);
        } else if let Err(error) = fs::rename(&temp_path, &object_path) {
            if object_path.exists() {
                verify_object_blocking(&object_path, &sha256, size_bytes)?;
                let _ = fs::remove_file(&temp_path);
            } else {
                return Err(StoreError::Io(format!(
                    "Artifact materialization failed: {error}"
                )));
            }
        }
        let mut permissions = fs::metadata(&object_path)
            .map_err(|error| StoreError::Io(error.to_string()))?
            .permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&object_path, permissions).map_err(|error| {
            StoreError::Io(format!("Artifact readonly protection failed: {error}"))
        })?;
        Ok(MaterializedObject {
            sha256,
            size_bytes,
            object_path,
        })
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

fn verify_object_blocking(
    path: &FsPath,
    expected_sha256: &str,
    expected_size: u64,
) -> Result<(), StoreError> {
    let metadata = fs::metadata(path)
        .map_err(|error| StoreError::Io(format!("Artifact object metadata failed: {error}")))?;
    if metadata.len() != expected_size {
        return Err(StoreError::Corrupt(
            "existing content-addressed Artifact object has the wrong size".to_owned(),
        ));
    }
    let mut file = File::open(path)
        .map_err(|error| StoreError::Io(format!("Artifact object open failed: {error}")))?;
    let mut hasher = Sha256::new();
    let mut buffer = vec![0_u8; COPY_BUFFER_BYTES];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|error| StoreError::Io(format!("Artifact object read failed: {error}")))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    if hex::encode(hasher.finalize()) != expected_sha256 {
        return Err(StoreError::Corrupt(
            "existing content-addressed Artifact object failed digest verification".to_owned(),
        ));
    }
    Ok(())
}

#[derive(Debug)]
struct RegistrationResult {
    artifact: StoredArtifact,
    reused: bool,
}

#[allow(clippy::too_many_arguments)]
fn register_materialized(
    store: &Store,
    workspace_id: &str,
    owner: &str,
    owner_ref: &str,
    source_path: &FsPath,
    filename: &str,
    media_type: &str,
    materialized: MaterializedObject,
) -> Result<RegistrationResult, StoreError> {
    let mut connection = store.connection()?;
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;

    if let Some(source_artifact_id) = transaction
        .query_row(
            "SELECT artifact_id FROM artifact_sources
             WHERE workspace_id = ?1 AND owner = ?2 AND owner_ref = ?3",
            params![workspace_id, owner, owner_ref],
            |row| row.get::<_, String>(0),
        )
        .optional()?
    {
        let artifact =
            load_artifact_connection(&transaction, &source_artifact_id)?.ok_or_else(|| {
                StoreError::Corrupt("Artifact source points to missing Artifact".to_owned())
            })?;
        if artifact
            .projection()?
            .get("content_sha256")
            .and_then(Value::as_str)
            != Some(materialized.sha256.as_str())
        {
            return Err(StoreError::Conflict(
                "Artifact owner reference is already bound to different content".to_owned(),
            ));
        }
        transaction.commit()?;
        return Ok(RegistrationResult {
            artifact,
            reused: true,
        });
    }

    if let Some(existing) =
        load_artifact_by_content_connection(&transaction, workspace_id, &materialized.sha256)?
    {
        attach_source(
            &transaction,
            workspace_id,
            &existing.artifact_id,
            owner,
            owner_ref,
            source_path,
        )?;
        let updated = update_source_count(&transaction, &existing.artifact_id)?;
        append_event(
            &transaction,
            workspace_id,
            "artifact.source.attached",
            json!({
                "artifact_id": updated.artifact_id,
                "content_sha256": materialized.sha256,
                "owner": owner,
                "owner_ref": owner_ref,
            }),
            Vec::new(),
        )?;
        transaction.commit()?;
        return Ok(RegistrationResult {
            artifact: updated,
            reused: true,
        });
    }

    let artifact_id = Uuid::new_v4().hyphenated().to_string();
    let now = now_rfc3339();
    let projection = artifact_projection(
        &artifact_id,
        workspace_id,
        1,
        &materialized.sha256,
        materialized.size_bytes,
        filename,
        media_type,
        1,
        &now,
        &now,
    );
    validate_projection_shape(&projection)?;
    let canonical = canonical_json(&projection).map_err(|error| {
        StoreError::InvalidInput(format!("Artifact projection serialization failed: {error}"))
    })?;
    let projection_sha256 = contract_sha256(&projection).map_err(|error| {
        StoreError::InvalidInput(format!("Artifact projection digest failed: {error}"))
    })?;
    transaction.execute(
        "INSERT INTO artifacts (
            artifact_id, workspace_id, content_sha256, size_bytes, object_path,
            projection_json, projection_sha256, revision, created_at, updated_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 1, ?8, ?8)",
        params![
            artifact_id,
            workspace_id,
            materialized.sha256,
            i64::try_from(materialized.size_bytes).map_err(|_| {
                StoreError::InvalidInput("Artifact size out of SQLite range".to_owned())
            })?,
            materialized.object_path.to_string_lossy(),
            canonical,
            projection_sha256,
            now,
        ],
    )?;
    attach_source(
        &transaction,
        workspace_id,
        &artifact_id,
        owner,
        owner_ref,
        source_path,
    )?;
    append_event(
        &transaction,
        workspace_id,
        "artifact.registered",
        json!({
            "artifact_id": artifact_id,
            "content_sha256": materialized.sha256,
            "size_bytes": materialized.size_bytes,
            "owner": owner,
            "owner_ref": owner_ref,
        }),
        Vec::new(),
    )?;
    let artifact = load_artifact_connection(&transaction, &artifact_id)?
        .ok_or_else(|| StoreError::Corrupt("new Artifact disappeared before commit".to_owned()))?;
    transaction.commit()?;
    Ok(RegistrationResult {
        artifact,
        reused: false,
    })
}

fn attach_source(
    transaction: &rusqlite::Transaction<'_>,
    workspace_id: &str,
    artifact_id: &str,
    owner: &str,
    owner_ref: &str,
    source_path: &FsPath,
) -> Result<(), StoreError> {
    transaction.execute(
        "INSERT INTO artifact_sources (
            source_id, workspace_id, artifact_id, owner, owner_ref, source_path, observed_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            Uuid::new_v4().hyphenated().to_string(),
            workspace_id,
            artifact_id,
            owner,
            owner_ref,
            source_path.to_string_lossy(),
            now_rfc3339(),
        ],
    )?;
    Ok(())
}

fn update_source_count(
    transaction: &rusqlite::Transaction<'_>,
    artifact_id: &str,
) -> Result<StoredArtifact, StoreError> {
    let existing = load_artifact_connection(transaction, artifact_id)?
        .ok_or_else(|| StoreError::Corrupt(format!("Artifact {artifact_id} disappeared")))?;
    let previous = existing.projection()?;
    let source_count: i64 = transaction.query_row(
        "SELECT COUNT(*) FROM artifact_sources WHERE artifact_id = ?1",
        [artifact_id],
        |row| row.get(0),
    )?;
    let revision = previous
        .get("revision")
        .and_then(Value::as_u64)
        .ok_or_else(|| StoreError::Corrupt("Artifact revision missing".to_owned()))?
        .checked_add(1)
        .ok_or_else(|| StoreError::Corrupt("Artifact revision overflow".to_owned()))?;
    let now = now_rfc3339();
    let projection = artifact_projection(
        artifact_id,
        &existing.workspace_id,
        revision,
        previous
            .get("content_sha256")
            .and_then(Value::as_str)
            .ok_or_else(|| StoreError::Corrupt("Artifact content digest missing".to_owned()))?,
        previous
            .get("size_bytes")
            .and_then(Value::as_u64)
            .ok_or_else(|| StoreError::Corrupt("Artifact size missing".to_owned()))?,
        previous
            .get("filename")
            .and_then(Value::as_str)
            .unwrap_or("artifact.bin"),
        previous
            .get("media_type")
            .and_then(Value::as_str)
            .unwrap_or(""),
        u64::try_from(source_count)
            .map_err(|_| StoreError::Corrupt("negative Artifact source count".to_owned()))?,
        previous
            .get("created_at")
            .and_then(Value::as_str)
            .ok_or_else(|| StoreError::Corrupt("Artifact created_at missing".to_owned()))?,
        &now,
    );
    validate_projection_shape(&projection)?;
    let canonical = canonical_json(&projection).map_err(|error| {
        StoreError::Corrupt(format!("Artifact projection serialization failed: {error}"))
    })?;
    let digest = contract_sha256(&projection).map_err(|error| {
        StoreError::Corrupt(format!("Artifact projection digest failed: {error}"))
    })?;
    transaction.execute(
        "UPDATE artifacts
         SET projection_json = ?2, projection_sha256 = ?3, revision = ?4, updated_at = ?5
         WHERE artifact_id = ?1",
        params![
            artifact_id,
            canonical,
            digest,
            i64::try_from(revision).map_err(|_| {
                StoreError::Corrupt("Artifact revision out of SQLite range".to_owned())
            })?,
            now
        ],
    )?;
    load_artifact_connection(transaction, artifact_id)?.ok_or_else(|| {
        StoreError::Corrupt(format!("Artifact {artifact_id} disappeared after update"))
    })
}

#[allow(clippy::too_many_arguments)]
fn artifact_projection(
    artifact_id: &str,
    workspace_id: &str,
    revision: u64,
    content_sha256: &str,
    size_bytes: u64,
    filename: &str,
    media_type: &str,
    source_count: u64,
    created_at: &str,
    updated_at: &str,
) -> Value {
    json!({
        "contract_type": "artifact_projection",
        "schema_version": "1.0.0",
        "artifact_id": artifact_id,
        "workspace_id": workspace_id,
        "revision": revision,
        "content_sha256": content_sha256,
        "size_bytes": size_bytes,
        "filename": filename,
        "media_type": media_type,
        "storage_class": "local_immutable",
        "source_count": source_count,
        "created_at": created_at,
        "updated_at": updated_at,
    })
}

fn validate_projection_shape(value: &Value) -> Result<(), StoreError> {
    let object = value
        .as_object()
        .ok_or_else(|| StoreError::Corrupt("Artifact projection must be an object".to_owned()))?;
    let expected = [
        "artifact_id",
        "content_sha256",
        "contract_type",
        "created_at",
        "filename",
        "media_type",
        "revision",
        "schema_version",
        "size_bytes",
        "source_count",
        "storage_class",
        "updated_at",
        "workspace_id",
    ];
    if object.len() != expected.len() || expected.iter().any(|field| !object.contains_key(*field)) {
        return Err(StoreError::Corrupt(
            "Artifact projection field set is invalid".to_owned(),
        ));
    }
    if object.get("contract_type").and_then(Value::as_str) != Some("artifact_projection")
        || object.get("schema_version").and_then(Value::as_str) != Some("1.0.0")
        || object.get("storage_class").and_then(Value::as_str) != Some("local_immutable")
    {
        return Err(StoreError::Corrupt(
            "Artifact projection identity is invalid".to_owned(),
        ));
    }
    normalize_uuid(
        object
            .get("artifact_id")
            .and_then(Value::as_str)
            .unwrap_or(""),
        "artifact_id",
    )?;
    normalize_uuid(
        object
            .get("workspace_id")
            .and_then(Value::as_str)
            .unwrap_or(""),
        "workspace_id",
    )?;
    let revision = object.get("revision").and_then(Value::as_u64).unwrap_or(0);
    let source_count = object
        .get("source_count")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let size_bytes = object
        .get("size_bytes")
        .and_then(Value::as_u64)
        .ok_or_else(|| StoreError::Corrupt("Artifact size is invalid".to_owned()))?;
    if revision == 0 || source_count == 0 || size_bytes > MAX_SAFE_INTEGER {
        return Err(StoreError::Corrupt(
            "Artifact revision/source/size values are invalid".to_owned(),
        ));
    }
    let digest = object
        .get("content_sha256")
        .and_then(Value::as_str)
        .unwrap_or("");
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase())
    {
        return Err(StoreError::Corrupt(
            "Artifact content digest is invalid".to_owned(),
        ));
    }
    Ok(())
}

fn load_artifact(store: &Store, artifact_id: &str) -> Result<Option<StoredArtifact>, StoreError> {
    let connection = store.connection()?;
    load_artifact_connection(&connection, artifact_id)
}

fn load_artifact_connection(
    connection: &rusqlite::Connection,
    artifact_id: &str,
) -> Result<Option<StoredArtifact>, StoreError> {
    connection
        .query_row(
            "SELECT artifact_id, workspace_id, projection_json, projection_sha256, object_path
             FROM artifacts WHERE artifact_id = ?1",
            [artifact_id],
            |row| {
                Ok(StoredArtifact {
                    artifact_id: row.get(0)?,
                    workspace_id: row.get(1)?,
                    projection_json: row.get(2)?,
                    projection_sha256: row.get(3)?,
                    object_path: row.get(4)?,
                })
            },
        )
        .optional()
        .map_err(StoreError::from)
}

fn load_artifact_by_content_connection(
    connection: &rusqlite::Connection,
    workspace_id: &str,
    content_sha256: &str,
) -> Result<Option<StoredArtifact>, StoreError> {
    connection
        .query_row(
            "SELECT artifact_id, workspace_id, projection_json, projection_sha256, object_path
             FROM artifacts WHERE workspace_id = ?1 AND content_sha256 = ?2",
            params![workspace_id, content_sha256],
            |row| {
                Ok(StoredArtifact {
                    artifact_id: row.get(0)?,
                    workspace_id: row.get(1)?,
                    projection_json: row.get(2)?,
                    projection_sha256: row.get(3)?,
                    object_path: row.get(4)?,
                })
            },
        )
        .optional()
        .map_err(StoreError::from)
}

fn list_stored_artifacts(
    store: &Store,
    workspace_id: Option<&str>,
) -> Result<Vec<StoredArtifact>, StoreError> {
    let connection = store.connection()?;
    let sql = if workspace_id.is_some() {
        "SELECT artifact_id, workspace_id, projection_json, projection_sha256, object_path
         FROM artifacts WHERE workspace_id = ?1 ORDER BY created_at, artifact_id"
    } else {
        "SELECT artifact_id, workspace_id, projection_json, projection_sha256, object_path
         FROM artifacts ORDER BY workspace_id, created_at, artifact_id"
    };
    let mut statement = connection.prepare(sql)?;
    let mut result = Vec::new();
    if let Some(workspace_id) = workspace_id {
        let rows = statement.query_map([workspace_id], stored_artifact_row)?;
        for row in rows {
            result.push(row?);
        }
    } else {
        let rows = statement.query_map([], stored_artifact_row)?;
        for row in rows {
            result.push(row?);
        }
    }
    Ok(result)
}

fn stored_artifact_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<StoredArtifact> {
    Ok(StoredArtifact {
        artifact_id: row.get(0)?,
        workspace_id: row.get(1)?,
        projection_json: row.get(2)?,
        projection_sha256: row.get(3)?,
        object_path: row.get(4)?,
    })
}

fn normalize_uuid(value: &str, field: &str) -> Result<String, StoreError> {
    let parsed = Uuid::parse_str(value.trim())
        .map_err(|_| StoreError::InvalidInput(format!("{field} must be a UUID")))?;
    Ok(parsed.hyphenated().to_string())
}

fn normalize_owner(value: &str) -> Result<String, StoreError> {
    let owner = value.trim().to_ascii_lowercase();
    if !matches!(owner.as_str(), "lumi" | "origins") {
        return Err(StoreError::InvalidInput(
            "Artifact registration accepts only canonical Lumi handoffs or Origins-owned artifacts"
                .to_owned(),
        ));
    }
    Ok(owner)
}

fn bounded_nonempty(value: &str, max_chars: usize, field: &str) -> Result<String, StoreError> {
    let value = value.trim();
    if value.is_empty() {
        return Err(StoreError::InvalidInput(format!("{field} cannot be empty")));
    }
    if value.chars().count() > max_chars {
        return Err(StoreError::InvalidInput(format!("{field} is too long")));
    }
    Ok(value.to_owned())
}

fn bounded_text(value: &str, max_chars: usize, field: &str) -> Result<String, StoreError> {
    let value = value.trim();
    if value.chars().count() > max_chars
        || value
            .chars()
            .any(|character| matches!(character, '\r' | '\n' | '\0'))
    {
        return Err(StoreError::InvalidInput(format!("invalid {field}")));
    }
    Ok(value.to_owned())
}

fn artifact_filename(requested: &str, source_path: &FsPath) -> Result<String, StoreError> {
    let candidate = if requested.trim().is_empty() {
        source_path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("artifact.bin")
            .to_owned()
    } else {
        requested.trim().to_owned()
    };
    if candidate.chars().count() > MAX_FILENAME_CHARS
        || candidate.is_empty()
        || candidate
            .chars()
            .any(|character| matches!(character, '/' | '\\' | '\r' | '\n' | '\0' | '"'))
        || candidate == "."
        || candidate == ".."
    {
        return Err(StoreError::InvalidInput(
            "invalid Artifact filename".to_owned(),
        ));
    }
    Ok(candidate)
}

fn require_auth(headers: &HeaderMap, expected: &str) -> Result<(), ArtifactApiError> {
    let supplied = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    if !constant_time_eq(supplied.as_bytes(), expected.as_bytes()) {
        return Err(ArtifactApiError::new(
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
struct ArtifactApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl ArtifactApiError {
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

impl IntoResponse for ArtifactApiError {
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
    fn missing_roots_fail_closed() {
        let policy = ArtifactRootPolicy::default();
        let error = policy
            .require_source("/tmp/anything")
            .expect_err("unconfigured Artifact roots must fail closed");
        assert!(matches!(error, StoreError::Conflict(_)));
    }

    #[test]
    fn filenames_cannot_escape_or_inject_headers() {
        let source = PathBuf::from("/tmp/proof.bin");
        assert!(artifact_filename("../proof.bin", &source).is_err());
        assert!(artifact_filename("bad\r\nheader.bin", &source).is_err());
        assert_eq!(
            artifact_filename("proof.bin", &source).unwrap(),
            "proof.bin"
        );
    }

    #[test]
    fn owner_contract_accepts_lumi_and_origins_only() {
        assert_eq!(normalize_owner("LUMI").unwrap(), "lumi");
        assert_eq!(normalize_owner("ORIGINS").unwrap(), "origins");
        assert!(normalize_owner("oracle").is_err());
        assert!(normalize_owner("origins-v1-proof").is_err());
    }

    #[test]
    fn projection_shape_rejects_missing_identity() {
        assert!(validate_projection_shape(&json!({})).is_err());
    }

    #[test]
    fn bearer_compare_is_exact() {
        assert!(constant_time_eq(b"same", b"same"));
        assert!(!constant_time_eq(b"same", b"diff"));
        assert!(!constant_time_eq(b"short", b"longer"));
    }
}
