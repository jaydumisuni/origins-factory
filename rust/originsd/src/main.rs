#![cfg_attr(windows, windows_subsystem = "windows")]

mod installed;

#[tokio::main]
async fn main() {
    let result = if installed::is_launcher_entrypoint() {
        installed::run().await
    } else {
        originsd::run_from_env()
            .await
            .map_err(|error| error.to_string())
    };

    if let Err(error) = result {
        eprintln!("Origins failed: {error}");
        std::process::exit(1);
    }
}
