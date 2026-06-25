// Tauri commands — the typed IPC surface between React and the Rust shell.
//
// These commands are thin proxies to the Python sidecar's REST API.
// The Rust shell does not interpret run state; it just ferries JSON
// between the UI and the sidecar.
//
// Why proxy through Rust instead of letting React call the sidecar
// directly?
// 1. CORS — the sidecar runs on localhost:8765 but the UI loads from
//    tauri://localhost. Tauri's invoke avoids CORS issues.
// 2. Lifecycle — the Rust shell knows when the sidecar is up and can
//    queue commands until it's ready.
// 3. Future-proofing — when we move to a frozen PyInstaller sidecar,
//    the Rust shell can route calls differently without UI changes.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::State;

use crate::AppState;

#[derive(Debug, Serialize, Deserialize)]
pub struct StartRunRequest {
    pub template: String,
    pub goal: String,
    #[serde(default = "default_max_cost")]
    pub max_cost_usd: f64,
    #[serde(default = "default_max_iterations")]
    pub max_iterations: i64,
    #[serde(default = "default_max_wall_clock")]
    pub max_wall_clock_seconds: i64,
    pub default_provider: Option<String>,
    pub default_model: Option<String>,
    #[serde(default)]
    pub env: std::collections::HashMap<String, String>,
    #[serde(default)]
    pub extras: Value,
}

fn default_max_cost() -> f64 { 10.0 }
fn default_max_iterations() -> i64 { 100 }
fn default_max_wall_clock() -> i64 { 3600 }

#[derive(Debug, Serialize)]
pub struct StartRunResponse {
    pub run_id: String,
    pub status: String,
}

#[tauri::command]
pub async fn start_run(
    state: State<'_, AppState>,
    req: StartRunRequest,
) -> Result<StartRunResponse, String> {
    let url = format!("{}/api/runs", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar returned {status}: {body}"));
    }
    resp.json::<StartRunResponse>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn resume_run(
    state: State<'_, AppState>,
    run_id: String,
    human_input: Option<Value>,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/resume", state.sidecar_url, run_id);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&human_input.unwrap_or(Value::Null))
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("sidecar returned {}", resp.status()));
    }
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn cancel_run(
    state: State<'_, AppState>,
    run_id: String,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/cancel", state.sidecar_url, run_id);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn get_run(
    state: State<'_, AppState>,
    run_id: String,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}", state.sidecar_url, run_id);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn list_templates(state: State<'_, AppState>) -> Result<Value, String> {
    let url = format!("{}/api/templates", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn sidecar_health(state: State<'_, AppState>) -> Result<Value, String> {
    let url = format!("{}/api/health", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
        .map_err(|e| format!("health check failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn open_external(url: String) -> Result<(), String> {
    // Open a URL in the user's default browser.
    // On Tauri 2 this requires the shell plugin + opener scope.
    // For dev simplicity, we just log; production wires up the opener.
    log::info!("open_external: {url}");
    Ok(())
}

// --- Live control: spawn sub-agents, trigger debates, create loops ---

#[derive(Debug, Serialize, Deserialize)]
pub struct SpawnSubAgentRequest {
    pub parent_id: String,
    pub sub_goal: String,
    #[serde(default = "default_role")]
    pub role: String,
    #[serde(default)]
    pub backstory: String,
    #[serde(default)]
    pub tools: Vec<String>,
    #[serde(default)]
    pub llm_hint: std::collections::HashMap<String, String>,
    #[serde(default = "default_memory_scope")]
    pub memory_scope: String,
    #[serde(default = "default_sub_max_iters")]
    pub max_iterations: i64,
}

fn default_role() -> String { "Sub-agent".to_string() }
fn default_memory_scope() -> String { "private".to_string() }
fn default_sub_max_iters() -> i64 { 10 }

#[tauri::command]
pub async fn spawn_subagent(
    state: State<'_, AppState>,
    runId: String,
    req: SpawnSubAgentRequest,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/spawn", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar returned {status}: {body}"));
    }
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DebateRequest {
    pub topic: String,
    pub participants: Vec<String>,
    #[serde(default = "default_true")]
    pub seek_consensus: bool,
    #[serde(default = "default_max_rounds")]
    pub max_rounds: i64,
}

fn default_true() -> bool { true }
fn default_max_rounds() -> i64 { 3 }

#[tauri::command]
pub async fn trigger_debate(
    state: State<'_, AppState>,
    runId: String,
    req: DebateRequest,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/debate", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar returned {status}: {body}"));
    }
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CreateLoopRequest {
    pub loop_id: String,
    pub body_agent_id: String,
    #[serde(default = "default_exit_kind")]
    pub exit_kind: String,
    #[serde(default)]
    pub exit_config: Value,
    #[serde(default = "default_loop_max_iters")]
    pub max_iterations: i64,
    #[serde(default)]
    pub max_cost_usd: Option<f64>,
    #[serde(default = "default_on_exceed")]
    pub on_exceed: String,
}

fn default_exit_kind() -> String { "tests".to_string() }
fn default_loop_max_iters() -> i64 { 20 }
fn default_on_exceed() -> String { "escalate".to_string() }

#[tauri::command]
pub async fn create_loop(
    state: State<'_, AppState>,
    runId: String,
    req: CreateLoopRequest,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/loops", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("sidecar returned {status}: {body}"));
    }
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn get_live_state(
    state: State<'_, AppState>,
    runId: String,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/live", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn get_cost_breakdown(
    state: State<'_, AppState>,
    runId: String,
) -> Result<Value, String> {
    let url = format!("{}/api/costs/{}", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn get_audit_log(
    state: State<'_, AppState>,
    runId: String,
) -> Result<Value, String> {
    let url = format!("{}/api/runs/{}/audit", state.sidecar_url, runId);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RecallRequest {
    pub query: String,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default)]
    pub agent_id: Option<String>,
    #[serde(default)]
    pub scope: Option<String>,
    #[serde(default = "default_top_k")]
    pub top_k: i64,
}

fn default_top_k() -> i64 { 5 }

#[tauri::command]
pub async fn recall_memory(
    state: State<'_, AppState>,
    req: RecallRequest,
) -> Result<Value, String> {
    let url = format!("{}/api/memory/recall", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PromoteRequest {
    pub agent_id: String,
    #[serde(default)]
    pub content: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default = "default_promote_scope")]
    pub scope: String,
    #[serde(default)]
    pub tags: Vec<String>,
}

fn default_promote_scope() -> String { "shared".to_string() }

#[tauri::command]
pub async fn promote_memory(
    state: State<'_, AppState>,
    req: PromoteRequest,
) -> Result<Value, String> {
    let url = format!("{}/api/memory/promote", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&req)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    resp.json::<Value>()
        .await
        .map_err(|e| format!("decode failed: {e}"))
}

#[tauri::command]
pub async fn list_plugins(state: State<'_, AppState>) -> Result<Value, String> {
    // Plugins are listed via the health endpoint.
    let url = format!("{}/api/health", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    let health: Value = resp
        .json()
        .await
        .map_err(|e| format!("decode failed: {e}"))?;
    Ok(health.get("plugins").cloned().unwrap_or(Value::Array(vec![])))
}

#[tauri::command]
pub async fn list_providers(state: State<'_, AppState>) -> Result<Value, String> {
    let url = format!("{}/api/health", state.sidecar_url);
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("request failed: {e}"))?;
    let health: Value = resp
        .json()
        .await
        .map_err(|e| format!("decode failed: {e}"))?;
    Ok(health.get("providers").cloned().unwrap_or(Value::Array(vec![])))
}
