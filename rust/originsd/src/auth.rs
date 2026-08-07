use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use uuid::Uuid;

pub const TOKEN_ENV: &str = "ORIGINS_LOCAL_TOKEN";
const TOKEN_FILE: &str = "local-token.txt";

pub fn load_or_create_token(data_dir: &Path) -> io::Result<String> {
    if let Ok(token) = env::var(TOKEN_ENV) {
        let token = token.trim().to_owned();
        if !token.is_empty() {
            return Ok(token);
        }
    }

    fs::create_dir_all(data_dir)?;
    let path = data_dir.join(TOKEN_FILE);
    if path.exists() {
        let token = fs::read_to_string(&path)?.trim().to_owned();
        if token.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Origins local token file is empty",
            ));
        }
        return Ok(token);
    }

    let token = format!(
        "origins_{}{}",
        Uuid::new_v4().simple(),
        Uuid::new_v4().simple()
    );
    write_new_token(&path, &token)?;
    Ok(token)
}

#[cfg(unix)]
fn write_new_token(path: &Path, token: &str) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;

    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(path)?;
    file.write_all(token.as_bytes())?;
    file.write_all(b"\n")?;
    file.sync_all()
}

#[cfg(not(unix))]
fn write_new_token(path: &Path, token: &str) -> io::Result<()> {
    let mut file = OpenOptions::new().create_new(true).write(true).open(path)?;
    file.write_all(token.as_bytes())?;
    file.write_all(b"\n")?;
    file.sync_all()
}
