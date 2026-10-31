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
- 2026-10-17: M1 done. Live recording `fixtures/riot/euw1` (10 games, scrubbed) with `test_fixture_replay` and `just pipeline` (1.3 s); corpus `crawl-euw1-16.20` (3305 games, 33 MB) uploaded as a prerelease asset on Lymero/stronk and pinned in `corpus.lock`; `just corpus` fetches private assets through the API with a token (ADR-028). Corpus test now runs: 213 passed.
  Open: commits not pushed, so CI has never run; `pipeline_fixtures` budget is met (1.3 s vs 60 s) but `just bench` doesn't exist to measure it; `invalid` skips aren't retried after parser fixes. Next: M2 `winprob`.
- 2026-10-18: quarantine (ADR-029): games failing validation keep their scrubbed payloads in `<crawl>/quarantine/` with a reason; `just extract … --retry-quarantine` stores the ones that now pass; report.json counts skips and quarantine by reason plus `skip_rate`, floored at 0.01 on `just pipeline` (0 today, about 0.09 before the ADR-028 fixes).
  Open: the full crawl predates quarantine, so its 32 early rejects were refetched by hand, not retried; `just bench` next.
- 2026-10-18: `just bench` times `just pipeline` 3 times into `perf/out/pipeline_fixtures.json`; the budget (max 60 s, measured 1.2 s) is enforced and `just check` runs bench before budgets.
  Open: lock-in, data-fetch and app-start scenarios with the app (M3). Next: M2 `winprob`.
- 2026-10-18: `winprob.train` (ADR-030): logistic and LightGBM fitted on training matches, best on validation kept (logistic today: test log loss 0.516, calibration error 0.014 on 495 corpus matches; LightGBM 0.520); `wpa.estimate` uses the model; winprob floors enforced on the corpus.
  Open: skill features in the WP model; next M2 item, `wpa` v1 scores with propensity overlap, shrinkage and bootstrap on real data.
- 2026-10-18: WPA fixes from the first real-data run (ADR-031): no number under 30 overlap decisions; shrunk intervals keep the prior's uncertainty (they collapsed to a point). Corpus: 24 of 12,503 estimates get a number, narrowest interval ±0.11.
  Open: data volume. Item WPA needs roughly ten times more games per champion (pool regions and patches, or a production key) before the rest of M2 means anything.
- 2026-10-18: signing (ADR-032; Python signatures verified by Rust minisign-verify) and `publish` (ADR-033): signed, contract-valid build files, whole-patch replacement; `just pipeline` now runs crawl → extract → winprob → wpa → publish on the fixture. Extract takes several crawls. KR, NA and EUW crawls running toward about 24k games on 16.20.
  Open: `just serve-data`; the real signing key (`just keygen`) and its public key for the app; the fast WPA implementation, if the reference is too slow at 24k games.
- 2026-10-18: crawls done until the dev key expired: 22,954 games on 16.20 (EUW 8005, KR 7475, NA 7474), skip rate 0.05%; logistic still beats LightGBM (test log loss 0.5215, calibration error 0.008). WPA overlap is now decided per option (ADR-035): 3008 estimates get a number (7 before), 515 without `low_sample`.
  Open: the 22,954-game corpus isn't packed or pinned; on it, test log loss (0.5215) is just above the 0.52 floor set on 3305 games, so switching the corpus needs that floor reset (a loosening, needs an ADR).
- 2026-10-18: Benjamini-Hochberg FDR decides `no_clear_difference` (ADR-036): 0 of the 71 survive, 1 clear estimate in 3008. Synthetic slot 4 (many options, rare tail) covers ADR-035's bug and showed v1 attenuates effects of situational choices. Cross-evaluation: corpus and 23k win probability models are equivalent; the floor gap is the test set.
  Open: overlap-weighted estimator for the attenuation (needs approval); CI corpus (~3,500 games stratified by region) plus a full 23k corpus entry with per-corpus floors, after the cross-evaluation is reviewed.
- 2026-10-18: FDR family is now the eligible options (neither low_sample nor low_overlap), each against its point's most played (ADR-036): 125 contrasts on the 23k, none survive. `overlap-weighted` estimator (ADR-037) alongside v1: synthetic G kept 99% vs 54%, but confounded A bias 0.0096 and coverage 0.75 break floors, so v1 stays the default; on real data the two agree (r 0.977).
  Open: doubly robust v2 with skill features; corpora (CI ~3,500 stratified, full 23k weekly).
- 2026-10-18: corpora (ADR-038): `crawl-ci-16.20` (3500 stratified by region, `just check`) and `crawl-all-16.20` (22,954, weekly `full-corpus` workflow), both uploaded and pinned; floors per corpus from their own baselines (CI log loss 0.5308, full 0.5215).
  Open: first run of the `full-corpus` workflow (dispatch by hand once merged); fresh crawls need a new dev key.
- 2026-10-18: M2 complete. Finding: at 22,954 games (16.20, three regions) no comparison survives FDR (125 contrasts of claimable options against the most played, smallest q 0.085), and 284 of 390 decision points have a single claimable option, so there is nothing to compare there. More data per champion is the bottleneck, and the production key (unlocked by the M3 prototype) is the main path to it.
  Open: before M3, outcome check (final result vs WP at t+5 and t+8) and class-level item estimates.
- 2026-10-18: pre-M3 checks (ADR-039): windowed outcome (WP at t+5, t+8) halves interval widths but also effects, 0 survivors; class pooling with champion fixed effects: 1 survivor (final result), 2 (t+8, tank supports). Defaults unchanged.
  Open: whether to publish class-level estimates next to champion ones (needs a contract field and your call).
- 2026-10-18: M3 scaffold: Cargo workspace (domain, service, data, lcu, cli, src-tauri; ADR-040), command registry with fuzzing, `stronk-core`, `DirectorySource` verifying signature, trusted comment and hashes on `fixtures/data`, `tools/lcu_mock` with the core tested end to end against it, Svelte UI behind the `Backend` port with `MockBackend` and `TauriBackend` (ADR-041), Tauri shell built in CI.
  Open: WebKitGTK locally to run `just app` and generate tauri-specta bindings; Riot's LCU root certificate (from a verifiable source) before a real client; a real champion-select recording; HttpSource and cache; imports (runes, item set, spells).
- 2026-10-18: League client trust (ADR-042): Riot's CA embedded (v1, SHA-1, so an explicit verifier; pin fallback ready), own HTTPS GETs over rustls; `stronk-core record-champselect` with allowlist scrubbing and identifier checks; Windows CI job and docs/windows.md.
  Open: first Windows run against the real client: does Riot's CA validate it, and a real recording to replace the hand-written session.
- 2026-10-18: LCU transport is reqwest with the verifier's rustls config (no hand-written HTTP); tokio-tungstenite takes the same config for the coming watcher; trust tests on a real TLS server, including that the name-check exception doesn't reach other clients; `.dangerous()` confined to `tls.rs` by `just arch`. Windows build needed `icon.ico`.
  Open: the Windows CI job's first full pass; the real-client run.
- 2026-10-19: first real recording (`tools/lcu_mock/sessions/custom-2026-10-19.json`, custom game on Windows): Riot's CA validated the client, scrub check clean, the core replays it (Diana, BOTTOM, hover then lock-in) in `just core-e2e`.
  Open: the champion-select watcher (websocket), imports, HttpSource and cache.
- 2026-10-19: imports (ADR-043): `build.plan` and `build.import`, most played whole combination unless clearly better; Stronk's own rune page and item set only; Flash stays on its key; auto-import toggle; UI labels Popular / Clearly better. build.v1 gains optional popularity and comparison fields; publish writes spell pairs.
  Open: check imports on the real client (custom game, Windows); the websocket watcher; the production key draft.
- 2026-10-19: champion-select websocket watcher (ADR-044): reconnecting with backoff, a trigger for `champselect.state`; the REST client reconnects too (Stronk can start before the client); `watch-champselect` CLI; the UI refreshes on `champselect-changed`; lcu-mock speaks websocket; e2e covers a whole champion select and a client started late.
  Open: real-client check of imports and the watcher (Windows, custom game); lock-in timing in `just bench`; production key draft.
- 2026-10-19: item set safety (ADR-043): the player's sets pass through as raw JSON (byte-for-byte tests with unknown fields), no write when reading fails, a local backup before every write (and no write if it fails). "Clearly better" tooltips show the head-to-head interval (new `comparison.ci`) and the games behind it.
  Open: the Windows real-client test of imports and the watcher.
- 2026-10-19: `item_sets.restore` and `item_sets.backups` (CLI `restore-item-sets`): byte-for-byte restore, current sets backed up first, other accounts refused; production-key draft notes the local backups contain the account ID and never leave the machine.
  Open: a restore button in the app's settings; the Windows real-client test.
- 2026-10-19: app work moves to a Windows clone (ADR-045): `just` runs PowerShell there, with Windows versions of `setup`, `test` (Rust and UI), `core` and `app` (`TAURI_APP_PATH`, since the Tauri CLI didn't find its config from `app/ui`); `just app` ran against `just lcu-mock` on Windows. docs/windows.md has a "With just" section.
  Open: whether the `[unix]` `app` recipe has the same config lookup problem (untested, no WebKitGTK locally); the real-client check of imports and the watcher.
- 2026-10-19: real-client check on Windows (custom games, Syndra mid): the watcher followed hover, lock-in, game start and leaving within a second, and reconnected by itself after a client restart; imports wrote "Stronk: Syndra MIDDLE" runes (once a page was free), item set (player's 30 sets unchanged in every backup) and spells (Flash kept on D); `restore-item-sets` put the pre-import sets back.
  Open: the UI shows raw rune, spell and item IDs and the raw phase (`BAN_PICK`); check that a full rune page inventory (20/20) is reported in the UI, not only skipped.
- 2026-10-19: `HttpSource` and cache (ADR-046): new `index.v1` contract (`/index.json`, written by `LocalPublisher`), manifests revalidated by ETag at most every 5 minutes, builds cached by hash, last verified cache used offline or on bad data, no rollback through the index; `STRONK_DATA_DIR` takes a URL (`just serve-data`), `just core-e2e` covers it online then offline.
  Open: data-fetch scenario in `just bench`; cache pruning; a settings screen for the source; the CDN URL and real public key (M4).
- 2026-10-19: docs caught up with today's work: README and AGENTS link docs/windows.md and the production key draft; gaps record the real-client check of imports; architecture describes Riot's CA trust (ADR-042), the Windows and app-shell CI jobs and the Windows clone (ADR-045).
  Open: roadmap items for the UI fixes from the real-client check and tauri-specta bindings, now unblocked on Windows.
- 2026-10-19: names from the client (ADR-047): `names.get` reads champion, rune, spell and item names from the League client's game data (lcu-mock serves a subset, `game_data.json`); the UI shows them, with readable phases and roles, and each skipped import part (for example all rune pages in use) as a warning.
  Open: check the names on the real client; tauri-specta bindings (Windows).
- 2026-10-19: settings panel: auto-import moved there, item set backups listed newest first with their dates (`item_sets.backups` now returns `{location, saved_at_ms}`), and a restore after an inline confirmation.
  Open: undo for rune pages and spells; check the restore button on the real client.
- 2026-10-19: Playwright end to end (ADR-048): `just e2e` (in `just check`) runs the UI in Chromium against MockBackend scenarios and against the real core through `CoreBackend` and `tools/lcu_mock/core_bridge.py` (replayed lobby to import, auto-import once, restore); screenshots in `runs/e2e/screenshots/`; CI installs Chromium first.
  Open: `just e2e` on Windows (PowerShell twin added, untested there).
- 2026-10-19: lock-in bench: `stronk-core serve` (JSON lines on stdin, one context) and `lockin_import_cache_hit` in `just bench`, 200 hover-then-lock-in replays on lcu-mock: p50 55 ms, p95 67 ms (debug build), so the budget (100/300 ms) is enforced.
  Open: tauri-specta bindings and the real-client check of names, restore and auto-import (Windows); data-fetch and app-start scenarios.
- 2026-10-19: `corpus-pack` archives are now byte-for-byte reproducible: the gzip header's timestamp is zeroed (it was the current second, which failed CI when two packs straddled one).
  Open: nothing new.
- 2026-10-19: champion select view redesign (ADR-049): a champion banner, then runes, spells and each item slot as cards listing the top alternatives from `build.get` (share of games, win impact, games, confidence marker: clearly better or worse, no clear difference, too few games, fragile), Stronk's pick highlighted, and a line saying when the import falls back to the most played build; MockBackend's Lee Sin has a richer build file to show it.
  Open: importing an alternative instead of Stronk's pick; champion and item icons from the client; check the view on the real client.
- 2026-10-19: real data for the app: `just data-real` (WSL) builds and signs `runs/real/data` from the full corpus in about 8 minutes (727 files; Lee Sin jungle from 4,190 games); `just app-real` now defaults to it and takes a folder or a `serve-data` URL, on Windows too.
  Open: `build.plan` picks items slot by slot, so the same item can fill several slots (Lee Sin: Guardian Angel at 4, 5 and 6); a hosted data location (M4).
- 2026-10-19: pick an alternative (ADR-050): clicking an option in runes, spells or an item slot imports it instead of Stronk's pick ("Use Stronk's picks" resets; all options on request); `build.import` takes `runes`, `spells` and `items` picks, refusing anything not published; `build.plan` no longer repeats an item across slots (Lee Sin real data: Guardian Angel at 4, then Maw and others).
  Open: check picking and importing on the real client; picks are forgotten on restart.
- 2026-10-19: one selection rule (ADR-049): `select::rank` next to `choose` ranks each slot's options from the published flags, `build.plan` returns them as `alternatives` (top 3 plus the chosen one, a `more` count) with the build's games, elo and region; the UI lost its own q threshold and the extra `build.get`, and the rule's cases moved to Rust.
  Open: options past the top 3 are counted but can't be picked from the view any more.
- 2026-10-19: `HttpSource` takes plain `http://` only for the loopback literals `127.0.0.1` and `[::1]`, no longer `localhost` (ADR-046, docs/security.md); `just serve-data` and the app recipes already use `127.0.0.1`.
  Open: nothing new from this change.
- 2026-10-19: docs caught up with the review fixes: architecture's `serve-data` source is `http://127.0.0.1:8787`; gaps and ADR-050 say the view lists only the top options from `build.plan` (the 2026-10-19 ADR-050 entry's "all options on request" no longer holds); roadmap lists M3's open items.
  Open: tauri-specta bindings; the real-client check of names, restore, auto-import and picking; picking past the top 3; picks across restarts; icons.
- 2026-10-19: pick any option, keep picks (ADR-051): `build.plan` returns every option of each slot, the short list marked `listed`; the view lists the rest behind "N more options" and keeps a pick from them listed; picks are saved per champion and role for the plan's patch and come back after a restart (only if still published); Playwright covers expanding, picking and a reload.
  Open: check picking past the short list and picks after a restart on the real client; a picked option from an earlier patch is silently dropped (no notice).
- 2026-10-19: icons from the client (ADR-052): `icons.get` returns champion, rune tree, rune, spell and item icons as `data:` URLs read from the client's game data (paths kept under `/lol-game-data/assets/`, PNG/JPEG/WebP only, 512 KiB at most); the view shows them on the champion banner, the rune page, and every option, with a lettered stand-in otherwise; lcu-mock serves generated PNGs, MockBackend SVG placeholders; CSP adds `img-src 'self' data:`.
  Open: check the icons on the real client (and that its `iconPath`s resolve as given); the Tauri shell build with the new CSP on Windows.
- 2026-10-19: typed IPC (ADR-053): command params, results and `CommandError` derive `schemars::JsonSchema`; `stronk-core schema` prints them, `contracts/commands_codegen.py` writes `app/ui/src/lib/backend/commands.ts` (json2ts), `just gen-check` catches drift; `backend.ts` uses the generated types (tauri-specta dropped: one generic `run` command, specta still RC).
  Open: the `champselect-changed` event payload is still typed by hand in `tauri.ts`.
- 2026-10-19: M3 done. Real-client check on Windows (custom games, Syndra mid, `just app-real` on the full-corpus data): names; icons once the core asked with `Accept: */*` (the client answers 406 to `image/*`, now mirrored by lcu-mock; the CSP allows the `data:` icons); a pick from the top 3 (Summon Aery) and one from the longer list (Imperial Mandate) kept across an app restart; auto-import on lock-in wrote both in the same second, also when the timer locked the hover; restore from Settings put this morning's 30 sets back, equal to the backup.
  Open: M4. Custom champion selects end after about a minute, so a check spans several of them; picks carrying over made that painless.
- 2026-10-19: production key draft caught up with M3 and Riot's current portal rules: the player picks among every option and auto-import is opt-in (Riot rejects apps "that dictate player decisions"), the client's game data read for names and icons, restore from settings, M3 evidence, and a "Before submitting" list (verified website with privacy policy and terms, riot.txt, Developer Portal registration noting LCU use, legal notice in the app).
  Open: everything in that list needs the owner (domain, site, registration, contact); the legal notice isn't in the app yet.
- 2026-10-19: product site (ADR-054): `site/public/` with the product page (real-data screenshot), method, privacy policy, terms and 404, Riot's notice in every footer; `site/wrangler.jsonc` for Cloudflare Workers static assets (root directory `site`, no build command, `npx wrangler deploy`); `just site` previews on 127.0.0.1:8788; production key draft points at `stronk.christophercastel.com`.
  Open: the owner connects the Cloudflare project and the subdomain's DNS; riot.txt once Riot gives the string; the contact address on the site is the commit email; the legal notice in the app.
- 2026-10-19: production key application submitted in the Developer Portal; `site/public/riot.txt` holds Riot's verification string and the site at stronk.christophercastel.com is verified.
  Open: Riot's review (answers come in the portal's messages); remove riot.txt once approved; the legal notice in the app.
- 2026-10-19: Riot's legal notice in the app's footer, below the settings (App.svelte, tested in App.test.ts); production key draft updated.
  Open: Riot's review of the application.
- 2026-10-20: architecture diagrams in `docs/architecture-diagrams.html` (UML, inline SVG, drawn from `02672bd`): deployment by M4 step, pipeline activity and ports, app components, lock-in sequence, data trust; linked from AGENTS.md and docs/architecture.md.
  Open: keep them in step with the code; the M4 step order there is a suggestion, and the web viewer's ranking (WASM or not) is undecided.
- 2026-10-20: the architecture diagrams moved to Markdown so GitHub renders them: `docs/architecture-diagrams.md` with one SVG per diagram (and per M4 step of the deployment view) in `docs/diagrams/`; the HTML page is gone.
  Open: the SVGs are hand-maintained; edit them with the code they describe.
- 2026-10-28: patch 16.21 crawled (23,675 games); `backtest.run` / `just backtest` compares two patches' contrasts (ADR-055): v1 sign agreement 0.655 over 84, overlap-weighted 0.643, class 0.570; winprob transfers across the patch.
  Then: `crawl-all-16.21` pinned, the weekly job runs the backtest, `backtest.sign_agreement` enforced at min 0.55.
  Open: the change half (`backtest.direction_share`) deferred until more data per patch; UI review proposed (collapsed build, one marker), awaiting go.
- 2026-10-28: UI redesign (ADR-056): one line per slot with options behind a click, numbers only for clear differences, Import next to the champion, a calm "League of Legends isn't open" state, works down to 420 px; layout bugs fixed (wrapping names, overflowing card).
  Open: check it on Windows against the real client (the shell window size, real icons); stat shards are no longer shown.
- 2026-10-28: every estimate shows again, grey with its uncertainty ("+0.4% ± 1.0 vs others"), on each slot's line and in its options; colour and ▲/▼ only for clear differences (ADR-056, amended at the owner's request).
  Open: the real-client check on Windows.
- 2026-10-28: runes and shards row by row (ADR-057): extract adds a decision per primary row, secondary pair and shard row; `runeChoices` in build.v1; `build.plan` ranks `rune_rows`; the runes slot shows "Rune by rune" with every choice's number, for reading; no middle dots in the UI (`Facts`).
  Open: rebuild the real data (`just data-real`) so the rows appear in the app; picking single runes is not supported.
- 2026-10-28: the rune page drawn as the client's trees (ADR-058): `names.get` gives `rune_trees` and `shard_rows` from the client's perkstyles; every rune with its number under its icon, the page's choices lit, keystones pick their page; the row list stays as the fallback.
  Open: check the trees on the real client (icons, real layout).
- 2026-10-28: the build as one board (ADR-059): runes as the client's trees with a tree switcher, spells and item slots as rows of icons, every option with its number, precision bars and games; rune pages built by clicking, `build.import` checks them with `select::valid_page`; window 1200 by 900.
  Open: check the board on the real client; starter items, boots and components aren't estimated yet (the Coachless panels we can't fill).
- 2026-10-28: a keystone's games are now every game with it (the estimate's `n`), not only those with its most played full page; Conqueror on Lee Sin showed 813 of its 4076 games, fewer than Triumph's 4067.
  Open: the mock's Precision rows still count all 1740 games while its Precision keystones count 1000.
- 2026-10-28: Stronk's own look (ADR-060): a strip of what Stronk changes from the most played build, cells as a share ring, an interval line against zero and the estimate, numbers in wins per 100 games; precision bars and game counts moved to titles.
  Open: owner to look on the real client and keep or revert parts; next candidates are items as a build path with a forest plot per slot, the client's line through the picked runes, settings as a header icon.
- 2026-10-28: ADR-060 iterated: the share ring is an SVG arc (the CSS gradient looked pixelated), and the interval line is gone, replaced by the ± written under each number.
  Open: owner to check the cells on the real client.
- 2026-10-28: fix: a secondary rune from a new row replaced the upper rune every time (the page keeps the pair in row order), so the lowest row's rune stuck; the panel now remembers the last secondary pick and replaces the other.
  Open: the last pick is forgotten on restart, so the first new-row pick after one replaces the upper rune.
- 2026-10-29: ADR-060 iterated again: the ± is off the board, on hover as "Likely between A and B (95%)" with the games; headers, the strip and the pair show the estimate alone.
  Open: the hover is the native title (slow, unstyled); a styled tooltip needs the panels' `overflow: hidden` reworked.
- 2026-10-29: a styled tooltip on every option (ADR-060), on hover or focus: whose pick, the estimate and what it's against, its likely range, the verdict in words, games and share; fixed to the window, so the panels keep `overflow: hidden`.
  Open: slot headers, the summary strip and the secondary pair still use the native title for their details.
- 2026-10-29: the most played option shows "most played", not its number against the rest (ADR-060): that number read as a verdict (Coup de Grace, Stronk's pick, at −2.4).
  Open: the shorter tooltip (title plus three lines, the base named) was proposed and not taken yet.
- 2026-10-29: the option tooltip is gone and no game counts are shown (the ring shows play share): each option is its ring and one number, the range only in its accessible name (ADR-060).
  Open: the range is now nowhere on screen; if players want it back, a details view on click rather than hover.
- 2026-10-29: one scale per row (ADR-060): numbers only for head-to-head comparisons with the row's most played option, which reads 0; pooled numbers (each against a different mix) are hidden, headers say "Compared with X".
  Open: Coachless's WPA is WR minus average pre-decision win probability (against the average choice, implicitly); a "vs the average pick" scale for Stronk would need the pipeline's estimand checked first.
- 2026-10-29: the baseline set apart (ADR-060): the 0 on its own tile, and in item rows a rule between it and the options measured against it.
  Open: owner to check it on the real client.
- 2026-10-29: picks framed instead of the baseline tile; "almost always" for a most played option flagged low_overlap (Triumph and Conqueror read "few games" at 97%); secondary runes show the numbers of the pair clicking them makes (ADR-060).
  Open: no UI test for "almost always" (the mock has no such row); covered by the core's rank test.
- 2026-10-29: `just e2e-real` (ADR-061): every real board checked by `board_sanity.py`, then Playwright screenshots of six picks in runs/e2e-real/screenshots/; "almost always" now needs 300 games (it showed on a 1-game board).
  Open: 43 options with 300+ games but under 300 comparable decisions read "few games" (`few-games-false`, so e2e-real fails until the wording is decided); "few games" clutter on thin item slots.
- 2026-10-30: "too few to compare" for an option with 300+ games but too few comparable ones (`Confidence::TooFewToCompare`, owner's wording); `just e2e-real` takes the picks first and passes on all 727 boards.
  Open: "few games" clutter on thin item slots.
- 2026-10-30: no label for options short of games (legend: "no number: too few games"), "Not measured yet" on spells, every option box one size; e2e-real now fails on boxes of different sizes or content spilling out (it caught the spell pair).
  Open: nothing new.
- 2026-10-30: the build sheet (ADR-062): the build by name on the left, one slot open on the right (rune tree, or options ranked against the baseline with share bars), dark ink and amber look; Stronk's gain badge only while its pick is imported.
  Open: owner to look at it on the real client.
- 2026-10-30: the option lists show each option's games again (ADR-062), beside its share, or under its name in a narrow window.
  Open: the rune tree's cells still show no games (the ring gives the share).
- 2026-10-30: runes and shards as named cards (ADR-063): name, number against the row's baseline, games, share bar; trees switched by name; fits 1200 by 900.
  Open: owner to look at it on the real client; in a narrow window the cards stack one per line, long.
- 2026-10-30: runes redone as three columns of lists (ADR-063, owner's pick): primary, secondary, shards side by side, one rune per line with name, games and number; the wide cards were too flat.
  Open: owner to look at it on the real client; tree switch icons are small (16 px).
- 2026-10-30: runes drawn as the client's trees again (ADR-063, owner's call: players know that layout): round icons, picks lit and ringed in amber, the picked rune's name and number under each row; the list designs are gone.
  Open: owner to check on the real client, with the real icons.
- 2026-10-30: "almost always" replaced by the share on every rune pick line ("Conqueror 97%"), chosen from three variants rendered on real data; gone from the item lists too.
  Open: nothing new.
- 2026-10-30: the rune page redesigned (ADR-064), chosen from three concepts rendered on real data: the client's tree with icons only, and the focused row beside it as an item-style list; shards in labelled groups.
  Open: owner to look at it on the real client.
- 2026-10-30: rune page per the owner's review (ADR-064): bigger runes, the ring inside the focus band, no "row N" in the list's heading; fixed "Your pick" appearing after only clicking lit runes (secondary pair order in `samePage`).
  Open: lcu-mock's placeholder icons show a square border inside the round runes; the real art doesn't.
- 2026-10-30: runes at the item icons' size (32 px, keystones 36), and tags under the name in a narrow list so "Legend: Alacrity" shows in full (ADR-064).
  Open: nothing new.
- 2026-10-30: Stronk imports its best bet (ADR-065): the largest shrunk gain against the most played option, labelled "Best bet" (amber) unless proven ("clearly better", green); rune pages get it row by row. Lee Sin now takes Cut Down.
  Open: τ = 0.02 and the 0.005 minimum are judgement calls; a backtest of best bets across patches (16.20 to 16.21) would say how often they hold.
- 2026-10-30: the summary of Stronk's changes is gone from the sheet (owner's request, ADR-065); the badges mark them; the thin-data warning stays.
  Open: nothing new.
- 2026-10-30: the site shows the current UI (ADR-066): `just site-shot` renders Lee Sin jungle from the real data into site/public/img/champion-select.png; home and method pages describe the sheet, rune tree and best bets.
  Open: check the deployed site after Cloudflare builds this push.
- 2026-10-30: the site's screenshot has the game's real icons (ADR-066): `just site-shot` fetches them from CommunityDragon into runs/site-icons and lcu-mock serves them; attributed in ATTRIBUTION.md.
  Open: check the deployed site after Cloudflare builds this push.
- 2026-10-30: the sheet and the open slot end on the same line (ADR-062), the legend at the slot's bottom; e2e-real checks it; site screenshot refreshed.
  Open: nothing new.
- 2026-10-30: the site's screenshot readable (ADR-066): the wide one at near its own size in a figure wider than the text, a narrow one for phones; `just site-shot` renders both.
  Open: check the deployed site after Cloudflare builds this push.
- 2026-10-30: the site shows two views (ADR-066): the rune page (runes.png) and an item slot (items.png), each wide and for phones; `just site-shot` renders all four.
  Open: a video was left out (over the 512 KB file limit); check the deployed site.
- 2026-10-30: the site's two views share one figure at the top, switched by "Runes" and "Items" (ADR-066); "What it does" is text only again.
  Open: on phones the two pictures differ in height, so the text below moves when switching.
- 2026-10-30: the secondary runes are listed as pairs (ADR-064 amended): clicking one focuses the secondary tree, its pairs listed with both runes, a pair picks both.
  Open: pairs rarely have numbers (24 of 727 boards have a second pair of 300+ games); more patches of data, not a looser rule, would fill them.
- 2026-10-30: items 4 to 7 are one late slot, "Items 4+" (ADR-067): extract pools them (decisions now unique per minute too), build.v1 gains `lateSlot`, the import writes one block of six late items, the sheet and site show it; real data and fixtures rebuilt.
  Open: late items still rarely reach a head-to-head (Lee Sin's most played late item has 392 purchases, the next 231); the late list's block members aren't marked in the panel, only under the pick in the sheet.
- 2026-10-30: `just data-to-windows` copies the real data into the Windows clone named by `STRONK_WINDOWS_CLONE` (.env), and `just data-real` runs it at the end (ADR-068).
  Open: the app still reads its data only when it starts; restart `just app-real` after a copy.
- 2026-10-30: the item set lists each slot's pick then its alternatives with 2%+ of games (4 per slot, 6 for 4+), is written first with `priority`, and is titled "Stronk: Lee Sin Jungle" (ADR-069).
  Open: check on the real client that the set opens on top; the rune page keeps the old name until the client's limit on page names is known.
- 2026-10-30: item set blocks list the player's pick, then Stronk's choice, then the rest by Stronk's judgement (`judged`, the shrunk head-to-head gain; 0 when unmeasured) (ADR-070).
  Open: none beyond ADR-069's (check the set's place in the real client).
- 2026-10-30: the start (items bought in the first 90 s, potions and wards aside) is a decision like a slot: extracted, published as `starts` with what is bought with it, chosen and ranked by build.plan, a "Start" row in the sheet, the item set's first block (ADR-071).
  Open: the first back (too scattered as whole purchases; try the first item bought after leaving base).
- 2026-10-30: the app asks the client for the starts' icons too (the pets showed stand-in letters); `site_icons.py` fetches them; site screenshots refreshed with the Start row.
  Open: `just site-shot` failed one screenshot on its first run right after fetching new icons, twice now, and passed on the rerun.
- 2026-10-31: the first components (what the first trip back buys, supplies, boots and completed items aside) are a choice like the start: extracted, published as `firstComponents`, chosen and ranked, a sheet row and the item set's second block (ADR-072).
  Open: boots as their own section.
- 2026-10-31: boots are their own section: the first upgraded boots, anchored at the plain Boots, published as `boots`, chosen and ranked, a "Boots" row and block after the first item (ADR-073).
  Open: the sheet's item names shorten beside a badge when a row has two icons ("Long Swor…"); the panel shows them in full.
- 2026-10-31: `just site-shot`'s failures on some runs came from the names route still holding a request when a page closed; each test now drops its routes after its picture (`unrouteAll`, ignoring errors). Site screenshots show the start, first back and boots.
  Open: none.
- 2026-10-31: the first components count planned backs only: a first back after a death of the player is left out and counted (`first_back_after_death`); the bias check (kills accounted for, deaths not) is recorded in ADR-072.
  Open: the order on planned backs carries over to backs after a death only loosely (8 of 10 clear pairs); revisit with more patches.
- 2026-10-31: validation (16.20 vs 16.21): best bets held on average (+0.9 wins per 100, predicted +1.2) but boots didn't; boots now follow the enemy team's damage once three enemies are picked: per-profile estimates, a signed champions.json with the ratings and cuts, enemies from champion select (ADR-074).
  Open: items 4+ against the enemy's damage when the data shows it; a recurring per-section holdout check.
- 2026-10-31: roadmap action point (M5): revalidate with more data, repeating the holdout, boots-by-profile, items-by-damage and first-back checks against their 16.20 baselines.
  Open: the analysis scripts behind those checks were one-off; turn them into a recurring check when revalidating.
- 2026-10-31: a throwaway signing key pair (`u`, `u.pub`), written into the repository root by the command fuzz test (`signing.keygen` with a random `out`), was committed in 8a604f8; removed. The fuzz test now runs in a scratch folder, and a `signing-key` commit hook refuses secret key lines whatever the file's name (security.md).
  Open: the key stays in the history of 8a604f8; it never signed anything and no app trusts it, so the history wasn't rewritten.
