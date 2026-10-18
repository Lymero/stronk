use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use base64::Engine;
use rustls::ClientConfig;
use serde::de::DeserializeOwned;
use serde_json::Value;
use stronk_service::ports::{ChampSelect, LeagueClient, PortError};

use crate::http;
use crate::lockfile::Lockfile;
use crate::models::{ChampionSummary, Session};
use crate::tls::{Trust, client_config};

pub const SESSION: &str = "/lol-champ-select/v1/session";
pub const CHAMPION_SUMMARY: &str = "/lol-game-data/assets/v1/champion-summary.json";

/// HTTPS to the local client, accepting its certificate per [`Trust`] only.
pub struct LcuClient {
    config: Arc<ClientConfig>,
    port: u16,
    auth: String,
    champions: Mutex<Option<HashMap<i64, String>>>,
}

impl LcuClient {
    pub fn new(lock: &Lockfile, trust: &Trust) -> Result<Self, PortError> {
        let config = client_config(trust).map_err(PortError::Invalid)?;
        let token =
            base64::engine::general_purpose::STANDARD.encode(format!("riot:{}", lock.password));
        Ok(Self {
            config,
            port: lock.port,
            auth: format!("Basic {token}"),
            champions: Mutex::new(None),
        })
    }

    /// The JSON at `path`, `None` on 404 (how the client says "not in that state").
    pub fn get_json(&self, path: &str) -> Result<Option<Value>, PortError> {
        self.get(path)
    }

    fn get<T: DeserializeOwned>(&self, path: &str) -> Result<Option<T>, PortError> {
        let (status, body) = http::get(&self.config, self.port, path, &self.auth)
            .map_err(|e| PortError::Unavailable(format!("League client: {e}")))?;
        match status {
            404 => return Ok(None),
            200..=299 => {}
            code => {
                return Err(PortError::Unavailable(format!(
                    "League client: HTTP {code} on {path}"
                )));
            }
        }
        serde_json::from_slice(&body)
            .map(Some)
            .map_err(|e| PortError::Invalid(format!("League client {path}: {e}")))
    }
}

impl LeagueClient for LcuClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Ok(self.get::<Session>(SESSION)?.map(|s| s.local()))
    }

    fn champion_key(&self, champion_id: i64) -> Result<String, PortError> {
        let mut cache = self
            .champions
            .lock()
            .map_err(|_| PortError::Unavailable("champion cache poisoned".into()))?;
        if cache.is_none() {
            let summary: Vec<ChampionSummary> = self
                .get(CHAMPION_SUMMARY)?
                .ok_or_else(|| PortError::NotFound("champion summary".into()))?;
            *cache = Some(summary.into_iter().map(|c| (c.id, c.alias)).collect());
        }
        cache
            .as_ref()
            .and_then(|by_id| by_id.get(&champion_id).cloned())
            .ok_or_else(|| PortError::NotFound(format!("champion {champion_id}")))
    }
}
