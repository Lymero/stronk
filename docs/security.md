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
- LCU connections pin the client's certificate; no general TLS bypass.
- Tauri 2 capabilities grant only the permissions the app uses; strict content security policy; no remote code or scripts loaded.

### Input

- All outside input (LCU events and responses, Riot payloads, published data) is validated into typed models at the boundary.
- Invalid input produces an error and a fallback, never a crash.
- Parsers and every command are fuzzed (see architecture, section 8).

### Data integrity

- Published data is signed (ed25519 manifest with per-file sha256).
- The app verifies signatures for every source, including local ones; invalid data is rejected and the last valid cache is kept.
- The private signing key never enters the repository. `just keygen` writes it to `~/.config/stronk/` with owner-only permissions and refuses to overwrite one. The only key in the repository, `contracts/tests/keys/test-only.key`, signs the contract example for cross-language tests; no app ever trusts it.

### Secrets and privacy

- Never log the LCU password, auth headers or API keys.
- `RIOT_API_KEY` lives in `.env` or CI secrets only; the app needs no Riot key. It travels in a request header, never in URLs, so it never reaches recordings or error messages.
- Crawled players are pseudonymous (keyed hash; the key stays in the crawl directory). Recordings meant for commits drop Riot ids and names and pseudonymise PUUIDs (ADR-027).
- No telemetry. Logs stay on the user's machine.

## Reporting

Report vulnerabilities privately to the maintainer (contact in the README). Do not open a public issue.
