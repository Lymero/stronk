//! HttpSource against a local server with the CDN's behaviour (ETag, 304), as `just serve-data`
//! serves: the fixture, and data roots signed here with a throwaway key to cover what the
//! fixture can't (newer and older runs, a moving index, tampering).

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing, clippy::expect_used)]

use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use minisign::KeyPair;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use stronk_data::{DirectorySource, HttpSource, TrustedKey, open_source};
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

fn patch(text: &str) -> Patch {
    text.parse().unwrap()
}

/// The fixture's first listed build: its key and bytes.
fn fixture_build() -> (BuildKey, Vec<u8>) {
    let manifest: Value =
        serde_json::from_slice(&fs::read(repo("fixtures/data/16.20/manifest.json")).unwrap())
            .unwrap();
    let path = manifest["files"][0]["path"].as_str().unwrap().to_owned();
    let parts: Vec<_> = path.trim_end_matches(".json").split('/').collect();
    let role = Role::ALL
        .into_iter()
        .find(|r| r.as_str() == parts[3])
        .unwrap();
    let key = BuildKey::new(parts[0], parts[1], parts[2], role).unwrap();
    let data = fs::read(repo("fixtures/data/16.20").join(&path)).unwrap();
    (key, data)
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

fn write_index(root: &Path, patches: &[&str]) {
    let index = json!({"schemaVersion": 1, "patches": patches});
    fs::write(root.join("index.json"), index.to_string()).unwrap();
}

/// A static file server like `just serve-data`: strong ETags, 304 on `If-None-Match`. It logs
/// each request (`path`, or `path (conditional)`), and while `down` it hangs up at once.
struct Server {
    url: String,
    log: Arc<Mutex<Vec<String>>>,
    down: Arc<AtomicBool>,
}

impl Server {
    fn start(root: &Path) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://127.0.0.1:{}", listener.local_addr().unwrap().port());
        let log = Arc::new(Mutex::new(Vec::new()));
        let down = Arc::new(AtomicBool::new(false));
        let (root, log_, down_) = (root.to_owned(), Arc::clone(&log), Arc::clone(&down));
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                if down_.load(Ordering::SeqCst) {
                    continue; // dropped: the connection closes without a response
                }
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let mut line = String::new();
                reader.read_line(&mut line).unwrap();
                let path = line.split(' ').nth(1).unwrap_or("/").to_owned();
                let mut tag = None;
                loop {
                    let mut header = String::new();
                    reader.read_line(&mut header).unwrap();
                    if header.trim().is_empty() {
                        break;
                    }
                    if let Some((name, value)) = header.split_once(':')
                        && name.eq_ignore_ascii_case("if-none-match")
                    {
                        tag = Some(value.trim().to_owned());
                    }
                }
                let mut entry = path.clone();
                if tag.is_some() {
                    entry.push_str(" (conditional)");
                }
                log_.lock().unwrap().push(entry);
                let file = root.join(path.trim_start_matches('/'));
                let response = match fs::read(&file) {
                    Ok(data) if !path.contains("..") => {
                        let etag = format!("\"{:x}\"", Sha256::digest(&data));
                        if tag.as_deref() == Some(etag.as_str()) {
                            format!("HTTP/1.1 304 Not Modified\r\nETag: {etag}\r\nConnection: close\r\n\r\n").into_bytes()
                        } else {
                            let mut out = format!("HTTP/1.1 200 OK\r\nETag: {etag}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", data.len()).into_bytes();
                            out.extend(data);
                            out
                        }
                    }
                    _ => {
                        b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                            .to_vec()
                    }
                };
                let _ = stream.write_all(&response);
            }
        });
        Self { url, log, down }
    }

    fn take_log(&self) -> Vec<String> {
        std::mem::take(&mut *self.log.lock().unwrap())
    }
}

/// The fixture served with an index, a server for it and an empty cache.
fn fixture_served() -> (tempfile::TempDir, Server, tempfile::TempDir) {
    let root = tempfile::tempdir().unwrap();
    copy_dir(&repo("fixtures/data"), root.path());
    write_index(root.path(), &["16.20"]);
    let server = Server::start(root.path());
    (root, server, tempfile::tempdir().unwrap())
}

fn source(server: &Server, cache: &Path) -> HttpSource {
    HttpSource::new(&server.url, fixture_key(), cache).unwrap()
}

#[test]
fn serves_what_the_directory_source_serves() {
    let (_root, server, cache) = fixture_served();
    let http = source(&server, cache.path());
    let dir = DirectorySource::new(repo("fixtures/data"), fixture_key());
    assert_eq!(http.status().unwrap(), dir.status().unwrap());
    let (key, _) = fixture_build();
    let p = patch("16.20");
    assert_eq!(
        serde_json::to_value(http.build(p, &key).unwrap()).unwrap(),
        serde_json::to_value(dir.build(p, &key).unwrap()).unwrap()
    );
    assert_eq!(
        server.take_log(),
        [
            "/index.json",
            "/16.20/manifest.json",
            "/16.20/manifest.json.minisig",
            &format!("/16.20/{}", key.path())
        ]
    );
}

#[test]
fn a_restart_revalidates_and_reads_builds_from_the_cache() {
    let (_root, server, cache) = fixture_served();
    let (key, _) = fixture_build();
    let first = source(&server, cache.path());
    let status = first.status().unwrap();
    first.build(status.patch, &key).unwrap();
    server.take_log();

    let again = source(&server, cache.path());
    assert_eq!(again.status().unwrap(), status);
    again.build(status.patch, &key).unwrap();
    assert_eq!(
        server.take_log(),
        [
            "/index.json (conditional)",
            "/16.20/manifest.json (conditional)"
        ]
    );
}

#[test]
fn status_asks_again_only_after_the_refresh_interval() {
    let (_root, server, cache) = fixture_served();
    let (key, _) = fixture_build();
    let source = source(&server, cache.path());
    let status = source.status().unwrap();
    server.take_log();
    source.status().unwrap();
    source.build(status.patch, &key).unwrap();
    source.build(status.patch, &key).unwrap();
    // One build request, then nothing: the lock-in path is a cache hit.
    assert_eq!(server.take_log(), [format!("/16.20/{}", key.path())]);

    let eager = source.with_refresh(Duration::ZERO);
    eager.status().unwrap();
    assert_eq!(
        server.take_log(),
        [
            "/index.json (conditional)",
            "/16.20/manifest.json (conditional)"
        ]
    );
}

#[test]
fn works_offline_from_the_cache() {
    let (_root, server, cache) = fixture_served();
    let (key, _) = fixture_build();
    let online = source(&server, cache.path());
    let status = online.status().unwrap();
    online.build(status.patch, &key).unwrap();

    server.down.store(true, Ordering::SeqCst);
    let offline = source(&server, cache.path());
    assert_eq!(offline.status().unwrap(), status);
    offline.build(status.patch, &key).unwrap();

    let empty = tempfile::tempdir().unwrap();
    let nothing = source(&server, empty.path());
    assert!(matches!(nothing.status(), Err(PortError::Unavailable(_))));
}

#[test]
fn a_build_not_cached_while_offline_is_unavailable() {
    let (_root, server, cache) = fixture_served();
    let (key, _) = fixture_build();
    let status = source(&server, cache.path()).status().unwrap();
    server.down.store(true, Ordering::SeqCst);
    let offline = source(&server, cache.path());
    assert!(matches!(
        offline.build(status.patch, &key),
        Err(PortError::Unavailable(_))
    ));
}

#[test]
fn a_tampered_manifest_is_refused_and_the_cached_one_kept() {
    let (root, server, cache) = fixture_served();
    let status = source(&server, cache.path()).status().unwrap();
    let manifest = root.path().join("16.20/manifest.json");
    let text = fs::read_to_string(&manifest).unwrap();
    fs::write(&manifest, text.replacen("\"bytes\":", "\"bytes\":1", 1)).unwrap();

    assert_eq!(source(&server, cache.path()).status().unwrap(), status);
    let empty = tempfile::tempdir().unwrap();
    let err = source(&server, empty.path()).status().unwrap_err();
    assert!(matches!(err, PortError::Invalid(_)), "{err:?}");
}

#[test]
fn a_tampered_build_is_refused_and_not_cached() {
    let (root, server, cache) = fixture_served();
    let (key, data) = fixture_build();
    let source = source(&server, cache.path());
    let p = source.status().unwrap().patch;
    let served = root.path().join("16.20").join(key.path());
    let mut bad = data.clone();
    bad[0] = b' ';
    fs::write(&served, &bad).unwrap();
    assert!(matches!(source.build(p, &key), Err(PortError::Invalid(_))));

    fs::write(&served, &data).unwrap();
    server.take_log();
    source.build(p, &key).unwrap();
    assert_eq!(server.take_log(), [format!("/16.20/{}", key.path())]); // it wasn't cached
}

#[test]
fn a_damaged_cached_build_is_fetched_again() {
    let (_root, server, cache) = fixture_served();
    let (key, _) = fixture_build();
    let source = source(&server, cache.path());
    let p = source.status().unwrap().patch;
    source.build(p, &key).unwrap();
    let cached = source.cache_dir().join("16.20").join(key.path());
    fs::write(&cached, b"{}").unwrap();
    server.take_log();
    source.build(p, &key).unwrap();
    assert_eq!(server.take_log(), [format!("/16.20/{}", key.path())]);
}

/// Data roots signed here, to cover runs and patches the fixture doesn't have.
struct Publisher {
    pair: KeyPair,
}

impl Publisher {
    fn new() -> Self {
        Self {
            pair: KeyPair::generate_unencrypted_keypair().unwrap(),
        }
    }

    fn key(&self) -> TrustedKey {
        TrustedKey::decode(&self.pair.pk.to_base64()).unwrap()
    }

    /// The fixture's first build as `patch`, in a manifest written at `at` (minutes past noon).
    fn publish(&self, root: &Path, patch: &str, at: u32) {
        let (key, data) = fixture_build();
        let mut build: Value = serde_json::from_slice(&data).unwrap();
        build["patch"] = json!(patch);
        let data = format!("{build}\n").into_bytes();
        let run = format!("run-{at:02}");
        let manifest = json!({
            "schemaVersion": 1,
            "patch": patch,
            "generatedAt": format!("2026-10-19T12:{at:02}:00Z"),
            "runId": run,
            "keyId": "0123456789ABCDEF",
            "files": [{
                "path": key.path(),
                "sha256": format!("{:x}", Sha256::digest(&data)),
                "bytes": data.len(),
            }],
        })
        .to_string();
        let comment = format!("stronk manifest v1 patch={patch} runId={run}");
        let signature = minisign::sign(
            None,
            &self.pair.sk,
            manifest.as_bytes(),
            Some(&comment),
            None,
        )
        .unwrap();
        let dir = root.join(patch);
        let file = dir.join(key.path());
        fs::create_dir_all(file.parent().unwrap()).unwrap();
        fs::write(file, data).unwrap();
        fs::write(dir.join("manifest.json"), manifest).unwrap();
        fs::write(dir.join("manifest.json.minisig"), signature.into_string()).unwrap();
    }
}

fn signed_root() -> (Publisher, tempfile::TempDir, Server, tempfile::TempDir) {
    let root = tempfile::tempdir().unwrap();
    let server = Server::start(root.path());
    (Publisher::new(), root, server, tempfile::tempdir().unwrap())
}

#[test]
fn a_new_run_replaces_the_cached_one_and_an_older_run_does_not() {
    let (publisher, root, server, cache) = signed_root();
    publisher.publish(root.path(), "26.20", 10);
    write_index(root.path(), &["26.20"]);
    let open = || {
        HttpSource::new(&server.url, publisher.key(), cache.path())
            .unwrap()
            .with_refresh(Duration::ZERO)
    };
    let (key, _) = fixture_build();
    assert_eq!(open().status().unwrap().run_id, "run-10");

    publisher.publish(root.path(), "26.20", 20);
    let source = open();
    assert_eq!(source.status().unwrap().run_id, "run-20");
    source.build(patch("26.20"), &key).unwrap();

    publisher.publish(root.path(), "26.20", 5); // replayed from an older run
    let source = open();
    assert_eq!(source.status().unwrap().run_id, "run-20");
    // The cached build still matches the kept manifest.
    server.take_log();
    source.build(patch("26.20"), &key).unwrap();
    assert!(server.take_log().is_empty());
}

#[test]
fn the_index_finds_new_patches_but_cannot_go_back() {
    let (publisher, root, server, cache) = signed_root();
    publisher.publish(root.path(), "26.19", 0);
    write_index(root.path(), &["26.19"]);
    let source = HttpSource::new(&server.url, publisher.key(), cache.path())
        .unwrap()
        .with_refresh(Duration::ZERO);
    assert_eq!(source.status().unwrap().patch, patch("26.19"));

    publisher.publish(root.path(), "26.20", 0);
    write_index(root.path(), &["26.19", "26.20"]);
    assert_eq!(source.status().unwrap().patch, patch("26.20"));

    write_index(root.path(), &["26.19"]);
    assert_eq!(source.status().unwrap().patch, patch("26.20"));
}

#[test]
fn a_newer_patch_that_fails_to_verify_leaves_the_last_good_one() {
    let (publisher, root, server, cache) = signed_root();
    publisher.publish(root.path(), "26.20", 0);
    Publisher::new().publish(root.path(), "26.21", 0); // another key
    write_index(root.path(), &["26.20", "26.21"]);
    let source = HttpSource::new(&server.url, publisher.key(), cache.path()).unwrap();
    assert_eq!(source.status().unwrap().patch, patch("26.20"));
}

#[test]
fn a_broken_index_is_refused_and_cached_patches_still_serve() {
    let (publisher, root, server, cache) = signed_root();
    publisher.publish(root.path(), "26.20", 0);
    fs::write(root.path().join("index.json"), "{\"patches\": [\"../x\"]}").unwrap();
    let open = || HttpSource::new(&server.url, publisher.key(), cache.path()).unwrap();
    assert!(matches!(open().status(), Err(PortError::Invalid(_))));
    open().build(patch("26.20"), &fixture_build().0).unwrap(); // a patch asked for by name
    assert_eq!(open().status().unwrap().patch, patch("26.20")); // now cached
}

#[test]
fn plain_http_is_for_this_machine_only() {
    let cache = tempfile::tempdir().unwrap();
    for ok in [
        "https://data.example/",
        "https://data.example/v1",
        "http://127.0.0.1:8787",
        "http://localhost:8787/data/",
    ] {
        assert!(
            HttpSource::new(ok, fixture_key(), cache.path()).is_ok(),
            "{ok}"
        );
    }
    for bad in [
        "http://data.example",
        "http://192.168.1.2:8787",
        "ftp://data.example",
        "https://u:p@data.example",
        "https://data.example/?x=1",
        "not a url",
    ] {
        assert!(
            matches!(
                HttpSource::new(bad, fixture_key(), cache.path()),
                Err(PortError::Invalid(_))
            ),
            "{bad}"
        );
    }
}

#[test]
fn a_base_path_is_kept() {
    let (_root, server, cache) = fixture_served();
    let nested = tempfile::tempdir().unwrap();
    copy_dir(_root.path(), &nested.path().join("data"));
    let nested_server = Server::start(nested.path());
    let source = HttpSource::new(
        &format!("{}/data", nested_server.url),
        fixture_key(),
        cache.path(),
    )
    .unwrap();
    assert_eq!(source.status().unwrap().patch, patch("16.20"));
    assert_eq!(nested_server.take_log()[0], "/data/index.json");
    assert!(server.take_log().is_empty());
}

#[test]
fn the_setting_picks_the_source() {
    let (_root, server, cache) = fixture_served();
    let fixture = repo("fixtures/data").display().to_string();
    for setting in [server.url.clone(), format!("dir:{fixture}"), fixture] {
        let source = open_source(&setting, fixture_key(), cache.path()).unwrap();
        assert_eq!(source.status().unwrap().patch, patch("16.20"), "{setting}");
    }
}
