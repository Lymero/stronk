use std::path::{Path, PathBuf};

/// The client's `lockfile`: `LeagueClient:<pid>:<port>:<password>:<protocol>`.
#[derive(Clone, PartialEq, Eq)]
pub struct Lockfile {
    pub port: u16,
    pub password: String,
    pub protocol: String,
}

impl std::fmt::Debug for Lockfile {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The password grants full control of the client: never in logs.
        f.debug_struct("Lockfile")
            .field("port", &self.port)
            .field("protocol", &self.protocol)
            .finish()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum LockfileError {
    #[error("no lockfile: is the League client running?")]
    Missing,
    #[error("unreadable lockfile at {0}")]
    Unreadable(PathBuf),
    #[error("malformed lockfile")]
    Malformed,
}

impl Lockfile {
    pub fn parse(text: &str) -> Result<Self, LockfileError> {
        let parts: Vec<&str> = text.trim().split(':').collect();
        let [_, _, port, password, protocol] = parts.as_slice() else {
            return Err(LockfileError::Malformed);
        };
        let port = port.parse().map_err(|_| LockfileError::Malformed)?;
        if password.is_empty() || *protocol != "https" {
            return Err(LockfileError::Malformed);
        }
        Ok(Self {
            port,
            password: (*password).to_owned(),
            protocol: (*protocol).to_owned(),
        })
    }

    pub fn read(path: &Path) -> Result<Self, LockfileError> {
        match std::fs::read_to_string(path) {
            Ok(text) => Self::parse(&text),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Err(LockfileError::Missing),
            Err(_) => Err(LockfileError::Unreadable(path.to_owned())),
        }
    }
}

/// `STRONK_LCU_LOCKFILE` if set, otherwise the first default install location that exists.
pub fn discover() -> Result<PathBuf, LockfileError> {
    if let Some(path) = std::env::var_os("STRONK_LCU_LOCKFILE") {
        return Ok(PathBuf::from(path));
    }
    const DEFAULTS: [&str; 2] = [
        r"C:\Riot Games\League of Legends\lockfile",
        "/Applications/League of Legends.app/Contents/LoL/lockfile",
    ];
    DEFAULTS
        .iter()
        .map(PathBuf::from)
        .find(|p| p.is_file())
        .ok_or(LockfileError::Missing)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_client_format() {
        let lock = Lockfile::parse("LeagueClient:1234:53210:s3cr3t:https\n").unwrap();
        assert_eq!(lock.port, 53210);
        assert_eq!(lock.password, "s3cr3t");
    }

    #[test]
    fn rejects_anything_else() {
        for bad in [
            "",
            "a:b:c",
            "LeagueClient:1:notaport:pw:https",
            "LeagueClient:1:1:pw:http",
            "LeagueClient:1:1::https",
        ] {
            assert_eq!(Lockfile::parse(bad), Err(LockfileError::Malformed), "{bad}");
        }
    }

    #[test]
    fn debug_output_hides_the_password() {
        let lock = Lockfile::parse("LeagueClient:1:2:s3cr3t:https").unwrap();
        assert!(!format!("{lock:?}").contains("s3cr3t"));
    }
}
