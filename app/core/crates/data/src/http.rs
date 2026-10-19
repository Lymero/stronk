//! Published data over HTTP (`just serve-data`, later the CDN), kept in a cache on disk
//! (ADR-046).
//!
//! `/index.json` names the patches. A patch's manifest is fetched with `If-None-Match` and
//! verified like any other, then cached with its ETag; build files are cached under the
//! manifest's hashes, so a cached file that still matches needs no request at all. Whatever
//! fails (the network, a signature, a hash) leaves the last verified cache in use, and the
//! unsigned index can't move the app backwards: a patch verified once stays a candidate for the
//! newest, and an older run of a cached patch is refused.

use std::collections::HashMap;
use std::error::Error as _;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use reqwest::blocking::Client;
use reqwest::header::{ETAG, IF_NONE_MATCH};
use reqwest::{StatusCode, Url};
use rustls::ClientConfig;
use rustls_platform_verifier::BuilderVerifierExt;
use sha2::{Digest, Sha256};
use stronk_contracts::build_v1::Build;
use stronk_contracts::index_v1::Index;
use stronk_domain::{BuildKey, Patch};
use stronk_service::ports::{BuildSource, DataStatus, PortError};

use crate::verify::{TrustedKey, VerifiedManifest};

const INDEX: &str = "index.json";
const MANIFEST: &str = "manifest.json";
const SIGNATURE: &str = "manifest.json.minisig";
/// How long `status` keeps the newest patch it found before asking the server again. In
/// between, lookups are served from memory and the disk cache: the lock-in path never waits on
/// the network for a build it has seen.
pub const REFRESH: Duration = Duration::from_secs(300);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const TIMEOUT: Duration = Duration::from_secs(15);
/// An index or a manifest bigger than this isn't one.
const MAX_METADATA: u64 = 16 * 1024 * 1024;
/// Patches tried, newest first, before `status` gives up.
const TRIES: usize = 4;

pub struct HttpSource {
    base: Url,
    key: TrustedKey,
    cache: PathBuf,
    http: Client,
    refresh: Duration,
    newest: Mutex<Option<(Instant, Patch)>>,
    manifests: Mutex<HashMap<Patch, Arc<VerifiedManifest>>>,
}

enum Fetched {
    Fresh { data: Vec<u8>, etag: Option<String> },
    NotModified,
}

/// A cached manifest, verified again on every read, and the ETag it was served with.
struct Cached {
    verified: Arc<VerifiedManifest>,
    etag: Option<String>,
}

impl HttpSource {
    /// `base` is `https://…`, or `http://` to this machine only (`just serve-data`). The cache
    /// for it is a folder of its own under `cache`.
    pub fn new(base: &str, key: TrustedKey, cache: &Path) -> Result<Self, PortError> {
        let invalid = |why: &str| PortError::Invalid(format!("data source {base}: {why}"));
        let mut url = Url::parse(base).map_err(|e| invalid(&e.to_string()))?;
        let local = matches!(url.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"));
        match url.scheme() {
            "https" => {}
            "http" if local => {}
            "http" => return Err(invalid("plain HTTP is for this machine only; use https")),
            _ => return Err(invalid("not an http(s) URL")),
        }
        if url.query().is_some() || url.fragment().is_some() || !url.username().is_empty() {
            return Err(invalid("a base URL has no query, fragment or credentials"));
        }
        if !url.path().ends_with('/') {
            let path = format!("{}/", url.path());
            url.set_path(&path);
        }
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        // The operating system's roots, as a browser would: the CDN's certificate is ordinary.
        let tls = ClientConfig::builder_with_provider(provider)
            .with_safe_default_protocol_versions()
            .and_then(BuilderVerifierExt::with_platform_verifier)
            .map_err(|e| invalid(&format!("TLS: {e}")))?
            .with_no_client_auth();
        let mut http = Client::builder()
            .tls_backend_preconfigured(tls)
            .connect_timeout(CONNECT_TIMEOUT)
            .timeout(TIMEOUT);
        if local {
            http = http.no_proxy();
        }
        let http = http
            .build()
            .map_err(|e| invalid(&format!("HTTP client: {}", chain(&e))))?;
        let folder: String = Sha256::digest(url.as_str().as_bytes())
            .iter()
            .take(8)
            .map(|b| format!("{b:02x}"))
            .collect();
        Ok(Self {
            base: url,
            key,
            cache: cache.join(folder),
            http,
            refresh: REFRESH,
            newest: Mutex::new(None),
            manifests: Mutex::new(HashMap::new()),
        })
    }

    /// How long the newest patch is kept before asking again ([`REFRESH`] by default).
    #[must_use]
    pub fn with_refresh(mut self, refresh: Duration) -> Self {
        self.refresh = refresh;
        self
    }

    /// Where this source caches what it fetched.
    pub fn cache_dir(&self) -> &Path {
        &self.cache
    }

    /// The newest patch that verifies, from the index and the cache. When the index can't be
    /// reached, only the cache is used.
    fn find_newest(&self) -> Result<Arc<VerifiedManifest>, PortError> {
        let index = self.index();
        let online = !matches!(index, Err(PortError::Unavailable(_)));
        let mut candidates = self.cached_patches();
        let mut last = match index {
            Ok(listed) => {
                candidates.extend(listed);
                None
            }
            Err(e) => Some(e),
        };
        candidates.sort_unstable_by(|a, b| b.cmp(a));
        candidates.dedup();
        for patch in candidates.into_iter().take(TRIES) {
            match self.manifest(patch, online) {
                Ok(verified) => return Ok(verified),
                Err(e) => last = last.or(Some(e)),
            }
        }
        Err(last.unwrap_or_else(|| {
            PortError::NotFound(format!("no patch at {} or in the cache", self.base))
        }))
    }

    fn index(&self) -> Result<Vec<Patch>, PortError> {
        let cached = read(&self.cache.join(INDEX));
        let etag = cached
            .as_ref()
            .and_then(|_| read_text(&self.cache.join(etag_name(INDEX))));
        let data = match self.get(INDEX, etag.as_deref(), MAX_METADATA)? {
            Fetched::NotModified => cached.ok_or_else(|| self.unexpected(INDEX))?,
            Fetched::Fresh { data, etag } => {
                parse_index(&data)?;
                self.store(INDEX, &data, etag.as_deref());
                data
            }
        };
        parse_index(&data)
    }

    /// Patches whose manifest is in the cache; each is verified before it's used.
    fn cached_patches(&self) -> Vec<Patch> {
        let Ok(entries) = fs::read_dir(&self.cache) else {
            return vec![];
        };
        entries
            .filter_map(Result::ok)
            .filter(|e| e.path().join(MANIFEST).is_file())
            .filter_map(|e| e.file_name().to_str()?.parse::<Patch>().ok())
            .collect()
    }

    /// The patch's manifest from memory, else as [`Self::manifest`] finds it.
    fn known(&self, patch: Patch) -> Result<Arc<VerifiedManifest>, PortError> {
        if let Some(verified) = lock(&self.manifests).get(&patch) {
            return Ok(Arc::clone(verified));
        }
        self.manifest(patch, true)
    }

    /// The patch's manifest, revalidated against the server when `online`; the cached one
    /// when the server's copy can't be had or doesn't verify, or is an older run.
    fn manifest(&self, patch: Patch, online: bool) -> Result<Arc<VerifiedManifest>, PortError> {
        let cached = self.cached_manifest(patch);
        let chosen = match (
            online.then(|| self.fetch_manifest(patch, cached.as_ref())),
            cached,
        ) {
            (Some(Ok(None)), Some(cached)) => cached.verified,
            (Some(Ok(Some(fresh))), Some(cached))
                if fresh.manifest.generated_at < cached.verified.manifest.generated_at =>
            {
                cached.verified
            }
            (Some(Ok(Some(fresh))), _) => Arc::new(fresh),
            (Some(Ok(None)), None) => return Err(self.unexpected(MANIFEST)),
            (Some(Err(_)) | None, Some(cached)) => cached.verified,
            (Some(Err(e)), None) => return Err(e),
            (None, None) => {
                return Err(PortError::Unavailable(format!(
                    "{patch}: {} can't be reached and nothing is cached",
                    self.base
                )));
            }
        };
        lock(&self.manifests).insert(patch, Arc::clone(&chosen));
        Ok(chosen)
    }

    /// `None` when the server says the cached manifest is current; a fresh one is verified and
    /// cached (unless it's an older run than the cache, which [`Self::manifest`] refuses).
    fn fetch_manifest(
        &self,
        patch: Patch,
        cached: Option<&Cached>,
    ) -> Result<Option<VerifiedManifest>, PortError> {
        let (manifest_path, signature_path) = (
            format!("{patch}/{MANIFEST}"),
            format!("{patch}/{SIGNATURE}"),
        );
        let etag = cached.and_then(|c| c.etag.as_deref());
        let Fetched::Fresh {
            data: manifest,
            etag,
        } = self.get(&manifest_path, etag, MAX_METADATA)?
        else {
            return Ok(None);
        };
        let Fetched::Fresh {
            data: signature, ..
        } = self.get(&signature_path, None, MAX_METADATA)?
        else {
            return Err(self.unexpected(&signature_path));
        };
        let verified = VerifiedManifest::verify(&self.key, patch, &manifest, &signature)?;
        let older = cached
            .is_some_and(|c| verified.manifest.generated_at < c.verified.manifest.generated_at);
        if !older {
            // The signature first: a manifest without its own signature beside it never
            // verifies from the cache, so an interrupted write is a miss, not a wrong answer.
            self.store(&signature_path, &signature, None);
            self.store(&manifest_path, &manifest, etag.as_deref());
        }
        Ok(Some(verified))
    }

    fn cached_manifest(&self, patch: Patch) -> Option<Cached> {
        let dir = self.cache.join(patch.to_string());
        let manifest = read(&dir.join(MANIFEST))?;
        let signature = read(&dir.join(SIGNATURE))?;
        let verified = VerifiedManifest::verify(&self.key, patch, &manifest, &signature).ok()?;
        Some(Cached {
            verified: Arc::new(verified),
            etag: read_text(&dir.join(etag_name(MANIFEST))),
        })
    }

    fn get(&self, path: &str, etag: Option<&str>, limit: u64) -> Result<Fetched, PortError> {
        let url = self
            .base
            .join(path)
            .map_err(|e| PortError::Invalid(format!("{path}: {e}")))?;
        let failed = |e: reqwest::Error| PortError::Unavailable(format!("{url}: {}", chain(&e)));
        let mut request = self.http.get(url.clone());
        if let Some(etag) = etag {
            request = request.header(IF_NONE_MATCH, etag);
        }
        let response = request.send().map_err(failed)?;
        match response.status() {
            StatusCode::OK => {}
            StatusCode::NOT_MODIFIED if etag.is_some() => return Ok(Fetched::NotModified),
            StatusCode::NOT_FOUND => return Err(PortError::NotFound(url.to_string())),
            status => return Err(PortError::Unavailable(format!("{url}: HTTP {status}"))),
        }
        let etag = response
            .headers()
            .get(ETAG)
            .and_then(|v| v.to_str().ok())
            .map(str::to_owned);
        let mut data = Vec::new();
        response
            .take(limit.saturating_add(1))
            .read_to_end(&mut data)
            .map_err(|e| PortError::Unavailable(format!("{url}: {e}")))?;
        if data.len() as u64 > limit {
            return Err(PortError::Invalid(format!("{url}: larger than expected")));
        }
        Ok(Fetched::Fresh { data, etag })
    }

    /// Writes `data` (and its ETag) into the cache, each file replaced in one rename. A cache
    /// that can't be written only costs a later request, so failures are ignored.
    fn store(&self, path: &str, data: &[u8], etag: Option<&str>) {
        let target = self.cache.join(path);
        let _ = write_atomic(&target, data);
        if let Some(name) = target.file_name().and_then(|n| n.to_str()) {
            let etag_path = target.with_file_name(etag_name(name));
            let _ = match etag {
                Some(etag) => write_atomic(&etag_path, etag.as_bytes()),
                None => fs::remove_file(&etag_path).or(Ok(())),
            };
        }
    }

    fn unexpected(&self, path: &str) -> PortError {
        PortError::Unavailable(format!("{}{path}: unexpected 304", self.base))
    }
}

impl BuildSource for HttpSource {
    fn status(&self) -> Result<DataStatus, PortError> {
        let verified = {
            let mut newest = lock(&self.newest);
            match *newest {
                Some((at, patch)) if at.elapsed() < self.refresh => self.known(patch)?,
                previous => match self.find_newest() {
                    Ok(verified) => {
                        *newest = Some((Instant::now(), verified.patch));
                        verified
                    }
                    // Keep serving what was found before rather than fail a lookup.
                    Err(e) => match previous {
                        Some((_, patch)) => {
                            *newest = Some((Instant::now(), patch));
                            self.known(patch)?
                        }
                        None => return Err(e),
                    },
                },
            }
        };
        Ok(DataStatus {
            patch: verified.patch,
            run_id: verified.manifest.run_id.to_string(),
            key_id: verified.manifest.key_id.to_string(),
            files: verified.manifest.files.len(),
        })
    }

    fn build(&self, patch: Patch, key: &BuildKey) -> Result<Build, PortError> {
        let verified = self.known(patch)?;
        let path = key.path();
        let bytes = verified
            .entry(&path)
            .ok_or_else(|| PortError::NotFound(format!("{patch} {path}")))?
            .bytes;
        let cached_path = format!("{patch}/{path}");
        if let Some(data) = read(&self.cache.join(&cached_path))
            && let Ok(build) = verified.parse_build(key, &data)
        {
            return Ok(build);
        }
        let Fetched::Fresh { data, .. } = self.get(&cached_path, None, bytes)? else {
            return Err(self.unexpected(&cached_path));
        };
        let build = verified.parse_build(key, &data)?;
        self.store(&cached_path, &data, None);
        Ok(build)
    }
}

/// `STRONK_CACHE_DIR`, else the platform's cache folder: `%LOCALAPPDATA%\stronk\cache` on
/// Windows, `$XDG_CACHE_HOME/stronk` or `~/.cache/stronk` elsewhere.
pub fn default_cache_dir() -> PathBuf {
    let var = |name: &str| std::env::var_os(name).map(PathBuf::from);
    if let Some(dir) = var("STRONK_CACHE_DIR") {
        return dir;
    }
    if let Some(local) = var("LOCALAPPDATA") {
        return local.join("stronk").join("cache");
    }
    var("XDG_CACHE_HOME")
        .or_else(|| var("HOME").map(|home| home.join(".cache")))
        .unwrap_or_else(|| PathBuf::from("."))
        .join("stronk")
}

fn parse_index(data: &[u8]) -> Result<Vec<Patch>, PortError> {
    let index: Index = serde_json::from_slice(data)
        .map_err(|e| PortError::Invalid(format!("{INDEX}: not an index.v1 ({e})")))?;
    index
        .patches
        .iter()
        .map(|p| {
            p.parse::<Patch>()
                .map_err(|e| PortError::Invalid(format!("{INDEX}: {e}")))
        })
        .collect()
}

/// The ETag beside a cached file: hidden, so it can never be taken for published data.
fn etag_name(file: &str) -> String {
    format!(".{file}.etag")
}

fn read(path: &Path) -> Option<Vec<u8>> {
    fs::read(path).ok()
}

fn read_text(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok().filter(|t| !t.is_empty())
}

fn write_atomic(target: &Path, data: &[u8]) -> std::io::Result<()> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let dir = target.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(dir)?;
    let name = target
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("file");
    let staging = dir.join(format!(
        ".{name}.{}-{}.tmp",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    let written = fs::write(&staging, data).and_then(|()| fs::rename(&staging, target));
    if written.is_err() {
        let _ = fs::remove_file(&staging);
    }
    written
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    // A panic elsewhere can't leave these maps half-updated; keep using them.
    mutex
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn chain(e: &reqwest::Error) -> String {
    let mut text = e.to_string();
    let mut source = e.source();
    while let Some(cause) = source {
        text.push_str(": ");
        text.push_str(&cause.to_string());
        source = cause.source();
    }
    text
}
