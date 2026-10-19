//! The Tauri shell (docs/architecture.md, section 5): a window, one IPC command, `run`, which
//! dispatches through the same registry as `stronk-core`, and the champion-select watcher's
//! `champselect-changed` event. Nothing else lives here.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use serde_json::Value;
use stronk_data::{DirectorySource, FileBackups, TrustedKey, default_backup_dir};
use stronk_service::{CommandError, Context, ErrorCode, Registry, registry};
use tauri::Emitter;

struct Core {
    registry: Arc<Registry>,
    context: Result<Context, CommandError>,
}

/// Runs a command off the UI thread: the core's ports block on disk and the local client.
#[tauri::command]
async fn run(
    core: tauri::State<'_, Core>,
    id: String,
    params: Value,
) -> Result<Value, CommandError> {
    let context = core.context.clone()?;
    let registry = Arc::clone(&core.registry);
    tauri::async_runtime::spawn_blocking(move || registry.run(&context, &id, params))
        .await
        .map_err(|e| CommandError::new(ErrorCode::Internal, e.to_string()))?
}

/// Settings come from the environment for now (`just app` sets them to the fixture data and
/// lcu-mock); a settings command replaces this with the setup screen.
fn context() -> Result<Context, CommandError> {
    let var = |name: &str| std::env::var_os(name).map(PathBuf::from);
    let data = var("STRONK_DATA_DIR").unwrap_or_else(|| PathBuf::from("dist/data"));
    let key_path = var("STRONK_DATA_KEY")
        .ok_or_else(|| CommandError::new(ErrorCode::Unavailable, "STRONK_DATA_KEY is not set"))?;
    let key_text = std::fs::read_to_string(&key_path).map_err(|e| {
        CommandError::new(
            ErrorCode::Unavailable,
            format!("{}: {e}", key_path.display()),
        )
    })?;
    Ok(Context {
        builds: Arc::new(DirectorySource::new(data, TrustedKey::decode(&key_text)?)),
        client: stronk_lcu::connect_or_absent(&lcu_options()),
        backups: Arc::new(FileBackups::new(default_backup_dir())),
    })
}

fn lcu_options() -> stronk_lcu::ConnectOptions {
    let var = |name: &str| std::env::var_os(name).map(PathBuf::from);
    stronk_lcu::ConnectOptions {
        lockfile: var("STRONK_LCU_LOCKFILE"),
        root: var("STRONK_LCU_CERT"),
        pin: std::env::var("STRONK_LCU_PIN").ok(),
    }
}

/// Follows champion select over the client's websocket and tells the UI when it changed (with
/// the reason when disconnected); the UI reads the state through `run` (ADR-044).
fn watch_champ_select(app: &tauri::App) {
    let handle = app.handle().clone();
    tauri::async_runtime::spawn(stronk_lcu::watch(lcu_options(), move |notice| {
        let reason = match notice {
            stronk_lcu::Notice::Disconnected(reason) => Some(reason),
            stronk_lcu::Notice::Connected | stronk_lcu::Notice::Changed => None,
        };
        // The UI keeps polling slowly as a safety net, so a failed emit is not fatal.
        let _ = handle.emit("champselect-changed", reason);
        true
    }));
}

fn main() -> ExitCode {
    let core = Core {
        registry: Arc::new(registry()),
        context: context(),
    };
    let app = tauri::Builder::default()
        .manage(core)
        .setup(|app| {
            watch_champ_select(app);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![run])
        .run(tauri::generate_context!());
    match app {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("stronk: {e}");
            ExitCode::FAILURE
        }
    }
}
