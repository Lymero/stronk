//! Commands against in-memory fakes of every port.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

mod common;

use std::sync::Arc;

use common::{ClientState, FakeBackups, FakeClient, NoClient, THEIR_SET, context, viego};
use serde_json::{Value, json};
use stronk_domain::Role;
use stronk_domain::select::PageInfo;
use stronk_service::ports::{Backups, ChampSelect, LeagueClient};
use stronk_service::{Context, ErrorCode, registry};

fn ctx(client: impl LeagueClient + 'static) -> Context {
    context(Arc::new(client), Arc::new(FakeBackups::default()))
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
            "data.status",
            "item_sets.backups",
            "item_sets.restore",
            "names.get"
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
    for id in ["champselect.state", "names.get"] {
        let err = run(&ctx(NoClient), id, json!({})).unwrap_err();
        assert_eq!(err.code, ErrorCode::Unavailable);
    }
}

#[test]
fn names_get_maps_ids_to_the_clients_names() {
    let out = run(&ctx(FakeClient::new(None)), "names.get", json!({})).unwrap();
    assert_eq!(out["champions"]["234"], "Viego");
    assert_eq!(out["rune_styles"]["8000"], "Precision");
    assert_eq!(out["runes"]["8010"], "Conqueror");
    assert_eq!(out["spells"]["11"], "Smite");
    assert_eq!(out["items"]["6692"], "Eclipse");
}

#[test]
fn unknown_commands_are_named() {
    let err = run(&ctx(NoClient), "nope", json!({})).unwrap_err();
    assert_eq!(err.code, ErrorCode::UnknownCommand);
    assert!(err.message.contains("build.get"));
}

fn import(client: FakeClient) -> (Value, FakeClient) {
    let (out, client, _) = import_with(client, FakeBackups::default());
    (out, client)
}

fn import_with(client: FakeClient, backups: FakeBackups) -> (Value, FakeClient, FakeBackups) {
    import_picks(client, backups, json!({}))
}

fn import_picks(
    client: FakeClient,
    backups: FakeBackups,
    picks: Value,
) -> (Value, FakeClient, FakeBackups) {
    let (client, backups) = (Arc::new(client), Arc::new(backups));
    let ctx = context(client.clone(), backups.clone());
    let out = registry().run(&ctx, "build.import", picks).unwrap();
    drop(ctx);
    let unwrap = |a| Arc::try_unwrap(a).ok().unwrap();
    (out, unwrap(client), Arc::try_unwrap(backups).ok().unwrap())
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
        json!([{"slot": 1, "value": 6693, "label": "clearly_better", "wpa": 0.021,
                "ci": [0.008, 0.034], "games": 2300}])
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
    assert_eq!(
        out["runes"]["reason"],
        "all your rune pages are in use: delete one in the client, then import again"
    );
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
fn import_adds_a_stronk_item_set_and_keeps_the_players_byte_for_byte() {
    let (out, client) = import(FakeClient::new(Some(viego((4, 14)))));
    assert_eq!(out["item_set"]["label"], "clearly_better");
    let written = client.state().item_sets.unwrap();
    // The player's set, with its unknown fields, odd spacing, `2.50` and `\u00e9`, is copied as
    // the client sent it; so are the other members and their order.
    let prefix = format!(r#"{{"accountId":99,"itemSets":[{THEIR_SET},"#);
    assert!(written.starts_with(&prefix), "{written}");
    assert!(written.ends_with(r#"],"timestamp":1}"#), "{written}");
    let ours: Value = serde_json::from_str(&written).unwrap();
    assert_eq!(ours["itemSets"][1]["title"], "Stronk: Viego JUNGLE");
    assert_eq!(
        ours["itemSets"][1]["blocks"][0]["items"],
        json!([{"id": "6693", "count": 1}])
    );
}

#[test]
fn the_players_item_sets_are_backed_up_before_the_write() {
    let original = ClientState::default().item_sets.unwrap();
    let (out, client, backups) = import_with(
        FakeClient::new(Some(viego((4, 14)))),
        FakeBackups::default(),
    );
    assert_eq!(out["item_set_backup"], "backup-1");
    let saved = backups.saved.lock().unwrap().clone();
    assert_eq!(saved, [("item-sets".to_owned(), original.into_bytes())]);
    assert_eq!(client.state().item_set_writes.len(), 1);
}

#[test]
fn nothing_is_written_when_reading_the_item_sets_fails() {
    let state = ClientState {
        item_sets: None,
        ..ClientState::default()
    };
    let (out, client, backups) = import_with(
        FakeClient::with(Some(viego((4, 14))), state),
        FakeBackups::default(),
    );
    assert_eq!(out["item_set"]["status"], "skipped");
    assert!(
        out["item_set"]["reason"]
            .as_str()
            .unwrap()
            .contains("nothing written")
    );
    assert!(client.state().item_set_writes.is_empty());
    assert!(backups.saved.lock().unwrap().is_empty());
    assert_eq!(out["runes"]["status"], "imported"); // the rest of the import still happens
}

#[test]
fn nothing_is_written_when_the_backup_fails() {
    let backups = FakeBackups {
        fail: true,
        ..FakeBackups::default()
    };
    let (out, client, _) = import_with(FakeClient::new(Some(viego((4, 14)))), backups);
    assert_eq!(out["item_set"]["status"], "skipped");
    assert!(
        out["item_set"]["reason"]
            .as_str()
            .unwrap()
            .contains("could not back up")
    );
    assert!(client.state().item_set_writes.is_empty());
}

#[test]
fn nothing_is_written_when_the_item_sets_are_not_what_the_client_sends() {
    let state = ClientState {
        item_sets: Some(r#"{"itemSets": "?"}"#.into()),
        ..ClientState::default()
    };
    let (out, client) = import(FakeClient::with(Some(viego((4, 14))), state));
    assert_eq!(out["item_set"]["status"], "skipped");
    assert!(client.state().item_set_writes.is_empty());
}

#[test]
fn import_writes_the_players_picks_instead_of_stronks() {
    let (out, client, _) = import_picks(
        FakeClient::new(Some(viego((14, 4)))),
        FakeBackups::default(),
        json!({"items": [{"slot": 1, "item": 6672}], "spells": [11, 4]}),
    );
    assert_eq!(out["item_set"]["label"], "picked");
    assert_eq!(out["spells"]["label"], "popular"); // the published pair, whatever its order
    let state = client.state();
    assert_eq!(state.spells, Some((11, 4))); // Flash stays on F
    let ours: Value = serde_json::from_str(&state.item_sets.unwrap()).unwrap();
    let block = &ours["itemSets"][1]["blocks"][0];
    assert_eq!(block["items"], json!([{"id": "6672", "count": 1}]));
    assert_eq!(block["type"], "Item 1 · Your pick");
}

#[test]
fn a_pick_that_isnt_published_writes_nothing() {
    for picks in [
        json!({"items": [{"slot": 1, "item": 3026}]}),
        json!({"items": [{"slot": 2, "item": 6672}]}),
        json!({"items": [{"slot": 1, "item": 6672}, {"slot": 1, "item": 6693}]}),
        json!({"spells": [4, 14]}),
        json!({"runes": {"primary_style": 8000, "sub_style": 8100, "perks": [8010]}}),
    ] {
        let client = Arc::new(FakeClient::new(Some(viego((4, 14)))));
        let backups = Arc::new(FakeBackups::default());
        let err = run_on(&client, &backups, "build.import", picks.clone()).unwrap_err();
        assert_eq!(err.code, ErrorCode::InvalidParams, "{picks}");
        let state = client.state();
        assert_eq!(state.pages.len(), 1, "{picks}");
        assert!(state.item_set_writes.is_empty(), "{picks}");
        assert_eq!(state.spells, None, "{picks}");
    }
}

#[test]
fn import_needs_a_champion_select() {
    let err = run(&ctx(FakeClient::new(None)), "build.import", json!({})).unwrap_err();
    assert_eq!(err.code, ErrorCode::InvalidParams);
}

fn run_on(
    client: &Arc<FakeClient>,
    backups: &Arc<FakeBackups>,
    id: &str,
    params: Value,
) -> Result<Value, stronk_service::CommandError> {
    registry().run(&context(client.clone(), backups.clone()), id, params)
}

#[test]
fn restore_puts_a_backup_back_exactly_and_backs_up_what_it_replaces() {
    let client = Arc::new(FakeClient::new(Some(viego((4, 14)))));
    let backups = Arc::new(FakeBackups::default());
    let original = client.state().item_sets.unwrap();
    run_on(&client, &backups, "build.import", json!({})).unwrap();
    let after_import = client.state().item_sets.unwrap();
    assert_ne!(after_import, original);

    let listed = run_on(&client, &backups, "item_sets.backups", json!({})).unwrap();
    assert_eq!(
        listed,
        json!({"backups": [{"location": "backup-1", "saved_at_ms": 1000}]})
    );
    let out = run_on(
        &client,
        &backups,
        "item_sets.restore",
        json!({"backup": "backup-1"}),
    )
    .unwrap();
    assert_eq!(
        out,
        json!({"restored": "backup-1", "sets": 1, "previous_backup": "backup-2"})
    );
    assert_eq!(client.state().item_sets.unwrap(), original); // byte for byte
    let saved = backups.saved.lock().unwrap();
    assert_eq!(saved[1].1, after_import.into_bytes()); // the restore itself can be undone
}

#[test]
fn restore_refuses_another_accounts_backup_and_writes_nothing() {
    let client = Arc::new(FakeClient::new(Some(viego((4, 14)))));
    let backups = Arc::new(FakeBackups::default());
    backups
        .save("item-sets", br#"{"accountId":12345,"itemSets":[]}"#)
        .unwrap();
    let err = run_on(
        &client,
        &backups,
        "item_sets.restore",
        json!({"backup": "backup-1"}),
    )
    .unwrap_err();
    assert_eq!(err.code, ErrorCode::InvalidParams);
    assert!(err.message.contains("another account"));
    assert!(client.state().item_set_writes.is_empty());
}

#[test]
fn restore_refuses_what_is_not_an_item_set_backup() {
    let client = Arc::new(FakeClient::new(Some(viego((4, 14)))));
    let backups = Arc::new(FakeBackups::default());
    backups
        .save("item-sets", br#"{"accountId":99,"itemSets":"?"}"#)
        .unwrap();
    let err = run_on(
        &client,
        &backups,
        "item_sets.restore",
        json!({"backup": "backup-1"}),
    )
    .unwrap_err();
    assert_eq!(err.code, ErrorCode::InvalidData);
    let missing = run_on(
        &client,
        &backups,
        "item_sets.restore",
        json!({"backup": "backup-9"}),
    )
    .unwrap_err();
    assert_eq!(missing.code, ErrorCode::NotFound);
    assert!(client.state().item_set_writes.is_empty());
}

#[test]
fn restore_writes_nothing_when_the_client_cant_be_read() {
    let state = ClientState {
        item_sets: None,
        ..ClientState::default()
    };
    let client = Arc::new(FakeClient::with(Some(viego((4, 14))), state));
    let backups = Arc::new(FakeBackups::default());
    backups
        .save("item-sets", br#"{"accountId":99,"itemSets":[]}"#)
        .unwrap();
    let err = run_on(
        &client,
        &backups,
        "item_sets.restore",
        json!({"backup": "backup-1"}),
    )
    .unwrap_err();
    assert_eq!(err.code, ErrorCode::Unavailable);
    assert!(client.state().item_set_writes.is_empty());
    assert_eq!(backups.saved.lock().unwrap().len(), 1);
}
