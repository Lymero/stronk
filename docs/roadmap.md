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
- [x] Typed IPC: command types generated from the registry (`stronk-core schema`, ADR-053, in place of tauri-specta); `Backend` port with `TauriBackend` and `MockBackend`; single serializable state
- [x] `data`: `DirectorySource`, `HttpSource`, cache, signature verification (ADR-046)
- [x] `tools/lcu_mock` with one recorded champion-select session (`custom-2026-10-19.json`, recorded on Windows, scrubbed; ADR-042)
- [x] Champion-select detection with preloading; import runes, item set and spells (ADR-043, ADR-044; checked on the real client 2026-10-19)
- [x] UI from the real-client check: names instead of raw rune, spell and item IDs; readable champion-select phase; tell the player when all rune pages are used (ADR-047)
- [x] Champion select view: the top alternatives per slot with win impact, games and a confidence marker, falling back clearly to the most played build (ADR-049); click an option to import it instead (ADR-050)
- [ ] Real-client check of names, icons, restore, auto-import and picking (Windows, custom game)
- [x] Pick any option of a slot, not only the listed ones; keep picks across restarts until the patch changes (ADR-051)
- [x] Champion, rune, spell and item icons from the client (ADR-052)
- [x] Settings: auto-import toggle and item set restore from a chosen backup, after a confirmation
- [x] Playwright end-to-end tests: the UI against `MockBackend` and against the real core on lcu-mock, with screenshots (ADR-048)
- [x] `just bench` lock-in scenario (`stronk-core serve` on lcu-mock, 200 replays); lock-in budget enforced (p50 55 ms, p95 67 ms)

**Milestone: usable in your own lobbies, with data served from your machine.**

## M4 · Public release

- [ ] All champions and roles, elo filters, several regions
- [ ] `R2Publisher`; scheduled pipeline on a VPS
- [ ] Web build viewer (`HttpBackend`), also hosting riot.txt
- [ ] Production key application (drafted: [production-key.md](production-key.md))
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
