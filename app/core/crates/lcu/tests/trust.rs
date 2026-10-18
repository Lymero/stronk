//! The LCU verifier against a real TLS server: what it accepts, what it rejects, and that its
//! exception (no name check, the client's CA only) stays inside the LCU client.

// Tests may panic: that is how they fail.
#![allow(clippy::unwrap_used, clippy::indexing_slicing)]

use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::sync::Arc;
use std::thread;

use rcgen::{BasicConstraints, CertificateParams, DnType, IsCa, Issuer, KeyPair, date_time_ymd};
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use rustls::{ClientConfig, RootCertStore, ServerConfig, ServerConnection, StreamOwned};
use sha2::{Digest, Sha256};
use stronk_lcu::{LcuClient, Lockfile, Trust};

struct Root {
    pem: String,
    der: CertificateDer<'static>,
    issuer: Issuer<'static, KeyPair>,
}

fn root(name: &str) -> Root {
    let mut params = CertificateParams::new(Vec::<String>::new()).unwrap();
    params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    params.distinguished_name.push(DnType::CommonName, name);
    let key = KeyPair::generate().unwrap();
    let cert = params.self_signed(&key).unwrap();
    Root {
        pem: cert.pem(),
        der: cert.der().clone(),
        issuer: Issuer::new(params, key),
    }
}

struct Leaf {
    der: CertificateDer<'static>,
    key: PrivateKeyDer<'static>,
}

fn leaf(root: &Root, names: &[&str], expired: bool) -> Leaf {
    let names: Vec<String> = names.iter().map(|n| (*n).to_owned()).collect();
    let mut params = CertificateParams::new(names).unwrap();
    if expired {
        params.not_before = date_time_ymd(2000, 1, 1);
        params.not_after = date_time_ymd(2001, 1, 1);
    }
    let key = KeyPair::generate().unwrap();
    let cert = params.signed_by(&key, &root.issuer).unwrap();
    Leaf {
        der: cert.der().clone(),
        key: PrivatePkcs8KeyDer::from(key.serialize_der()).into(),
    }
}

/// An HTTPS server on 127.0.0.1 answering every request with `{}`; returns its port.
fn serve(leaf: &Leaf) -> u16 {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let config = Arc::new(
        ServerConfig::builder_with_provider(provider)
            .with_safe_default_protocol_versions()
            .unwrap()
            .with_no_client_auth()
            .with_single_cert(vec![leaf.der.clone()], leaf.key.clone_key())
            .unwrap(),
    );
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            let Ok(connection) = ServerConnection::new(Arc::clone(&config)) else {
                continue;
            };
            let mut tls = StreamOwned::new(connection, stream);
            let mut line = String::new();
            // Read the request head; a rejected handshake ends here with an error.
            {
                let mut reader = BufReader::new(&mut tls);
                while reader.read_line(&mut line).is_ok_and(|n| n > 2) {
                    line.clear();
                }
            }
            let _ = tls.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}",
            );
            tls.conn.send_close_notify();
            let _ = tls.flush();
        }
    });
    port
}

fn lcu(port: u16, trust: &Trust) -> LcuClient {
    let lock = Lockfile::parse(&format!("LeagueClient:1:{port}:pw:https")).unwrap();
    LcuClient::new(&lock, trust).unwrap()
}

fn trusting(root: &Root) -> Trust {
    Trust::Root(root.pem.clone().into_bytes())
}

/// A client with standard verification (webpki: chain, dates, name), as every other
/// connection the app makes is built (the data source over HTTPS, for one).
fn standard_client(roots: &[&Root]) -> reqwest::blocking::Client {
    let mut store = RootCertStore::empty();
    for root in roots {
        store.add(root.der.clone()).unwrap();
    }
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let config = ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()
        .unwrap()
        .with_root_certificates(store)
        .with_no_client_auth();
    reqwest::blocking::Client::builder()
        .tls_backend_preconfigured(config)
        .no_proxy()
        .build()
        .unwrap()
}

#[test]
fn accepts_a_certificate_from_the_trusted_root() {
    let ca = root("client CA");
    let port = serve(&leaf(&ca, &["127.0.0.1"], false));
    assert_eq!(
        lcu(port, &trusting(&ca)).get_json("/x").unwrap(),
        Some(serde_json::json!({}))
    );
}

#[test]
fn rejects_a_certificate_from_another_root_and_names_it() {
    let (ca, other) = (root("client CA"), root("someone else"));
    let port = serve(&leaf(&other, &["127.0.0.1"], false));
    let error = lcu(port, &trusting(&ca))
        .get_json("/x")
        .unwrap_err()
        .to_string();
    assert!(
        error.contains("certificate rejected: not issued by the trusted root"),
        "{error}"
    );
    assert!(error.contains("CN=someone else"), "{error}");
    assert!(error.contains("sha256"), "{error}");
}

#[test]
fn rejects_an_expired_certificate_from_the_trusted_root() {
    let ca = root("client CA");
    let port = serve(&leaf(&ca, &["127.0.0.1"], true));
    let error = lcu(port, &trusting(&ca))
        .get_json("/x")
        .unwrap_err()
        .to_string();
    assert!(error.contains("outside its validity dates"), "{error}");
}

#[test]
fn a_pin_accepts_exactly_its_certificate() {
    let ca = root("client CA");
    let presented = leaf(&ca, &["127.0.0.1"], false);
    let pin: String = Sha256::digest(&presented.der)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let port = serve(&presented);
    assert!(lcu(port, &Trust::pin(&pin).unwrap()).get_json("/x").is_ok());
    let error = lcu(port, &Trust::Pin([7; 32]))
        .get_json("/x")
        .unwrap_err()
        .to_string();
    assert!(error.contains("not the pinned certificate"), "{error}");
}

/// The verifier's exception (no name check) applies to the LCU client only: with an LCU client
/// alive in the same process, a standard client still rejects a host whose certificate chains
/// to a root it trusts but names another host, and one with default trust rejects it outright.
#[test]
fn the_lcu_exception_does_not_reach_other_connections() {
    let ca = root("client CA");
    let port = serve(&leaf(&ca, &["not-the-lcu.example"], false));
    let lcu_client = lcu(port, &trusting(&ca));
    assert!(
        lcu_client.get_json("/x").is_ok(),
        "the LCU client skips the name check by design"
    );

    let url = format!("https://127.0.0.1:{port}/x");
    let standard = standard_client(&[&ca]).get(&url).send().unwrap_err();
    let text = format!("{standard:?}");
    assert!(text.contains("NotValidForName"), "{text}");
    assert!(standard_client(&[]).get(&url).send().is_err());
    assert!(lcu_client.get_json("/x").is_ok()); // and the LCU client is unaffected
}

/// The champion-select watcher will use tokio-tungstenite: the same verifier plugs into it.
#[test]
fn the_verifier_plugs_into_the_websocket_connector() {
    let config: Arc<ClientConfig> = stronk_lcu::tls::client_config(&Trust::riot()).unwrap();
    let connector = tokio_tungstenite::Connector::Rustls(config);
    assert!(matches!(connector, tokio_tungstenite::Connector::Rustls(_)));
}
