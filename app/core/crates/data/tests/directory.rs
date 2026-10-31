//! DirectorySource against `fixtures/data`: the fixture pipeline's signed output
//! (`just fixture-data`), signed by a throwaway key whose public half is `fixtures/data.pub`.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

use std::fs;
use std::path::{Path, PathBuf};

use stronk_data::{DirectorySource, TrustedKey};
use stronk_domain::{BuildKey, Patch, Role};
use stronk_service::ports::{BuildSource, PortError};

fn repo(path: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../..")
        .join(path)
}

fn fixture_key() -> TrustedKey {
    TrustedKey::decode(&fs::read_to_string(repo("fixtures/data.pub")).unwrap()).unwrap()
}

fn patch() -> Patch {
    "16.20".parse().unwrap()
}

/// A listed file, read from the manifest so the test follows the fixture.
fn listed_key() -> BuildKey {
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(repo("fixtures/data/16.20/manifest.json")).unwrap())
            .unwrap();
    let path = manifest["files"][0]["path"].as_str().unwrap().to_owned();
    let parts: Vec<_> = path.trim_end_matches(".json").split('/').collect();
    let role = Role::ALL
        .into_iter()
        .find(|r| r.as_str() == parts[3])
        .unwrap();
    BuildKey::new(parts[0], parts[1], parts[2], role).unwrap()
}

/// A writable copy of the fixture.
fn copy() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    copy_dir(&repo("fixtures/data"), dir.path());
    dir
}

fn copy_dir(from: &Path, to: &Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_dir(&entry.path(), &target);
        } else {
            fs::copy(entry.path(), target).unwrap();
        }
    }
}

#[test]
fn serves_verified_builds() {
    let source = DirectorySource::new(repo("fixtures/data"), fixture_key());
    let status = source.status().unwrap();
    assert_eq!(status.patch, patch());
    assert!(status.files > 10);
    let key = listed_key();
    let build = source.build(patch(), &key).unwrap();
    assert_eq!(build.champion.as_str(), key.champion);
}

#[test]
fn serves_the_verified_champion_ratings() {
    let source = DirectorySource::new(repo("fixtures/data"), fixture_key());
    let champions = source.champions(patch()).unwrap();
    assert_eq!(
        (champions.physical_below, champions.magic_from),
        (0.43, 0.5)
    );
    assert!(!champions.champions.is_empty());
    // Changed by one byte: refused like a build.
    let dir = copy();
    let file = dir.path().join("16.20").join("champions.json");
    let mut data = fs::read(&file).unwrap();
    data.insert(1, b' ');
    fs::write(&file, data).unwrap();
    let err = DirectorySource::new(dir.path(), fixture_key())
        .champions(patch())
        .unwrap_err();
    assert!(matches!(err, PortError::Invalid(m) if m.contains("hash mismatch")));
}

#[test]
fn a_changed_file_is_rejected() {
    let dir = copy();
    let file = dir.path().join("16.20").join(listed_key().path());
    let mut data = fs::read(&file).unwrap();
    data.insert(1, b' ');
    fs::write(&file, data).unwrap();
    let source = DirectorySource::new(dir.path(), fixture_key());
    let err = source.build(patch(), &listed_key()).unwrap_err();
    assert!(matches!(err, PortError::Invalid(m) if m.contains("hash mismatch")));
}

#[test]
fn a_changed_manifest_is_rejected() {
    let dir = copy();
    let manifest = dir.path().join("16.20/manifest.json");
    let text = fs::read_to_string(&manifest)
        .unwrap()
        .replacen("\"bytes\":", "\"bytes\": ", 1);
    fs::write(&manifest, text).unwrap();
    let err = DirectorySource::new(dir.path(), fixture_key())
        .status()
        .unwrap_err();
    assert!(matches!(err, PortError::Invalid(m) if m.contains("signature rejected")));
}

#[test]
fn another_key_is_not_trusted() {
    let other = fs::read_to_string(repo("contracts/tests/keys/test-only.pub")).unwrap();
    let source = DirectorySource::new(repo("fixtures/data"), TrustedKey::decode(&other).unwrap());
    assert!(matches!(
        source.status().unwrap_err(),
        PortError::Invalid(_)
    ));
}

#[test]
fn a_manifest_moved_to_another_patch_is_rejected() {
    let dir = copy();
    fs::rename(dir.path().join("16.20"), dir.path().join("16.21")).unwrap();
    let err = DirectorySource::new(dir.path(), fixture_key())
        .status()
        .unwrap_err();
    assert!(matches!(err, PortError::Invalid(m) if m.contains("lists patch 16.20")));
}

#[test]
fn missing_builds_and_directories_are_not_found() {
    let source = DirectorySource::new(repo("fixtures/data"), fixture_key());
    let absent = BuildKey::new("all", "master_plus", "NotAChampion", Role::Top).unwrap();
    assert!(matches!(
        source.build(patch(), &absent).unwrap_err(),
        PortError::NotFound(_)
    ));
    let nowhere = DirectorySource::new("/nonexistent/stronk", fixture_key());
    assert!(matches!(
        nowhere.status().unwrap_err(),
        PortError::Unavailable(_)
    ));
}
