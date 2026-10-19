# Contracts

The published data contract shared by the pipeline (Python) and the app (Rust, TypeScript). JSON Schema in `schemas/` is the source of truth; everything in `generated/` comes from it.

| Path | What |
|---|---|
| `schemas/build.v1.schema.json` | One champion and role: `/{patch}/{region}/{elo}/{champion}/{role}.json` |
| `schemas/manifest.v1.schema.json` | Every file of one patch with its hash: `/{patch}/manifest.json` |
| `schemas/index.v1.schema.json` | The published patches, oldest first: `/index.json` (unsigned, see below) |
| `examples/` | One valid file per schema, checked by the contract tests |
| `generated/python` | `stronk-contracts` pydantic models (datamodel-code-generator) |
| `generated/ts` | `@stronk/contracts` types (json-schema-to-typescript) |
| `generated/rust` | `stronk-contracts` crate (typify) |
| `codegen.py` | `just gen` writes `generated/`; `just check` fails if it is stale |
| `tests/` | Python contract tests; Rust ones live in `generated/rust/tests/` |

## Changing the contract

1. Edit the schema. New fields are optional (not in `required`).
2. A breaking change adds a new file (`build.v2.schema.json`) with `schemaVersion` 2. Both versions are published until old apps age out.
3. Add or update the example, run `just gen`, commit schema, example and generated code together.

`schemaVersion` is written as `"enum": [1]`, not `"const": 1`, because typify only validates the enum form.

### Known limits of the generated types

| Language | Enforces | Does not enforce |
|---|---|---|
| Python | everything the schema says | |
| TypeScript | shape and enums (types only, no runtime checks) | patterns, bounds |
| Rust | shape, enums, patterns, array lengths, `schemaVersion` | numeric `maximum`, `minimum` above 0 (for example item `slot` ≤ 6) |

The app's `data` crate checks the numeric bounds it relies on after parsing. Signed data comes from our own pipeline, which validates with the Python models before publishing, so these checks are defence in depth.

## Signed manifest

Each patch directory has two files next to the data, and the root lists the patches:

```
/index.json                     # index.v1: published patches; unsigned
/{patch}/manifest.json          # manifest.v1: every file with sha256 and size
/{patch}/manifest.json.minisig  # minisign signature of manifest.json's exact bytes
/{patch}/{region}/{elo}/{champion}/{role}.json
```

### Signature

- Format: [minisign](https://jedisct1.github.io/minisign/), Ed25519 with BLAKE2b-512 prehashing (algorithm `ED`).
- Signed bytes: `manifest.json` exactly as published (UTF-8, no re-serialisation before verifying).
- Trusted comment: `stronk manifest v1 patch=<patch> runId=<runId>`. The verifier checks it matches the manifest.
- `keyId` in the manifest equals the key id in the signature (upper-case hex of minisign's 8-byte id).

### Verification (app, every source including local directories)

1. Fetch `manifest.json` and `manifest.json.minisig`.
2. Find the public key whose id matches the signature among the keys compiled into the app; unknown key → reject.
3. Verify the signature and the trusted comment, then parse the manifest and check `schemaVersion` is supported.
4. For every data file read: its path is listed, its size matches `bytes` and its sha256 matches `sha256`; only then parse it.
5. Any failure rejects the whole patch and keeps the last valid cache.

### The index

`/index.json` is how a client over HTTP finds the newest patch (a directory can just be listed). It isn't signed: it only says where to look, and each patch it names is verified as above. A client never trusts it to go backwards: it keeps the newest patch it has verified even if the index stops listing it, and never replaces a cached manifest with an older run of the same patch (`generatedAt`). The publisher rewrites it after every patch it publishes.

### Keys

- The private key lives outside the repository (local keychain, later a CI secret). See `docs/security.md`.
- The app ships a list of trusted public keys so a key can be rotated: publish with the new key once every supported app version trusts it.
