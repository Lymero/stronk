//! Who the app believes is the League client (docs/security.md, "League client").
//!
//! The client serves HTTPS on 127.0.0.1 with a certificate from Riot's own CA, published at
//! https://static.developer.riotgames.com/docs/lol/riotgames.pem (`certs/riotgames.pem`). That
//! CA is an X.509 v1 certificate signed with SHA-1, which standard verifiers (webpki) reject,
//! so the check is explicit: the presented certificate must be signed directly by the trusted
//! root (legacy SHA-1/RSA accepted, as the CA uses it) and be within its validity dates. The
//! name isn't checked: connections only ever go to the 127.0.0.1 literal. As a fallback, a
//! [`Trust::Pin`] accepts exactly one certificate by sha256. Every rejection names the
//! certificate presented, so a failure against a real client says which way to go.

use std::sync::Arc;

use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::crypto::{CryptoProvider, verify_tls12_signature, verify_tls13_signature};
use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
use rustls::{ClientConfig, DigitallySignedStruct, SignatureScheme};
use sha2::{Digest, Sha256};
use x509_parser::prelude::{ASN1Time, FromDer, X509Certificate};

/// Riot's CA for the League client, sha256 recorded in docs/security.md and ATTRIBUTION.md.
pub const RIOT_ROOT_PEM: &[u8] = include_bytes!("../certs/riotgames.pem");

/// What the client's certificate must chain to, or be.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Trust {
    /// A root certificate (PEM) that signs the client's certificate directly.
    Root(Vec<u8>),
    /// The sha256 of the one certificate to accept.
    Pin([u8; 32]),
}

impl Trust {
    pub fn riot() -> Self {
        Self::Root(RIOT_ROOT_PEM.to_vec())
    }

    /// A pin written as 64 hex digits, `:` separators allowed (as `openssl x509 -fingerprint`).
    pub fn pin(hex: &str) -> Result<Self, String> {
        let digits: String = hex.chars().filter(|c| *c != ':').collect();
        let mut pin = [0u8; 32];
        if digits.len() != 64 {
            return Err(format!("a pin is 64 hex digits, got {}", digits.len()));
        }
        for (byte, pair) in pin.iter_mut().zip(digits.as_bytes().chunks(2)) {
            let text = std::str::from_utf8(pair).map_err(|e| e.to_string())?;
            *byte = u8::from_str_radix(text, 16).map_err(|e| format!("pin: {e}"))?;
        }
        Ok(Self::Pin(pin))
    }
}

/// A rustls configuration that accepts the client per `trust` and nothing else.
pub fn client_config(trust: &Trust) -> Result<Arc<ClientConfig>, String> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let anchor = match trust {
        Trust::Root(pem) => Anchor::Root(root_der(pem)?),
        Trust::Pin(pin) => Anchor::Pin(*pin),
    };
    let verifier = ClientVerifier {
        anchor,
        provider: Arc::clone(&provider),
    };
    let config = ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()
        .map_err(|e| e.to_string())?
        .dangerous() // a custom verifier, not "no verification": see the module docs
        .with_custom_certificate_verifier(Arc::new(verifier))
        .with_no_client_auth();
    Ok(Arc::new(config))
}

fn root_der(pem: &[u8]) -> Result<Vec<u8>, String> {
    let (_, parsed) = x509_parser::pem::parse_x509_pem(pem)
        .map_err(|e| format!("root certificate is not PEM: {e}"))?;
    X509Certificate::from_der(&parsed.contents)
        .map_err(|e| format!("root certificate is not X.509: {e}"))?;
    Ok(parsed.contents)
}

#[derive(Debug)]
enum Anchor {
    Root(Vec<u8>),
    Pin([u8; 32]),
}

#[derive(Debug)]
struct ClientVerifier {
    anchor: Anchor,
    provider: Arc<CryptoProvider>,
}

impl ClientVerifier {
    fn check(&self, leaf_der: &[u8], now: UnixTime) -> Result<(), String> {
        let (_, leaf) =
            X509Certificate::from_der(leaf_der).map_err(|e| format!("unparsable: {e}"))?;
        match &self.anchor {
            Anchor::Pin(pin) => {
                if Sha256::digest(leaf_der).as_slice() != pin {
                    return Err("not the pinned certificate".into());
                }
            }
            Anchor::Root(root_der) => {
                let (_, root) = X509Certificate::from_der(root_der).map_err(|e| e.to_string())?;
                if leaf.issuer() != root.subject() {
                    return Err("not issued by the trusted root".into());
                }
                leaf.verify_signature(Some(root.public_key()))
                    .map_err(|e| format!("signature doesn't verify against the root: {e}"))?;
            }
        }
        let seconds = i64::try_from(now.as_secs()).map_err(|e| e.to_string())?;
        let now = ASN1Time::from_timestamp(seconds).map_err(|e| e.to_string())?;
        if !leaf.validity().is_valid_at(now) {
            return Err("outside its validity dates".into());
        }
        Ok(())
    }
}

/// One line naming a certificate, for errors: what the client presented.
pub fn describe(der: &[u8]) -> String {
    let fingerprint: String = Sha256::digest(der)
        .iter()
        .map(|b| format!("{b:02X}"))
        .collect();
    match X509Certificate::from_der(der) {
        Ok((_, c)) => format!(
            "subject \"{}\", issuer \"{}\", signature {}, sha256 {fingerprint}",
            c.subject(),
            c.issuer(),
            c.signature_algorithm.algorithm,
        ),
        Err(_) => format!("unparsable certificate, sha256 {fingerprint}"),
    }
}

impl ServerCertVerifier for ClientVerifier {
    fn verify_server_cert(
        &self,
        end_entity: &CertificateDer<'_>,
        _intermediates: &[CertificateDer<'_>],
        _server_name: &ServerName<'_>,
        _ocsp_response: &[u8],
        now: UnixTime,
    ) -> Result<ServerCertVerified, rustls::Error> {
        self.check(end_entity, now)
            .map(|()| ServerCertVerified::assertion())
            .map_err(|why| {
                rustls::Error::General(format!(
                    "League client certificate rejected: {why} (presented: {})",
                    describe(end_entity)
                ))
            })
    }

    fn verify_tls12_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        verify_tls12_signature(
            message,
            cert,
            dss,
            &self.provider.signature_verification_algorithms,
        )
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        verify_tls13_signature(
            message,
            cert,
            dss,
            &self.provider.signature_verification_algorithms,
        )
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        self.provider
            .signature_verification_algorithms
            .supported_schemes()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_riot_root_parses() {
        assert!(root_der(RIOT_ROOT_PEM).is_ok());
        assert!(client_config(&Trust::riot()).is_ok());
    }

    #[test]
    fn pins_read_like_openssl_prints_them() {
        let colons = "CA:8C:9D:32:5B:4C:DC:46:4C:6C:94:A5:85:C8:5E:91:EC:23:D4:0B:A5:BF:3A:E2:82:2B:95:1A:4A:50:4E:A3";
        let Trust::Pin(pin) = Trust::pin(colons).unwrap() else {
            panic!("not a pin")
        };
        assert_eq!(pin[0], 0xCA);
        assert!(Trust::pin("abc").is_err());
    }

    #[test]
    fn describes_the_riot_root() {
        let der = root_der(RIOT_ROOT_PEM).unwrap();
        let text = describe(&der);
        assert!(
            text.contains("LoL Game Engineering Certificate Authority"),
            "{text}"
        );
        assert!(text.contains("sha256 CA8C9D32"), "{text}");
    }
}
