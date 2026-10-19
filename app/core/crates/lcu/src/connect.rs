use std::path::PathBuf;
use std::sync::{Arc, Mutex};

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

/// The League client wherever it is now: the lockfile is read before each call and the
/// connection rebuilt when its port or password changed, so Stronk can start before the client
/// and survive the client restarting. When there is no client, every call says why.
pub fn connect_or_absent(options: &ConnectOptions) -> Arc<dyn LeagueClient> {
    Arc::new(Reconnecting {
        options: options.clone(),
        current: Mutex::new(None),
    })
}

struct Reconnecting {
    options: ConnectOptions,
    current: Mutex<Option<(Lockfile, Arc<LcuClient>)>>,
}

impl Reconnecting {
    fn client(&self) -> Result<Arc<dyn LeagueClient>, PortError> {
        let unavailable = |e: &dyn std::fmt::Display| PortError::Unavailable(e.to_string());
        let path = match &self.options.lockfile {
            Some(path) => path.clone(),
            None => discover().map_err(|e| unavailable(&e))?,
        };
        let lock = Lockfile::read(&path).map_err(|e| unavailable(&e))?;
        let mut current = self
            .current
            .lock()
            .map_err(|_| unavailable(&"client cache poisoned"))?;
        if let Some((known, client)) = current.as_ref()
            && *known == lock
        {
            return Ok(client.clone());
        }
        let client = Arc::new(LcuClient::new(&lock, &self.options.trust()?)?);
        *current = Some((lock, client.clone()));
        Ok(client)
    }
}

impl LeagueClient for Reconnecting {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        self.client()?.champ_select()
    }

    fn champion_key(&self, champion_id: i64) -> Result<String, PortError> {
        self.client()?.champion_key(champion_id)
    }

    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError> {
        self.client()?.rune_pages()
    }

    fn rune_page_capacity(&self) -> Result<usize, PortError> {
        self.client()?.rune_page_capacity()
    }

    fn delete_rune_page(&self, id: i64) -> Result<(), PortError> {
        self.client()?.delete_rune_page(id)
    }

    fn create_rune_page(&self, page: &NewRunePage) -> Result<(), PortError> {
        self.client()?.create_rune_page(page)
    }

    fn item_sets(&self) -> Result<String, PortError> {
        self.client()?.item_sets()
    }

    fn save_item_sets(&self, document: &str) -> Result<(), PortError> {
        self.client()?.save_item_sets(document)
    }

    fn set_spells(&self, spells: (i64, i64)) -> Result<(), PortError> {
        self.client()?.set_spells(spells)
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

#[cfg(test)]
mod reconnecting {
    use super::*;

    #[test]
    fn says_why_while_there_is_no_client_and_picks_it_up_once_there_is() {
        let dir = std::env::temp_dir().join(format!("stronk-lcu-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let lockfile = dir.join("lockfile");
        let _ = std::fs::remove_file(&lockfile);
        let client = connect_or_absent(&ConnectOptions {
            lockfile: Some(lockfile.clone()),
            ..Default::default()
        });
        let before = client.champ_select().unwrap_err().to_string();
        assert!(before.contains("is the League client running"), "{before}");
        // A client appears (nothing listens on the port: the call now fails on connecting).
        std::fs::write(&lockfile, "LeagueClient:1:1:pw:https").unwrap();
        let after = client.champ_select().unwrap_err().to_string();
        assert!(after.contains("League client:"), "{after}");
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
