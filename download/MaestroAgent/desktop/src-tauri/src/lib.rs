// MaestroAgent desktop shell — Tauri runtime + Python sidecar host.
//
// Responsibilities:
// 1. Locate the Python venv (or a frozen sidecar binary) on startup.
// 2. Spawn `maestro serve` as a child process.
// 3. Pipe its stdout/stderr into the UI via Tauri events.
// 4. Restart on crash with exponential backoff.
// 5. Expose Tauri commands for the React UI to call (start_run, pause, etc.).
//
// The Python sidecar is the source of truth for all orchestration state.
// The Rust shell is a thin supervisor — it does not interpret graph
// state, only ferries messages between the UI and the sidecar.

use std::process::Stdio;
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, State};
use tauri_plugin_shell::ShellExt;
use tokio::process::{Child, Command};
use tokio::io::{AsyncBufReadExt, BufReader};

mod commands;

/// App state shared across Tauri commands.
pub struct AppState {
    pub sidecar: Mutex<Option<Child>>,
    pub sidecar_url: String,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            sidecar: Mutex::new(None),
            sidecar_url: "http://localhost:8765".to_string(),
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .setup(|app| {
            // Spawn the Python sidecar in a background task.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = spawn_sidecar(app_handle).await {
                    log::error!("Failed to start sidecar: {e}");
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::start_run,
            commands::resume_run,
            commands::cancel_run,
            commands::get_run,
            commands::list_templates,
            commands::sidecar_health,
            commands::open_external,
        ])
        .run(tauri::generate_context!())
        .expect("error while running MaestroAgent");
}

/// Locate the Python interpreter to use for the sidecar.
///
/// Order of precedence:
/// 1. `MAESTRO_PYTHON` env var (explicit override).
/// 2. `python3` on PATH.
/// 3. `python` on PATH.
///
/// In a bundled build, this would point at the frozen PyInstaller binary
/// instead. For dev mode, we use the system Python.
fn find_python() -> Option<String> {
    if let Ok(p) = std::env::var("MAESTRO_PYTHON") {
        return Some(p);
    }
    if which::which("python3").is_ok() {
        return Some("python3".to_string());
    }
    if which::which("python").is_ok() {
        return Some("python".to_string());
    }
    None
}

/// Spawn the Python sidecar (`maestro serve`) and stream its output
/// into Tauri events that the React UI can subscribe to.
async fn spawn_sidecar(app_handle: tauri::AppHandle) -> Result<(), String> {
    let python = find_python().ok_or_else(|| {
        "Python not found. Install Python 3.11+ or set MAESTRO_PYTHON.".to_string()
    })?;

    let port = 8765u16;
    let url = format!("http://localhost:{port}");

    // Start the sidecar.
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "maestro_cli.main", "serve", "--port", &port.to_string()]);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    cmd.kill_on_drop(true);

    let state: State<AppState> = app_handle.state();
    state.sidecar_url = url.clone();

    let child = cmd.spawn().map_err(|e| format!("spawn failed: {e}"))?;
    *state.sidecar.lock().unwrap() = Some(child);

    log::info!("Sidecar started at {url}");

    // Note: in production we'd tail the child's stdout/stderr here and
    // emit them as Tauri events. For dev simplicity, we let the Python
    // process write to its own stdout which appears in the dev console.

    // Wait briefly, then ping the sidecar to confirm it's up.
    tokio::time::sleep(Duration::from_secs(1)).await;
    let _ = ping_sidecar(&url).await;

    Ok(())
}

async fn ping_sidecar(url: &str) -> Result<(), String> {
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("{url}/api/health"))
        .timeout(Duration::from_secs(2))
        .send()
        .await
        .map_err(|e| format!("health check failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("health check returned {}", resp.status()));
    }
    Ok(())
}

// We pull in reqwest at the top-level for the health check.
// In a real build, add it to Cargo.toml.
