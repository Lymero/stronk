//! Commands against in-memory fakes of every port.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

use std::sync::Arc;

use serde_json::{Value, json};
use stronk_contracts::build_v1::Build;
use stronk_domain::{BuildKey, Patch, Role};
use stronk_service::ports::{BuildSource, ChampSelect, DataStatus, LeagueClient, PortError};
use stronk_service::{Context, ErrorCode, registry};

fn example_build() -> Build {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../../../contracts/examples/build.v1.json"
    );
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

struct FakeBuilds;

impl BuildSource for FakeBuilds {
    fn status(&self) -> Result<DataStatus, PortError> {
        Ok(DataStatus {
            patch: "16.20".parse().unwrap(),
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

struct FakeClient(Option<ChampSelect>);

impl LeagueClient for FakeClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Ok(self.0.clone())
    }

    fn champion_key(&self, champion_id: i64) -> Result<String, PortError> {
        match champion_id {
            234 => Ok("Viego".into()),
            id => Err(PortError::NotFound(format!("champion {id}"))),
        }
    }
}

struct NoClient;

impl LeagueClient for NoClient {
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError> {
        Err(PortError::Unavailable(
            "the League client isn't running".into(),
        ))
    }

    fn champion_key(&self, _: i64) -> Result<String, PortError> {
        Err(PortError::Unavailable(
            "the League client isn't running".into(),
        ))
    }
}

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
    assert_eq!(ids, ["build.get", "champselect.state", "data.status"]);
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
        champion_id: 234,
        locked: false,
        role: Some(Role::Jungle),
        phase: "PLANNING".into(),
    };
    let out = run(
        &ctx(FakeClient(Some(session))),
        "champselect.state",
        json!({}),
    )
    .unwrap();
    assert_eq!(out["champion"], "Viego");
    assert_eq!(out["role"], "JUNGLE");
}

#[test]
fn champselect_state_outside_champion_select() {
    let out = run(&ctx(FakeClient(None)), "champselect.state", json!({})).unwrap();
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
