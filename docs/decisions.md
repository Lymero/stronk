# Decisions

Architecture decision log. One entry per decision: context, decision, consequences. Add new entries at the bottom; never rewrite old ones, supersede them.

---

### ADR-001 · Desktop app with Tauri 2

- **Context:** importing runes and items needs the League client lockfile and its local API (self-signed certificate, no CORS), plus a background process reacting to champion select. A website can do none of this.
- **Decision:** desktop app on Tauri 2. It uses the OS webview, so it's small and light compared with Electron.
- **Consequences:** a thin Rust layer is required; the UI stays web technology.

### ADR-002 · TypeScript UI, Rust core

- **Context:** perceived speed is bound by local I/O, not CPU.
- **Decision:** Svelte 5 + TypeScript for the UI; Rust only for native work (LCU, cache, IPC).
- **Consequences:** fast UI iteration; Rust code stays small and focused.

### ADR-003 · Python pipeline

- **Context:** the statistical method will change often; data volume is large but batch.
- **Decision:** Python with Polars, DuckDB and LightGBM (Rust/C++ under the hood).
- **Consequences:** near-native speed with fast iteration. Rewrite a hot spot in Rust only if profiling demands it.

### ADR-004 · Static data on a CDN, no live backend

- **Context:** statistics change per patch, not per request.
- **Decision:** precompute JSON per patch, region, elo, champion and role; host on Cloudflare R2/Pages.
- **Consequences:** nothing to scale or keep alive; the app works offline with cached data.

### ADR-005 · Ports and adapters in every component

- **Context:** the project must stay clean as it grows, and every feature must run offline.
- **Decision:** domain / application / adapters / entry points, dependencies pointing inward, enforced by import-linter, the Cargo crate graph and dependency-cruiser.
- **Consequences:** a little more structure up front; domain logic testable in isolation; fakes for every external system.

### ADR-006 · JSON Schema as the single data contract

- **Context:** three languages read the same data.
- **Decision:** JSON Schema with generated Python, TypeScript and Rust types; Tauri IPC typed with tauri-specta.
- **Consequences:** contract changes fail at compile or CI time instead of at runtime.

### ADR-007 · Monorepo with mise and just

- **Decision:** one repository, pinned toolchains, one command per task.
- **Consequences:** one place to look; identical commands locally and in CI.

### ADR-008 · Lessons adopted from storytold/photocraft

- **Adopted:** reference-oracle testing, pinned and hash-verified test data, never-crash lints and parser fuzzing, metrics that must not regress, session notes, contracts that fail loudly.
- **Not adopted:** "pure Rust, no webview" (fits a GPU editor, not this UI); multi-agent coordination rules (solo project).

### ADR-009 · "Win impact" in the UI, "WPA" in code

- **Context:** "WPA" is unclear to most players and associated with Coachless.
- **Decision:** UI label "Win impact" with an explanatory tooltip; "WPA" in code, docs and the method page.
- **Consequences:** clearer for players; method stays precisely named for those who care.

### ADR-010 · Solo project: light process, full architecture

- **Context:** one developer, working with one AI agent at a time.
- **Decision:** keep architecture, typing, layering and testing at team standard; keep process light (no coordination rules, short session notes).
- **Consequences:** the codebase is ready for contributors at any time without carrying team overhead.

### ADR-011 · Every use case is a command

- **Context:** the UI, dev CLIs, tests and a future MCP server all need to trigger the same behavior.
- **Decision:** a command registry in each component (id, typed params, result, error). Entry points only dispatch by id.
- **Consequences:** agents and scripts can drive anything from the terminal; one generic fuzz test covers every command.

### ADR-012 · Single serializable UI state

- **Decision:** UI state is one plain typed object in `lib/state`.
- **Consequences:** tests, mocks and debugging tools can read and set it; avoids scattered component state.

### ADR-013 · Performance budgets on P95

- **Context:** speed is the main promise; averages hide slow cases and P99 is too noisy on shared CI runners.
- **Decision:** budgets in `perf/budgets.toml`, enforced on P95 (lock-in to import ≤ 300 ms, target P50 ≤ 100 ms), with P99 and max reported. A budget is enforced once first met.
- **Consequences:** regressions fail CI; per-step timings show the cause.

### ADR-014 · Quality floors only go up

- **Decision:** calibration, synthetic-truth recovery and coverage have floors in `metrics/floors.toml`. Lowering one requires a new decision entry.
- **Consequences:** the statistics cannot degrade silently.

### ADR-015 · Pinned test corpus outside git

- **Decision:** large samples stored outside the repository, pinned by URL and sha256 in `corpus.lock`, fetched by `just corpus`, always tested in CI.
- **Consequences:** reproducible results without bloating the repository.

### ADR-016 · Signed published data

- **Context:** the app writes published data into users' clients; a compromised host would affect every user.
- **Decision:** ed25519-signed manifest with per-file sha256; the app verifies every source, including local ones.
- **Consequences:** tampered data is rejected; one code path from local development to CDN.

### ADR-017 · Local data first, CDN later

- **Decision:** `LocalPublisher` writes to `dist/data/` with the CDN layout; the app reads it through `DirectorySource` or `just serve-data`. `R2Publisher` and the CDN URL come at public release.
- **Consequences:** no hosting needed to start; moving to the CDN changes one adapter and one setting.

### ADR-018 · Web build viewer via `HttpBackend`

- **Decision:** the same UI, with a read-only `HttpBackend`, serves as a web viewer for preparing builds in advance.
- **Consequences:** covers Coachless's preparation use case at little cost; also hosts riot.txt.

### ADR-019 · Causal framing, decision-point anchoring, versioned estimators

- **Context:** the goal is each option's true effect on winning, from observational data with limited sample sizes.
- **Decision:** define the estimand as the effect of choosing an option at a decision point, within the overlap population. v1: adjusted WPA with situation and crawl-derived skill features, propensity-based overlap, empirical Bayes shrinkage. v2: doubly robust estimation. v3: situation buckets and build paths for popular champions only. No deep learning, causal forests everywhere or full Bayesian models.
- **Consequences:** removes timing and survivorship bias at no extra cost; honest "no clear difference" results where data is thin; all runs fit in hours on a normal machine.

### ADR-020 · Method changes must prove a measured gain

- **Context:** statistical work can absorb unlimited effort for gains nobody can verify.
- **Decision:** a new method, feature or model ships only if it measurably improves synthetic-truth recovery or patch backtests without breaking any floor.
- **Consequences:** complexity stays justified; non-experts can judge method changes by numbers.

### ADR-021 · Product name: Stronk

- **Context:** the working name "coach" was too close to Coachless; Riot item and champion names (such as Mejai) carry trademark risk.
- **Decision:** name the project **Stronk** (`stronk` in code and folders), gaming slang for "strong".
- **Consequences:** recognizable to players, no Riot IP in the name; domain and trademark check still due before public release.

### ADR-022 · MIT licence

- **Context:** the repository needs a licence before it is public; the app is free and contributions should be easy.
- **Decision:** MIT, copyright "The Stronk authors". Provisional: revisit before the first public release if a copyleft licence is preferred.
- **Consequences:** anyone may reuse the code, including commercially; third-party assets keep their own licences in `ATTRIBUTION.md`.

### ADR-023 · Generated contract code: accepted gaps

- **Context:** typify (Rust codegen) unwraps regexes compiled from schema patterns, ignores `const`, and does not enforce numeric `maximum` or `minimum` above 0.
- **Decision:** allow `clippy::unwrap_used` on generated modules only (`contracts/generated/rust/src/lib.rs`); contract tests parse a value through every pattern so a bad pattern fails CI. Write `schemaVersion` as `"enum": [1]`, which typify validates. The app's `data` crate checks the numeric bounds it relies on. Limits are listed in `contracts/README.md`.
- **Consequences:** the never-crash rule holds for handwritten Rust; generated types are slightly weaker than the schema in Rust and TypeScript, and the Python models (used before publishing) enforce everything.

### ADR-024 · WPA v1 reference in plain NumPy, with a baseline WP stand-in

- **Context:** the reference must be obviously correct, deterministic and type-checked under pyright strict; scikit-learn has no type information. The `winprob` stage (LightGBM) comes in M2.
- **Decision:** a small Newton-method logistic regression in `domain/logistic.py` serves the propensity model (one-vs-rest, normalised) and a baseline win probability model (`domain/winprob.py`, logistic on situation features, minute and their interaction) used by `wpa.estimate` until `winprob` exists. The bootstrap resamples matches with both models held fixed. Synthetic truth runs on 8 seeds; floors are set just above the measured values.
- **Consequences:** no untyped dependency in the domain. Intervals ignore model-fitting uncertainty; v2 (cross-fitting) addresses it. With hidden skill on, interval coverage is 87.5% and A's bias +0.6%: the skill proxy removes most, not all, of the confounding, and the floors record that honestly.

### ADR-025 · Root workspaces; ratchets checked mechanically

- **Context:** three languages share tooling; floors and budgets "only tighten" needs enforcing, not just stating.
- **Decision:** one uv workspace (`pipeline`, `tools/synth`, `contracts/generated/python`) and one pnpm workspace at the root, a standalone crate for the generated Rust types until the app workspace exists (M3). Pyright runs from pnpm so `just check` downloads nothing. `tools/checks` compares `metrics/floors.toml` and `perf/budgets.toml` with `HEAD`: a loosened entry fails unless this file names it. Pre-commit hooks run local tools from the lockfiles, plus `pre-commit-hooks`; Renovate waits 14 days after a release.
- **Consequences:** one `uv sync` and one `pnpm install` set everything up; lowering a floor needs a decision entry, by construction.

### ADR-026 · Decision points v1: completed items, anchored at the first component

- **Context:** WPA scores choices at decision points (wpa-method, section 2); the data has purchase events, not intentions, and the method leaves components, boots and unfinished items open.
- **Decision:** slot 0 is the keystone rune, at minute 0. Slot k ≥ 1 is the k-th **completed item**: purchasable on Summoner's Rift, built from components, at least 2,000 gold, upgrades into nothing, not boots, consumable, trinket or champion-specific (from Data Dragon). Its decision is the first purchase of a **component** (anything in a completed recipe) after slot k − 1 completes; purchases before 1:30 are starting items. Undone purchases are removed. A slot unfinished at the end keeps its decision when the components bought fit exactly one completed item, otherwise it is dropped and counted (`unfinished_slot`). Six slots at most. Features: team leads (gold, XP, kills, towers, inhibitors, dragons, barons, heralds, grubs) from the frame at or before the decision, lane gold against the same position, the enemy's magic share from Data Dragon ratings, and crawl-derived skill on the champion (prior games only, shrunk by 5 games toward 50%).
- **Consequences:** boots and components get no estimates in v1. Dropping ambiguous unfinished slots biases late slots toward long games slightly; the extract report counts every drop so the size of that bias is visible, and the corpus test caps it at 30%. Revisit with patch backtests (M5).

### ADR-027 · Crawl: compact pseudonymous games, recordings at the HTTP transport

- **Context:** raw match and timeline JSON is about 1 MB per game; tests must run offline against real responses; recordings and the corpus will be shared; a development key allows 100 requests per 2 minutes and expires daily.
- **Decision:** the crawler validates match and timeline at the boundary and stores one compact domain `Match` per game (`<crawl>/matches/<id>.json.gz`, about 20× smaller), plus Data Dragon data per patch, and `skipped.jsonl` so rejected games are never refetched; reruns resume. Players are stored as HMAC-SHA256 pseudonyms under a per-crawl `.salt` that is never packed or committed. Recording and playback are httpx transports, so tests run the production client; recordings drop Riot ids and names and replace PUUIDs (in bodies and URLs) with consistent pseudonyms, and never contain headers. Rate limits come from Riot's headers (sliding windows, never looser than Riot's), with Retry-After on 429 and exponential backoff on 5xx. Without an explicit patch, the crawl keeps the newest patch already stored, or else takes the patch of the best player's latest game. The crawl is sequential async: the development key's limit, not latency, sets its speed. Lint: `PLR0911` is off (matching on `Result` returns early by design) and tests may use seeded `random` (`S311`).
- **Consequences:** raw JSON is gone after the crawl; new features need a re-crawl unless they come from fields already kept. Pseudonyms are stable within a crawl, so skill can be derived, but are not linkable across crawls. A few thousand games take about 2 hours on a development key.

### ADR-028 · Corpus on private GitHub release assets; live payload quirks dropped at the boundary

- **Context:** the repository is private, so release download URLs need auth, and a bearer token on `github.com/…/releases/download/…` is not honoured. The first live crawl showed shapes the documented match-v5 schema doesn't mention: item and skill events with participant 0, and elite monster kills by team 300 (a Void Grub despawning).
- **Decision:** corpus entries point at the API asset URL (`api.github.com/repos/<owner>/<repo>/releases/assets/<id>`), fetched with `Accept: application/octet-stream` and `GITHUB_TOKEN` (or `GH_TOKEN`; `just corpus` falls back to `gh auth token`). The redirect is followed by hand so the token never reaches the signed storage host. Each corpus archive gets its own prerelease tagged `corpus/<name>`. The parser drops events owned by participant 0 and monster kills by team 300; any other out-of-range id still rejects the game. `fixtures/riot/euw1` (10 games, about 1 MB) is a scrubbed live recording replayed by `just pipeline` and `test_fixture_replay`.
- **Consequences:** fetching the corpus needs a token with read access to the repository; CI passes `github.token`. Moving the corpus to a public bucket later only changes `corpus.lock`. A parser change does not retry games already skipped as `invalid`; their lines must be removed from `skipped.jsonl` by hand.

### ADR-029 · Rejected games go to quarantine, retried by extract

- **Context:** a game that failed validation was recorded as an `invalid` skip and its payloads discarded, so a parser fix needed the crawl's `skipped.jsonl` pruned by hand and the games fetched again (ADR-028). The first live crawl lost 32 games of about 340 that way.
- **Decision:** the Riot adapter returns a `Rejected` outcome holding a short, id-free reason (`event.ELITE_MONSTER_KILL.killerTeamId.literal[100,200]: literal_error`) and the payloads. The crawl stores it in `<crawl>/quarantine/<id>.json.gz` (gitignored, never packed), scrubbed like recordings but with PUUIDs replaced by the crawl's own pseudonyms, so a game that passes later is stored as is and still links to its players. Quarantined games count as known and aren't fetched again. `extract.run` with `retry_quarantine` (`just extract … --retry-quarantine`) reads them through the injected `PayloadParser`: games that pass are stored and released; a match kept without its timeline (the match itself failed) is released for the next crawl once it reads; the rest stay, with their reason updated. `report.json` counts skips by reason (`skipped`), quarantined games by reason (`quarantined`), and `skip_rate`: games lost to a failure (quarantined, or dropped whole by extract) over games attempted. `pipeline.skip_rate` on the committed recording has a ceiling of 0.01 in `metrics/floors.toml`.
- **Consequences:** a parser fix no longer needs a re-crawl or hand edits. Quarantine holds raw-sized JSON (about 1 MB a game), acceptable at a few per thousand. Reasons are pydantic error locations, so they change if payload models are renamed. Supersedes the last consequence of ADR-028.

### ADR-030 · Win probability: best candidate on validation matches; LightGBM behind a port

- **Context:** WPA v1 needs P(win | state at minute t), calibrated more than accurate (docs/wpa-method.md). The plan was LightGBM. On the 3305-game corpus (2314 training, 496 validation, 495 test matches), LightGBM loses to a logistic model on leads, minute and lead × minute under every regularisation tried: test log loss 0.5203 against 0.5161, calibration error after 30 minutes 0.085 against 0.046, and it is overconfident at the extremes. With a few thousand games, the logistic form's built-in "a lead matters more later" beats what trees can learn.
- **Decision:** `winprob.train` fits every learner on the training matches and keeps the one with the lowest validation log loss; test matches only report, for every candidate. Learners sit behind `WinProbLearner` (`LogisticLearner` in the domain, `LightGbmLearner` in adapters: deterministic, one thread, every lead monotone increasing); `JsonWinProbStore` saves either kind in one JSON file. Predictions are symmetrised, `(p(x) + 1 − p(−x)) / 2`. Inputs are picked by feature name. `lightgbm` is forbidden in domain and application (import-linter). `wpa.estimate` takes `winprob` (a model path) and falls back to the logistic form fitted on decisions, so synthetic truth is unchanged. Floors `winprob.calibration_error` (max 0.015) and `winprob.log_loss` (max 0.52) are measured on the corpus in `just check`, which therefore needs `just corpus` (cached; CI already fetches it).
- **Consequences:** the logistic model is in use today; LightGBM takes over by itself when more data makes it win on validation. `just check` takes about 25 s more. Skill features aren't model inputs yet (frames don't carry them). The pipeline now depends on LightGBM (and scipy through it).

### ADR-031 · No number under 30 decisions; shrunk intervals keep the prior's uncertainty

- **Context:** the first WPA run on real data (corpus, 3305 games) reported intervals of zero width. Two causes. An option chosen once against an alternative chosen once got a number: a bootstrap over two matches reproduces the same values, so "WPA 1.0, interval [1.0, 1.0]". Those zero-variance estimates then dominated their shrinkage group, and shrinkage moved interval ends like the estimate, `w·end + (1 − w)·prior`, so a fully shrunk estimate (w = 0) also got a zero-width interval. Synthetic truth didn't catch it: its games never trigger shrinkage or tiny samples.
- **Decision:** under `min_estimate_decisions` (30) overlap decisions for the option or for its alternatives, no number, only `low_sample`. Shrinkage returns each shrunk estimate's standard error, `sqrt(w·se² + (1 − w)²·Var(prior))` with `Var(prior) = 1 / Σ 1/(se² + τ²)`, and the bootstrap interval is rescaled around the shrunk estimate to that standard error, keeping its shape.
- **Consequences:** synthetic metrics are unchanged (point estimates don't move). On the corpus, 24 of 12,503 estimates get a number and the narrowest interval is 0.21 wide: one patch of one region is far too little data to rank items (see NOTES).

### ADR-032 · Signing in Python with `cryptography`, checked against minisign-verify

- **Context:** published manifests are signed in minisign format (ADR-016, contracts/README.md) and the app will verify them in Rust. The `minisign` binary isn't part of the toolchain, and its secret key file is scrypt-encrypted, which a non-interactive pipeline can't unlock without storing the password next to it.
- **Decision:** the pipeline signs with `cryptography` (Ed25519 over BLAKE2b-512, algorithm `ED`), writing minisign signatures and public keys byte for byte. The secret key file is a plain format of our own (`stronk signing key v1`, key id, seed), created by `signing.keygen` with mode 0600 outside the repository. A throwaway test key signed `contracts/examples/manifest.v1.json`; only its public half (`contracts/tests/keys/test-only.pub`) and the signature are committed. Python and the Rust `minisign-verify` crate (contracts dev-dependency) both verify it, and both reject a tampered byte. Changing the example means signing it again with a new throwaway key (`signing.keygen`) and replacing both files.
- **Consequences:** compatibility with the app's verifier is tested on every `just check`. The secret key is protected by file permissions, not a password; moving it to a keychain or CI secret later changes only `SigningKeys`.

### ADR-033 · Publish: whole-patch replacement, canonical bytes, pages from crawls

- **Context:** build.v1 publishes rune options as whole pages, but WPA estimates keystones (slot 0); the manifest's hashes must match the bytes the app reads; a half-written patch must never be visible; the fixture pipeline must not overwrite real data.
- **Decision:** `publish` reads `wpa.estimate`'s estimates (`out`, `EstimateStore`) and the crawls they came from. Each keystone option carries the page most played with it for that champion and role (ties go to the smallest page, so order never matters); `games` counts that champion's games in the role. Every file is validated with the generated contract models, serialised canonically (sorted keys, compact, UTF-8, final newline), hashed into the manifest, which is signed and checked. `LocalPublisher` writes a patch into a hidden sibling and swaps it in, so readers see one run or the other. The run id is the UTC time plus a hash of the file contents. Region defaults to `all` (pooled crawls) and elo to `master_plus`. `just pipeline` signs with a throwaway key and publishes under `runs/pipeline/dist`; `dist/data` is only written by `just publish` with the real key.
- **Consequences:** a published page is the keystone's usual page, not an estimated one. Spells and skill order are empty arrays until they have decision points.

### ADR-034 · The WPA reference is fast enough; the fast implementation waits

- **Context:** the architecture planned a `fast` (Polars) WPA v1 next to the plain `reference`, kept in agreement by an oracle test. Measured 2026-10-18 on the corpus decisions replicated 8 times (993k decisions, about the 24k games being crawled): the reference takes 21.5 s and 1.3 GB at peak.
- **Decision:** no fast implementation for now. It is written when a measured budget (a `perf/budgets.toml` scenario on real-size data) needs it, together with the oracle-agreement test.
- **Consequences:** one implementation to keep correct. The `Estimator` port is unchanged, so adding `fast` later needs no other change.

### ADR-035 · Overlap per option: P(A) in [ε, 1 − ε]

- **Context:** the reference put a decision in the overlap population only when every option at its decision point had propensity ≥ ε (0.05). Real decision points have long tails of options chosen a handful of times; their propensity is far below ε everywhere, so the overlap population was empty for the popular options too. More games meant more rare options and fewer numbers: 24 estimates on 3305 games, 7 of 30,855 on 22,954 (KR, NA, EUW, 16.20). Synthetic games have two options per slot, where both rules agree, so no test caught it.
- **Decision:** the estimand compares option A with its alternatives (docs/wpa-method.md, section 2), so overlap is decided per option: A's propensity, a logistic fit of A against the rest, must lie in [ε, 1 − ε]. A's effect compares A with the alternatives inside A's overlap. With two options this is exactly the old rule. The bootstrap resamples all matches at the decision point, so each option's interval uses the same draws.
- **Consequences:** synthetic-truth metrics are unchanged. On the 22,954 games, 3008 estimates across 298 champion-role picks get a number; 515 of them clear `low_sample`, with a median interval width of 0.073, and 71 of those exclude zero (about 26 expected by chance). Rare options still get `low_overlap`.

### ADR-036 · "Clear" means surviving false discovery control over pre-registered contrasts; synthetic many-option slot

- **Context:** on 22,954 games (16.20), 515 well-sampled estimates had 71 intervals excluding zero, where about 26 are expected by chance; across all 3008 numbers, 330. `no_clear_difference` was set when an interval overlapped the best option's, with no correction for testing thousands of options. Separately, synthetic games had two options per slot, so nothing synthetic covered the overlap bug of ADR-035.
- **Decision:**
  - *Family, fixed before results.* Only options eligible to be claimed are tested: a number, neither `low_sample` nor `low_overlap`. Eligibility and the comparisons depend on decision counts only. The family is every contrast of one `wpa.estimate` run; decision tables carry no patch, but `publish` only accepts one-patch crawls, so a published patch is one family.
  - *Hypotheses.* At each decision point, every eligible option is compared head to head with the most played eligible option: the estimator's own effect on the rows of the two, with a pairwise propensity and overlap, and the same bootstrap draws as the point's other estimates. The p-value of no difference uses that contrast's bootstrap standard error, normal approximation (200 resamples can't resolve the p-values near 1e-5 that BH needs). A contrast too small to measure stays in the family with p = 1.
  - *Claims.* Benjamini-Hochberg over the family gives `q` (with `versus`, the option compared with, in the estimates file). q > 0.05 (`WpaSettings.fdr`) gets `no_clear_difference`; so does a most played option none of whose contrasts is clear. Options outside the family keep their other flags and get no `q`.
  - *Synthetic slot 4:* four common options (G +3%, bought when ahead; I bought when behind) and eight rare ones at about 0.1% each, drawn from their own random stream so slots 1–3 are the same games as before. Floors require the common options estimated, the tail `low_overlap`, and planted effects clear. Truth compares an option with the alternatives chosen in the same situation.
- **Consequences:**
  - On the 22,954 games, the family holds 125 contrasts (284 of the 390 points with an eligible option have only that one) and none survives; the smallest q is 0.085. A first, broader family (every estimate with a number, against zero) had 0 of the 71 surviving too.
  - `synthetic.clean.planted_clear` and `synthetic.confounded.planted_clear` drop from 0.9375 to 0.8125: G is now tested against the most played option rather than against zero, and v1 keeps about half of G's effect. Their floors go from 0.875 to 0.75, one missed planted effect in 16 below the measurement.
  - Slot 4 exposed a bias in v1: the difference of mean scores targets E[π(1−π)Δ] / (E[π]·E[1−π]), so the effect of a choice the situation predicts shrinks toward zero (G keeps 54% of its effect, with the win probability model absorbing more of it). Slot 4 is left out of v1's error and coverage metrics; ADR-037 adds the overlap-weighted estimator that removes the bias.

### ADR-037 · Overlap-weighted WPA alongside v1, not the default yet

- **Context:** synthetic slot 4 showed v1 shrinking the effect of a choice the situation predicts (ADR-036): G, +3% and bought when ahead, kept 54% of its effect. Overlap weights (Li, Morgan & Zaslavsky 2018) target E[e(1−e)Δ] / E[e(1−e)], the effect against the alternatives chosen in the same situation, averaged where both are realistically chosen, with no attenuation.
- **Decision:** estimators share one pipeline (decision points, overlap gate, flags, match bootstrap, shrinkage, contrasts and FDR) and differ only by their effect function. `overlap-weighted` (`OverlapWeightedEstimator`) weighs choosers of an option by 1 − e and the others by e, on the same scores, propensities and bootstrap draws; it is registered next to `v1-reference` and chosen with `wpa.estimate`'s `estimator`. It becomes the default only when, on synthetic truth, G keeps about +3%, the other planted effects stay right, and every floor holds for it; `stronk-synth eval` reports its metrics under `synthetic.overlap_weighted.*` (not enforced) so that stays measured.
- **Consequences:**
  - Synthetic, 8 seeds: G keeps 99% of its effect (v1 54%) and its interval covers the truth in 88% of seeds (v1 25%). But in the confounded scenario A's bias is +0.0096 (floor ±0.008, v1 +0.0036) and coverage 0.75 (floor 0.8, v1 1.0); in 1 of 8 seeds B, truly 0, is called clear (v1 never). Weighting removes v1's attenuation, which was also hiding part of the hidden-skill confounding. v1 stays the default.
  - Real data, 22,954 games: the two agree closely on the 515 eligible estimates (correlation 0.977, slope 0.96, median interval width 0.073 vs 0.074); leads and minute predict item choices only weakly, so v1 attenuates little there. Neither has a contrast surviving FDR (smallest q 0.085 for v1, 0.368 for overlap weights).
  - The next step for both is confounding, not weighting: a doubly robust estimator (v2) with skill features once frames carry them.

### ADR-038 · Two corpora, floors per corpus

- **Context:** the only corpus was 3305 EUW games; its win probability floors (log loss max 0.52, calibration error max 0.015) were set from 495 test matches. On the 22,954 games of three regions, test log loss is 0.5215, above that floor, yet the cross-evaluation shows the models agree: the corpus model on the new test games scores 0.523 [0.511, 0.534], the new model on the corpus's test games 0.513 [0.480, 0.547] (bootstrap by match). The gap is the test games, not the model. By region the new model's test log loss is EUW 0.532 [0.510, 0.554], KR 0.513 [0.495, 0.533], NA 0.518 [0.498, 0.539], calibration error 0.019, 0.003 and 0.012: EUW games are harder to predict, as the EUW crawl went deepest down the ladder. A corpus's mix of regions moves its baseline, so one set of numbers can't serve every corpus.
- **Decision:**
  - `crawl-ci-16.20`: 3500 games stratified by region from the crawls, in proportion to their size (EUW 1220, KR 1140, NA 1140; within a region, the smallest sha256 of the file name, `corpus.py merge --games`). `just check` and every CI run use it.
  - `crawl-all-16.20`: all 22,954 games, for real runs and the `full-corpus` workflow (weekly and on demand, `just floors-full`). Both are private release assets pinned in `corpus.lock`; `just corpus` takes entry names, so CI downloads 34 MB, not 257 MB. `crawl-euw1-16.20` leaves the lock (its release stays).
  - Floors are per corpus, named after it, each from its own baseline with the earlier margins: `winprob.ci.log_loss` max 0.535 (measured 0.5308), `winprob.ci.calibration_error` max 0.013 (0.0114), `extract.ci.skip_rate` max 0.01 (0); `winprob.full.log_loss` max 0.525 (0.5215), `winprob.full.calibration_error` max 0.0095 (0.0082), `extract.full.skip_rate` max 0.01 (0). A floor's `suite` (`check` or `full`) says which run measures it. `winprob.log_loss` and `winprob.calibration_error`, measured on the EUW-only corpus, are removed.
- **Consequences:** each floor ratchets against data it was measured on. The full corpus's floors fail only in the weekly job, not on a push. The corpus extract test runs on the CI corpus only.

### ADR-039 · Windowed outcome and class-level pooling as options; the defaults stay

- **Context:** at 22,954 games no comparison survives FDR (ADR-036). Two cheap ways to more power were checked before M3: scoring against a shorter-term outcome (docs/wpa-method.md, section 5: WP at t + Δ, less noise), and pooling every champion of a class at each decision point (more decisions per point).
- **Decision:**
  - `wpa.estimate` takes `window` (minutes; needs `frames` and `winprob`): the outcome becomes the decision maker's team's WP at the first frame at least that long after the decision, or the result when the game ends first. Estimators take the outcome as an argument; the default is the final result. `Match` now rejects games where participants 1–5 aren't team 100 (Riot's convention, true of all 22,954 games), since decision tables keep the participant, not the team.
  - `group: "class"` pools champions of a class. Champion is a confounder there, handled twice: a 0/1 feature per champion, so propensity and overlap are within champion; and a stratum, so event scores are centred within champion at each point (champion fixed effects) before options are compared. Pooling returns the row permutation, since canonical order sorts by the new champion column, and WP and outcomes follow it. Columns constant at a point are dropped before fitting (exactly the same fit, faster).
  - Neither default changes. Results (crawl-all-16.20, v1, family of ADR-036):

    | Outcome | Grouping | Claimable | Contrasts | Survive | Smallest q | Median interval width |
    |---|---|---|---|---|---|---|
    | Final result | champion | 515 | 125 | 0 | 0.085 | 0.073 |
    | WP at t+5 | champion | 515 | 125 | 0 | 0.380 | 0.031 |
    | WP at t+8 | champion | 515 | 125 | 0 | 0.531 | 0.041 |
    | Final result | class | 449 | 351 | 1 | 0.022 | 0.080 |
    | WP at t+8 | class | 449 | 351 | 2 | 0.005 | 0.047 |

- **Consequences:** the window narrows intervals to 43% (t+5) and 55% (t+8) of the final result's, but effects shrink about as much (median |WPA| 0.0157 to 0.0074 and 0.0083) and correlate only 0.43 and 0.56 with the final-result estimates: it measures a shorter-term effect, not the same one more precisely. Class pooling turns 76 of 98 class decision points into comparisons (against 106 of 390 per champion); survivors: fighters MIDDLE slot 1, Blade of the Ruined King (3153) against Immortal Shieldbow (6673), −0.078, n 743 (final result); tank supports, Zeke's Convergence (3050) against Knight's Vow (3109) at slot 2, −0.039, n 840, and Knight's Vow against Locket (3190) at slot 1, +0.023, n 2247 (t+8). More data per champion stays the main path; the production key needs the M3 prototype.

### ADR-040 · App core: a Cargo workspace with synchronous ports, verified data from the first slice

- **Context:** M3 starts the desktop app. The core must run every feature without the game or the network, crash on nothing, and only ever use data whose signature checked out (ADR-016). The local machine (WSL) has no WebKitGTK, which the Tauri shell needs to build on Linux.
- **Decision:**
  - `app/core` is a Cargo workspace: `stronk-domain` (pure: `Role`, `Patch`, `BuildKey`), `stronk-service` (ports `BuildSource` and `LeagueClient`, the command registry, one command per file: `build.get`, `data.status`, `champselect.state`), `stronk-data` (`DirectorySource`), `stronk-lcu` (lockfile, typed session models, HTTPS client) and `stronk-cli` (`stronk-core commands`, `stronk-core run <id> --params`). `src-tauri` joins the workspace outside `default-members`, so `just check` builds without GTK and CI builds the shell. `tools/checks/rust_layers.py` checks the crate graph points inward (in `just arch`).
  - Commands take JSON, are validated into typed params (`deny_unknown_fields`) and return a typed result or a `CommandError` with a stable code. A proptest fuzzes every command with arbitrary JSON: never a panic. Clippy denies `unwrap`, `expect`, `panic!`, `todo!`, `unimplemented!` and indexing outside tests; `unsafe` is forbidden.
  - Ports are synchronous for now: the CLI is synchronous and Tauri can run blocking calls off its main thread. The champion-select watcher (websocket, reconnects) is the point to move to `tokio`.
  - `DirectorySource` verifies the manifest's minisign signature against the app's key, checks the signed trusted comment names the manifest's patch and run (a manifest can't be replayed under another patch), then each file's size and sha256, and that the build describes the key asked for. Tests run on `fixtures/data`, the fixture pipeline's signed output (80 build files, 624 KB) with its throwaway public key `fixtures/data.pub`, refreshed by `just fixture-data`.
  - `LcuClient` trusts exactly one root certificate given by the caller. `tools/lcu-mock` writes its own. Riot's root certificate for the real client is not in the repository yet: it gets added from a verifiable source, with attribution, before the app talks to a real client.
- **Consequences:** every entry point (CLI now, Tauri next) goes through the same registry, ports and verification. The real League client can't be used until its root certificate lands.

### ADR-041 · UI: Svelte 5 behind a typed Backend port, MockBackend first

- **Context:** the UI must run in a plain browser and in tests without the core, never call Tauri directly (AGENTS.md, rule 6), and keep one serializable state.
- **Decision:** `app/ui` is Svelte 5 (runes) with Vite and strict TypeScript, in the pnpm workspace, versions pinned. `lib/backend/backend.ts` is the `Backend` port: one typed `run(id, params)` whose ids, params and results mirror the Rust registry, returning a result or a `CommandError` with the core's codes. `MockBackend` replays scenarios (`ranked-jungle`, the same steps as lcu-mock's session with the signed fixture builds; `no-client`; `bad-data`). `lib/state/app.svelte.ts` holds the single state and the only function that changes it; a build is fetched as soon as a champion is hovered and reused at lock-in. Colors, spacing and type come from `lib/ui/tokens.css` (light and dark). Vitest with Testing Library runs in `just test`, svelte-check in `just typecheck`; `just app-mock` serves the mock in a browser. Playwright is installed for screenshots now and the end-to-end suite later in M3.
- **Consequences:** the port's types are hand-written until the Tauri shell generates them with tauri-specta; then `TauriBackend` uses the generated bindings and the hand-written types become a check against them. Rune and item ids are shown raw until the app reads names from Data Dragon.

### ADR-042 · Trusting the League client: Riot's CA with an explicit check; Windows builds; scrubbed recordings

- **Context:** the League client runs on Windows; WSL2 can't reach its `127.0.0.1`. Riot publishes the client's CA for the Game Client API (https://static.developer.riotgames.com/docs/lol/riotgames.pem), but it is an X.509 v1 certificate without extensions, signed with SHA-1, which rustls' standard verifier (webpki) rejects. Testing the app also needs a real champion-select recording without anyone's personal data.
- **Decision:**
  - `stronk-lcu` trusts Riot's CA (embedded; source and sha256 in docs/security.md and ATTRIBUTION.md) through its own verifier: the presented certificate must be signed directly by the trusted root (SHA-1/RSA accepted there only), within its validity; no name check, since connections go to the 127.0.0.1 literal only. A pinned certificate (`--lcu-pin`, `STRONK_LCU_PIN`) is the fallback if the real client's certificate doesn't validate; every rejection names the certificate presented. `tools/lcu_mock` keeps its own root (`--lcu-cert`).
  - Transport: `reqwest` (blocking, `rustls-no-provider`) with the verifier's rustls `ClientConfig` passed in whole (`tls_backend_preconfigured`, which reqwest 0.13 calls what was `use_preconfigured_tls`); the champion-select watcher will use `tokio-tungstenite` with the same config as `Connector::Rustls`. No blocker: verifier, reqwest and tokio-tungstenite share one rustls (0.23.46), checked by `cargo tree` and by a test that builds the WebSocket connector from the verifier's config. A first version did its own GETs over rustls because ureq takes no custom verifier; it is gone, so no HTTP parser of our own to maintain or fuzz. reqwest ignores its own TLS settings once a config is preconfigured, so every TLS decision is in that one config.
  - The exception stays in its box: only `LcuClient` gets the verifier, and it has no constructor that takes a host (always `127.0.0.1`). `crates/lcu/tests/trust.rs` runs a real TLS server: a certificate from the trusted root is accepted; one from another root, an expired one, and a wrong pin are rejected, each error naming the certificate; and with an LCU client alive in the same process, a standard client rejects a host whose certificate chains to a root it trusts but names another host (`NotValidForName`), and a client with default trust rejects it outright (checked to fail when the LCU verifier is put into the standard client). `tools/checks/rust_layers.py` (in `just arch`) fails if `.dangerous()` or `danger_accept_invalid_*` appears anywhere but `crates/lcu/src/tls.rs`.
  - CI builds and tests on `windows-latest` (UI tests and build, core tests, shell lint and build, the core and recorder against lcu-mock); `.gitattributes` keeps signed and hashed files byte-exact on every platform. docs/windows.md is the guide for building and running natively.
  - `stronk-core record-champselect` polls the session until a champion select starts and ends, keeps each distinct state as a step in lcu-mock's format, and saves only an allowlist of fields (`scrub.rs`); it refuses to save when anything still looks like an identifier (personal key names, UUIDs, long tokens, `name#tag`). The same rules run over every committed session in `tools/lcu_mock/tests/test_sessions_scrubbed.py`, and an end-to-end test records a mock session seeded with PUUIDs, names and chat credentials and checks none survive.
- **Consequences:** the first Windows run (2026-10-18, custom game) connected with the default trust, Riot's CA, and recorded `tools/lcu_mock/sessions/custom-2026-10-19.json` (5 steps, lobby to game start; clean by the identifier rules); the core replays it end to end. The pin fallback stays available but unused.
