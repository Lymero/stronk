use std::collections::HashMap;
use std::error::Error as _;
use std::sync::Mutex;
use std::time::Duration;

use reqwest::StatusCode;
use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION};
use serde::de::DeserializeOwned;
use serde_json::Value;
use stronk_service::ports::{ChampSelect, LeagueClient, PortError};

use crate::lockfile::Lockfile;
use crate::models::{ChampionSummary, Session};
use crate::tls::{Trust, client_config};

pub const SESSION: &str = "/lol-champ-select/v1/session";
pub const CHAMPION_SUMMARY: &str = "/lol-game-data/assets/v1/champion-summary.json";

const TIMEOUT: Duration = Duration::from_secs(3);

/// HTTPS to the local client, accepting its certificate per [`Trust`] only. The address is
/// always the `127.0.0.1` literal: the verifier skips the name check for that reason alone, so
/// no constructor takes a host.
pub struct LcuClient {
    http: Client,
    base: String,
    auth: String,
    champions: Mutex<Option<HashMap<i64, String>>>,
}

impl LcuClient {
    pub fn new(lock: &Lockfile, trust: &Trust) -> Result<Self, PortError> {
        let config = client_config(trust).map_err(PortError::Invalid)?;
        // This client, and only this one, carries the LCU verifier (docs/security.md).
        let http = Client::builder()
            .tls_backend_preconfigured((*config).clone())
            .timeout(TIMEOUT)
            .no_proxy()
            .build()
            .map_err(|e| PortError::Invalid(format!("HTTP client: {}", chain(&e))))?;
        let token = base64::Engine::encode(
            &base64::engine::general_purpose::STANDARD,
            format!("riot:{}", lock.password),
        );
        Ok(Self {
            http,
            base: format!("https://127.0.0.1:{}", lock.port),
            auth: format!("Basic {token}"),
            champions: Mutex::new(None),
        })
    }

    /// The JSON at `path`, `None` on 404 (how the client says "not in that state").
    pub fn get_json(&self, path: &str) -> Result<Option<Value>, PortError> {
        self.get(path)
    }

    fn get<T: DeserializeOwned>(&self, path: &str) -> Result<Option<T>, PortError> {
        let unavailable =
            |e: reqwest::Error| PortError::Unavailable(format!("League client: {}", chain(&e)));
        let response = self
            .http
            .get(format!("{}{path}", self.base))
            .header(AUTHORIZATION, &self.auth)
            .header(ACCEPT, "application/json")
            .send()
            .map_err(unavailable)?;
        match response.status() {
            StatusCode::NOT_FOUND => return Ok(None),
            status if status.is_success() => {}
            status => {
                return Err(PortError::Unavailable(format!(
                    "League client: HTTP {status} on {path}"
                )));
            }
        }
        let body = response.bytes().map_err(unavailable)?;
        serde_json::from_slice(&body)
            .map(Some)
            .map_err(|e| PortError::Invalid(format!("League client {path}: {e}")))
    }
}

/// An error with its causes: a rejected certificate's description sits a few levels down.
fn chain(e: &reqwest::Error) -> String {
    let mut text = e.to_string();
    let mut source = e.source();
    while let Some(cause) = source {
        text.push_str(": ");
        text.push_str(&cause.to_string());
        source = cause.source();
    }
    text
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
