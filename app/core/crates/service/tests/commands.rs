//! Commands against in-memory fakes of every port.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

mod common;

use std::sync::Arc;

use common::{ClientState, FakeBuilds, FakeClient, NoClient, viego};
use serde_json::{Value, json};
use stronk_domain::Role;
use stronk_domain::select::PageInfo;
use stronk_service::ports::{ChampSelect, LeagueClient};
use stronk_service::{Context, ErrorCode, registry};

fn ctx(client: impl LeagueClient + 'static) -> Context {
    Context {
        builds: Arc::new(FakeBuilds),
        client: Arc::new(client),
    }
}

fn run(ctx: &Context, id: &str, params: Value) -> Result<Value, stronk_service::CommandError> {
    registry().run(ctx, id, params)
}

#[test]
fn lists_every_command() {
    let ids: Vec<_> = registry().list().into_iter().map(|c| c.id).collect();
    assert_eq!(
        ids,
        [
            "build.get",
            "build.import",
            "build.plan",
            "champselect.state",
            "data.status"
        ]
    );
}

#[test]
fn build_get_defaults_to_the_newest_patch() {
    let out = run(
        &ctx(NoClient),
        "build.get",
        json!({"champion": "Viego", "role": "JUNGLE"}),
    )
    .unwrap();
    assert_eq!(out["champion"], "Viego");
}

#[test]
fn build_get_rejects_unsafe_and_unknown_params() {
    let unsafe_key = run(
        &ctx(NoClient),
        "build.get",
        json!({"champion": "../x", "role": "TOP"}),
    );
    assert_eq!(unsafe_key.unwrap_err().code, ErrorCode::InvalidParams);
    let extra = run(
        &ctx(NoClient),
        "build.get",
        json!({"champion": "Viego", "role": "TOP", "x": 1}),
    );
    assert_eq!(extra.unwrap_err().code, ErrorCode::InvalidParams);
    let missing = run(
        &ctx(NoClient),
        "build.get",
        json!({"champion": "Viego", "role": "TOP"}),
    );
    assert_eq!(missing.unwrap_err().code, ErrorCode::NotFound);
}

#[test]
fn champselect_state_names_the_champion() {
    let session = ChampSelect {
        spells: None,
        champion_id: 234,
        locked: false,
        role: Some(Role::Jungle),
        phase: "PLANNING".into(),
    };
    let out = run(
        &ctx(FakeClient::new(Some(session))),
        "champselect.state",
        json!({}),
    )
    .unwrap();
    assert_eq!(out["champion"], "Viego");
    assert_eq!(out["role"], "JUNGLE");
}

#[test]
fn champselect_state_outside_champion_select() {
    let out = run(&ctx(FakeClient::new(None)), "champselect.state", json!({})).unwrap();
    assert_eq!(
        out,
        json!({"session": null, "champion": null, "role": null})
    );
}

#[test]
fn a_missing_client_is_an_error_not_a_crash() {
    let err = run(&ctx(NoClient), "champselect.state", json!({})).unwrap_err();
    assert_eq!(err.code, ErrorCode::Unavailable);
}

#[test]
fn unknown_commands_are_named() {
    let err = run(&ctx(NoClient), "nope", json!({})).unwrap_err();
    assert_eq!(err.code, ErrorCode::UnknownCommand);
    assert!(err.message.contains("build.get"));
}

fn import(client: FakeClient) -> (Value, FakeClient) {
    let client = Arc::new(client);
    let ctx = Context {
        builds: Arc::new(FakeBuilds),
        client: client.clone(),
    };
    let out = registry().run(&ctx, "build.import", json!({})).unwrap();
    drop(ctx);
    (out, Arc::try_unwrap(client).ok().unwrap())
}

#[test]
fn plan_takes_the_popular_combination_unless_one_is_clearly_better() {
    let out = run(
        &ctx(NoClient),
        "build.plan",
        json!({"champion": "Viego", "role": "JUNGLE"}),
    )
    .unwrap();
    assert_eq!(out["runes"]["label"], "popular");
    assert_eq!(out["runes"]["value"]["perks"].as_array().unwrap().len(), 9);
    assert_eq!(out["spells"], json!({"value": [4, 11], "label": "popular"}));
    // Item 6693 beats the most picked 6672 head to head and survives FDR.
    assert_eq!(
        out["items"],
        json!([{"slot": 1, "value": 6693, "label": "clearly_better", "wpa": 0.021}])
    );
}

#[test]
fn import_writes_a_full_stronk_page_and_leaves_the_players_alone() {
    let (out, client) = import(FakeClient::new(Some(viego((4, 14)))));
    assert_eq!(out["runes"]["status"], "imported");
    let state = client.state();
    assert_eq!(state.pages.len(), 2);
    assert_eq!(
        state.pages[0],
        (
            PageInfo {
                id: 1,
                name: "My Viego".into(),
                editable: true
            },
            None
        )
    );
    let (info, written) = &state.pages[1];
    assert_eq!(info.name, "Stronk: Viego JUNGLE");
    let written = written.as_ref().unwrap();
    assert_eq!(
        written.perks,
        [8010, 9111, 9104, 8299, 8143, 8135, 5005, 5008, 5001]
    );
    assert_eq!((written.primary_style, written.sub_style), (8000, 8100));
}

#[test]
fn import_replaces_an_existing_stronk_page() {
    let mut state = ClientState::default();
    state.pages.push((
        PageInfo {
            id: 7,
            name: "Stronk: Ahri MIDDLE".into(),
            editable: true,
        },
        None,
    ));
    let (_, client) = import(FakeClient::with(Some(viego((4, 14))), state));
    let state = client.state();
    assert_eq!(state.deleted, [7]);
    let names: Vec<_> = state.pages.iter().map(|(p, _)| p.name.as_str()).collect();
    assert_eq!(names, ["My Viego", "Stronk: Viego JUNGLE"]);
}

#[test]
fn import_never_deletes_the_players_page_to_make_room() {
    let state = ClientState {
        capacity: 1,
        ..ClientState::default()
    };
    let (out, client) = import(FakeClient::with(Some(viego((4, 14))), state));
    assert_eq!(out["runes"]["status"], "skipped");
    assert!(client.state().deleted.is_empty());
    assert_eq!(client.state().pages.len(), 1);
}

#[test]
fn import_keeps_flash_on_the_players_key() {
    let smite = 11;
    for (current, expected) in [((4, 14), (4, smite)), ((14, 4), (smite, 4))] {
        let (_, client) = import(FakeClient::new(Some(viego(current))));
        assert_eq!(
            client.state().spells,
            Some(expected),
            "Flash was on {current:?}"
        );
    }
}

#[test]
fn import_adds_a_stronk_item_set_and_keeps_the_players() {
    let (out, client) = import(FakeClient::new(Some(viego((4, 14)))));
    assert_eq!(out["item_set"]["label"], "clearly_better");
    let sets = client.state().item_sets;
    assert_eq!(sets["accountId"], 99);
    assert_eq!(
        sets["itemSets"][0],
        json!({"title": "My set", "blocks": []})
    );
    assert_eq!(sets["itemSets"][1]["title"], "Stronk: Viego JUNGLE");
    assert_eq!(
        sets["itemSets"][1]["blocks"][0]["items"],
        json!([{"id": "6693", "count": 1}])
    );
}

#[test]
fn import_needs_a_champion_select() {
    let ctx = Context {
        builds: Arc::new(FakeBuilds),
        client: Arc::new(FakeClient::new(None)),
    };
    let err = run(&ctx, "build.import", json!({})).unwrap_err();
    assert_eq!(err.code, ErrorCode::InvalidParams);
}
