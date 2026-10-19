//! Local backups of what an import replaces in the client (ADR-043): written before each
//! write, newest `KEEP` per kind kept, on this machine only.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use stronk_service::ports::{Backups, PortError};

const KEEP: usize = 20;

pub struct FileBackups {
    dir: PathBuf,
}

impl FileBackups {
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        Self { dir: dir.into() }
    }
}

/// `STRONK_BACKUP_DIR`, else the platform's data folder: `%APPDATA%\stronk\backups` on
/// Windows, `$XDG_DATA_HOME/stronk/backups` or `~/.local/share/stronk/backups` elsewhere.
pub fn default_backup_dir() -> PathBuf {
    let var = |name: &str| std::env::var_os(name).map(PathBuf::from);
    if let Some(dir) = var("STRONK_BACKUP_DIR") {
        return dir;
    }
    let base = var("APPDATA")
        .or_else(|| var("XDG_DATA_HOME"))
        .or_else(|| var("HOME").map(|home| home.join(".local/share")))
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("stronk").join("backups")
}

impl Backups for FileBackups {
    fn save(&self, kind: &str, data: &[u8]) -> Result<String, PortError> {
        let failed =
            |e: std::io::Error| PortError::Unavailable(format!("{}: {e}", self.dir.display()));
        if !kind.bytes().all(|b| b.is_ascii_lowercase() || b == b'-') || kind.is_empty() {
            return Err(PortError::Invalid(format!("backup kind {kind:?}")));
        }
        fs::create_dir_all(&self.dir).map_err(failed)?;
        let millis = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |d| d.as_millis());
        // Zero-padded time, then a counter for writes in the same millisecond that continues
        // after the highest one there (pruning frees low counters; reusing one would sort a new
        // backup before older ones): name order is the order they were written in.
        let stem = format!("{kind}-{millis:016}-");
        let next = fs::read_dir(&self.dir)
            .map_err(failed)?
            .filter_map(Result::ok)
            .filter_map(|e| {
                let name = e.file_name().into_string().ok()?;
                name.strip_prefix(&stem)?
                    .strip_suffix(".json")?
                    .parse::<u32>()
                    .ok()
            })
            .max()
            .map_or(0, |n| n + 1);
        let path = self.dir.join(format!("{stem}{next:03}.json"));
        fs::write(&path, data).map_err(failed)?;
        // Oldest first by name (see above); everything but the newest KEEP goes.
        let mut old: Vec<PathBuf> = fs::read_dir(&self.dir)
            .map_err(failed)?
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| {
                p.file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.starts_with(&format!("{kind}-")))
            })
            .collect();
        old.sort();
        let excess = old.len().saturating_sub(KEEP);
        for stale in old.into_iter().take(excess) {
            let _ = fs::remove_file(stale); // keeping one too many is harmless
        }
        Ok(path.display().to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saves_exact_bytes_and_keeps_the_newest() {
        let dir = std::env::temp_dir().join(format!("stronk-backups-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let backups = FileBackups::new(&dir);
        let first = backups.save("item-sets", br#"{"a": 1}"#).unwrap();
        assert_eq!(fs::read(&first).unwrap(), br#"{"a": 1}"#);
        for i in 0..KEEP + 3 {
            backups.save("item-sets", i.to_string().as_bytes()).unwrap();
        }
        let mut kept: Vec<PathBuf> = fs::read_dir(&dir)
            .unwrap()
            .map(|e| e.unwrap().path())
            .collect();
        kept.sort();
        let contents: Vec<String> = kept
            .iter()
            .map(|p| fs::read_to_string(p).unwrap())
            .collect();
        let newest: Vec<String> = (3..KEEP + 3).map(|i| i.to_string()).collect();
        assert_eq!(contents, newest); // the newest KEEP, in the order they were written
        assert!(!PathBuf::from(&first).exists());
        assert!(backups.save("../x", b"").is_err());
        fs::remove_dir_all(&dir).unwrap();
    }
}
