use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Duration;

use base64::Engine;
use serde::de::DeserializeOwned;
use stronk_service::ports::{ChampSelect, LeagueClient, PortError};
use ureq::Agent;
use ureq::tls::{Certificate, RootCerts, TlsConfig};

use crate::lockfile::Lockfile;
use crate::models::{ChampionSummary, Session};

const TIMEOUT: Duration = Duration::from_secs(2);

/// HTTPS to the local client, trusting one root certificate only.
pub struct LcuClient {
    agent: Agent,
    base: String,
    auth: String,
    champions: Mutex<Option<HashMap<i64, String>>>,
}

impl LcuClient {
    /// `root_pem`: the certificate the client's HTTPS chains to (`tools/lcu-mock` writes its
    /// own; the real client's root is added with the champion-select work).
    pub fn new(lock: &Lockfile, root_pem: &[u8]) -> Result<Self, PortError> {
        let root = Certificate::from_pem(root_pem)
            .map_err(|e| PortError::Invalid(format!("root certificate: {e}")))?;
        let tls = TlsConfig::builder()
            .root_certs(RootCerts::new_with_certs(&[root]))
            .build();
        let agent = Agent::config_builder()
            .tls_config(tls)
            .timeout_global(Some(TIMEOUT))
            .http_status_as_error(false)
            .build()
            .new_agent();
        let token =
            base64::engine::general_purpose::STANDARD.encode(format!("riot:{}", lock.password));
        Ok(Self {
            agent,
            base: format!("https://127.0.0.1:{}", lock.port),
            auth: format!("Basic {token}"),
            champions: Mutex::new(None),
        })
    }

    /// `None` on 404, which is how the client says "not in that state".
    fn get<T: DeserializeOwned>(&self, path: &str) -> Result<Option<T>, PortError> {
        let unavailable = |e: ureq::Error| PortError::Unavailable(format!("League client: {e}"));
        let mut response = self
            .agent
            .get(&format!("{}{path}", self.base))
            .header("Authorization", &self.auth)
            .header("Accept", "application/json")
            .call()
            .map_err(unavailable)?;
        match response.status().as_u16() {
            404 => return Ok(None),
            200..=299 => {}
            code => {
                return Err(PortError::Unavailable(format!(
                    "League client: HTTP {code} on {path}"
                )));
            }
        }
        let body = response.body_mut().read_to_vec().map_err(unavailable)?;
        serde_json::from_slice(&body)
            .map(Some)
            .map_err(|e| PortError::Invalid(format!("League client {path}: {e}")))
    }
}

impl LeagueClient for LcuClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Ok(self
            .get::<Session>("/lol-champ-select/v1/session")?
            .map(|s| s.local()))
    }

    fn champion_key(&self, champion_id: i64) -> Result<String, PortError> {
        let mut cache = self
            .champions
            .lock()
            .map_err(|_| PortError::Unavailable("champion cache poisoned".into()))?;
        if cache.is_none() {
            let summary: Vec<ChampionSummary> = self
                .get("/lol-game-data/assets/v1/champion-summary.json")?
                .ok_or_else(|| PortError::NotFound("champion summary".into()))?;
            *cache = Some(summary.into_iter().map(|c| (c.id, c.alias)).collect());
        }
        cache
            .as_ref()
            .and_then(|by_id| by_id.get(&champion_id).cloned())
            .ok_or_else(|| PortError::NotFound(format!("champion {champion_id}")))
    }
}
