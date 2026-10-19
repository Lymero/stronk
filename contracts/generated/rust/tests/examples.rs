//! The committed examples parse, and values breaking a schema rule are rejected.
//! Parsing goes through every pattern, so a pattern the regex engine can't compile fails here.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

use serde_json::{Value, json};
use stronk_contracts::{build_v1::Build, index_v1::Index, manifest_v1::Manifest};

fn example(name: &str) -> Value {
    let path = format!("{}/../../examples/{name}", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn with(mut value: Value, pointer: &str, replacement: Value) -> Value {
    *value.pointer_mut(pointer).unwrap() = replacement;
    value
}

#[test]
fn build_example_parses() {
    let build: Build = serde_json::from_value(example("build.v1.json")).unwrap();
    assert_eq!(build.items.len(), 3);
    let comparison = build.items[1].comparison.as_ref().unwrap();
    assert_eq!(
        (comparison.versus, build.items[1].picks),
        (6672, Some(2300))
    );
}

#[test]
fn manifest_example_parses() {
    let manifest: Manifest = serde_json::from_value(example("manifest.v1.json")).unwrap();
    assert_eq!(manifest.files.len(), 1);
}

// Typify doesn't enforce numeric bounds (`minimum` above 0, `maximum`); see contracts/README.md.
#[test]
fn build_rejects_invalid_values() {
    let cases = [
        ("/schemaVersion", json!(2)),
        ("/patch", json!("26")),
        ("/role", json!("SUPPORT")),
        ("/region", json!("EUW1")),
        ("/items/2/flags/0", json!("unknown_flag")),
        ("/items/0/ci", json!([0.1])),
        ("/runes/0/page/perks", json!([1, 2, 3])),
    ];
    for (pointer, bad) in cases {
        let value = with(example("build.v1.json"), pointer, bad);
        assert!(
            serde_json::from_value::<Build>(value).is_err(),
            "accepted bad {pointer}"
        );
    }
}

#[test]
fn manifest_rejects_invalid_values() {
    let cases = [
        ("/files/0/path", json!("../escape.json")),
        ("/files/0/path", json!("/absolute.json")),
        ("/files/0/path", json!("euw1/./x.json")),
        ("/files/0/sha256", json!("ABC")),
        ("/keyId", json!("0123456789abcdef")),
        ("/runId", json!("bad id")),
        ("/generatedAt", json!("yesterday")),
    ];
    for (pointer, bad) in cases {
        let value = with(example("manifest.v1.json"), pointer, bad);
        assert!(
            serde_json::from_value::<Manifest>(value).is_err(),
            "accepted bad {pointer}"
        );
    }
}

#[test]
fn index_example_parses_and_rejects_invalid_values() {
    let index: Index = serde_json::from_value(example("index.v1.json")).unwrap();
    assert_eq!(index.patches.len(), 2);
    let cases = [
        ("/schemaVersion", json!(2)),
        ("/patches/0", json!("../26.19")),
        ("/patches", json!("26.20")),
    ];
    for (pointer, bad) in cases {
        let value = with(example("index.v1.json"), pointer, bad);
        assert!(
            serde_json::from_value::<Index>(value).is_err(),
            "accepted bad {pointer}"
        );
    }
}

#[test]
fn unknown_fields_are_rejected() {
    let mut value = example("build.v1.json");
    value["extra"] = json!(true);
    assert!(serde_json::from_value::<Build>(value).is_err());
}
