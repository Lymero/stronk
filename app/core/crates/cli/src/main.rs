//! `stronk-core`: the app's commands from the terminal (docs/architecture.md, section 2).
//!
//!     stronk-core commands
//!     stronk-core run build.get --params '{"champion": "LeeSin", "role": "JUNGLE"}'
//!     stronk-core record-champselect --out tools/lcu_mock/sessions/custom.json
//!     stronk-core watch-champselect --events 4
//!
//! `run` prints the result as JSON on stdout, or the error as JSON on stderr with exit code 1.

mod record;

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use clap::{Parser, Subcommand};
use serde_json::{Value, json};
use stronk_data::{DirectorySource, TrustedKey};
use stronk_service::{CommandError, Context, ErrorCode, registry};

#[derive(Parser)]
#[command(name = "stronk-core", about = "Run Stronk app commands")]
struct Cli {
    /// Published data directory (`just publish`, `fixtures/data`).
    #[arg(long, env = "STRONK_DATA_DIR", default_value = "dist/data")]
    data: PathBuf,
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
    /// Run one command.
    Run {
        id: String,
        #[arg(long, default_value = "{}")]
        params: String,
    },
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

fn context(cli: &Cli) -> Result<Context, CommandError> {
    let key_text = std::fs::read_to_string(expand(&cli.key)).map_err(|e| {
        CommandError::new(
            ErrorCode::Unavailable,
            format!("{}: {e}", cli.key.display()),
        )
    })?;
    let key = TrustedKey::decode(&key_text)?;
    Ok(Context {
        builds: Arc::new(DirectorySource::new(expand(&cli.data), key)),
        client: stronk_lcu::connect_or_absent(&lcu_options(cli)),
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

fn expand(path: &std::path::Path) -> PathBuf {
    match (path.strip_prefix("~"), std::env::var_os("HOME")) {
        (Ok(rest), Some(home)) => PathBuf::from(home).join(rest),
        _ => path.to_owned(),
    }
}
