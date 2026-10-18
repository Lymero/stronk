use std::path::{Path, PathBuf};
use std::sync::Arc;

use stronk_service::ports::{ChampSelect, LeagueClient, PortError};

use crate::{LcuClient, Lockfile, discover};

/// The client behind `lockfile` (discovered when `None`), trusting the root in `cert`; when
/// either is missing, a client whose every call says why, so commands that don't need the
/// League client still run.
pub fn connect_or_absent(lockfile: Option<&Path>, cert: Option<&Path>) -> Arc<dyn LeagueClient> {
    match connect(lockfile, cert) {
        Ok(client) => Arc::new(client),
        Err(reason) => Arc::new(Absent(reason)),
    }
}

fn connect(lockfile: Option<&Path>, cert: Option<&Path>) -> Result<LcuClient, PortError> {
    let unavailable = |e: &dyn std::fmt::Display| PortError::Unavailable(e.to_string());
    let path: PathBuf = match lockfile {
        Some(path) => path.to_owned(),
        None => discover().map_err(|e| unavailable(&e))?,
    };
    let lock = Lockfile::read(&path).map_err(|e| unavailable(&e))?;
    let cert = cert.ok_or_else(|| {
        PortError::Unavailable("no root certificate for the League client".into())
    })?;
    let pem = std::fs::read(cert)
        .map_err(|e| PortError::Unavailable(format!("{}: {e}", cert.display())))?;
    LcuClient::new(&lock, &pem)
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
