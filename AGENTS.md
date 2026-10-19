# AGENTS.md

Working guide for AI agents and contributors. Read this first.

## Orientation

| Read | For |
|---|---|
| [README.md](README.md) | What the project is |
| [docs/project-brief.md](docs/project-brief.md) | Goals, principles, product decisions |
| [docs/architecture.md](docs/architecture.md) | Components, layering, commands, contracts, budgets, testing |
| [docs/wpa-method.md](docs/wpa-method.md) | The statistics and the tests that protect them |
| [docs/security.md](docs/security.md) | Threat model and security rules |
| [docs/decisions.md](docs/decisions.md) | Why things are the way they are |
| [docs/roadmap.md](docs/roadmap.md) | Current focus and next tasks |
| [docs/gaps.md](docs/gaps.md) | What's missing compared with other tools |
| [docs/windows.md](docs/windows.md) | Building and running on Windows, real-client testing |
| [docs/production-key.md](docs/production-key.md) | Draft of the Riot production API key application |
| [NOTES.md](NOTES.md) | What the last session did and left open |

## Commands

All tasks go through `just`. Everything runs offline. Recipes arrive with their milestone; `just --list` shows what exists today. On Windows, `just` runs the app recipes in PowerShell; the pipeline recipes run in WSL ([docs/windows.md](docs/windows.md)).

| Command | Does |
|---|---|
| `just setup` | Install dependencies |
| `just check` | Format, lint, typecheck, architecture rules, tests, codegen drift, floors, enforced budgets. Run before finishing. |
| `just test` | All tests |
| `just gen` | Regenerate types from `contracts/schemas/`, and the UI's command types from the core (`stronk-core schema`) |
| `just corpus [name…]` | Fetch and verify the pinned corpora (`crawl-ci-16.20` for checks, `crawl-all-16.20` for real runs) |
| `just pipeline` | Full pipeline on the committed fixture (crawl replay, extract, winprob, wpa, publish) into `runs/pipeline/`, signed with a throwaway key |
| `just publish <estimates> <crawl,…> [key] [out]` | Signed build files into `dist/data/` |
| `just pipeline-stage <name>` | One stage: `crawl`, `extract`, `winprob`, `wpa`, `publish` |
| `just crawl <platform> <games>` | Crawl ranked games from the Riot API (needs `RIOT_API_KEY`); rerun to resume |
| `just extract [crawl,…] [out] [--retry-quarantine]` | Frames and decision points from one or more crawl directories (comma-separated) into one table; the flag first re-reads games the crawl quarantined |
| `just keygen [out]` | Create the data signing key outside the repository (default `~/.config/stronk/signing.key`) |
| `just winprob [frames] [out]` | Train the win probability model and write its calibration report |
| `just corpus-merge <out> "<crawl> …" [games]` | One crawl from several: all games, or a sample stratified by crawl |
| `just corpus-pack <crawl> <name>` | Archive a crawl for the corpus and print its `corpus.lock` entry |
| `just floors-full` | Floors on the full corpus (weekly CI job) |
| `just serve-data [root] [port]` | Serve `dist/data/` locally like the CDN: ETag and 304, CORS, on `127.0.0.1` only |
| `just app-mock` | UI in the browser against `MockBackend` |
| `just lcu-mock [session]` | Fake League client replaying a session (`tools/lcu_mock/sessions/`) |
| `just app` | Desktop app on the fixture data (pair with `just lcu-mock`; needs WebKitGTK on Linux) |
| `just data-real [key] [out]` | Real data for the app from the full corpus, signed with your key (stops if it's missing: `just keygen` once), into `runs/real/data` (+ `data.pub`) |
| `just app-real [data] [key]` | Desktop app on real data (default `runs/real/data`, a folder or a `serve-data` URL) against the real League client (start League first) |
| `just app-build` | Build and lint the Tauri shell (CI's `app-shell` job) |
| `just core-e2e` | The real `stronk-core` against lcu-mock and the signed fixture data (in `just check`) |
| `just fixture-data` | Refresh `fixtures/data`, the signed fixture data the app tests use |
| `just core build.plan '{"champion": "LeeSin", "role": "JUNGLE"}'` | What an import would write, each choice labelled (`build.import` writes it to the client) |
| `stronk-core schema` | Every command's params and result as one JSON Schema (what the UI's types come from) |
| `stronk-core serve` | Commands from stdin, one JSON line each, with one context as in the app |
| `stronk-core restore-item-sets [file]` | Put a backup of the player's item sets back (without a file: list them) |
| `stronk-core watch-champselect [--events N]` | Follow champion select over the client's websocket, one JSON line per state |
| `stronk-core record-champselect --out <file>` | Record one champion select from the real client, scrubbed (on Windows: docs/windows.md) |
| `just core <command-id> <params>` | Run an app command from the terminal |
| `just e2e` | Playwright: the UI against `MockBackend` and against the real core on lcu-mock; screenshots in `runs/e2e/screenshots/` (in `just check`) |
| `just bench` | Performance scenarios against `perf/budgets.toml`: the fixture pipeline and lock-in to import on lcu-mock |

## Rules

1. **Respect the layers.** Domain code is pure. I/O lives in adapters behind ports.
2. **Everything is a command.** New behavior is a registered command with typed params, result and errors, plus tests. Entry points only dispatch.
3. **Statistics come first.** Changes to `winprob` or `wpa` keep synthetic-truth, oracle and calibration tests green.
4. **Never crash.** No `unwrap`, `expect` or `panic!` outside tests in Rust. Validate outside input at the boundary. A crash fix comes with a regression test.
5. **Contract first.** Change `contracts/schemas/`, bump the version, run `just gen`. New fields are optional.
6. **The UI never calls Tauri directly.** Only through the `Backend` port. UI state lives in the single app state; styles use design tokens.
7. **Floors and budgets only tighten.** Raise a floor or enforce a budget when it's met. Loosening one requires an entry in `docs/decisions.md`.
8. **No network in tests.** Use fixtures, the corpus, recorded responses, `lcu-mock` and `serve-data`.
9. **Secrets stay out.** API and signing keys never appear in code, commits, logs or the app. See `docs/security.md`.
10. **Assets are attributed.** Every third-party asset gets a line in `ATTRIBUTION.md` in the same change.
11. **Record decisions.** A choice that changes structure, tooling or a contract gets an entry in `docs/decisions.md`.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- One use case per file in `application/` (Python) and `service/` (Rust).
- Tests live in each component's `tests/` folder, named after the module they cover.

## Definition of done

- `just check` passes.
- Tests added or updated.
- Stats changed: metrics reviewed against floors.
- Hot path changed: `just bench` run, budgets respected.
- UI changed: viewed via `just app-mock` or a Playwright screenshot.
- Capability added: status updated in `docs/gaps.md`.
- Decision made: entry added to `docs/decisions.md`.
- Two lines appended to `NOTES.md`: what landed, what's open.
