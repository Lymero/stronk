//! `stronk-core`: the app's commands from the terminal (docs/architecture.md, section 2).
//!
//!     stronk-core commands
//!     stronk-core run build.get --params '{"champion": "LeeSin", "role": "JUNGLE"}'
//!
//! Prints the result as JSON on stdout, or the error as JSON on stderr with exit code 1.

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
    /// Root certificate the client's HTTPS chains to (`tools/lcu-mock` writes one).
    #[arg(long, env = "STRONK_LCU_CERT")]
    lcu_cert: Option<PathBuf>,
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
        client: stronk_lcu::connect_or_absent(cli.lockfile.as_deref(), cli.lcu_cert.as_deref()),
    })
}

fn expand(path: &std::path::Path) -> PathBuf {
    match (path.strip_prefix("~"), std::env::var_os("HOME")) {
        (Ok(rest), Some(home)) => PathBuf::from(home).join(rest),
        _ => path.to_owned(),
    }
}
