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
use stronk_lcu::{LcuClient, Lockfile};
use stronk_service::ports::{ChampSelect, LeagueClient, PortError};
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
        client: client(cli),
    })
}

/// The real client when its lockfile and certificate are there; otherwise a client that says
/// why it is unavailable, so commands that don't need it still run.
fn client(cli: &Cli) -> Arc<dyn LeagueClient> {
    let connect = || -> Result<LcuClient, PortError> {
        let path = match &cli.lockfile {
            Some(path) => path.clone(),
            None => stronk_lcu::discover().map_err(|e| PortError::Unavailable(e.to_string()))?,
        };
        let lock = Lockfile::read(&path).map_err(|e| PortError::Unavailable(e.to_string()))?;
        let cert_path = cli.lcu_cert.as_ref().ok_or_else(|| {
            PortError::Unavailable("no root certificate for the League client (--lcu-cert)".into())
        })?;
        let pem = std::fs::read(cert_path)
            .map_err(|e| PortError::Unavailable(format!("{}: {e}", cert_path.display())))?;
        LcuClient::new(&lock, &pem)
    };
    match connect() {
        Ok(client) => Arc::new(client),
        Err(e) => Arc::new(Absent(e)),
    }
}

struct Absent(PortError);

impl LeagueClient for Absent {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Err(self.0.clone())
    }
    fn champion_key(&self, _: i64) -> Result<String, PortError> {
        Err(self.0.clone())
    }
}

fn expand(path: &std::path::Path) -> PathBuf {
    match (path.strip_prefix("~"), std::env::var_os("HOME")) {
        (Ok(rest), Some(home)) => PathBuf::from(home).join(rest),
        _ => path.to_owned(),
    }
}
