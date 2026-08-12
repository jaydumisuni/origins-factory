use origins_native_sandbox::{run, SandboxSpec};
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    if let Err(error) = execute() {
        eprintln!("ORIGINS_NATIVE_SANDBOX_ERROR: {error}");
        std::process::exit(125);
    }
}

fn execute() -> Result<(), Box<dyn std::error::Error>> {
    let path = env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .ok_or("usage: origins-native-sandbox <sandbox-spec.json>")?;
    let bytes = fs::read(&path)?;
    let spec: SandboxSpec = serde_json::from_slice(&bytes)?;
    let _ = fs::remove_file(&path);
    let exit_code = run(spec)?;
    std::process::exit(exit_code);
}
