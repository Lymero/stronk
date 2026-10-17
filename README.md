# Stronk

A free, fast desktop companion for League of Legends. It recommends runes, items and summoner spells ranked by **win impact** (win probability added, adjusted for game state) and imports them into the client during champion select in one click, or automatically.

> Name: **Stronk** (`stronk` in code, packages and folders).

## Why

Existing tools are either slow websites or ranked by raw win rates, which reward items for being bought by players who were already winning. This project combines an honest statistical method with instant, in-lobby import.

## Repository

| Path | What |
|---|---|
| `pipeline/` | Python: crawls matches, trains the win probability model, computes WPA, publishes JSON |
| `app/` | Desktop app: Rust core (Tauri 2) + Svelte UI |
| `contracts/` | JSON Schemas shared by the pipeline and the app |
| `tools/` | League client mock, synthetic game generator |
| `perf/`, `metrics/` | Performance budgets and quality floors |
| `docs/` | Brief, architecture, method, decisions, roadmap |

## Quick start

```sh
mise install        # toolchains
just setup          # dependencies
just check          # lint, typecheck, tests (offline)
just pipeline       # pipeline on fixture data
just app-mock       # UI in the browser against mock data
```

## Documentation

- [Project brief](docs/project-brief.md): goals, principles, product decisions
- [Architecture](docs/architecture.md): components, layering, contracts, testing
- [WPA method](docs/wpa-method.md): the statistics
- [Security](docs/security.md): threat model and rules
- [Decisions](docs/decisions.md): architecture decision log
- [Roadmap](docs/roadmap.md): milestones and current focus
- [Gaps](docs/gaps.md): what's missing compared with other tools
- [AGENTS.md](AGENTS.md): working rules for contributors and AI agents

## Legal

Not endorsed by Riot Games. League of Legends is a trademark of Riot Games, Inc.
