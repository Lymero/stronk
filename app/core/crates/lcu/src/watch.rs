//! The champion-select watcher (docs/architecture.md, section 5: one task owns the client's
//! websocket and reconnects with backoff).
//!
//! It is a trigger, not a second decoder: it tells its caller when the client connected or the
//! champion-select session changed, and the caller reads the state through the usual command
//! (`champselect.state`). TLS is the LCU verifier's own config (`tls.rs`), through tokio-rustls;
//! the websocket handshake runs on that stream.

use std::sync::Arc;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use rustls::pki_types::{IpAddr, ServerName};
use tokio::net::TcpStream;
use tokio_rustls::TlsConnector;
use tokio_tungstenite::client_async;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::http::HeaderValue;

use crate::connect::ConnectOptions;
use crate::discover;
use crate::lockfile::Lockfile;
use crate::tls::client_config;

/// The client's event for the champion-select session (WAMP topic).
pub const SESSION_EVENT: &str = "OnJsonApiEvent_lol-champ-select_v1_session";

const FIRST_RETRY: Duration = Duration::from_millis(500);
const LAST_RETRY: Duration = Duration::from_secs(10);

/// What the watcher tells its caller.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Notice {
    /// Connected (again): read the current state, it may have changed while disconnected.
    Connected,
    /// The champion-select session was created, updated or deleted.
    Changed,
    /// Not connected; retrying. The reason is for logs and the UI.
    Disconnected(String),
}

/// Runs until `notify` returns false: connects, subscribes, reports changes, and reconnects
/// with backoff (0.5 s doubling to 10 s, back to 0.5 s after a connection worked).
pub async fn watch(options: ConnectOptions, mut notify: impl FnMut(Notice) -> bool) {
    let mut retry = FIRST_RETRY;
    loop {
        let outcome = session(&options, &mut notify).await;
        let reason = match outcome {
            Ok(Ended::Stopped) => return,
            Ok(Ended::Closed) => {
                retry = FIRST_RETRY;
                "the League client closed the connection".to_owned()
            }
            Err(reason) => reason,
        };
        if !notify(Notice::Disconnected(reason)) {
            return;
        }
        tokio::time::sleep(retry).await;
        retry = (retry * 2).min(LAST_RETRY);
    }
}

enum Ended {
    Stopped,
    Closed,
}

async fn session(
    options: &ConnectOptions,
    notify: &mut impl FnMut(Notice) -> bool,
) -> Result<Ended, String> {
    // The lockfile is read on every attempt: a restarted client has a new port and password.
    let path = match &options.lockfile {
        Some(path) => path.clone(),
        None => discover().map_err(|e| e.to_string())?,
    };
    let lock = Lockfile::read(&path).map_err(|e| e.to_string())?;
    let config = client_config(&options.trust().map_err(|e| e.to_string())?)?;
    let tcp = TcpStream::connect(("127.0.0.1", lock.port))
        .await
        .map_err(|e| e.to_string())?;
    let name = ServerName::IpAddress(IpAddr::from(std::net::Ipv4Addr::LOCALHOST));
    let tls = TlsConnector::from(Arc::clone(&config))
        .connect(name, tcp)
        .await
        .map_err(|e| {
            e.into_inner()
                .map_or_else(|| "TLS failed".to_owned(), |inner| inner.to_string())
        })?;
    let mut request = format!("wss://127.0.0.1:{}/", lock.port)
        .into_client_request()
        .map_err(|e| e.to_string())?;
    let token = base64::Engine::encode(
        &base64::engine::general_purpose::STANDARD,
        format!("riot:{}", lock.password),
    );
    let auth = HeaderValue::from_str(&format!("Basic {token}")).map_err(|e| e.to_string())?;
    request.headers_mut().insert("Authorization", auth);
    let (mut socket, _) = client_async(request, tls)
        .await
        .map_err(|e| e.to_string())?;
    socket
        .send(Message::text(format!("[5,\"{SESSION_EVENT}\"]")))
        .await
        .map_err(|e| e.to_string())?;
    if !notify(Notice::Connected) {
        return Ok(Ended::Stopped);
    }
    while let Some(message) = socket.next().await {
        match message.map_err(|e| e.to_string())? {
            Message::Text(text) if is_session_event(&text) => {
                if !notify(Notice::Changed) {
                    return Ok(Ended::Stopped);
                }
            }
            Message::Close(_) => return Ok(Ended::Closed),
            _ => {}
        }
    }
    Ok(Ended::Closed)
}

/// `[8, "<topic>", {...}]`: an event message for the session topic.
pub fn is_session_event(text: &str) -> bool {
    match serde_json::from_str::<serde_json::Value>(text) {
        Ok(serde_json::Value::Array(parts)) => {
            parts.first().and_then(serde_json::Value::as_i64) == Some(8)
                && parts.get(1).and_then(serde_json::Value::as_str) == Some(SESSION_EVENT)
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognises_session_events_only() {
        let event = format!("[8,\"{SESSION_EVENT}\",{{\"eventType\":\"Update\",\"data\":{{}}}}]");
        assert!(is_session_event(&event));
        assert!(!is_session_event(
            "[8,\"OnJsonApiEvent_lol-lobby_v2_lobby\",{}]"
        ));
        assert!(!is_session_event(&format!("[5,\"{SESSION_EVENT}\"]")));
        assert!(!is_session_event("not json"));
    }

    #[tokio::test]
    async fn reports_why_it_cant_connect_and_stops_when_told() {
        let options = ConnectOptions {
            lockfile: Some("/nonexistent/lockfile".into()),
            ..Default::default()
        };
        let mut seen = vec![];
        watch(options, |notice| {
            seen.push(notice);
            false
        })
        .await;
        assert!(
            matches!(seen.as_slice(), [Notice::Disconnected(reason)] if reason.contains("lockfile"))
        );
    }
}
