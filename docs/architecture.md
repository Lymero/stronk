# Architecture

## 1. System overview

```
                 ┌──────────────────── pipeline (batch) ───────────────────┐
  Riot API ────► │ crawl → extract → winprob → wpa → publish (signed JSON) │ ──► data store
                 └─────────────────────────────────────────────────────────┘     (local dir → CDN)
                                                                                        │
  League client (LCU, local) ◄────► app core (Rust) ◄──── typed commands ────► app UI (Svelte)
```

Two independent systems joined by one **versioned, signed data contract**:

- **Pipeline:** offline batch job that turns matches into per-champion build statistics. Its speed does not affect users.
- **Desktop app:** detects champion select, reads cached statistics and imports runes, item sets and spells. Its speed is what users feel.

There is no live backend. Published data is static files, served first from a local directory and later from a CDN.

## 2. Architectural style

### Ports and adapters

Every component uses the same layers:

| Layer | Contains | May depend on |
|---|---|---|
| **domain** | Pure types and logic (game state, WPA math, build selection). No I/O. | nothing |
| **application** | Use cases, exposed as commands, working through ports (interfaces) | domain |
| **adapters** | Port implementations: Riot API, storage, LCU, data source, Tauri | application, domain |
| **entry points** | CLI, Tauri shell, UI | everything above |

Dependencies point inward only, enforced by tooling (section 8). Every external system has a fake adapter, so every feature runs offline.

### Everything is a command

Each use case is a **command** registered in one place, with:

- an id (`build.get`, `build.import`, `champselect.state`, `data.refresh`, `pipeline.wpa`…);
- a typed parameter schema and a typed result;
- a typed error: commands return errors, never crash.

Entry points only dispatch commands by id: the Tauri shell, the dev CLIs (`stronk-core run <id> --params '{…}'`, `stronk-pipeline run <stage>`) and, later, an MCP server. Anything the UI can do, a script or an agent can do from the terminal.

## 3. Repository layout

```
stronk/
├── README.md · AGENTS.md · CLAUDE.md · NOTES.md · ATTRIBUTION.md
├── justfile · .mise.toml · .env.example · corpus.lock
├── pyproject.toml · uv.lock     # uv workspace: pipeline, tools/synth, generated Python
├── package.json · pnpm-workspace.yaml
├── contracts/
│   ├── schemas/                 # JSON Schema: source of truth for published data
│   ├── examples/                # one valid file per schema
│   ├── codegen.py               # `just gen`, `--check` for drift
│   ├── tests/                   # schema, example and model agreement
│   └── generated/               # committed codegen output (Python, TS, Rust)
├── pipeline/                    # Python package `stronk_pipeline`
│   ├── src/stronk_pipeline/
│   │   ├── domain/              # game state, features, WPA math (pure)
│   │   ├── application/         # stages as commands: crawl, extract, winprob, wpa, publish
│   │   ├── ports.py             # MatchSource, MatchStore, DecisionStore, FrameStore, Estimator; later Publisher, Signer
│   │   ├── adapters/            # riot/ (client, rate limits, payloads), recording, match_store, parquet_store; later local_publisher, r2_publisher
│   │   ├── config.py            # typed settings (pydantic-settings)
│   │   └── cli.py               # Typer entry point
│   └── tests/
├── app/
│   ├── core/                    # Cargo workspace
│   │   ├── crates/domain/       # build selection, rune/item mapping (pure)
│   │   ├── crates/service/      # command registry and use cases
│   │   ├── crates/lcu/          # LeagueClient adapter
│   │   ├── crates/data/         # BuildSource adapters: directory, HTTP; cache; signature check
│   │   ├── crates/cli/          # `stronk-core` dev CLI
│   │   └── src-tauri/           # Tauri shell
│   └── ui/                      # Svelte 5 + TypeScript
│       └── src/lib/
│           ├── backend/         # Backend port: TauriBackend, HttpBackend, MockBackend
│           ├── state/           # single serializable app state
│           ├── features/        # champ-select, build-view, settings
│           └── ui/              # design system: components and tokens
├── tools/
│   ├── lcu_mock/                # fake League client replaying recorded sessions
│   ├── synth/                   # synthetic games with planted effects; `stronk-synth eval`
│   ├── corpus/                  # `just corpus`: fetch, verify and pack the test corpus
│   └── checks/                  # floors, budgets and commit-message checks
├── perf/
│   └── budgets.toml             # performance budgets
├── metrics/
│   └── floors.toml              # quality floors (only go up)
├── fixtures/                    # small committed samples (scrubbed Riot recordings)
└── docs/
```

## 4. Pipeline

### Stages

Each stage is a command with explicit inputs and outputs, reading and writing Parquet through the `Store` port, rerunnable on its own.

| Stage | Input | Output |
|---|---|---|
| `crawl` | `MatchSource` (Riot API or a recording) | compact validated games and Data Dragon data per patch, in a crawl directory |
| `extract` | raw data | `frames` (per minute, per team and player, with situation features), `decisions` (decision points with game state, options and the chosen one) |
| `winprob` | frames | win probability model (best of logistic and LightGBM on validation matches), calibration report on test matches |
| `wpa` | decisions + model | propensity model, estimates per champion, role, slot and option, with interval, sample size and flags |
| `publish` | estimates + crawls | signed JSON per patch, region, elo, champion and role, through the `Publisher` port: keystone estimates carry the page most played with them; spells and skill order stay empty until they are estimated |

### Publishing

| Adapter | Use |
|---|---|
| `LocalPublisher` | Writes to `dist/data/` with the exact layout of the future CDN. Default. |
| `R2Publisher` | Uploads to Cloudflare R2. Added at public release. |

Moving to the CDN means switching the publisher and the app's data URL; no other code changes.

### Runs and reproducibility

- Each run writes to `runs/<run-id>/` with a `manifest.json`: input hashes, code version, parameters.
- Each stage writes `report.json` (metrics, sample sizes, warnings) and a small HTML report.
- `metrics.json` holds the tracked quality metrics, checked against `metrics/floors.toml`.
- `--fixture` runs the whole pipeline on the committed sample in under a minute.

### Crawler

- Async HTTP (httpx) behind the `MatchSource` port.
- Seeds players from league endpoints (Challenger to Diamond), walks match histories, fetches match and timeline. The timeline is fetched only for games that pass the header checks (queue, map, remake, patch).
- Rate limiter driven by Riot's rate-limit headers; Retry-After on 429, exponential backoff on 5xx and transport errors.
- Riot payloads become validated models at the boundary; nothing raw passes inward.
- Games are stored compact and pseudonymous, one file per game, and raw JSON is discarded (ADR-027). Reruns resume.
- Recording and playback are httpx transports: `crawl.run` with `record` saves scrubbed responses, with `replay` plays them back with no key or network.
- Player skill comes from the crawl itself (prior games only), not from extra rank or mastery calls.

```
runs/crawl/<platform>/
├── matches/<match_id>.json.gz   # domain Match: participants, frames, item/kill/objective events
├── static/<patch>.json.gz       # Data Dragon champions and items
├── skipped.jsonl                # rejected games and why: never refetched
└── .salt                        # pseudonym key: never packed, published or committed
```

### WPA

Defined in [wpa-method.md](wpa-method.md). Each estimator version (v1 adjusted, v2 doubly robust…) implements the same `Estimator` port, so versions can run side by side and be compared on the same data. v1 has two implementations, `reference` (plain, slow, obviously correct) and `fast` (Polars), which must agree on fixtures.

## 5. Desktop app

### Rust core

| Crate | Role |
|---|---|
| `domain` | Pure logic: choose a build for champion, role and matchup; map it to rune pages, item sets and spells |
| `service` | Command registry and use cases, over traits `LeagueClient`, `BuildSource`, `Settings`, `Clock` |
| `lcu` | Lockfile discovery, HTTPS trusting Riot's client CA through an explicit verifier, a pinned certificate as fallback (ADR-042), websocket events decoded into typed models |
| `data` | `DirectorySource` and `HttpSource` (ETag), local cache, offline fallback, signature verification |
| `cli` | `stronk-core` dev CLI over the command registry |
| `src-tauri` | Thin shell: exposes commands and events, window, tray, hotkeys, auto-start |

Patterns:
- `thiserror` in libraries; one app error type mapped to user-facing messages.
- `tracing` with a rotating local log; no telemetry.
- `tokio`; one task owns the LCU connection and reconnects with backoff.
- Typed IPC: every command's params, result and error types generated for the UI from the registry (`stronk-core schema`, JSON Schema via `schemars`, then `json2ts`, ADR-053); the shell keeps one IPC command, `run`.
- Clippy denies `unwrap`, `expect`, `panic!`, `todo!` and unchecked indexing outside tests. Unfinished features return an "unsupported" error.

### Data source

Chosen by one setting:

| Setting | Source |
|---|---|
| `data.source = "dir:./dist/data"` | Local directory (development) |
| `data.source = "http://127.0.0.1:8787"` | `just serve-data`: local static server with ETag, mimics the CDN |
| `data.source = "https://…"` | CDN (public release) |

Signatures are verified for every source, including local ones, so the code path never changes. For now the setting is `STRONK_DATA_DIR` (a directory, `dir:…` or a URL). Over HTTP the app reads `/index.json` for the patches, revalidates the newest patch's manifest with its ETag at most every five minutes, and caches verified manifests and builds on disk (`STRONK_CACHE_DIR`, else the platform's cache folder); a cached build that still matches the manifest's hash needs no request, and when the source can't be reached the cache serves (ADR-046).

### Lock-in path

Data for the likely champions is loaded when champion select starts and on hover, so lock-in is always a cache hit and never waits on the network. Each step (lookup, rune write, item set write, spell write) is timed separately and logged locally.

`just bench` measures this path (`lockin_import_cache_hit`): the real core in one long-lived process (`stronk-core serve`, one context as in the app) against lcu-mock and the signed fixture data, 200 replays of a hover then lock-in, timed from lock-in to the import confirmed. The budget (p50 100 ms, p95 300 ms) is enforced.

### UI

- Svelte 5 (runes), TypeScript strict, Vite.
- **One serializable app state** in `lib/state`: a plain typed object that tests, mocks and debugging tools can read.
- Features in `lib/features`; design system with tokens for color, spacing and type (light and dark) in `lib/ui`. No hard-coded colors or sizes.
- The UI only talks to the `Backend` port:

| Backend | Use |
|---|---|
| `TauriBackend` | Desktop app, through `run` with the generated command types |
| `MockBackend` | Scripted scenarios in a plain browser |
| `CoreBackend` | The real core in a plain browser, through a local test bridge (Playwright, ADR-048) |
| `HttpBackend` | Read-only web build viewer, reading the published data directly |

### League client mock

`tools/lcu_mock` impersonates the League client: writes a fake lockfile, serves the endpoints the core uses, replays recorded champion-select sessions, adds configurable latency and records what the app imported. The real Rust core is tested end to end without the game.

## 6. Data contract

- JSON Schema in `contracts/schemas/` is the single source of truth.
- Codegen for all three languages, committed to `contracts/generated/`: pydantic (Python), json-schema-to-typescript (TS), typify (Rust). CI regenerates and fails on any diff.
- Every file carries `schemaVersion`. New fields are optional; a breaking change bumps the major version and both versions are published until old apps age out.
- **Signed.** `publish` writes a `manifest.json` per patch listing every file with its sha256, signed with ed25519 (minisign format). The app ships the public key, verifies the manifest, then each file's hash. Invalid data is rejected and the last valid cache is used.

Shape of one file (`/{patch}/{region}/{elo}/{champion}/{role}.json`):

```json
{
  "schemaVersion": 1,
  "patch": "26.20",
  "champion": "Viego",
  "role": "JUNGLE",
  "games": 18432,
  "runes":  [{ "page": {}, "wpa": 0.012, "ci": [0.004, 0.020], "n": 9120, "flags": [] }],
  "items":  [{ "slot": 1, "item": 6672, "wpa": 0.008, "ci": [0.001, 0.015], "n": 5400, "flags": ["low_comparison_group"] }],
  "spells": [],
  "skillOrder": []
}
```

## 7. Budgets and floors

### Performance budgets (`perf/budgets.toml`)

| Scenario | Budget | Measured on |
|---|---|---|
| Lock-in → import confirmed (cache hit) | P50 ≤ 100 ms, **P95 ≤ 300 ms** | `lcu-mock`, 200 replays |
| Cold data fetch | P95 ≤ 1 s | `serve-data` |
| App cold start to ready | P95 ≤ 1 s | release build |
| Pipeline on fixtures | ≤ 60 s total | CI |

- Lock-in is measured from receiving the LCU lock-in event to the client confirming all writes.
- P99 and max are reported, not enforced (too noisy on shared runners).
- Each budget has `enforce = false` until first met, then `true`. CI fails on enforced budgets. If runners prove noisy, compare against a stored baseline with a margin instead.
- `just bench` runs the scenarios; real-client timings come from the app's local log.

### Quality floors (`metrics/floors.toml`)

- Win probability model: calibration error and log loss, per corpus (`winprob.ci.*` in `just check`, `winprob.full.*` in the weekly full-corpus job; ADR-038).
- Synthetic truth: recovery error of planted effects, with and without hidden confounders.
- Patch backtests: share of item changes whose estimate moved in the right direction.
- Coverage: champion and role pairs with enough data for a confident estimate.

A floor can be raised, never lowered without an entry in `docs/decisions.md`. CI fails when a metric falls below its floor.

## 8. Quality and tooling

### Testing

| Level | Tools | Covers |
|---|---|---|
| Domain unit | pytest, cargo test, Vitest | pure logic |
| Statistical truth | pytest + `tools/synth` | planted effects recovered; "bought while ahead" gets no credit; meta-locked choices flagged |
| Oracle agreement | pytest | `reference` and `fast` WPA agree |
| Calibration | pytest | win probability model above its floors |
| Command fuzzing | proptest, Hypothesis | every registered command, given adversarial params and broken LCU states, returns an error and never crashes |
| Parser fuzzing | proptest, Hypothesis | LCU and Riot parsers on malformed input |
| Adapter | pytest, cargo test | against recorded responses, `lcu-mock`, `serve-data` |
| Contract | codegen check, schema validation, signature tests | generated types current; published data valid and verifiable; tampered data rejected |
| Component | Vitest + Testing Library | UI against `MockBackend` |
| End to end | Playwright + `lcu-mock` (`just e2e`) | the UI in Chromium against `MockBackend` scenarios, and against the real core through `CoreBackend` and `tools/lcu_mock/core_bridge.py`: a replayed lobby leads to the correct import, auto-import writes once, restore puts the sets back; screenshots in `runs/e2e/screenshots/` (ADR-048) |
| Performance | `just bench` | budgets in `perf/budgets.toml` |

### Test corpus

- Larger real-data samples live outside git (a GitHub release or an R2 bucket), listed in `corpus.lock` with URL and sha256.
- `just corpus [name...]` fetches and verifies them into `corpus/` (gitignored).
- Two entries (ADR-038): `crawl-ci-16.20`, 3500 games stratified by region, used by `just check` and every CI run; `crawl-all-16.20`, every crawled game (22,954), used by real runs and the weekly `full-corpus` workflow (`just floors-full`, also on demand).
- A floor's `suite` says which run measures it; each corpus's floors come from its own baseline.
- Corpus tests are opt-in locally and always run in CI on the CI corpus, with the download cached by hash.

### Static checks

| Language | Format and lint | Types | Architecture rules |
|---|---|---|---|
| Python | ruff | pyright (strict) | import-linter: `domain` imports no adapters or I/O libraries |
| Rust | rustfmt, clippy (deny lints) | compiler | crate graph: `domain` depends on no workspace crate |
| TypeScript | Biome | tsc (strict) | dependency-cruiser: features never import Tauri directly |

### Tooling

- mise (toolchains), just (tasks), uv, pnpm, cargo.
- pre-commit hooks, Conventional Commits, generated changelog.
- CI (GitHub Actions) runs `just check`, builds and lints the Tauri shell (`app-shell`) and builds and tests the app on Windows (`windows`); Renovate keeps dependencies current.
- The pipeline runs on Linux or WSL; app work against the real League client happens in a native Windows clone, where `just` runs the app recipes in PowerShell (ADR-045, [windows.md](windows.md)).

## 9. Operations

- **Pipeline:** run manually at first, publishing to `dist/data/`; later scheduled on a VPS (systemd timer) and publishing to R2.
- **Signing key:** private key outside the repo (local keychain, later a CI secret); public key compiled into the app.
- **App releases:** Tauri bundler, signed installers, built-in updater.
- **Data updates:** independent of app releases; the app checks on start and when champion select begins.

See [security.md](security.md) for the threat model.
