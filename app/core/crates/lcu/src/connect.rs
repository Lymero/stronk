use std::path::PathBuf;
use std::sync::Arc;

use serde_json::Value;
use stronk_domain::select::PageInfo;
use stronk_service::ports::{ChampSelect, LeagueClient, NewRunePage, PortError};

use crate::tls::Trust;
use crate::{LcuClient, Lockfile, discover};

/// How to find and trust the client. Defaults: the discovered lockfile, Riot's root.
#[derive(Default, Clone, Debug)]
pub struct ConnectOptions {
    pub lockfile: Option<PathBuf>,
    /// A root certificate (PEM) to trust instead of Riot's (`tools/lcu-mock` writes one).
    pub root: Option<PathBuf>,
    /// The sha256 of the one certificate to accept, instead of any root (the fallback).
    pub pin: Option<String>,
}

impl ConnectOptions {
    pub fn trust(&self) -> Result<Trust, PortError> {
        if let Some(pin) = &self.pin {
            return Trust::pin(pin).map_err(PortError::Invalid);
        }
        match &self.root {
            Some(path) => std::fs::read(path)
                .map(Trust::Root)
                .map_err(|e| PortError::Unavailable(format!("{}: {e}", path.display()))),
            None => Ok(Trust::riot()),
        }
    }
}

/// The client, connected per `options`.
pub fn connect(options: &ConnectOptions) -> Result<LcuClient, PortError> {
    let unavailable = |e: &dyn std::fmt::Display| PortError::Unavailable(e.to_string());
    let path = match &options.lockfile {
        Some(path) => path.clone(),
        None => discover().map_err(|e| unavailable(&e))?,
    };
    let lock = Lockfile::read(&path).map_err(|e| unavailable(&e))?;
    LcuClient::new(&lock, &options.trust()?)
}

/// [`connect`], or when that fails a client whose every call says why, so commands that don't
/// need the League client still run.
pub fn connect_or_absent(options: &ConnectOptions) -> Arc<dyn LeagueClient> {
    match connect(options) {
        Ok(client) => Arc::new(client),
        Err(reason) => Arc::new(Absent(reason)),
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

    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError> {
        Err(self.0.clone())
    }

    fn rune_page_capacity(&self) -> Result<usize, PortError> {
        Err(self.0.clone())
    }

    fn delete_rune_page(&self, _: i64) -> Result<(), PortError> {
        Err(self.0.clone())
    }

    fn create_rune_page(&self, _: &NewRunePage) -> Result<(), PortError> {
        Err(self.0.clone())
    }

    fn item_sets(&self) -> Result<Value, PortError> {
        Err(self.0.clone())
    }

    fn save_item_sets(&self, _: &Value) -> Result<(), PortError> {
        Err(self.0.clone())
    }

    fn set_spells(&self, _: (i64, i64)) -> Result<(), PortError> {
        Err(self.0.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trusts_riots_root_by_default_and_a_pin_over_anything() {
        assert_eq!(ConnectOptions::default().trust(), Ok(Trust::riot()));
        let pinned = ConnectOptions {
            pin: Some("00".repeat(32)),
            root: Some("x".into()),
            ..Default::default()
        };
        assert_eq!(pinned.trust(), Ok(Trust::Pin([0; 32])));
    }
}
