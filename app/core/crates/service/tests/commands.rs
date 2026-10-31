//! Commands against in-memory fakes of every port.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

mod common;

use std::sync::Arc;

use common::{ClientState, FakeBackups, FakeClient, NoClient, THEIR_SET, context, viego};
use serde_json::{Value, json};
use stronk_domain::Role;
use stronk_domain::select::{PageInfo, shrunk};
use stronk_service::ports::{Backups, ChampSelect, LeagueClient};
use stronk_service::{Context, ErrorCode, registry};

fn ctx(client: impl LeagueClient + 'static) -> Context {
    context(Arc::new(client), Arc::new(FakeBackups::default()))
}

fn run(ctx: &Context, id: &str, params: Value) -> Result<Value, stronk_service::CommandError> {
    registry().run(ctx, id, params)
}

#[test]
fn the_schema_types_every_commands_params_and_result() {
    let registry = registry();
    let schema = registry.schema().unwrap();
    let ids: Vec<&str> = registry.list().into_iter().map(|c| c.id).collect();
    let properties = schema["properties"].as_object().unwrap();
    assert_eq!(
        properties.keys().map(String::as_str).collect::<Vec<_>>(),
        ids
    );
    for id in ids {
        let signature = &properties[id]["properties"];
        assert!(
            signature["params"].is_object() && signature["result"].is_object(),
            "{id}"
        );
    }
    let defs = schema["definitions"].as_object().unwrap();
    for name in [
        "Plan",
        "ImportParams",
        "Imported",
        "ChampSelectState",
        "CommandError",
    ] {
        assert!(defs.contains_key(name), "{name}");
    }
    // A flattened label next to an outcome's own fields stays in one object for json2ts.
    let outcome = &defs["Outcome"]["oneOf"][0];
    assert!(
        outcome["allOf"][0]["properties"]["name"].is_object(),
        "{outcome}"
    );
    assert_eq!(
        properties["build.get"]["properties"]["result"],
        json!({"tsType": "BuildV1.Build"})
    );
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
            "icons.get",
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
        enemies: vec![],
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
    for (id, params) in [
        ("champselect.state", json!({})),
        ("names.get", json!({})),
        ("icons.get", json!({"items": [6692]})),
    ] {
        let err = run(&ctx(NoClient), id, params).unwrap_err();
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
fn icons_get_returns_data_urls_and_leaves_out_what_has_none() {
    let out = run(
        &ctx(FakeClient::new(None)),
        "icons.get",
        json!({"champions": [234, 234], "items": [6692, 1, 3071], "runes": [8010]}),
    )
    .unwrap();
    assert_eq!(
        out,
        json!({
            "champions": {"234": "data:image/png;base64,cG5n"},
            "rune_styles": {},
            "runes": {},
            "spells": {},
            "items": {"6692": "data:image/png;base64,cG5n"},
        })
    );
}

#[test]
fn icons_get_takes_a_bounded_list_of_known_kinds() {
    let none = run(&ctx(FakeClient::new(None)), "icons.get", json!({})).unwrap();
    assert_eq!(none["items"], json!({}));
    let unknown = run(
        &ctx(FakeClient::new(None)),
        "icons.get",
        json!({"skins": [1]}),
    );
    assert_eq!(unknown.unwrap_err().code, ErrorCode::InvalidParams);
    let ids: Vec<i64> = (0..201).collect();
    let many = run(
        &ctx(FakeClient::new(None)),
        "icons.get",
        json!({"items": ids}),
    );
    assert_eq!(many.unwrap_err().code, ErrorCode::InvalidParams);
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
                "ci": [0.008, 0.034], "games": 2300, "then": [6672],
                // The block draws from the slot's order (Stronk's choice first), four in all.
                "order": [6693, 6672], "block": 4}])
    );
}

#[test]
fn plan_ranks_each_slots_alternatives_by_the_same_rule() {
    let out = run(
        &ctx(NoClient),
        "build.plan",
        json!({"champion": "Viego", "role": "JUNGLE"}),
    )
    .unwrap();
    assert_eq!(
        (&out["games"], &out["elo"], &out["region"]),
        (&json!(18432), &json!("diamond_plus"), &json!("euw1"))
    );
    let alternatives = &out["alternatives"];
    assert_eq!(
        alternatives["items"],
        json!([{"slot": 1, "more": 0, "rows": [
            {"value": 6672, "played": 6100, "share": 6100.0 / 8540.0, "wpa": 0.008,
             "ci": [0.001, 0.015], "versus": "alternatives", "confidence": "most_played",
             "fragile": false, "chosen": false, "listed": true, "judged": 0.0},
            // Stronk's judgement: the head-to-head gain, shrunk by its uncertainty.
            {"value": 6693, "played": 2300, "share": 2300.0 / 8540.0, "wpa": 0.021,
             "ci": [0.008, 0.034], "versus": "most_played", "confidence": "clearly_better",
             "fragile": false, "chosen": true, "listed": true,
             "judged": shrunk(0.021, Some((0.008, 0.034)))},
            {"value": 6692, "played": 140, "share": 140.0 / 8540.0, "wpa": null, "ci": null,
             "versus": "alternatives", "confidence": "too_few_games", "fragile": false,
             "chosen": false, "listed": true, "judged": 0.0}
        ]}])
    );
    let spells = &alternatives["spells"]["rows"][0];
    assert_eq!(
        (&spells["value"], &spells["confidence"], &spells["chosen"]),
        (&json!([4, 11]), &json!("most_played"), &json!(true))
    );
    assert_eq!(alternatives["runes"]["rows"][0]["chosen"], true);
    // A page row stands for its keystone: all 9120 games with Conqueror, not only the 7810 with
    // exactly this page.
    assert_eq!(alternatives["runes"]["rows"][0]["played"], 9120);
}

#[test]
fn plan_takes_the_most_played_start_and_ranks_the_others() {
    let out = run(
        &ctx(NoClient),
        "build.plan",
        json!({"champion": "Viego", "role": "JUNGLE"}),
    )
    .unwrap();
    assert_eq!(out["start"], json!({"value": [1102], "label": "popular"}));
    assert_eq!(out["start_buy"], json!([1102, 2003]));
    assert_eq!(
        out["components"],
        json!({"value": [1036], "label": "popular"})
    );
    assert_eq!(
        out["alternatives"]["components"]["rows"][1]["value"],
        json!([1036, 1037])
    );
    assert_eq!(out["boots"], json!({"value": 3047, "label": "popular"}));
    assert_eq!(out["boots_then"], json!([3111]));
    let rows = &out["alternatives"]["start"]["rows"];
    assert_eq!(rows[0]["confidence"], "most_played");
    // Compared head to head with the most played start, no clear difference.
    assert_eq!(
        (&rows[1]["value"], &rows[1]["versus"], &rows[1]["wpa"]),
        (&json!([1101]), &json!("most_played"), &json!(-0.005))
    );
}

#[test]
fn plan_chooses_boots_against_the_enemy_teams_damage() {
    let plan = |enemies: Value| {
        run(
            &ctx(NoClient),
            "build.plan",
            json!({"champion": "Viego", "role": "JUNGLE", "enemies": enemies}),
        )
        .unwrap()
    };
    // Two Ahris and a Lee Sin: a magic team, and the data has boots against magic teams.
    let magic = plan(json!([103, 103, 64]));
    assert_eq!(magic["boots_against"], "magic");
    assert_eq!(magic["boots"]["value"], 3111);
    assert_eq!(magic["alternatives"]["boots"]["rows"][1]["value"], 3047);
    // A physical team, with no boots against physical teams: every game.
    let physical = plan(json!([64, 64, 234]));
    assert_eq!(physical["boots_against"], Value::Null);
    assert_eq!(physical["boots"]["value"], 3047);
    // Two enemies only: too few to read.
    assert_eq!(plan(json!([103, 103]))["boots_against"], Value::Null);
}

#[test]
fn import_writes_the_boots_for_the_enemy_team_it_sees() {
    let mut session = viego((4, 14));
    session.enemies = vec![103, 103, 64];
    let (_, client) = import(FakeClient::new(Some(session)));
    let ours: Value = serde_json::from_str(&client.state().item_sets.unwrap()).unwrap();
    let boots = &ours["itemSets"][0]["blocks"][3];
    assert_eq!(boots["type"], "Boots: Popular");
    assert_eq!(boots["items"][0]["id"], "3111");
}

#[test]
fn plan_ranks_each_rune_row_and_marks_the_imported_pages_choices() {
    let out = run(
        &ctx(NoClient),
        "build.plan",
        json!({"champion": "Viego", "role": "JUNGLE"}),
    )
    .unwrap();
    let rows = &out["alternatives"]["rune_rows"];
    let shape: Vec<_> = rows
        .as_array()
        .unwrap()
        .iter()
        .map(|r| (r["kind"].clone(), r["style"].clone(), r["row"].clone()))
        .collect();
    assert_eq!(
        shape,
        vec![
            (json!("primary"), json!(8000), json!(1)),
            (json!("secondary"), json!(8100), json!(null)),
            (json!("shard"), json!(null), json!(1)),
        ]
    );
    // Precision row 1: Triumph is in the imported page and the most played; Legend: Alacrity is
    // compared with it, with no clear difference.
    assert_eq!(
        rows[0]["rows"],
        json!([
            {"value": [9111], "played": 5200, "share": 5200.0 / 7600.0, "wpa": 0.006,
             "ci": [-0.004, 0.016], "versus": "alternatives", "confidence": "most_played",
             "fragile": false, "chosen": true, "listed": true, "judged": 0.0},
            {"value": [8009], "played": 2400, "share": 2400.0 / 7600.0, "wpa": -0.009,
             "ci": [-0.026, 0.008], "versus": "most_played", "confidence": "no_clear_difference",
             "fragile": false, "chosen": false, "listed": true,
             "judged": shrunk(-0.009, Some((-0.026, 0.008)))}
        ])
    );
    assert_eq!(rows[1]["rows"][0]["value"], json!([8135, 8143]));
    assert_eq!(rows[1]["rows"][0]["chosen"], true);
    assert_eq!(rows[2]["rows"][0]["chosen"], true); // shard row 1 of the page: 5005
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
    // Stronk's set first, on top in the shop; the player's set, with its unknown fields, odd
    // spacing, `2.50` and `\u00e9`, copied as the client sent it; so are the other members and
    // their order.
    assert!(
        written.starts_with(r#"{"accountId":99,"itemSets":[{"#),
        "{written}"
    );
    let suffix = format!(r#",{THEIR_SET}],"timestamp":1}}"#);
    assert!(written.ends_with(&suffix), "{written}");
    let ours: Value = serde_json::from_str(&written).unwrap();
    let set = &ours["itemSets"][0];
    // The champion as the client names it, the role as players say it.
    assert_eq!(set["title"], "Stronk: Viego Jungle");
    assert_eq!(set["priority"], true);
    // The start first, as bought with its potion (ADR-071).
    assert_eq!(set["blocks"][0]["type"], "Start: Popular");
    assert_eq!(
        set["blocks"][0]["items"],
        json!([{"id": "1102", "count": 1}, {"id": "2003", "count": 1}])
    );
    // Then the first components as bought, boots included (ADR-072).
    assert_eq!(set["blocks"][1]["type"], "First components: Popular");
    assert_eq!(
        set["blocks"][1]["items"],
        json!([{"id": "1036", "count": 1}, {"id": "2003", "count": 1}])
    );
    // Stronk's choice, then the slot's other item with enough games (Eclipse, at 1.6%, isn't).
    assert_eq!(
        set["blocks"][2]["items"],
        json!([{"id": "6693", "count": 1}, {"id": "6672", "count": 1}])
    );
    // Boots after the first item (ADR-073); Ionian Boots, under 2% of games, aren't listed.
    assert_eq!(set["blocks"][3]["type"], "Boots: Popular");
    assert_eq!(
        set["blocks"][3]["items"],
        json!([{"id": "3047", "count": 1}, {"id": "3111", "count": 1}])
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
        json!({"items": [{"slot": 1, "item": 6672}], "spells": [11, 4], "start": [1101],
               "components": [1037, 1036], "boots": 3111}),
    );
    assert_eq!(out["item_set"]["label"], "picked");
    assert_eq!(out["spells"]["label"], "popular"); // the published pair, whatever its order
    let state = client.state();
    assert_eq!(state.spells, Some((11, 4))); // Flash stays on F
    let ours: Value = serde_json::from_str(&state.item_sets.unwrap()).unwrap();
    let start = &ours["itemSets"][0]["blocks"][0];
    assert_eq!(start["type"], "Start: Your pick");
    assert_eq!(
        start["items"],
        json!([{"id": "1101", "count": 1}, {"id": "2003", "count": 1}])
    );
    let components = &ours["itemSets"][0]["blocks"][1];
    assert_eq!(components["type"], "First components: Your pick");
    assert_eq!(
        components["items"],
        json!([{"id": "1001", "count": 1}, {"id": "1036", "count": 1}, {"id": "1037", "count": 1}])
    );
    let boots = &ours["itemSets"][0]["blocks"][3];
    assert_eq!(boots["type"], "Boots: Your pick");
    assert_eq!(
        boots["items"],
        json!([{"id": "3111", "count": 1}, {"id": "3047", "count": 1}])
    );
    let block = &ours["itemSets"][0]["blocks"][2];
    assert_eq!(
        block["items"],
        json!([{"id": "6672", "count": 1}, {"id": "6693", "count": 1}])
    );
    assert_eq!(block["type"], "Item 1: Your pick");
}

#[test]
fn import_writes_a_page_the_player_built_rune_by_rune() {
    // Not a published page, but one the client's trees allow (ADR-059).
    let page = json!({"primary_style": 8000, "sub_style": 8300,
        "perks": [8005, 8009, 9104, 8014, 8304, 8347, 5005, 5008, 5011]});
    let (out, client, _) = import_picks(
        FakeClient::new(Some(viego((4, 14)))),
        FakeBackups::default(),
        json!({"runes": page}),
    );
    assert_eq!(out["runes"]["status"], "imported");
    assert_eq!(out["runes"]["label"], "picked");
    let written = client.state().pages.last().unwrap().1.clone().unwrap();
    assert_eq!(
        written.perks,
        vec![8005, 8009, 9104, 8014, 8304, 8347, 5005, 5008, 5011]
    );
    assert_eq!((written.primary_style, written.sub_style), (8000, 8300));
}

#[test]
fn a_pick_that_isnt_published_writes_nothing() {
    for picks in [
        json!({"items": [{"slot": 1, "item": 3026}]}),
        json!({"items": [{"slot": 2, "item": 6672}]}),
        json!({"items": [{"slot": 1, "item": 6672}, {"slot": 1, "item": 6693}]}),
        json!({"spells": [4, 14]}),
        json!({"start": [1055]}),
        json!({"components": [1037]}),
        json!({"boots": 3006}),
        json!({"runes": {"primary_style": 8000, "sub_style": 8100, "perks": [8010]}}),
        // Two secondary runes from the same row: no client would take it.
        json!({"runes": {"primary_style": 8000, "sub_style": 8300,
            "perks": [8005, 8009, 9104, 8014, 8304, 8321, 5005, 5008, 5011]}}),
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
