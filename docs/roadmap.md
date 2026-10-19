# Roadmap

Build a thin version end to end first, then improve each part. Structure is set up correctly from the start; scope grows later. Use [gaps.md](gaps.md) to choose within a milestone.

**Current focus: M3.** M0 done 2026-10-17, M1 and M2 done 2026-10-18.

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

- [x] Development API key in `.env`
- [x] `crawl`: Riot adapter with rate limiting, recorded-response adapter
- [x] Crawl a few thousand high-elo games (one region, one patch): 3305 EUW games on 16.20
- [x] Commit a small fixture sample; publish the larger one and pin it in `corpus.lock`; `just corpus`
- [x] `extract`: frames with situation features, decision points, crawl-derived skill

## M2 · Statistics v1 (done 2026-10-18)

- [x] `winprob`: model, calibration report, first floors set
- [x] `wpa` v1: decision-point scores, propensity overlap, shrinkage, bootstrap intervals, flags
- [ ] `wpa` fast implementation and oracle-agreement test (deferred until a budget needs it, ADR-034; not part of M2)
- [x] Item WPA per slot for about 10 champions (132 picks on 22,954 games, ADR-035)
- [x] Corpora: `crawl-ci-16.20` (3500, stratified by region) for checks, `crawl-all-16.20` (22,954) weekly; floors per corpus (ADR-038)
- [x] `publish` with `LocalPublisher`: signed JSON in `dist/data/`
- [x] `just serve-data`: local static server with ETag

## M3 · App v1

- [x] Tauri 2 + Svelte scaffold; Cargo workspace (`domain`, `service`, `lcu`, `data`, `cli`, `src-tauri`) (ADR-040, ADR-041)
- [x] Command registry in `service`; `stronk-core` CLI; command fuzzing test
- [ ] Typed IPC with tauri-specta; `Backend` port with `TauriBackend` and `MockBackend`; single serializable state (port, both backends and state done; tauri-specta bindings once the shell builds locally)
- [x] `data`: `DirectorySource`, `HttpSource`, cache, signature verification (ADR-046)
- [x] `tools/lcu_mock` with one recorded champion-select session (`custom-2026-10-19.json`, recorded on Windows, scrubbed; ADR-042)
- [x] Champion-select detection with preloading; import runes, item set and spells (ADR-043, ADR-044; checked on the real client 2026-10-19)
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
