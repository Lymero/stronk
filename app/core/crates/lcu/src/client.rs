use std::collections::{BTreeMap, HashMap};
use std::error::Error as _;
use std::sync::Mutex;
use std::time::Duration;

use reqwest::Method;
use reqwest::StatusCode;
use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION, CONTENT_TYPE};
use serde::de::DeserializeOwned;
use serde_json::Value;
use stronk_domain::select::PageInfo;
use stronk_service::ports::{
    ChampSelect, GameNames, Icon, IconKind, LeagueClient, NewRunePage, PortError,
};

use crate::lockfile::Lockfile;
use crate::models::{
    ChampionSummary, CurrentSummoner, Named, PerkInventory, PerkPage, PerkStyles, Session, by_id,
    icons_by_id, image_type,
};
use crate::tls::{Trust, client_config};

pub const SESSION: &str = "/lol-champ-select/v1/session";
pub const CHAMPION_SUMMARY: &str = "/lol-game-data/assets/v1/champion-summary.json";
pub const PERK_STYLES: &str = "/lol-game-data/assets/v1/perkstyles.json";
pub const PERKS: &str = "/lol-game-data/assets/v1/perks.json";
pub const SPELLS: &str = "/lol-game-data/assets/v1/summoner-spells.json";
pub const ITEMS: &str = "/lol-game-data/assets/v1/items.json";
const PAGES: &str = "/lol-perks/v1/pages";

const TIMEOUT: Duration = Duration::from_secs(3);
/// The largest icon read: the client's are a few kilobytes to a few tens.
const MAX_ICON_BYTES: usize = 512 * 1024;

/// What the client's game data says, read once per client: it changes only when the client
/// updates.
#[derive(Clone)]
struct GameData {
    names: GameNames,
    /// Icon paths by kind, then id, each checked to stay under `/lol-game-data/assets/`.
    icons: BTreeMap<IconKind, BTreeMap<i64, String>>,
}

/// HTTPS to the local client, accepting its certificate per [`Trust`] only. The address is
/// always the `127.0.0.1` literal: the verifier skips the name check for that reason alone, so
/// no constructor takes a host.
pub struct LcuClient {
    http: Client,
    base: String,
    auth: String,
    champions: Mutex<Option<HashMap<i64, String>>>,
    game_data: Mutex<Option<GameData>>,
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
            game_data: Mutex::new(None),
        })
    }

    /// The JSON at `path`, `None` on 404 (how the client says "not in that state").
    pub fn get_json(&self, path: &str) -> Result<Option<Value>, PortError> {
        self.get(path)
    }

    fn get<T: DeserializeOwned>(&self, path: &str) -> Result<Option<T>, PortError> {
        let Some(body) = self.send(Method::GET, path, None)? else {
            return Ok(None);
        };
        serde_json::from_slice(&body)
            .map(Some)
            .map_err(|e| PortError::Invalid(format!("League client {path}: {e}")))
    }

    /// A write; the client answering 404 means the thing written to isn't there.
    fn write(&self, method: Method, path: &str, body: Option<&Value>) -> Result<(), PortError> {
        self.send(method, path, body)?
            .map(|_| ())
            .ok_or_else(|| PortError::NotFound(format!("League client: {path}")))
    }

    /// A write of `body` exactly as given (no re-encoding).
    fn write_raw(&self, method: Method, path: &str, body: &str) -> Result<(), PortError> {
        self.send_text(method, path, Some(body.to_owned()))?
            .map(|_| ())
            .ok_or_else(|| PortError::NotFound(format!("League client: {path}")))
    }

    /// The body of a successful response, `None` on 404.
    fn send(
        &self,
        method: Method,
        path: &str,
        body: Option<&Value>,
    ) -> Result<Option<Vec<u8>>, PortError> {
        self.send_text(method, path, body.map(Value::to_string))
    }

    fn send_text(
        &self,
        method: Method,
        path: &str,
        body: Option<String>,
    ) -> Result<Option<Vec<u8>>, PortError> {
        let unavailable =
            |e: reqwest::Error| PortError::Unavailable(format!("League client: {}", chain(&e)));
        let mut request = self
            .http
            .request(method.clone(), format!("{}{path}", self.base))
            .header(AUTHORIZATION, &self.auth)
            .header(ACCEPT, "application/json");
        if let Some(body) = body {
            request = request.header(CONTENT_TYPE, "application/json").body(body);
        }
        let response = request.send().map_err(unavailable)?;
        match response.status() {
            StatusCode::NOT_FOUND => return Ok(None),
            status if status.is_success() => {}
            status => {
                return Err(PortError::Unavailable(format!(
                    "League client: HTTP {status} on {method} {path}"
                )));
            }
        }
        Ok(Some(response.bytes().map_err(unavailable)?.to_vec()))
    }

    /// A game data document that must be there.
    fn game_data<T: DeserializeOwned>(&self, path: &str) -> Result<T, PortError> {
        self.get(path)?
            .ok_or_else(|| PortError::NotFound(format!("League client: {path}")))
    }

    /// Names and icon paths from the game data documents, read on first use.
    fn game_data_cached(&self) -> Result<GameData, PortError> {
        let mut cache = self
            .game_data
            .lock()
            .map_err(|_| PortError::Unavailable("game data cache poisoned".into()))?;
        if let Some(data) = cache.as_ref() {
            return Ok(data.clone());
        }
        let champions: Vec<ChampionSummary> = self.game_data(CHAMPION_SUMMARY)?;
        let styles = self.game_data::<PerkStyles>(PERK_STYLES)?.styles;
        let runes = self.game_data::<Vec<Named>>(PERKS)?;
        let spells = self.game_data::<Vec<Named>>(SPELLS)?;
        let items = self.game_data::<Vec<Named>>(ITEMS)?;
        let paths =
            |entries: &[Named]| icons_by_id(entries.iter().map(|e| (e.id, e.icon_path.as_str())));
        let data = GameData {
            names: GameNames {
                champions: champions
                    .iter()
                    .filter(|c| !c.name.is_empty())
                    .map(|c| (c.id, c.name.clone()))
                    .collect(),
                rune_styles: by_id(&styles),
                runes: by_id(&runes),
                spells: by_id(&spells),
                items: by_id(&items),
            },
            icons: BTreeMap::from([
                (
                    IconKind::Champion,
                    icons_by_id(
                        champions
                            .iter()
                            .map(|c| (c.id, c.square_portrait_path.as_str())),
                    ),
                ),
                (IconKind::RuneStyle, paths(&styles)),
                (IconKind::Rune, paths(&runes)),
                (IconKind::Spell, paths(&spells)),
                (IconKind::Item, paths(&items)),
            ]),
        };
        *cache = Some(data.clone());
        Ok(data)
    }

    /// An image the client serves at `path`, `None` on 404; anything else than a small PNG,
    /// JPEG or WebP is refused.
    fn image(&self, path: &str) -> Result<Option<Icon>, PortError> {
        let unavailable =
            |e: reqwest::Error| PortError::Unavailable(format!("League client: {}", chain(&e)));
        let response = self
            .http
            .get(format!("{}{path}", self.base))
            .header(AUTHORIZATION, &self.auth)
            // The client answers 406 to anything narrower, even `image/png`; the bytes are
            // checked below instead.
            .header(ACCEPT, "*/*")
            .send()
            .map_err(unavailable)?;
        match response.status() {
            StatusCode::NOT_FOUND => return Ok(None),
            status if status.is_success() => {}
            status => {
                return Err(PortError::Unavailable(format!(
                    "League client: HTTP {status} on GET {path}"
                )));
            }
        }
        let too_large =
            || PortError::Invalid(format!("{path}: larger than {MAX_ICON_BYTES} bytes"));
        if response
            .content_length()
            .is_some_and(|n| n > MAX_ICON_BYTES as u64)
        {
            return Err(too_large());
        }
        let bytes = response.bytes().map_err(unavailable)?.to_vec();
        if bytes.len() > MAX_ICON_BYTES {
            return Err(too_large());
        }
        let mime = image_type(&bytes)
            .ok_or_else(|| PortError::Invalid(format!("{path}: not a PNG, JPEG or WebP image")))?;
        Ok(Some(Icon { mime, bytes }))
    }

    fn summoner_id(&self) -> Result<i64, PortError> {
        self.get::<CurrentSummoner>("/lol-summoner/v1/current-summoner")?
            .map(|s| s.summoner_id)
            .ok_or_else(|| PortError::Unavailable("no summoner logged in".into()))
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

    fn game_names(&self) -> Result<GameNames, PortError> {
        Ok(self.game_data_cached()?.names)
    }

    fn icon(&self, kind: IconKind, id: i64) -> Result<Option<Icon>, PortError> {
        let data = self.game_data_cached()?;
        match data.icons.get(&kind).and_then(|paths| paths.get(&id)) {
            Some(path) => self.image(path),
            None => Ok(None),
        }
    }

    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError> {
        let pages: Vec<PerkPage> = self.get(PAGES)?.unwrap_or_default();
        Ok(pages
            .into_iter()
            .map(|p| PageInfo {
                id: p.id,
                name: p.name,
                editable: p.is_editable,
            })
            .collect())
    }

    fn rune_page_capacity(&self) -> Result<usize, PortError> {
        Ok(self
            .get::<PerkInventory>("/lol-perks/v1/inventory")?
            .unwrap_or_default()
            .owned_page_count)
    }

    fn delete_rune_page(&self, id: i64) -> Result<(), PortError> {
        self.write(Method::DELETE, &format!("{PAGES}/{id}"), None)
    }

    fn create_rune_page(&self, page: &NewRunePage) -> Result<(), PortError> {
        let body = serde_json::json!({
            "name": page.name,
            "primaryStyleId": page.primary_style,
            "subStyleId": page.sub_style,
            "selectedPerkIds": page.perks,
            "current": true,
        });
        self.write(Method::POST, PAGES, Some(&body))
    }

    fn item_sets(&self) -> Result<String, PortError> {
        let path = format!("/lol-item-sets/v1/item-sets/{}/sets", self.summoner_id()?);
        let body = self
            .send(Method::GET, &path, None)?
            .ok_or_else(|| PortError::NotFound("item sets".into()))?;
        String::from_utf8(body).map_err(|_| PortError::Invalid("item sets are not UTF-8".into()))
    }

    fn save_item_sets(&self, document: &str) -> Result<(), PortError> {
        let path = format!("/lol-item-sets/v1/item-sets/{}/sets", self.summoner_id()?);
        self.write_raw(Method::PUT, &path, document)
    }

    fn set_spells(&self, (d, f): (i64, i64)) -> Result<(), PortError> {
        let body = serde_json::json!({"spell1Id": d, "spell2Id": f});
        self.write(
            Method::PATCH,
            "/lol-champ-select/v1/session/my-selection",
            Some(&body),
        )
    }
}
