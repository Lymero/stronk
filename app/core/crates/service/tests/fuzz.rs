//! Command fuzzing (roadmap M3): any id with any JSON params returns a result or a typed
//! error, never a panic.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

use std::sync::Arc;

use proptest::prelude::*;
use serde_json::{Map, Value};
use stronk_contracts::build_v1::Build;
use stronk_domain::{BuildKey, Patch};
use stronk_service::ports::{BuildSource, ChampSelect, DataStatus, PortError};
use stronk_service::{Context, registry};

mod common;

struct Empty;

impl BuildSource for Empty {
    fn status(&self) -> Result<DataStatus, PortError> {
        Err(PortError::Unavailable("offline".into()))
    }
    fn build(&self, _: Patch, key: &BuildKey) -> Result<Build, PortError> {
        Err(PortError::NotFound(key.path()))
    }
}

fn json() -> impl Strategy<Value = Value> {
    let leaf = prop_oneof![
        Just(Value::Null),
        any::<bool>().prop_map(Value::Bool),
        any::<i64>().prop_map(Value::from),
        any::<f64>().prop_map(Value::from),
        prop_oneof![
            Just("TOP".to_owned()),
            Just("16.20".to_owned()),
            Just("../..".to_owned()),
            ".*"
        ]
        .prop_map(Value::String),
    ];
    leaf.prop_recursive(3, 24, 6, |inner| {
        let keys = prop_oneof![
            Just("champion".to_owned()),
            Just("role".to_owned()),
            Just("patch".to_owned()),
            Just("region".to_owned()),
            Just("elo".to_owned()),
            "[a-z]{1,6}",
        ];
        prop_oneof![
            prop::collection::vec(inner.clone(), 0..4).prop_map(Value::Array),
            prop::collection::vec((keys, inner), 0..5)
                .prop_map(|kv| Value::Object(kv.into_iter().collect::<Map<_, _>>())),
        ]
    })
}

proptest! {
    #[test]
    fn commands_never_panic(
        id in prop_oneof![Just("build.get"), Just("build.plan"), Just("build.import"),
                          Just("champselect.state"), Just("data.status"), Just("x")],
        params in json(),
    ) {
        let session = ChampSelect { champion_id: 7, locked: true, role: None, phase: "FINALIZATION".into(), spells: None };
        let ctx = Context { builds: Arc::new(Empty), client: Arc::new(common::FakeClient::new(Some(session))) };
        let _ = registry().run(&ctx, id, params);
    }
}
