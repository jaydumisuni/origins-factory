#[cfg(windows)]
use origins_native_sandbox::{recover_windows_cleanup, watch_windows_cleanup};
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
    let mut args = env::args_os();
    let _program = args.next();
    let first = args
        .next()
        .ok_or("usage: origins-native-sandbox <sandbox-spec.json>")?;

    #[cfg(windows)]
    if first.to_str() == Some("--cleanup-watch") {
        let owner_pid = args
            .next()
            .and_then(|value| value.to_str().and_then(|text| text.parse::<u32>().ok()))
            .ok_or("cleanup watchdog requires owner pid")?;
        let manifest = args
            .next()
            .map(PathBuf::from)
            .ok_or("cleanup watchdog requires manifest path")?;
        if args.next().is_some() {
            return Err("cleanup watchdog received unexpected arguments".into());
        }
        watch_windows_cleanup(owner_pid, &manifest)?;
        return Ok(());
    }

    #[cfg(windows)]
    recover_windows_cleanup()?;

    if args.next().is_some() {
        return Err("native sandbox accepts exactly one sandbox spec path".into());
    }
    let path = PathBuf::from(first);
    let bytes = fs::read(&path)?;
    let spec: SandboxSpec = serde_json::from_slice(&bytes)?;
    let _ = fs::remove_file(&path);
    let exit_code = run(spec)?;
    std::process::exit(exit_code);
}
