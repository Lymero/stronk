# NOTES

Session log. Append two lines per session: what landed, what's still open. Newest at the bottom.

- 2026-10-15 (planning chat): decided goals, stack, architecture, WPA method and roadmap; wrote AGENTS.md and docs/.
  Open: everything in M0 (`docs/roadmap.md`). Next session: scaffold the repo and get the first synthetic-truth test running.
- 2026-10-15: naming decided: "WPA" in code/docs, "Win impact" label in the UI (see docs/project-brief.md).
- 2026-10-16: docs restructured: README, decisions log (ADRs), full layered architecture (ports and adapters everywhere, typed contracts in all three languages, enforced dependency rules). Solo affects process only.
  Open: M0 in docs/roadmap.md.
- 2026-10-16: added commands registry, single UI state, P95 budgets, quality floors, pinned corpus, signed data, local-first data source, web viewer (ADR-011 to 018); new docs/security.md and docs/gaps.md.
  Open: M0 in docs/roadmap.md.
- 2026-10-16: WPA method rewritten: causal framing, decision-point anchoring, data limits and sample sizes, versioned estimators (v1 adjusted, v2 doubly robust, v3 conditional), validation and flags (ADR-019, ADR-020); roadmap gains M5.
  Open: M0 in docs/roadmap.md.
- 2026-10-16: project named Stronk (ADR-021); docs updated (`stronk-core`, `stronk-pipeline`, `stronk_pipeline`).
  Open: M0 in docs/roadmap.md.
- 2026-10-17: M0 landed. Repo, mise toolchains, justfile, CI, pre-commit, Renovate; contracts v1 (build, signed manifest) with Python/TS/Rust codegen and drift check; pipeline skeleton with command registry (`wpa.estimate`), import-linter layers; floors and budgets with mechanical ratchet; `tools/synth`; WPA v1 reference passing the synthetic-truth test (ADR-022 to 025). `just check` green, 92 Python + 5 Rust tests.
  Open: CI never run (no remote yet); MIT licence provisional (ADR-022); hidden-skill scenario covers 87.5% not 95% (bias +0.6%) — watch it when `winprob` replaces the baseline; Rust types don't enforce numeric bounds (ADR-023). Next: M1 crawl.
- 2026-10-17: M1 code landed: `crawl.run` (Riot client with header-driven rate limits, retries, resumable compact pseudonymous store, record/replay transports with scrubbing), `extract.run` (frames, decision points per ADR-026, crawl-derived skill, report), `just crawl|extract|pipeline-stage|corpus|corpus-pack`, corpus tooling and opt-in corpus test, offline crawl→extract→wpa test (ADR-026, ADR-027). Fuzzing found and fixed a parser crash on non-string event types.
  Open: the key in `.env` gets 401 "Unknown apikey" (regenerate); then the real crawl (`just crawl euw1 3000`), a recorded fixture under `fixtures/` with a replay test and `just pipeline`, and the corpus upload (repo is private: release assets need auth, or use a public bucket). Payload models are written from the documented match-v5 shape and are untested against live 2026 responses.
- 2026-10-17: new Riot key works. Live timelines carry item/skill events with participantId 0 (item 3865, one SKILL_LEVEL_UP per game) which rejected every match as invalid; the parser now drops ownerless events (tests added). 5-game smoke crawl and extract on live data are clean; full `just crawl euw1 3000` started (log: `runs/logs/crawl-euw1.log`).
  Open: finish the crawl (rerun to resume if it stops; dev key expires after 24 h); recorded fixture plus replay test; `just pipeline`; corpus upload; M1 still uncommitted.
- 2026-10-17: crawl found elite monster kills with killerTeamId 300 (neutral; a Void Grub despawn, killerId 0) rejecting ~10% of matches; the parser now drops them (tests added), the 32 `invalid` skips were removed from `runs/crawl/euw1/skipped.jsonl` (backup alongside) and the crawl resumed.
  Open: skips recorded as `invalid` are never retried, so a parser fix needs the skip list pruned by hand; consider retrying `invalid` skips when the parser changes.
- 2026-10-17: real crawl done: `runs/crawl/euw1` holds 3305 patch-16.20 games (39 MB, 542 players, 0 errors, 24 retries, ~2 h on rate limits); extract gives 178k frames and 124k decision points (19.7k unfinished slots dropped).
  Open: recorded fixture plus replay test; `just pipeline`; `just corpus-pack` and the corpus upload; M1 still uncommitted.
