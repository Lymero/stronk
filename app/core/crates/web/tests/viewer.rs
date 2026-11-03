//! The viewer's core against the committed signed fixture data (`fixtures/data`, 16.20).

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing, clippy::expect_used)]

use std::path::PathBuf;

use stronk_domain::Role;
use stronk_web::{Data, Listed, abilities_of, names_of};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../..")
}

fn read(path: &str) -> Vec<u8> {
    std::fs::read(root().join(path)).unwrap()
}

fn data() -> Data {
    let key = String::from_utf8(read("fixtures/data.pub")).unwrap();
    let manifest = read("fixtures/data/16.20/manifest.json");
    let signature = read("fixtures/data/16.20/manifest.json.minisig");
    Data::verified(&key, "16.20", &manifest, &signature).unwrap()
}

#[test]
fn a_manifest_is_used_only_with_its_signature_and_patch() {
    let key = String::from_utf8(read("fixtures/data.pub")).unwrap();
    let manifest = read("fixtures/data/16.20/manifest.json");
    let signature = read("fixtures/data/16.20/manifest.json.minisig");
    let mut tampered = manifest.clone();
    tampered.extend_from_slice(b" ");
    assert!(Data::verified(&key, "16.20", &tampered, &signature).is_err());
    assert!(Data::verified(&key, "16.21", &manifest, &signature).is_err());
    let other =
        "untrusted comment: another key\nRWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3";
    assert!(Data::verified(other, "16.20", &manifest, &signature).is_err());
}

#[test]
fn lists_every_champion_and_role_with_a_build() {
    let listed = data().listed();
    assert!(listed.contains(&Listed {
        champion: "LeeSin".into(),
        role: Role::Jungle
    }));
    assert!(listed.windows(2).all(|w| w[0] < w[1]));
}

#[test]
fn reads_the_closest_bracket_with_a_build_as_the_app_does() {
    let data = data();
    assert_eq!(data.elos(), ["master_plus"]);
    // The fixture has Master+ only: Diamond+ falls back to it (ADR-079).
    let bracket = data.bracket_for("LeeSin", "JUNGLE", "diamond_plus");
    assert_eq!(bracket.as_deref(), Some("master_plus"));
    assert_eq!(data.bracket_for("LeeSin", "TOP", "master_plus"), None);
    assert_eq!(data.bracket_for("../x", "JUNGLE", "master_plus"), None);
}

#[test]
fn plans_a_verified_build_as_build_plan_does() {
    let data = data();
    let path = Data::path("LeeSin", "JUNGLE", "master_plus").unwrap();
    let bytes = read(&format!("fixtures/data/16.20/{path}"));
    let plan = data
        .plan_of("LeeSin", "JUNGLE", "master_plus", &bytes)
        .unwrap();
    assert_eq!(
        (plan.champion.as_str(), plan.role),
        ("LeeSin", Role::Jungle)
    );
    let build = serde_json::from_slice(&bytes).unwrap();
    let core = stronk_service::commands::build_plan::plan(&build, Role::Jungle, None);
    assert_eq!(
        serde_json::to_value(&plan).unwrap(),
        serde_json::to_value(&core).unwrap()
    );
    // Another file's bytes, or changed ones, are refused.
    let mut changed = bytes.clone();
    changed.push(b'\n');
    assert!(
        data.plan_of("LeeSin", "JUNGLE", "master_plus", &changed)
            .is_err()
    );
    let other = read("fixtures/data/16.20/all/master_plus/Graves/JUNGLE.json");
    assert!(
        data.plan_of("LeeSin", "JUNGLE", "master_plus", &other)
            .is_err()
    );
}

#[test]
fn names_and_icon_paths_come_from_the_game_data_documents() {
    let docs: serde_json::Value =
        serde_json::from_slice(&read("tools/lcu_mock/game_data.json")).unwrap();
    let doc = |name: &str| docs[format!("/lol-game-data/assets/v1/{name}")].to_string();
    let champions = r#"[{"id": 64, "alias": "LeeSin", "name": "Lee Sin",
        "squarePortraitPath": "/lol-game-data/assets/v1/champion-icons/64.png"},
        {"id": 1, "alias": "X", "name": "X", "squarePortraitPath": "https://example.com/x.png"}]"#;
    let names = names_of(
        champions,
        &doc("perkstyles.json"),
        &doc("perks.json"),
        &doc("summoner-spells.json"),
        &doc("items.json"),
    )
    .unwrap();
    assert_eq!(names.names.champions[&64], "Lee Sin");
    assert_eq!(names.names.shard_rows.len(), 3);
    assert!(names.names.rune_trees.contains_key(&8000));
    let champion_icons = &names.icons["champions"];
    assert_eq!(champion_icons.len(), 1); // a path outside the game data is left out
    assert_eq!(
        champion_icons[&64],
        "/lol-game-data/assets/v1/champion-icons/64.png"
    );
    assert!(names_of("{", "{}", "[]", "[]", "[]").is_err());
}

#[test]
fn ability_icon_paths_come_from_the_champions_document() {
    let lee = r#"{"id": 64, "spells": [
        {"spellKey": "q", "abilityIconPath": "/lol-game-data/assets/ASSETS/Characters/LeeSin/HUD/Icons2D/LeeSinQ1.png"},
        {"spellKey": "r", "abilityIconPath": "/lol-game-data/assets/ASSETS/Characters/LeeSin/HUD/Icons2D/LeeSinR.png"},
        {"spellKey": "e", "abilityIconPath": "../../etc/passwd"}]}"#;
    let icons = abilities_of(64, lee).unwrap();
    assert_eq!(icons.keys().copied().collect::<Vec<_>>(), [641, 644]);
    assert!(icons[&641].ends_with("LeeSinQ1.png"));
    assert!(abilities_of(64, "[").is_err());
}
