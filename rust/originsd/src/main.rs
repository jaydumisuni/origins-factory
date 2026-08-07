#[tokio::main]
async fn main() {
    if let Err(error) = originsd::run_from_env().await {
        eprintln!("originsd failed: {error}");
        std::process::exit(1);
    }
}
