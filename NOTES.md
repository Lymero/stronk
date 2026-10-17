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
