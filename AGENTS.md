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
| [NOTES.md](NOTES.md) | What the last session did and left open |

## Commands

All tasks go through `just`. Everything runs offline. Recipes arrive with their milestone; `just --list` shows what exists today.

| Command | Does |
|---|---|
| `just setup` | Install dependencies |
| `just check` | Format, lint, typecheck, architecture rules, tests, codegen drift, floors, enforced budgets. Run before finishing. |
| `just test` | All tests |
| `just gen` | Regenerate types from `contracts/schemas/` |
| `just corpus` | Fetch and verify the pinned test corpus |
| `just pipeline` | Full pipeline on the committed fixture (crawl replay, extract, wpa) into `runs/pipeline/`; publishes to `dist/data/` once `publish` exists |
| `just pipeline-stage <name>` | One stage: `crawl`, `extract`, `winprob`, `wpa`, `publish` |
| `just crawl <platform> <games>` | Crawl ranked games from the Riot API (needs `RIOT_API_KEY`); rerun to resume |
| `just extract [crawl] [out] [--retry-quarantine]` | Frames and decision points from a crawl directory; the flag first re-reads games the crawl quarantined |
| `just corpus-pack <crawl> <name>` | Archive a crawl for the corpus and print its `corpus.lock` entry |
| `just serve-data` | Serve `dist/data/` locally, like the CDN |
| `just app-mock` | UI in the browser against `MockBackend` |
| `just lcu-mock <session>` | Fake League client replaying a recorded session |
| `just app` | Desktop app (pair with `just lcu-mock`) |
| `just core <command-id> <params>` | Run an app command from the terminal |
| `just e2e` | Playwright end-to-end tests |
| `just bench` | Performance scenarios against `perf/budgets.toml` |

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
