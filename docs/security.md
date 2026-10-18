# Security

The app runs on players' machines and writes into their League client. These are the rules that keep that safe.

## Assets to protect

| Asset | Risk |
|---|---|
| The user's League client session | Malicious data or code could change their client settings |
| The LCU password (from the lockfile) | Grants local control of the client if leaked |
| Published build data | Tampered data would reach every user |
| The data signing key and the Riot API key | Compromise enables the above or gets the key revoked |

## Rules

### Network

- The app talks to two places only: the local League client (`127.0.0.1`) and the configured data source.
- LCU connections trust Riot's League client CA only, never the system store and never "no verification" (see "League client" below).
- Tauri 2 capabilities grant only the permissions the app uses; strict content security policy; no remote code or scripts loaded.

### Input

- All outside input (LCU events and responses, Riot payloads, published data) is validated into typed models at the boundary.
- Invalid input produces an error and a fallback, never a crash.
- Parsers and every command are fuzzed (see architecture, section 8).

### Data integrity

- Published data is signed (ed25519 manifest with per-file sha256).
- The app verifies signatures for every source, including local ones; invalid data is rejected and the last valid cache is kept.
- The private signing key never enters the repository. `just keygen` writes it to `~/.config/stronk/` with owner-only permissions and refuses to overwrite one. No private key is committed, not even a test one (`*.key` is ignored): the contract example is signed with a throwaway test key whose public half is `contracts/tests/keys/test-only.pub`, and no app ever trusts it.

### Secrets and privacy

- Never log the LCU password, auth headers or API keys.
- `RIOT_API_KEY` lives in `.env` or CI secrets only; the app needs no Riot key. It travels in a request header, never in URLs, so it never reaches recordings or error messages.
- Crawled players are pseudonymous (keyed hash; the key stays in the crawl directory). Recordings meant for commits drop Riot ids and names and pseudonymise PUUIDs (ADR-027).
- No telemetry. Logs stay on the user's machine.

## Reporting

Report vulnerabilities privately to the maintainer (contact in the README). Do not open a public issue.

## League client

The client serves HTTPS on `127.0.0.1` with a certificate from Riot's own CA.

- **Root:** `app/core/crates/lcu/certs/riotgames.pem`, downloaded 2026-10-18 from Riot's official source for the Game Client API, https://static.developer.riotgames.com/docs/lol/riotgames.pem. sha256 of the file: `da884275737f024b33c93ae5d28bdb002768a3cb73752ab40254a32218193521`; certificate sha256 fingerprint `CA:8C:9D:32:5B:4C:DC:46:4C:6C:94:A5:85:C8:5E:91:EC:23:D4:0B:A5:BF:3A:E2:82:2B:95:1A:4A:50:4E:A3`; subject "LoL Game Engineering Certificate Authority"; valid 2013-12-04 to 2043-11-27. It is embedded in the binary; changing it means a new download, new hashes here and in `ATTRIBUTION.md`.
- **Check:** that root is an X.509 v1 certificate signed with SHA-1, which standard verifiers reject, so `stronk_lcu::tls` checks explicitly: the client's certificate must be signed directly by the root (legacy SHA-1/RSA accepted for that signature only), within its validity dates. The name isn't checked because connections only go to the `127.0.0.1` literal. The TLS handshake itself uses rustls' normal algorithms.
- **Fallback:** if the real client's certificate doesn't validate against the root, `--lcu-pin` / `STRONK_LCU_PIN` accepts exactly one certificate by sha256. Every rejection names the certificate presented (subject, issuer, signature algorithm, sha256), so the pin comes from an actual failure, not a guess. Status: not yet tried against a real client (docs/windows.md).
- **Tests** use `tools/lcu_mock`, which writes its own root and trusts nothing else.
- **Recordings** (`stronk-core record-champselect`) keep an allowlist of fields, are checked for identifiers before saving, and committed sessions are checked again by `tools/lcu_mock/tests/test_sessions_scrubbed.py`.
