//! The Tauri shell (docs/architecture.md, section 5): a window and one IPC command, `run`,
//! which dispatches through the same registry as `stronk-core`. Nothing else lives here.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use serde_json::Value;
use stronk_data::{DirectorySource, TrustedKey};
use stronk_service::{CommandError, Context, ErrorCode, Registry, registry};

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
        client: stronk_lcu::connect_or_absent(
            var("STRONK_LCU_LOCKFILE").as_deref(),
            var("STRONK_LCU_CERT").as_deref(),
        ),
    })
}

fn main() -> ExitCode {
    let core = Core {
        registry: Arc::new(registry()),
        context: context(),
    };
    let app = tauri::Builder::default()
        .manage(core)
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
