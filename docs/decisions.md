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
  - Transport: `reqwest` (blocking, `rustls-no-provider`) with the verifier's rustls `ClientConfig` passed in whole (`tls_backend_preconfigured`, which reqwest 0.13 calls what was `use_preconfigured_tls`); the champion-select watcher (ADR-044) runs `tokio-tungstenite` over a TLS stream opened with `tokio-rustls` and the same config. No blocker: verifier, reqwest, tokio-rustls and tokio-tungstenite share one rustls (0.23.46), checked by `cargo tree`. tokio-tungstenite's own `Connector::Rustls` takes the config too, but needs its internal `__rustls-tls` feature, so the watcher opens TLS itself and runs the websocket handshake on that stream (`client_async`), with public features only. A first version did its own GETs over rustls because ureq takes no custom verifier; it is gone, so no HTTP parser of our own to maintain or fuzz. reqwest ignores its own TLS settings once a config is preconfigured, so every TLS decision is in that one config.
  - The exception stays in its box: only `LcuClient` gets the verifier, and it has no constructor that takes a host (always `127.0.0.1`). `crates/lcu/tests/trust.rs` runs a real TLS server: a certificate from the trusted root is accepted; one from another root, an expired one, and a wrong pin are rejected, each error naming the certificate; and with an LCU client alive in the same process, a standard client rejects a host whose certificate chains to a root it trusts but names another host (`NotValidForName`), and a client with default trust rejects it outright (checked to fail when the LCU verifier is put into the standard client). `tools/checks/rust_layers.py` (in `just arch`) fails if `.dangerous()` or `danger_accept_invalid_*` appears anywhere but `crates/lcu/src/tls.rs`.
  - CI builds and tests on `windows-latest` (UI tests and build, core tests, shell lint and build, the core and recorder against lcu-mock); `.gitattributes` keeps signed and hashed files byte-exact on every platform. docs/windows.md is the guide for building and running natively.
  - `stronk-core record-champselect` polls the session until a champion select starts and ends, keeps each distinct state as a step in lcu-mock's format, and saves only an allowlist of fields (`scrub.rs`); it refuses to save when anything still looks like an identifier (personal key names, UUIDs, long tokens, `name#tag`). The same rules run over every committed session in `tools/lcu_mock/tests/test_sessions_scrubbed.py`, and an end-to-end test records a mock session seeded with PUUIDs, names and chat credentials and checks none survive.
- **Consequences:** the first Windows run (2026-10-18, custom game) connected with the default trust, Riot's CA, and recorded `tools/lcu_mock/sessions/custom-2026-10-19.json` (5 steps, lobby to game start; clean by the identifier rules); the core replays it end to end. The pin fallback stays available but unused.

### ADR-043 · What the app imports: most played unless clearly better, whole combinations, never the player's own

- **Context:** at 22,954 games no comparison survives FDR (ADR-036, ADR-039), so the data rarely says one option beats another. The app still has to import something useful, and must never damage what the player set up.
- **Decision:**
  - *Choice.* At each decision the app imports the **popular** option: the most played whole combination, not per-slot maxima. Runes: the most played full page (`RuneOption.games`, games with exactly that page; each keystone's page is the page most played with it, so the most played page overall is among them). Spells: the most played pair, whichever key each spell was on (`SpellOption.games`). Items: per slot, the most picked item (`ItemOption.picks`). An option replaces the popular one only when it is **clearly better**: claimable (a number, neither `low_sample` nor `low_overlap`), compared head to head with the popular option (`comparison.versus` is the popular option's id), positive (`comparison.wpa` > 0) and surviving FDR (no `no_clear_difference`). Among several, the largest `comparison.wpa` wins. The app needs no threshold of its own: the pipeline's FDR decision is in the flags.
  - *Contract.* build.v1 gains optional fields for this (no version change, contracts/README.md): `RuneOption.games`, `ItemOption.picks`, `SpellOption.games`, and `comparison` (`versus`, `wpa`, `q`) on rune and item options. `publish` now writes spell pairs (the five most played, in their usual key order; no WPA yet).
  - *Writing.* Stronk writes only its own rune page and its own item set: a page or set is Stronk's when its name starts with `Stronk: `. An existing Stronk page is replaced; the player's pages are never edited or deleted; when there is no room for a page without deleting one of the player's, the import says so and writes no page. The item set document is read as raw JSON and only its outline parsed (each set's `title`): the player's sets are written back byte for byte, unknown fields included, and the other top-level members keep their order and raw values. If reading or parsing the current document fails, the item set is skipped and nothing is written; the rest of the import goes ahead. Before each write the exact document read is saved locally (`item-sets-<time>.json` in `STRONK_BACKUP_DIR`, by default `%APPDATA%\stronk\backups` or `~/.local/share/stronk/backups`; the newest 20 kept), and the write only happens if that backup succeeded. `item_sets.restore` (CLI: `stronk-core restore-item-sets <file>`, without a file it lists them via `item_sets.backups`) puts a backup back byte for byte: it backs up the current sets first so a restore can be undone, writes nothing when the client can't be read or the file isn't an item set document, and refuses a backup whose `accountId` differs from the account logged in. Spells: Flash stays on the key it is on now (D or F); with no Flash selected, the chosen pair's usual order is kept, and a spell already on one key stays there.
  - *When.* Auto-import on lock-in is a setting, off by default; the build view has an Import button either way.
  - *UI.* Each imported choice is labelled "Popular", or "Clearly better" with its win impact against the popular option; the latter's tooltip gives the head-to-head interval (`comparison.ci`, published since this change) and the games behind the option.
- **Consequences:** imports are useful today (popular combinations) and improve by themselves as data grows and comparisons survive FDR. A page the player renames stops being Stronk's and is left alone; a page the player creates with the `Stronk: ` prefix is treated as Stronk's (documented in the UI's settings text).

### ADR-044 · Champion select over the client's websocket; reconnecting everywhere

- **Context:** the app polled `champselect.state` every second. Lock-in should be a cache hit (docs/architecture.md, "Lock-in path"), which needs to know of a hover at once; and the app must cope with the League client starting after it, or restarting.
- **Decision:**
  - `stronk_lcu::watch` owns the client's websocket: it reads the lockfile on every attempt, opens TLS with the LCU verifier's config (tokio-rustls), runs the websocket handshake on that stream, subscribes to `OnJsonApiEvent_lol-champ-select_v1_session`, and reports `Connected`, `Changed` or `Disconnected(reason)`; it reconnects with backoff (0.5 s doubling to 10 s, reset after a working connection).
  - The watcher is a trigger, not a second decoder: on each notice the caller reads the state through `champselect.state` (a local HTTPS read), so the session is decoded in one place. Blocking HTTP stays out of the async runtime: the CLI's `watch-champselect` runs the watcher on its own thread and reads on the main one; the Tauri shell emits `champselect-changed` and the UI refreshes through `run`.
  - The `Backend` port gains an optional `subscribe(onChange)`; `TauriBackend` listens to the event, `MockBackend` notifies on each step. With notices the UI polls every 5 s as a safety net, without them every second.
  - The REST client reconnects too: before each call it reads the lockfile and rebuilds the connection when the port or password changed (`connect_or_absent`), so Stronk can start before the client and survive a client restart.
  - `tools/lcu_mock` serves a minimal websocket (RFC 6455: handshake, masked client frames, pushed text frames) and sends the client's event shape on every step; `just core-e2e` runs the real `watch-champselect` through a whole champion select (each state within 2 s of the step, pushed rather than polled) and with the mock started after Stronk.
- **Consequences:** a hover reaches the UI as an event and its plan loads at once, so lock-in reuses it. The lock-in budget (`perf/budgets.toml`) can now be measured on this path; enforcing it waits for `just bench` to time it.

### ADR-045 · App work on a Windows clone; `just` runs PowerShell there

- **Context:** the League client runs on Windows, so app work moves to a native Windows clone while the pipeline stays in WSL. The `justfile` runs every recipe in `bash`, and on Windows the `bash.exe` on the path is WSL's, so no recipe ran natively.
- **Decision:** `set windows-shell` runs recipes in Windows PowerShell (`powershell.exe`, present on every Windows; PowerShell 7 is not assumed). Recipes whose bash syntax doesn't carry over get a `[windows]` twin next to an unchanged `[unix]` one: `setup`, `test` (Rust and UI only), `core` (escapes the JSON's double quotes, which Windows PowerShell drops when calling a program) and `app` (sets the `STRONK_*` variables with `$env:`, and `TAURI_APP_PATH`, since the Tauri CLI looks for its config under the working directory, `app/ui`). `lcu-mock` and `app-mock` work unchanged. Pipeline recipes have no Windows version. CI's `windows` job keeps calling the tools directly, so it doesn't depend on `just`.
- **Consequences:** the app recipes in docs/windows.md work in PowerShell; on Linux and in CI nothing changes. JSON typed at a Windows PowerShell 5.1 prompt still needs `\"`, since the shell strips the quotes before `just` sees them (docs/windows.md).

### ADR-046 · `HttpSource`: an unsigned patch index, ETag revalidation, a verified disk cache

- **Context:** over HTTP the app can't list directories to find the newest patch, and the lock-in path must never wait on the network (architecture, "Lock-in path"), yet new runs and patches have to reach the app.
- **Decision:**
  - Contract `index.v1` (new, `/index.json`): the published patches, oldest first, rewritten by `LocalPublisher` after each patch. It is not signed: it only says where to look, and every patch it names is verified by its own manifest.
  - `HttpSource` (`stronk-data`, reqwest blocking, rustls with the platform verifier): `status` reads the index and revalidates the newest patch's manifest with `If-None-Match`, then keeps that answer for five minutes; builds are read from the cache when they match the manifest's sha256, otherwise fetched, checked and cached. Every cached manifest is verified again when read, so a torn or altered cache is a miss.
  - Last valid cache: any failure (unreachable, bad signature, bad hash, broken index) keeps what verified before. The index can't move the app backwards: cached patches stay candidates for the newest, an older `generatedAt` for a cached patch is refused, and at most four patches are tried, newest first.
  - Plain `http://` only to the loopback literals `127.0.0.1` and `[::1]` (and without a proxy there); `https://` elsewhere. Not `localhost`: a name the hosts file can point anywhere, while the League client side also trusts only the `127.0.0.1` literal. One cache folder per base URL.
  - `open_source` turns the setting into a source (`http(s)://` or a directory, `dir:` optional); `stronk-core` and the shell take it from `STRONK_DATA_DIR`.
- **Consequences:** the app works offline once it has seen the data (docs/gaps.md). A withdrawn patch stays in use where it was cached until a newer one is published. The cache keeps old patches and runs' files; pruning comes when its size matters.

### ADR-047 · Names from the League client's game data

- **Context:** the real-client check (2026-10-19) showed rune, spell and item ids and the raw phase (`BAN_PICK`). Names could come from Data Dragon at publish time (a new signed file per patch) or from the running client, which serves its own game data under `/lol-game-data/assets/v1/`.
- **Decision:** names come from the client. `LeagueClient::game_names` reads `champion-summary.json`, `perkstyles.json`, `perks.json`, `summoner-spells.json` and `items.json`, keeps only ids and names, and caches them per client; the `names.get` command returns them as five id-to-name maps. The UI loads them once a champion select is seen, shows ids for anything without a name, and never reports a failure to load them (they are cosmetic). Phases and roles are worded in the UI (`labels.ts`). An import part that was skipped shows as a warning with its reason, so "all your rune pages are in use" can't pass unnoticed. `tools/lcu_mock` serves a small hand-written subset (`game_data.json`).
- **Consequences:** names are in the player's language and match the client's patch, with no new published file or network call; the plan is only shown during champion select, when the client is there anyway. A future web build viewer (no client) will need names from published data instead.

### ADR-048 · Playwright against the real core through a test bridge

- **Context:** end-to-end tests should drive the UI through a replayed champion select into real imports. The desktop shell needs WebKitGTK on Linux, which neither this machine nor `just check` has, and the shell's IPC can't be driven from a plain browser.
- **Decision:**
  - A third `Backend` adapter, `CoreBackend`, posts `{id, params}` to `/core/run`; the Vite dev server proxies `/core` to `tools/lcu_mock/core_bridge.py`, which runs `stronk-core run` per command against lcu-mock and the signed fixture data and answers in the port's `Result` shape. The bridge also exposes the test controls (`/mock/step`, `/mock/reset`, `/mock/recorded`). It listens on 127.0.0.1 only and is test tooling; the app never ships it. `?backend=core` selects it.
  - `just e2e` (in `just check`) runs Playwright in Chromium, one worker: `mock.spec.ts` covers the UI against `MockBackend` scenarios, `core.spec.ts` the UI against the real core (a replayed ranked lobby to the Lee Sin import, auto-import once on lock-in, restore after an import). The session is stepped by the test, only ever on lcu-mock; nothing scripted touches a real client.
  - Screenshots are saved to `runs/e2e/screenshots/` for review rather than compared pixel by pixel: fonts differ between machines, and a reviewer looking at them catches more than a pixel diff.
  - CI installs Playwright's Chromium before `just check`; locally `STRONK_CHROMIUM` can point at an existing Chromium instead.
- **Consequences:** the UI, the core and lcu-mock are tested together on every check. The Tauri layer itself (IPC, the `champselect-changed` event) stays covered by the `app-shell` and `windows` CI jobs and by hand on Windows. One process per command makes the bridge slower than the app, so lock-in timing is measured on the core directly (`just bench`), not here.

### ADR-049 · The champion select view shows each slot's alternatives, ranked in the core

- **Context:** the view showed only what an import writes, so with today's data (no comparison survives false discovery control, NOTES 2026-10-18) every slot read "Popular" with nothing to judge it by. The published build file already carries every option with its games, win impact, interval, flags and head-to-head comparison.
- **Decision:** `build.plan` returns, next to its choices, `alternatives`: per slot (runes, spells, each item slot) the three most played options plus the chosen one when it is rarer, with a `more` count of those left out. Each row has its share of the slot's games, games, win impact (against the most played option when compared with it, else against the alternatives), a confidence marker, `fragile`, and whether it is Stronk's choice. The rows come from `stronk_domain::select::rank`, next to `choose` and by the same rule (ADR-043): "clearly better" or "clearly worse" needs a comparison with the slot's most played option, claimable and without `no_clear_difference`; `low_sample` or `low_overlap` reads "too few games". There is one rule and no threshold of its own in the UI: `options.ts` only keys the rows, marks the player's pick and formats numbers, and the view asks for nothing besides `build.plan` (the plan also carries the build file's games, elo and region for its header). A line above the build says when nothing beats the most played build, which is what gets imported. No contract change.
- **Consequences:** the view grows with the data: more games turn "too few games" into numbers and, eventually, clear differences, with no UI change. Impact is coloured only when the difference is clear, so noise never looks like a finding, and a row reads "clearly better" exactly when `choose` could pick it. Options beyond the listed ones are counted, not shown (a first version listed them on request from `build.get`, with its own q ≤ 0.05 rule in TypeScript).

### ADR-050 · The player can import another published option, and an item fills one slot

- **Context:** with alternatives on screen (ADR-049), players want to import one of them instead of Stronk's choice. The real data also showed `build.plan` choosing slot by slot, so the most picked item could fill several slots (Lee Sin: Guardian Angel at 4, 5 and 6).
- **Decision:**
  - `build.import` takes optional picks: `runes` (a page), `spells` (a pair, any order) and `items` (`{slot, item}`). Each must be an option in the published build file for that slot, otherwise the command fails with `invalid_params` before writing anything; a pick equal to Stronk's choice keeps its label, any other is labelled `picked` (item set blocks read "Your pick"). Flash still goes on the player's key.
  - Clicking an option in the UI picks it, clicking Stronk's again or "Use Stronk's picks" drops picks. Picks are kept per champion and role in the app state, sent with every import (auto-import included, so it writes what the player chose), and the import result says when they changed since. Every option of a slot could first be shown on request; since `select::rank` (ADR-049) only the listed options are shown and the rest are counted (and since ADR-051, every option again, on request).
  - `choose_items` (domain) chooses slots in order and leaves an item already chosen out of later slots, so Stronk never repeats an item. The player may still pick the same item twice; the view says "Also in item N".
- **Consequences:** imports stay limited to published options, so the UI can't write arbitrary pages or items. A slot's most played item may differ from what Stronk imports there when it was already used earlier; the view shows both. No contract change.

### ADR-051 · Every option can be picked, and picks last until the patch changes

- **Context:** since `select::rank` (ADR-049), `build.plan` returned only each slot's three most played options and Stronk's choice, so the rest of the published options (Lee Sin real data: up to 30 per item slot) were counted but couldn't be picked; and picks lived only in the app state, so a restart dropped them.
- **Decision:**
  - `select::rank` returns every option of a slot in popularity order, each with its numbers and confidence by the same rule, and marks the short list with `listed` (the three most played, plus Stronk's choice); `more` still counts the rest. The short list stays a core decision: the UI lists `listed` rows and the player's pick, and the others behind "N more options". `build.import` is unchanged: any published option can be imported, anything else is refused.
  - Picks are saved per champion and role (`LeeSin/JUNGLE`) with the patch of the plan they were made on, in the webview's storage like the auto-import setting (`stronk.picks`, behind a `PicksStore` so tests use memory). When a plan loads, saved picks come back only for the same patch and only those still among its options; saving drops picks made on another patch, so storage holds one patch at most. Storage is outside input: entries that aren't picks are ignored.
- **Consequences:** `build.plan` grows with the data (Lee Sin jungle on the real data: about 27 KB of JSON for 142 options, well inside the lock-in budget since the plan loads on hover). Picks are per machine and webview profile, not synced; a new patch starts from Stronk's choices. No contract change (`build.plan` and `build.import` are core commands, not published contracts).

### ADR-052 · Icons from the League client, through the core as data URLs

- **Context:** the champion select view showed names only. Icons could come from Data Dragon or Community Dragon (a third-party CDN, a network call per icon, and assets to attribute), or from the running client, which serves its own game data images under `/lol-game-data/assets/`. The webview can't fetch those itself: the client wants the lockfile's password and presents Riot's certificate, which only `LcuClient` trusts (docs/security.md).
- **Decision:**
  - `icons.get` takes ids by kind (champions, rune trees, runes, spells, items; at most 200 per call) and returns `data:` URLs. `LcuClient` reads each icon's path from the same game data documents as names (`squarePortraitPath` for champions, `iconPath` for the rest), keeps only paths under `/lol-game-data/assets/` (no `..`, query, fragment, `%` or backslash), fetches it with the client's credentials, and keeps it only if it is a PNG, JPEG or WebP by its first bytes and at most 512 KiB. A missing or refused icon is left out; a client that stops answering fails the call.
  - The UI asks once per id for what is on screen (the champion, every listed option), after the plan and any auto-import, so icons never delay an import. Like names they are cosmetic: a failure is never reported, and a plain square with the name's first letter stands in. The app's CSP adds `img-src 'self' data:`.
  - lcu-mock gives every champion the client's `squarePortraitPath` and `game_data.json` an `iconPath` per entry, and serves a generated PNG at each (a square in a colour taken from the path); `MockBackend` answers with SVG placeholders showing the name's initials. No Riot artwork is committed.
- **Consequences:** icons match the client's patch, with no network call, no published file and nothing to attribute. Each image crosses the IPC once as base64 (a few kilobytes each, a few dozen per champion). A future web build viewer (no client) will need icons from elsewhere, as for names (ADR-047).

### ADR-053 · The UI's command types are generated from the registry, not with tauri-specta

- **Context:** ADR-041 kept the `Backend` port's types hand-written until tauri-specta could generate them once the shell built (it does on Windows, ADR-045). But the shell has one IPC command, `run(id, params)`, so tauri-specta alone types every call as plain JSON: the per-command types have to come from the registry anyway. specta (2.0.0-rc.25, like tauri-specta) refuses `u64`/`i64` without an override per field, exports `f64` as `number | null`, and needs a second release candidate to follow serde's `flatten`, `tag` and `rename_all`.
- **Decision:** every command's params and result derive `schemars::JsonSchema` (1.x, stable, follows serde's attributes); `Command::new` requires it, so a command can't be registered untyped. `Registry::schema` writes them as one JSON Schema (draft 7): a `{params, result}` property per command id, named types and `CommandError` in `definitions`; `stronk-core schema` prints it. `contracts/commands_codegen.py` turns it into `app/ui/src/lib/backend/commands.ts` with `json2ts`, the tool the contracts already use, and `just gen-check` (in `just check`) fails when the file is stale. `build.get` points at the contract's own `BuildV1.Build` rather than repeating it. `backend.ts` names the generated types for the UI and keeps generic forms of the option types (`Choice<T>`, `Row<T>`, `Ranked<T>`), each checked at compile time to equal its generated copies. The shell is unchanged: one `run` command and the `champselect-changed` event.
- **Consequences:** a command's Rust types are the only definition; changing one and forgetting `just gen` fails the check. Domain types carry a `JsonSchema` derive, a compile-time trait with no I/O. Generic types get generated names from their parameter (`PageRow`, `TupleOfInt64AndInt64Row`), which the UI only sees through `backend.ts`. The same schema can describe the commands to other entry points later (an MCP server, docs/roadmap.md).

### ADR-054 · A static product site on Cloudflare Workers, apart from the web build viewer

- **Context:** Riot grants a production key only to a product with a verified website (a text string in `riot.txt` at the site's root), and reviews its privacy policy and terms; a GitHub repository is not accepted instead. ADR-018 planned riot.txt on the web build viewer, which doesn't exist yet. The owner has a personal domain.
- **Decision:** `site/` holds plain HTML and one stylesheet in `public/` (product page, method, privacy policy, terms, 404), no build step and no JavaScript; every page carries Riot's legal notice in its footer. It is served at `stronk.christophercastel.com` by Cloudflare Workers static assets (`site/wrangler.jsonc`; Cloudflare builds `main` with root directory `site` and `npx wrangler deploy`), next to the R2 storage planned for the data. `just site` previews it on 127.0.0.1 with the same URL handling. The page's screenshot is the app on real data, without Riot artwork. The web build viewer (ADR-018) can join the site later; riot.txt no longer waits for it.
- **Consequences:** the production key application no longer waits on M4's viewer. The site's claims about the app (what it reads and writes, what stays local) must change with the app; they mirror docs/production-key.md. A domain change means a new Riot verification and, for the data, a new URL in the app.

### ADR-055 · Patch backtest, stability half: do contrasts keep their sign on the next patch?

- **Context:** M5 plans patch backtests with the floor `backtest.direction_share`: items Riot nerfed or buffed should move the right way, unchanged ones stay put (docs/wpa-method.md, section 6). That needs a list of each patch's changes, which the pipeline doesn't have. Meanwhile a second patch was crawled (16.21, 23,675 games, EUW, KR, NA, like 16.20's 22,954), and the simplest question it answers is whether the estimates replicate at all.
- **Decision:** `backtest.run` (`just backtest <earlier> <later>`) reads two estimate files and pairs every head-to-head contrast (option against its point's most played, ADR-036) that both patches measured with the same most played option. It reports the share whose `contrast` has the same sign on both (`backtest.sign_agreement`), the same among contrasts whose earlier interval excludes zero (`clear_sign_agreement`), correlation and slope of later on earlier, and what happened to each claim (q at most the FDR) of the earlier patch. Metrics go to `metrics/out/backtest.json`; `backtest.sign_agreement` is a pending floor, and `backtest.direction_share` keeps its meaning for the change half.
- **Measured (2026-10-28, 16.20 -> 16.21, each patch's own win probability model):**

  | | v1 | overlap-weighted | class pooling |
  |---|---|---|---|
  | paired contrasts | 84 | 84 | 228 |
  | sign agreement | 0.655 | 0.643 | 0.570 |
  | among clear on 16.20 | 7 of 8 | 7 of 9 | 16 of 22 |
  | correlation / slope | 0.31 / 0.38 | 0.26 / 0.32 | 0.16 / 0.18 |
  | claims 16.20 -> held / clear again | 0 | 0 | 1 -> 1 / 0 |

  The 16.20 win probability model on 16.21's test matches: log loss 0.5188 against 0.5183 for a 16.21 model (difference 0.0005, interval -0.0003 to 0.0013).
- **Consequences:** signal is real but weak at this size: about a third of an effect carries over, so most of one patch's estimate is noise; v1 replicates at least as well as the overlap-weighted estimator (it stays the default, ADR-037), and class pooling worst (it stays off the default, ADR-039). `crawl-all-16.21` is pinned and the weekly job (`just floors-full`, about 3.5 minutes more) reruns the backtest; `backtest.sign_agreement` is enforced there at min 0.55 (owner's approval), the bottom of a 95% interval at 84 contrasts. The change half is deferred until there is more data per patch (16.21 changed four items, about five estimates cover them). Win probability transfers across one patch, so its model can be trained on several.

### ADR-056 · The champion select view: one line per slot, colour only for clear differences

- **Context:** a UI review (2026-10-28) found the view long (about 1,600 px for one champion, all options of every slot open), labelled four ways at once (a chip per card, a "Stronk's pick" or "Your pick" badge, a status per row, the highlight), with "No clear difference" on most rows and a win percentage on every row, which invites comparing numbers the confidence rule says are noise. Badges squeezed names into broken lines ("Smite · Flash" over three lines, a card overflowing). The rune page showed twice, the patch twice, and a missing client showed as a raw error.
- **Decision:**
  - The build is a list, one line per slot (runes, spells, items): the option the import writes with its icons, the rest of a rune page on a second line, and a note only when it says something: "▲ +2.1% vs Black Cleaver" when Stronk's choice clearly beats the most played option (the interval and games in its tooltip), or "Your pick" (numbers on every line since, see the amendment). A slot with more than one option opens on click to its list; closed by default.
  - In a slot's list one marker says what gets imported (a filled radio and the highlight); a number shows only for "clearly better" (▲, green) or "clearly worse" (▼, red); a "too few games" option is greyed with "few games" by its share; "Stronk's pick" shows only next to Stronk's choice when the player picked another. No status text for the most played option or for no clear difference.
  - The champion line carries Import and "Use Stronk's picks"; the data's patch, games, elo and region follow once, with "How Stronk picks" as a tooltip instead of a paragraph.
  - Waiting says what Stronk waits for ("Builds for patch 16.20 are ready"); a missing client (`unavailable` and the lockfile or client message) reads "League of Legends isn't open, start it and Stronk connects on its own", with the error as its tooltip, not as an alert. Other errors still show as alerts.
  - One column, at most 720 px, down to a 420 px window (slot names move above the value); a Playwright test checks there is no sideways scrolling there.
- **Amended the same day (owner: "as transparent as possible to the player"):** hiding the numbers left nothing to judge on real data, where no comparison passes false discovery control. Every estimate now shows, with its uncertainty and what it is measured against: "+0.4% ± 1.0 vs others" (an option not compared with the most played one) or "−0.9% ± 1.5" (against the most played), grey; colour and ▲ or ▼ stay for clear differences ("▲ +2.1% ± 1.3 vs Black Cleaver"). Each slot's line shows the number of the option the import writes; each number's tooltip spells out its interval, what it's against and how to read it. "±" is half the 95% interval's width.
- **Consequences:** the whole build fits on one screen; looking at alternatives is one click per slot. The rule is unchanged (`select::rank`, ADR-049); `options.ts` gains `verdict`, `figure`, `explain`, `mostPlayed` and `selected`. Stat shards no longer show (they are part of every listed page and rarely differ). No contract or command change.

### ADR-057 · Runes and shards row by row, and no middle dots

- **Context:** the owner asked for the app to be as transparent as possible: WPA for each rune and stat shard, not only for the page. The pipeline estimated the keystone only (slot 0) and published, per keystone, the page most played with it, so a page's number was its keystone's and nothing told the player whether Triumph or Presence of Mind, or which shards, mattered. The owner also asked for no middle dots ("·") as separators.
- **Decision:**
  - `extract` adds one champion-select decision per row of the page after the keystone: each primary row (slot `tree * 10 + row`, option the rune), the secondary tree's two runes as one pair (slot `tree * 10 + 5`, option `"low,high"`, since the client lets the player take any two rows), and each stat shard row (slot `50000 + row`). A row compares only runes of the same tree and row, as the client offers them. `wpa.estimate` handles them like any slot (overlap, bootstrap, shrinkage, comparison with the row's most played choice, FDR across the patch).
  - `build.v1` gains an optional `runeChoices` (kind, tree, row, perks, games, the usual numbers and a comparison whose `versus` is one rune or the pair), published by `publish`; no version bump, as for ADR-043's optional fields. `fixtures/data` is regenerated.
  - `build.plan` adds `alternatives.rune_rows`, each row ranked by `select::rank` like any slot, the choice in Stronk's page marked chosen. Imports still write whole published pages (ADR-043): the rows are for reading. The view shows, inside the runes slot, "Rune by rune": the rows of the page the import writes (its primary tree's rows, its secondary pairs, the three shard rows), each choice with its share, games and number; the page's choice highlighted; not clickable.
  - Separators: a `Facts` component puts short facts side by side with a thin rule between them (champion, role and phase; patch, games, elo and region; share, games, few games, fragile); pairs read "Smite + Flash"; a page reads "Conqueror (Precision + Inspiration)", the rest of its runes separated by commas.
- **Consequences:** about seven more decisions per player (14 instead of about 7), so extract tables and `wpa.estimate` roughly double in size and time; the fixture pipeline stays far inside its budget. These numbers share the keystone's limitation (decided at win probability 0.5, docs/wpa-method.md, section 2). Picking single runes is not possible: a pick is still a whole page. Real data must be rebuilt (`just data-real`) for the rows to appear; older data simply has none.

### ADR-058 · The rune page drawn as the client's trees

- **Context:** ADR-057 listed the page row by row; the owner found a tree like the League client's much clearer. Drawing one needs every row of every tree, including runes nobody in the data played, which the published data can't give (it only has what was played) but the client does: `perkstyles.json` has each tree's `slots` (`kKeyStone`, three `kMixedRegularSplashable`, three `kStatMod`).
- **Decision:**
  - `LcuClient` reads the slots with the names: `names.get` gains `rune_trees` (each tree's rows, keystones first; a tree whose layout isn't four rows is left out) and `shard_rows` (offense, flex, defense). lcu-mock's `game_data.json` gains the trees' slots and the missing rune names.
  - The runes slot opens on the page as the client draws it: the primary tree's keystones and three rows on one side, the secondary tree's rows and the shard rows on the other. Every rune shows its icon with its number under it ("+0.2%", "± 0.8"; ▲ or ▼ and colour when clear; "few" with too few games; nothing when nobody took it); the page's nine choices are lit, the rest greyed. The secondary pair is one decision (ADR-057), so its number shows once under that tree. A keystone with a published page is a button that picks that page; everything else is for reading. The full pages stay listed below ("Pages by keystone").
  - Every rune of the trees has its icon asked for, played or not. Without a layout (no names from the client, or an older one), the row-by-row list of ADR-057 shows instead.
  - Each rune is labelled for screen readers with its name and number.
- **Consequences:** the page reads like the client's, with nothing added the client doesn't already show besides the numbers. One more call's worth of icons (about seventy runes). The layout follows the player's own client, so a new rune or a reworked tree shows as soon as the client has it.

### ADR-059 · The build as one board, and rune pages built rune by rune

- **Context:** the owner wanted the build to read like the client's rune trees or Coachless: everything on screen at once, no lists to open and scroll, and the page built by clicking runes. Until now the runes slot opened onto a list of published pages (ADR-049 to ADR-058), and imports were limited to published options (ADR-050).
- **Decision:**
  - **A board.** Runes on the left (the primary tree with its keystones and rows, the secondary tree, the shards, then summoner spells), items on the right (one panel per slot); one column under 900 px. Every option is an icon with its numbers under it (`Cell`): win impact, grey unless the difference is clear (green ▲, red ▼, owner's choice, against colouring by sign), a five-bar precision mark from the 95% interval's half-width (five at ±0.5 points or less, one above ±3.5), and its games. Lit means imported; a dot marks Stronk's choice when the player picked another. A slot shows the options played in at least 2% of its games, its short list and the pick; the rest are behind "+N" in the same row. The window opens at 1200 by 900.
  - **Runes built by clicking** (owner's choice). Each tree panel has the other trees' icons to switch to: a new primary tree brings the page most played with it (shards kept), else its first rune per row; a new secondary tree brings its most played pair. A keystone or primary rune replaces its row's; a secondary rune replaces the one in its row, else the one picked before the other, as the client does; a shard replaces its row's. Keystones carry the numbers of their pages, primary runes and shards their rows' (ADR-057), and the secondary pair its own under that tree.
  - **Imports.** `build.import` takes any rune page the client's own layout allows (`select::valid_page`: a keystone and one rune per primary row, two runes from two different rows of another tree, one shard per row), checked against `names.get`'s trees before anything is written; spells and items stay limited to published options. This replaces ADR-050's rule for runes only. Saved picks keep a whole built page. Without the client's layout the runes panel falls back to picking whole published pages.
  - The item set's block titles lose their middle dot: "Item 1: Your pick".
- **Consequences:** the whole build fits a 1200 by 900 window with no scrolling for most champions; the app's window is larger by default. A built page may have no page-level number (nobody played exactly it): each rune still shows its own. The list components (`OptionList`, `RuneTree`) are gone.

### ADR-060 · Stronk's own look: what changes first, intervals instead of stat stacks

- **Context:** the owner found the board of ADR-059 too close to Coachless: a grid of icons with a stack of small stats under each (win impact, a five-bar precision mark, games). What only Stronk has is a measured effect with its uncertainty, and the few places it departs from the most played build; the board didn't lead with either.
- **Decision:**
  - **What Stronk changes, first.** Under the champion, a strip names each slot where Stronk imports a clearly better option instead of the most played one: the slot, the option, the one it beats, and its wins per 100 games with the ± (`changes` in `options.ts`). With none: "The most played build. No option is clearly better yet." A one-line legend for the cells follows.
  - **One cell, three marks.** A ring around the icon filled by its share of games (an SVG arc, accent when imported); the estimate under it, ▲ or ▼ and colour only when clear. Too few games: "few games". No estimate (spells): nothing. The precision bars and the game count under each icon are gone. The uncertainty and game counts are not on screen: the ring already shows how much an option is played and "few games" flags the thin ones, and the range stays in the option's accessible name for screen readers. Headers, the strip and the secondary pair show the estimate alone ("+2.1 wins per 100"). This amends ADR-056 (every estimate shown with its ±) at the owner's request: an error range isn't something players read directly. Earlier versions were dropped as too busy: the interval as a line against zero, the ± under each number, and a tooltip on each option with its range, verdict and games.
  - **Wins per 100 games.** Win impact reads "+2.1 ± 1.3 wins per 100", the same percentage points as before, in the player's terms.
  - **One scale per row, the most played option at 0.** Every number on the board is the option's head-to-head difference with its row's most played option, in wins per 100 games, and that option reads 0 (nothing for spells, which have no estimate). An option without that comparison has no number. Short of games (`too_few_games`, or never played in the data) it shows nothing, and the legend says "no number: too few games" (owner's choice over labelling both "few games" and "not played"); "too few to compare" and "almost always" say why an option with plenty of games has none. Spells, which have no estimates, say "Not measured yet" in their header. Every option's box is the same size (64 px, 56 px for shards, 88 px for a spell pair), so rows line up and hover frames match. The published number against the other options pooled isn't shown: each option's pool is a different mix, so those numbers can't be ranked against each other, and next to head-to-head numbers they read as the same thing (on the real client, a `low_sample` +2.4 sat beside head-to-head +1.0 and −1.7). Slot headers say what the row is compared with ("Compared with Black Cleaver"), or the clear result against it. In item rows the baseline comes first, with a thin rule before the options measured against it. What the import writes is framed (accent border and tint) as well as lit, so the pick reads at a glance; a tile on the baseline was tried and dropped, as it read as a pick. The most played option flagged `low_overlap` (nearly everyone takes it: Triumph on Lee Sin, 97%) reads "almost always" (`Confidence::AlmostAlways`), not "few games". Secondary runes carry the numbers of the pair clicking them makes, since pairs are what's measured (ADR-057); a caption under the tree says so. The most played option's own number against the rest stays hidden: on the real client, Coup de Grace (Stronk's pick) read −2.4 with a range below zero, as if Stronk picked a losing rune.
- **Consequences:** the board shows one number per option, and colour alone says whether a difference is clear; how wide the range is no longer shows anywhere on screen. Popularity reads as the ring rather than a number. The owner may revert or iterate on parts of it; the build path for items (one row of steps, a forest plot per slot) is the next candidate.

### ADR-061 · The board checked on real data

- **Context:** the mock data behind `just e2e` is tidy, and the bugs the owner found on the real client came from shapes it doesn't have: options nearly everyone takes read "few games", rows mixed numbers against different options, secondary pairs nobody played, a board with one game. Those were caught by the owner's screenshots, after the change.
- **Decision:**
  - `just e2e-real [Champion/ROLE,…] [data] [key]`, outside `just check` (CI has no real data), run after any UI change.
  - `tools/checks/board_sanity.py` runs `build.plan` for every champion and role of the data through one `stronk-core serve`, and fails on what a player must not see: "few games" under an option with 300 games or more (`few-games-false`), "almost always" under one with fewer (`almost-always-few-games`), a baseline that isn't first, a clear result off the row's scale, a slot with no pick or a choice that isn't the chosen row. Numbers against another option than the most played, which the board leaves blank, are reported.
  - `tools/lcu_mock/real_session.py` writes a champion select session over the data: one locked-in step per pick (by default a popular champion per role and the board with the fewest games), champions and every item name from the crawl's static data, which a session can now lay over lcu-mock's game data (`game_data`). `core_bridge.py` takes `--data` and `--key`.
  - `e2e/real.spec.ts` (`playwright.real.config.ts`, 1200 by 900) locks in each pick against the real core and lcu-mock, saves the board to `runs/e2e-real/screenshots/`, and checks it: no leaked values (NaN, undefined), only a number, 0, "few games" or "almost always" under an option, one pick lit per item slot, nine runes, one spell pair, no sideways scroll, no option named by its id, every option of a kind the same size and none spilling out of its box.
- **Consequences:** an agent sees the board as the data makes it before the owner does. Icons are lcu-mock's placeholders and names come from the crawl, so the look of icons still needs the real client. Its first run found that "almost always" (ADR-060) showed on boards with one game, fixed by requiring 300 games (`ENOUGH_GAMES`), and 43 options with 300 or more games but too few comparable decisions reading "few games": they read "too few to compare" (`Confidence::TooFewToCompare`, owner's wording), "few games" staying for options under 300 games.

### ADR-062 · Stronk's own design: the build sheet

- **Context:** the owner wanted a design with its own identity, enjoyable, easy to use and good looking, that shows everything needed without clutter. The board of ADR-059 put every slot's options on screen at once as icons with marks under them: it looked like Coachless, it read as icon soup on real data (rows of letters and "few games"), and nothing on it said what the build actually was by name.
- **Decision:**
  - **The build sheet.** On the left, the build the import writes, one row per slot with its pick by name (Conqueror, with its trees under it; Smite + Flash; Item 1 Eclipse…), a green "▲ +2.1" where Stronk takes a clearly better option than the most played one (only while Stronk's pick is the one imported), "Your pick" where the player changed it, and what Stronk changes above. On a board with under 300 games, an amber line says so first.
  - **One slot open beside it.** Each row of the sheet is a tab (arrow keys move between them); the open slot fills the right: the rune tree editor (ADR-058, ADR-059) for runes, and for spells and items a ranked list (`OptionTable`): each option's name, its wins per 100 games against the baseline (the most played option, tagged "baseline" at 0), its share of games as a bar, and its games (owner's request; under the name in a narrow window); colour only for a clear result, nothing when short of games, "in item 3" on an item the build already has elsewhere. Rarely played options are behind "Show N more". The patch, games and the legend close the panel. It opens on the first slot Stronk changes, else the runes. Under 900 px the two stack.
  - **The look.** Ink surfaces with a forge-amber accent, dark by default as the League client is, a light variant from the system's setting; the wordmark STRONK in spaced capitals with an amber bar. The picked option is outlined in amber wherever it shows.
  - `ChoicePanel` is gone; `just e2e-real` opens every tab of the sheet and checks each slot, and saves dark screenshots (one in light).
- **Amended:** the sheet and the open slot are as tall as each other (their bottoms line up), the slot's patch line and legend closing it at its bottom however short the slot; `just e2e-real` checks they end on the same line.
- **Consequences:** the whole build reads in a second, by name, and alternatives read as a list with aligned numbers instead of icons with marks. Alternatives show one slot at a time, a click away, where ADR-059 showed every slot's at once. Supersedes ADR-059's board layout; its rune building and imports stay.

### ADR-063 · Runes drawn as the client's trees, picks named

- **Context:** after the build sheet (ADR-062) the owner liked the item lists but not the rune and shard selection, the icon grid of ADR-058 and ADR-059. Two list designs followed, a row of wide cards per rune row and then three columns of named lines: easier to read, but the owner wants the client's rune tree, because players already know it.
- **Decision:**
  - The client's layout: the primary tree (keystones larger, then three rows), the secondary tree (three rows) and the shards (Offense, Flex, Defense) side by side, each tree on its own surface with its icon, name and role, and the other trees as icons beside the name (named for screen readers). Every rune a round icon (`Rune`), greyed until picked; a picked rune in colour, ringed and glowing in amber, as the client lights it. A rune's name shows on hover, as in the client.
  - What Stronk adds: under each row, the picked rune's name with its number (or "too few to compare") and its share of games, so the page reads without knowing the icons; under every other rune, its number against the row's most played rune when it has one (the picked one's is on the name line, not twice). Secondary runes carry their pair's numbers, as before.
  - The client's rules and the building of ADR-059 are unchanged; the panel's own title is left out for runes; the page fits 1200 by 900. `reading` in `options.ts` gives a rune's number or note to both the icon and the name line. `Cell` is gone; `just e2e-real` checks that runes line up and nothing spills out.
- **Consequences:** the page looks like the client's and reads by name where it matters, the picks. Unpicked runes are icons with a number, named only on hover; the two list designs were dropped.
- **Amended:** the owner found "almost always" added little. Three variants were rendered on the real data: nothing, the share, and "picked in 97% of games". The share won: as short as nothing, it says more ("Conqueror 97%", against "Coup de Grace 0 54%", a real choice), and the phrase spilled out of the shards column. Every pick line shows its share; an option nearly everyone takes shows no word, in the item lists too (their share column says it). The legend adds "%: share of games". `Confidence::AlmostAlways` stays in the core: it still keeps "few games" off those options and gives screen readers "almost always taken".

### ADR-064 · The rune page: the client's tree, the focused row as a list

- **Context:** the owner wasn't a fan of the tree with names and numbers under each row (ADR-063) and asked for a total redesign. Three concepts were built over one model of the page's rows and rendered on the real data: (A) the client's tree, icons only, with the focused row beside it as a list like the item lists; (B) no tree, the page as a path of named picks with the focused row's list; (C) whole pages ranked like the item lists, with A behind "Customize runes". The owner chose A: familiar like the client, read like the items.
- **Decision:**
  - `runeRows` (runeRows.ts) gives the page as rows of decisions: the keystones, the primary tree's three rows, the secondary tree's three rows and the three shard rows, each with its options in the item lists' shape (`Slot`), the rune the page has in it, and the page picking an option makes (the client's rules stay in runes.ts).
  - `RunePage`: on the left the client's tree, icons only: the primary and secondary trees side by side (each with its icon, name, role, and the other trees as icons), the shards under them in Offense, Flex and Defense; picks lit and ringed in amber, Stronk's pick marked by a dot when the player took another, names on hover. On the right the row in focus ("Precision, row 3"), as an `OptionTable`: each rune's name, baseline tag, number, share and games. Clicking a rune picks it and brings its row into focus; picking from the list does the same. The keystones are in focus first. A hint under the tree says so.
  - `OptionTable` lays itself out by its own width (a container query), so it also reads in half a panel: games under the name, the share as a figure.
  - `RunesPanel` and `Rune` are gone, and so are the unchosen concepts; `just e2e-real` brings every picked rune's row into focus and checks its list.
- **Consequences:** the tree carries no text and no numbers, so it looks like the client's; the numbers are one click away, a row at a time, in the same form as the items. Supersedes ADR-063's layout.
- **Amended (owner's review):** runes at the item icons' size (32 px; keystones 36 px as the client makes them larger, shards 28 px; a first try at 48 and 40 px was too big), with room around them so a picked rune's ring stays inside the focused row's band; the list is headed by its tree ("Precision", "Precision keystones", "Offense shard") without the row number, which players know (screen readers still get "Precision, row 3"); long names wrap in a narrow list, their tags going under them ("Legend: Alacrity" was cut beside "Stronk's pick"). Clicking a rune already on the page only brings its row into focus. Fixed with it: `samePage` read the same page as another when its two secondary runes came in the other order (the data gives Cosmic Insight then Magical Footwear, the app keeps row order), so looking at a row marked the page "Your pick"; `just e2e-real` now fails if looking through the slots leaves any "your pick".
- **Amended (owner's review):** the secondary runes are one decision, measured as a pair, but the list split them into single runes, each showing the numbers of the pair it would make: the page's two runes showed the same games, and a pair changing both runes was in neither list. Clicking a secondary rune now brings the whole secondary tree into focus (the tree's band), and the list beside it is the tree's pairs (`runePairs`: every pair played in the tree, most played first, the page's own pair even when nobody played it), each with both icons and names ("Magical Footwear + Cosmic Insight"); picking a pair sets both runes. The tree still picks one rune at a time, as the client does. Numbers stay rare: on the 16.20 data only 24 of 727 boards have a second pair in their secondary tree with the 300 games a head-to-head needs (`min_decisions`, unchanged). `just e2e-real` checks the pair list and saves it (`<pick>-pairs.png`).

### ADR-065 · Import the best bet, claim only what's clear

- **Context:** Stronk imported the most played option unless another was clearly better (ADR-043), so on Lee Sin it kept Coup de Grace while Cut Down read +2.7 wins per 100 games (likely 0.0 to +5.6, q 0.61). The owner: if it's the best bet, Stronk should show it. Requiring a claim to be proven protects what Stronk says; it doesn't maximise wins, which is what the import is for.
- **Decision:**
  - `select::choose` takes the best bet: among the options compared head to head with the most played one and claimable (a number, neither `low_sample` nor `low_overlap`), the largest gain once shrunk toward 0 by its uncertainty (`shrunk`: `wpa × τ²/(τ²+se²)`, τ = 0.02, `se` from the 95% interval), if at least `BEST_BET_MIN` (0.005, half a win per 100 games). It is labelled `clearly_better` when it also survives false discovery control, else `best_bet` (new `Label::BestBet` and `Confidence::BestBet`). Items and spells follow the same rule (spells have no estimates, so stay popular).
  - Rune pages: the page is still chosen by its keystone, then row by row (`with_row_bets`: the primary tree's rows, the secondary pair, the shards) each row takes the rule's choice, its best bet or else its most played rune (a page's rune that trails the most played one is the worse bet). A popular page changed by a best bet is labelled by its largest. The pages' list marks the keystone's page; the rune rows mark the page's runes.
  - The app: a filled amber "Best bet" tag in the lists, an amber "Best bet +2.7" badge in the sheet and the summary (green "▲" stays for proven ones), "Best bet +2.7 wins per 100 vs Coup de Grace" in the slot header, and a legend line. The item set block reads "Best bet, +2.7% win".
  - `board_sanity` fails on a best bet not measured against the most played option.
- **Consequences:** the import follows the numbers, not only the proven ones: on the real 16.20 data, Lee Sin jungle takes Cut Down, Adaptive Force (offense shard), Profane Hydra and Voltaic Cyclosword. Best bets can change from patch to patch as estimates move; green still means proven. τ and the minimum gain are judgement calls, recorded here; changing them is a new entry.
- **Amended:** the owner asked not to show the summary of changes at the top of the sheet; it's gone, each change marked by its badge on its slot. Only the warning for a board under 300 games stays there.

### ADR-066 · The site's screenshot, rendered from the app

- **Context:** the site's screenshot showed the list board of ADR-049, and its text promised "the most played build unless something is clearly better", both out of date after the build sheet, the rune tree and best bets (ADR-062 to ADR-065). It had been taken by hand.
- **Decision:** `just site-shot` renders it: the real core on the real data with lcu-mock (`e2e/site.spec.ts` through `playwright.real.config.ts`), Lee Sin jungle locked in, the rune page open on the row of Stronk's best bet (Cut Down), in the app's dark look at 1200 px wide and twice the pixel density, clipped from the wordmark to the open slot. Icons are the game's own: `tools/lcu_mock/site_icons.py` fetches, from CommunityDragon's mirror of the client's game data, the champion's portrait, every rune, shard, tree and spell, and the items of the build, into `runs/site-icons/` (not committed), and lcu-mock serves them in place of its placeholders (`STRONK_LCU_ASSETS`); the capture fails if any icon is still a stand-in letter. The screenshot is attributed in ATTRIBUTION.md, under Riot's policy for fan projects (the site carries Riot's notice). The champion reads "Lee Sin" as the client names it. The recipe needs the network; tests don't. The home page's "What it does" and the method page describe the sheet, the rune tree and best bets; the figure fills the page's width.
- **Amended:** shrunk into the 760 px text column, the 1200 px screenshot showed at 61% (30% on a phone) and its text was unreadable. Now two pictures, each shown near its own size: the wide one (the champion to the open slot, without the app's wordmark, legend and hint, which the site explains) in a figure that breaks out of the text column up to 1120 px, and on screens up to 640 px a narrow one taken in the app's own narrow layout (the champion, the rune page and its open row), chosen by `<picture>`.
- **Amended:** two views, as the rune page and the item slots read differently: the rune page on Cut Down's row (`runes.png`) and Item 1 where Stronk takes Profane Hydra (`items.png`), each wide and for phones (`-phone`), shown in one figure at the top, switched by "Runes" and "Items" under it (radio inputs and CSS, no script; the owner wanted one slot, not a second picture under "What it does"). A video was weighed and left out: a few seconds of the app is 1 to 3 MB, over the repository's 512 KB file limit.
- **Consequences:** the picture can be refreshed with one command whenever the UI changes. It shows real numbers from the corpus, so it changes with the data.

### ADR-067 · The late items as one slot, "4+"

- **Context:** items were measured slot by slot up to the sixth, and bot laners can carry a seventh, which was not followed. The owner asked to merge items 4 to 7 as "4+". Late items are bought for the game at hand more than in a set order, and one slot at a time they split the games too thinly to compare: on the 16.20 data, Jinx's fifth item had 289 decisions and her sixth 62.
- **Decision:**
  - `extract`: items 1 to 3 keep a slot each; the fourth completed item and every later one, up to the seventh (`MAX_ITEMS`), take the late slot 4 (`LATE_SLOT`), each purchase its own decision anchored as before. A decision is now unique per player, slot and minute (it was per player and slot, which kept only the first late item); a duplicated match still counts once. One game gives several late decisions; the bootstrap resamples matches, so its intervals account for that.
  - `build.v1` gains optional `lateSlot` (4): the slot of the late items. Absent in older files, where every slot is its own and the app reads them as before.
  - `build.plan`: the late slot's choice follows the same rule as every slot (its best bet, else its most played), and `then` lists the other late items the import writes after it: the slot's options most played first, without any item another slot already has, six in all (`LATE_ITEMS`). The import recomputes it after the player's picks.
  - The import writes one block "Items 4+: <why>" with those six items, so the client shows the late options in one row.
  - The app: the sheet's last item row reads "Items 4+", its pick by name and "then …" under it; its panel lists every late item against the most played one, like any slot.
- **Consequences:** fewer, fuller late estimates, and the seventh item counts. A late number now reads as "this item among the late ones", not at a given position. Shares in the late slot are of late purchases.
