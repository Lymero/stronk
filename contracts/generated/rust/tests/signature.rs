//! The example manifest's signature, made by the pipeline (Python), verifies with the
//! minisign-verify crate: the formats agree byte for byte. The key is a test-only key that no
//! app trusts (contracts/tests/keys/).

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used)]

use minisign_verify::{PublicKey, Signature};

fn read(path: &str) -> Vec<u8> {
    std::fs::read(format!("{}/../../{path}", env!("CARGO_MANIFEST_DIR"))).unwrap()
}

fn key() -> PublicKey {
    PublicKey::decode(&String::from_utf8(read("tests/keys/test-only.pub")).unwrap()).unwrap()
}

fn signature() -> Signature {
    Signature::decode(&String::from_utf8(read("examples/manifest.v1.json.minisig")).unwrap())
        .unwrap()
}

#[test]
fn pipeline_signature_verifies() {
    let manifest = read("examples/manifest.v1.json");
    key().verify(&manifest, &signature(), false).unwrap();
    assert_eq!(
        signature().trusted_comment(),
        "stronk manifest v1 patch=26.20 runId=2026-10-16T1200-a1b2c3"
    );
}

#[test]
fn tampered_manifest_is_rejected() {
    let mut manifest = read("examples/manifest.v1.json");
    manifest.push(b' ');
    assert!(key().verify(&manifest, &signature(), false).is_err());
}
