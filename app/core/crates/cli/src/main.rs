//! `stronk-core`: the app's commands from the terminal (docs/architecture.md, section 2).
//!
//!     stronk-core commands
//!     stronk-core schema
//!     stronk-core run build.get --params '{"champion": "LeeSin", "role": "JUNGLE"}'
//!     stronk-core record-champselect --out tools/lcu_mock/sessions/custom.json
//!     stronk-core watch-champselect --events 4
//!     stronk-core restore-item-sets <backup file>
//!     stronk-core serve < commands.jsonl
//!
//! `run` prints the result as JSON on stdout, or the error as JSON on stderr with exit code 1.

mod record;

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use clap::{Parser, Subcommand};
use serde_json::{Value, json};
use stronk_data::{FileBackups, TrustedKey, default_backup_dir, default_cache_dir, open_source};
use stronk_service::{CommandError, Context, ErrorCode, registry};

#[derive(Parser)]
#[command(name = "stronk-core", about = "Run Stronk app commands")]
struct Cli {
    /// Published data: a directory (`just publish`, `fixtures/data`; `dir:` prefix optional) or
    /// an http(s) URL (`just serve-data`, the CDN), fetched into `STRONK_CACHE_DIR`.
    #[arg(long, env = "STRONK_DATA_DIR", default_value = "dist/data")]
    data: String,
    /// Public key the data must be signed with.
    #[arg(
        long,
        env = "STRONK_DATA_KEY",
        default_value = "~/.config/stronk/signing.key.pub"
    )]
    key: PathBuf,
    /// The League client's lockfile; default: discovered.
    #[arg(long, env = "STRONK_LCU_LOCKFILE")]
    lockfile: Option<PathBuf>,
    /// Root certificate to trust instead of Riot's (`tools/lcu-mock` writes one).
    #[arg(long, env = "STRONK_LCU_CERT")]
    lcu_cert: Option<PathBuf>,
    /// sha256 of the one client certificate to accept, instead of a root (fallback).
    #[arg(long, env = "STRONK_LCU_PIN")]
    lcu_pin: Option<String>,
    #[command(subcommand)]
    action: Action,
}

#[derive(Subcommand)]
enum Action {
    /// List every command.
    Commands,
    /// Every command's params and result as one JSON Schema, which the UI's types are
    /// generated from (`just gen`).
    Schema,
    /// Run one command.
    Run {
        id: String,
        #[arg(long, default_value = "{}")]
        params: String,
    },
    /// Run commands from stdin with one context, as the app does: one `{"id", "params"}` per
    /// line in, one `{"ok": true, "value"}` or `{"ok": false, "error"}` per line out
    /// (`just bench` times lock-in this way).
    Serve,
    /// Put a backup of your item sets back into the client (`item_sets.restore`); without a
    /// file, list the backups.
    RestoreItemSets { backup: Option<String> },
    /// Follow champion select over the client's websocket: one JSON line per new state.
    WatchChampselect {
        /// Stop after this many states (default: run until interrupted).
        #[arg(long)]
        events: Option<usize>,
    },
    /// Record one champion select from the running client, scrubbed, in lcu-mock's format.
    RecordChampselect {
        #[arg(long)]
        out: PathBuf,
        /// Give up if no champion select starts and ends within this many minutes.
        #[arg(long, default_value_t = 15)]
        timeout_minutes: u64,
    },
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.action {
        Action::Commands => {
            for c in registry().list() {
                println!("{}\t{}", c.id, c.summary);
            }
            ExitCode::SUCCESS
        }
        Action::Schema => match registry().schema() {
            Ok(schema) => {
                println!("{schema:#}");
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("{}", json!({"code": e.code, "message": e.message}));
                ExitCode::FAILURE
            }
        },
        Action::RestoreItemSets { ref backup } => {
            let (id, params) = match backup {
                Some(file) => ("item_sets.restore", json!({ "backup": file })),
                None => ("item_sets.backups", json!({})),
            };
            match context(&cli).and_then(|ctx| registry().run(&ctx, id, params)) {
                Ok(value) => {
                    println!("{value:#}");
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("{}", json!({"code": e.code, "message": e.message}));
                    ExitCode::FAILURE
                }
            }
        }
        Action::WatchChampselect { events } => match watch(&cli, events) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("{}", json!({"code": e.code, "message": e.message}));
                ExitCode::FAILURE
            }
        },
        Action::RecordChampselect {
            ref out,
            timeout_minutes,
        } => {
            let recorded = stronk_lcu::connect(&lcu_options(&cli))
                .map_err(|e| e.to_string())
                .and_then(|client| {
                    eprintln!("recording: waiting for champion select (Ctrl-C to stop)");
                    let timeout = std::time::Duration::from_secs(timeout_minutes * 60);
                    record::record(&client, out, timeout, std::time::Duration::from_millis(500))
                });
            match recorded {
                Ok(r) => {
                    println!(
                        "saved {} ({} steps, {} champions)",
                        out.display(),
                        r.steps,
                        r.champions
                    );
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("recording failed: {e}");
                    ExitCode::FAILURE
                }
            }
        }
        Action::Serve => match serve(&cli) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("{}", json!({"code": e.code, "message": e.message}));
                ExitCode::FAILURE
            }
        },
        Action::Run { ref id, ref params } => match run(&cli, id, params) {
            Ok(value) => {
                println!("{value:#}");
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("{}", json!({"code": e.code, "message": e.message}));
                ExitCode::FAILURE
            }
        },
    }
}

fn run(cli: &Cli, id: &str, params: &str) -> Result<Value, CommandError> {
    let params: Value = serde_json::from_str(params)
        .map_err(|e| CommandError::new(ErrorCode::InvalidParams, format!("--params: {e}")))?;
    let ctx = context(cli)?;
    registry().run(&ctx, id, params)
}

fn serve(cli: &Cli) -> Result<(), CommandError> {
    use std::io::{BufRead, Write};
    let ctx = context(cli)?;
    let registry = registry();
    let mut out = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let line =
            line.map_err(|e| CommandError::new(ErrorCode::Unavailable, format!("stdin: {e}")))?;
        if line.trim().is_empty() {
            continue;
        }
        let answer = match serde_json::from_str::<Value>(&line) {
            Ok(request) => {
                let id = request
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let params = request.get("params").cloned().unwrap_or_else(|| json!({}));
                match registry.run(&ctx, id, params) {
                    Ok(value) => json!({"ok": true, "value": value}),
                    Err(e) => json!({"ok": false, "error": {"code": e.code, "message": e.message}}),
                }
            }
            Err(e) => {
                json!({"ok": false, "error": {"code": ErrorCode::InvalidParams, "message": format!("not JSON: {e}")}})
            }
        };
        writeln!(out, "{answer}")
            .and_then(|()| out.flush())
            .map_err(|e| CommandError::new(ErrorCode::Unavailable, format!("stdout: {e}")))?;
    }
    Ok(())
}

fn context(cli: &Cli) -> Result<Context, CommandError> {
    let key_text = std::fs::read_to_string(expand(&cli.key)).map_err(|e| {
        CommandError::new(
            ErrorCode::Unavailable,
            format!("{}: {e}", cli.key.display()),
        )
    })?;
    let key = TrustedKey::decode(&key_text)?;
    Ok(Context {
        builds: open_source(&data_setting(&cli.data), key, &default_cache_dir())?,
        client: stronk_lcu::connect_or_absent(&lcu_options(cli)),
        backups: Arc::new(FileBackups::new(default_backup_dir())),
    })
}

/// The watcher runs on its own runtime thread; this thread reads the state through the usual
/// command (blocking HTTP must stay out of the async runtime) and prints each new one.
fn watch(cli: &Cli, events: Option<usize>) -> Result<(), CommandError> {
    let ctx = context(cli)?;
    let options = lcu_options(cli);
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        match tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
        {
            Ok(runtime) => {
                runtime.block_on(stronk_lcu::watch(options, |notice| tx.send(notice).is_ok()))
            }
            Err(e) => eprintln!("watch: no async runtime: {e}"),
        }
    });
    let mut last: Option<Value> = None;
    let mut printed = 0;
    for notice in rx {
        if let stronk_lcu::Notice::Disconnected(reason) = notice {
            eprintln!("watch: {reason}; retrying");
            continue;
        }
        let state = registry().run(&ctx, "champselect.state", json!({}))?;
        if last.as_ref() != Some(&state) {
            println!("{state}");
            last = Some(state);
            printed += 1;
            if events.is_some_and(|n| printed >= n) {
                break;
            }
        }
    }
    Ok(())
}

fn lcu_options(cli: &Cli) -> stronk_lcu::ConnectOptions {
    stronk_lcu::ConnectOptions {
        lockfile: cli.lockfile.clone(),
        root: cli.lcu_cert.clone(),
        pin: cli.lcu_pin.clone(),
    }
}

/// A directory setting with `~` expanded; URLs as they are.
fn data_setting(setting: &str) -> String {
    if setting.starts_with("http://") || setting.starts_with("https://") {
        return setting.to_owned();
    }
    let dir = setting.strip_prefix("dir:").unwrap_or(setting);
    expand(std::path::Path::new(dir)).display().to_string()
}

fn expand(path: &std::path::Path) -> PathBuf {
    match (path.strip_prefix("~"), std::env::var_os("HOME")) {
        (Ok(rest), Some(home)) => PathBuf::from(home).join(rest),
        _ => path.to_owned(),
    }
}
