//! In-memory fakes of every port, shared by the service's tests.

#![allow(dead_code, clippy::unwrap_used)]

use std::collections::{BTreeMap, HashMap};
use std::sync::{Arc, Mutex};

use stronk_contracts::build_v1::Build;
use stronk_domain::select::PageInfo;
use stronk_domain::{BuildKey, Patch, Role};
use stronk_service::Context;
use stronk_service::ports::{
    Backup, Backups, BuildSource, ChampSelect, DataStatus, GameNames, Icon, IconKind, LeagueClient,
    NewRunePage, PortError,
};

pub fn example_build() -> Build {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../../../contracts/examples/build.v1.json"
    );
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

/// Serves the contract's example (Viego JUNGLE, 16.20) and nothing else.
pub struct FakeBuilds;

impl BuildSource for FakeBuilds {
    fn status(&self) -> Result<DataStatus, PortError> {
        let patch = "16.20".parse().unwrap();
        Ok(DataStatus {
            patch,
            run_id: "r".into(),
            key_id: "K".into(),
            files: 1,
        })
    }

    fn build(&self, patch: Patch, key: &BuildKey) -> Result<Build, PortError> {
        if patch.to_string() == "16.20" && key.path() == "all/master_plus/Viego/JUNGLE.json" {
            Ok(example_build())
        } else {
            Err(PortError::NotFound(key.path()))
        }
    }
}

/// The player's item set as the client might send it: odd spacing, an escape, a number written
/// `2.50`, and fields Stronk has never heard of.
pub const THEIR_SET: &str =
    r#"{"title": "My set", "blocks":[ ],"x-future": {"n": 2.50, "s": "é", "list": [1,  2]}}"#;

/// What the fake client holds, readable by tests after a command ran.
#[derive(Clone, Debug)]
pub struct ClientState {
    /// Every page with what was written into it (`None` for pages the player made).
    pub pages: Vec<(PageInfo, Option<NewRunePage>)>,
    pub capacity: usize,
    /// The client's item set document, raw; `None` makes reading it fail.
    pub item_sets: Option<String>,
    /// Every document written, raw.
    pub item_set_writes: Vec<String>,
    pub spells: Option<(i64, i64)>,
    pub deleted: Vec<i64>,
}

impl Default for ClientState {
    fn default() -> Self {
        Self {
            pages: vec![(
                PageInfo {
                    id: 1,
                    name: "My Viego".into(),
                    editable: true,
                },
                None,
            )],
            capacity: 2,
            item_sets: Some(format!(
                r#"{{"accountId":99,"itemSets":[{THEIR_SET}],"timestamp":1}}"#
            )),
            item_set_writes: vec![],
            spells: None,
            deleted: vec![],
        }
    }
}

pub struct FakeClient {
    pub session: Option<ChampSelect>,
    pub state: Mutex<ClientState>,
}

impl FakeClient {
    pub fn new(session: Option<ChampSelect>) -> Self {
        Self {
            session,
            state: Mutex::new(ClientState::default()),
        }
    }

    pub fn with(session: Option<ChampSelect>, state: ClientState) -> Self {
        Self {
            session,
            state: Mutex::new(state),
        }
    }

    pub fn state(&self) -> ClientState {
        self.state.lock().unwrap().clone()
    }
}

/// Viego, locked in the jungle, with these spells on D and F.
pub fn viego(spells: (i64, i64)) -> ChampSelect {
    ChampSelect {
        champion_id: 234,
        locked: true,
        role: Some(Role::Jungle),
        phase: "FINALIZATION".into(),
        spells: Some(spells),
    }
}

impl LeagueClient for FakeClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Ok(self.session.clone())
    }

    fn champion_key(&self, champion_id: i64) -> Result<String, PortError> {
        HashMap::from([(234, "Viego")])
            .get(&champion_id)
            .map(|k| (*k).to_owned())
            .ok_or_else(|| PortError::NotFound(format!("champion {champion_id}")))
    }

    fn game_names(&self) -> Result<GameNames, PortError> {
        Ok(GameNames {
            champions: BTreeMap::from([(234, "Viego".to_owned())]),
            rune_styles: BTreeMap::from([(8000, "Precision".to_owned())]),
            runes: BTreeMap::from([(8010, "Conqueror".to_owned())]),
            spells: BTreeMap::from([(4, "Flash".to_owned()), (11, "Smite".to_owned())]),
            items: BTreeMap::from([(6692, "Eclipse".to_owned())]),
        })
    }

    /// Icons for Viego and Eclipse; item 1's "icon" is not an image.
    fn icon(&self, kind: IconKind, id: i64) -> Result<Option<Icon>, PortError> {
        match (kind, id) {
            (IconKind::Champion, 234) | (IconKind::Item, 6692) => Ok(Some(Icon {
                mime: "image/png",
                bytes: b"png".to_vec(),
            })),
            (IconKind::Item, 1) => Err(PortError::Invalid("items/1.png: not an image".into())),
            _ => Ok(None),
        }
    }

    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError> {
        Ok(self
            .state
            .lock()
            .unwrap()
            .pages
            .iter()
            .map(|(p, _)| p.clone())
            .collect())
    }

    fn rune_page_capacity(&self) -> Result<usize, PortError> {
        Ok(self.state.lock().unwrap().capacity)
    }

    fn delete_rune_page(&self, id: i64) -> Result<(), PortError> {
        let mut state = self.state.lock().unwrap();
        state.pages.retain(|(p, _)| p.id != id);
        state.deleted.push(id);
        Ok(())
    }

    fn create_rune_page(&self, page: &NewRunePage) -> Result<(), PortError> {
        let mut state = self.state.lock().unwrap();
        let id = state.pages.iter().map(|(p, _)| p.id).max().unwrap_or(0) + 1;
        state.pages.push((
            PageInfo {
                id,
                name: page.name.clone(),
                editable: true,
            },
            Some(page.clone()),
        ));
        Ok(())
    }

    fn item_sets(&self) -> Result<String, PortError> {
        let state = self.state.lock().unwrap();
        state
            .item_sets
            .clone()
            .ok_or_else(|| PortError::Unavailable("item sets: HTTP 500".into()))
    }

    fn save_item_sets(&self, document: &str) -> Result<(), PortError> {
        let mut state = self.state.lock().unwrap();
        state.item_sets = Some(document.to_owned());
        state.item_set_writes.push(document.to_owned());
        Ok(())
    }

    fn set_spells(&self, spells: (i64, i64)) -> Result<(), PortError> {
        self.state.lock().unwrap().spells = Some(spells);
        Ok(())
    }
}

/// No client running: every call says so.
pub struct NoClient;

fn down<T>() -> Result<T, PortError> {
    Err(PortError::Unavailable(
        "the League client isn't running".into(),
    ))
}

impl LeagueClient for NoClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        down()
    }
    fn champion_key(&self, _: i64) -> Result<String, PortError> {
        down()
    }
    fn game_names(&self) -> Result<GameNames, PortError> {
        down()
    }
    fn icon(&self, _: IconKind, _: i64) -> Result<Option<Icon>, PortError> {
        down()
    }
    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError> {
        down()
    }
    fn rune_page_capacity(&self) -> Result<usize, PortError> {
        down()
    }
    fn delete_rune_page(&self, _: i64) -> Result<(), PortError> {
        down()
    }
    fn create_rune_page(&self, _: &NewRunePage) -> Result<(), PortError> {
        down()
    }
    fn item_sets(&self) -> Result<String, PortError> {
        down()
    }
    fn save_item_sets(&self, _: &str) -> Result<(), PortError> {
        down()
    }
    fn set_spells(&self, _: (i64, i64)) -> Result<(), PortError> {
        down()
    }
}

/// Backups kept in memory; `fail` makes saving fail.
#[derive(Default)]
pub struct FakeBackups {
    pub fail: bool,
    pub saved: Mutex<Vec<(String, Vec<u8>)>>,
}

impl Backups for FakeBackups {
    fn save(&self, kind: &str, data: &[u8]) -> Result<String, PortError> {
        if self.fail {
            return Err(PortError::Unavailable("disk full".into()));
        }
        let mut saved = self.saved.lock().unwrap();
        saved.push((kind.to_owned(), data.to_vec()));
        Ok(format!("backup-{}", saved.len()))
    }

    fn list(&self, _: &str) -> Result<Vec<Backup>, PortError> {
        let saved = self.saved.lock().unwrap();
        Ok((1..=saved.len())
            .rev()
            .map(|n| Backup {
                location: format!("backup-{n}"),
                saved_at_ms: Some(n as u64 * 1_000),
            })
            .collect())
    }

    fn load(&self, location: &str) -> Result<Vec<u8>, PortError> {
        let n: usize = location
            .strip_prefix("backup-")
            .and_then(|n| n.parse().ok())
            .ok_or_else(|| PortError::NotFound(location.into()))?;
        let saved = self.saved.lock().unwrap();
        saved
            .get(n - 1)
            .map(|(_, data)| data.clone())
            .ok_or_else(|| PortError::NotFound(location.into()))
    }
}

/// A context over these fakes.
pub fn context(client: Arc<dyn LeagueClient>, backups: Arc<dyn Backups>) -> Context {
    Context {
        builds: Arc::new(FakeBuilds),
        client,
        backups,
    }
}
