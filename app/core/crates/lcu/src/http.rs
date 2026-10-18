//! Just enough HTTP/1.1 over rustls for the client's JSON GETs: one request per connection.

use std::io::{ErrorKind, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::sync::Arc;
use std::time::Duration;

use rustls::pki_types::{IpAddr, ServerName};
use rustls::{ClientConfig, ClientConnection, StreamOwned};

const TIMEOUT: Duration = Duration::from_secs(3);
const MAX_RESPONSE: usize = 32 * 1024 * 1024;

/// GET `path` on 127.0.0.1:`port`; (status, body).
pub fn get(
    config: &Arc<ClientConfig>,
    port: u16,
    path: &str,
    authorization: &str,
) -> Result<(u16, Vec<u8>), String> {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let tcp = TcpStream::connect_timeout(&address, TIMEOUT).map_err(|e| e.to_string())?;
    tcp.set_read_timeout(Some(TIMEOUT))
        .map_err(|e| e.to_string())?;
    tcp.set_write_timeout(Some(TIMEOUT))
        .map_err(|e| e.to_string())?;
    let name = ServerName::IpAddress(IpAddr::from(Ipv4Addr::LOCALHOST));
    let connection = ClientConnection::new(Arc::clone(config), name).map_err(|e| e.to_string())?;
    let mut tls = StreamOwned::new(connection, tcp);
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: {authorization}\r\n\
         Accept: application/json\r\nConnection: close\r\n\r\n"
    );
    tls.write_all(request.as_bytes()).map_err(tls_error)?;
    let mut raw = Vec::new();
    let mut chunk = [0u8; 16 * 1024];
    loop {
        match tls.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                raw.extend(chunk.get(..n).unwrap_or_default());
                if raw.len() > MAX_RESPONSE {
                    return Err("response too large".into());
                }
            }
            // Servers often close without TLS close_notify; the framing below still checks
            // that the whole body arrived.
            Err(e) if e.kind() == ErrorKind::UnexpectedEof => break,
            Err(e) => return Err(tls_error(e)),
        }
    }
    parse_response(&raw)
}

fn tls_error(e: std::io::Error) -> String {
    // A rejected certificate surfaces here with its description (tls.rs).
    e.into_inner()
        .map_or_else(|| "connection failed".to_owned(), |inner| inner.to_string())
}

/// Status and body of a complete HTTP/1.x response (Content-Length, chunked, or to EOF).
pub fn parse_response(raw: &[u8]) -> Result<(u16, Vec<u8>), String> {
    let split = raw
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .ok_or("no end of headers")?;
    let head = std::str::from_utf8(raw.get(..split).unwrap_or_default())
        .map_err(|_| "headers are not text")?;
    let body = raw.get(split + 4..).unwrap_or_default();
    let mut lines = head.split("\r\n");
    let status = lines
        .next()
        .and_then(|line| line.split(' ').nth(1))
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or("no status line")?;
    let mut length = None;
    let mut chunked = false;
    for line in lines {
        let Some((name, value)) = line.split_once(':') else {
            continue;
        };
        let value = value.trim();
        if name.eq_ignore_ascii_case("content-length") {
            length = Some(value.parse::<usize>().map_err(|_| "bad Content-Length")?);
        } else if name.eq_ignore_ascii_case("transfer-encoding")
            && value.eq_ignore_ascii_case("chunked")
        {
            chunked = true;
        }
    }
    let body = match (chunked, length) {
        (true, _) => dechunk(body)?,
        (false, Some(n)) => body
            .get(..n)
            .ok_or("body shorter than Content-Length")?
            .to_vec(),
        (false, None) => body.to_vec(),
    };
    Ok((status, body))
}

fn dechunk(mut rest: &[u8]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    loop {
        let end = rest
            .windows(2)
            .position(|w| w == b"\r\n")
            .ok_or("truncated chunk size")?;
        let size_text = std::str::from_utf8(rest.get(..end).unwrap_or_default())
            .map_err(|_| "bad chunk size")?;
        let size = usize::from_str_radix(size_text.split(';').next().unwrap_or("").trim(), 16)
            .map_err(|_| "bad chunk size")?;
        rest = rest.get(end + 2..).unwrap_or_default();
        if size == 0 {
            return Ok(out);
        }
        out.extend(rest.get(..size).ok_or("truncated chunk")?);
        rest = rest.get(size + 2..).ok_or("truncated chunk")?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_content_length_bodies() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}extra";
        assert_eq!(parse_response(raw), Ok((200, b"{}".to_vec())));
    }

    #[test]
    fn reads_chunked_bodies() {
        let raw =
            b"HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\n\r\n2\r\n[1\r\n1\r\n]\r\n0\r\n\r\n";
        assert_eq!(parse_response(raw), Ok((200, b"[1]".to_vec())));
    }

    #[test]
    fn rejects_truncated_responses() {
        assert!(parse_response(b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\n{}").is_err());
        assert!(parse_response(b"HTTP/1.1 200 OK\r\n").is_err());
        assert!(
            parse_response(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n").is_err()
        );
    }

    #[test]
    fn reads_404s() {
        let raw = b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n";
        assert_eq!(parse_response(raw), Ok((404, vec![])));
    }
}
