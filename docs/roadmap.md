# Roadmap

Build a thin version end to end first, then improve each part. Structure is set up correctly from the start; scope grows later. Use [gaps.md](gaps.md) to choose within a milestone.

**Current focus: M1.** M0 done 2026-10-17.

## M0 · Foundation

- [x] Repository: git, `.gitignore`, `.env.example`, README, licence, `ATTRIBUTION.md`
- [x] Toolchains with mise; `justfile` with `setup`, `check`, `test`, `gen`
- [x] CI running `just check`; pre-commit hooks; Renovate
- [x] `contracts/`: schema v1, signed manifest format, codegen for Python, TypeScript and Rust
- [x] `pipeline/`: package skeleton (domain, application, ports, adapters), command registry, ruff, pyright, import-linter, pytest
- [x] `perf/budgets.toml` and `metrics/floors.toml` with checks wired into `just check` (budgets not enforced yet)
- [x] `tools/synth/`: synthetic games with planted effects, hidden skill and situational buying
- [x] `wpa` v1 reference implementation and the first synthetic-truth test

## M1 · Data in

- [ ] Development API key in `.env`
- [ ] `crawl`: Riot adapter with rate limiting, recorded-response adapter
- [ ] Crawl a few thousand high-elo games (one region, one patch)
- [ ] Commit a small fixture sample; publish the larger one and pin it in `corpus.lock`; `just corpus`
- [ ] `extract`: frames with situation features, decision points, crawl-derived skill

## M2 · Statistics v1

- [ ] `winprob`: model, calibration report, first floors set
- [ ] `wpa` v1: decision-point scores, propensity overlap, shrinkage, bootstrap intervals, flags
- [ ] `wpa` fast implementation and oracle-agreement test
- [ ] Item WPA per slot for about 10 champions
- [ ] `publish` with `LocalPublisher`: signed JSON in `dist/data/`
- [ ] `just serve-data`: local static server with ETag

## M3 · App v1

- [ ] Tauri 2 + Svelte scaffold; Cargo workspace (`domain`, `service`, `lcu`, `data`, `cli`, `src-tauri`)
- [ ] Command registry in `service`; `stronk-core` CLI; command fuzzing test
- [ ] Typed IPC with tauri-specta; `Backend` port with `TauriBackend` and `MockBackend`; single serializable state
- [ ] `data`: `DirectorySource`, `HttpSource`, cache, signature verification
- [ ] `tools/lcu-mock` with one recorded champion-select session
- [ ] Champion-select detection with preloading; import runes, item set and spells
- [ ] Playwright end-to-end tests; `just bench`; enforce the lock-in budget once met

**Milestone: usable in your own lobbies, with data served from your machine.**

## M4 · Public release

- [ ] All champions and roles, elo filters, several regions
- [ ] `R2Publisher`; scheduled pipeline on a VPS
- [ ] Web build viewer (`HttpBackend`), also hosting riot.txt
- [ ] Production key application
- [ ] Privacy note, Riot legal notice, `ATTRIBUTION.md` complete
- [ ] Signed installers and app auto-update

## M5 · Statistics v2

- [ ] Patch backtests and their floor
- [ ] `wpa` v2: doubly robust estimator, compared with v1 side by side
- [ ] E-values and the `fragile` flag
- [ ] Within-player check report

## Later

- `wpa` v3 if tests show a gain: situation buckets, top build paths (popular champions)
- Matchup-adjusted builds, skill order
- MCP server over the command registry
