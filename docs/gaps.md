# Gaps

What comparable tools offer and where we stand. Use it with the roadmap to pick work. Update the status when a change lands.

Status: **missing** · **partial** · **done**

## Statistics

| Capability | Reference | Status |
|---|---|---|
| Item ranking by WPA | Coachless | partial: estimated and published per slot; at 22,954 games no comparison survives FDR (ADR-036, ADR-039) |
| Rune ranking by WPA | Coachless | partial: keystones estimated, published with their usual page |
| Confidence intervals and sample sizes shown | none | partial: published in build files; the app shows WPA and flags, not yet intervals |
| Flags for meta-locked or low-sample choices | none | done: published, shown by the app instead of numbers |
| Per-slot item ranking | Coachless | partial: per slot in build files; ranking claims need FDR survivors |
| Elo filters | Coachless, u.gg | missing |
| Matchup-adjusted builds | u.gg, Blitz | missing |
| Skill order | u.gg, Blitz | missing |

## Champion select

| Capability | Reference | Status |
|---|---|---|
| Detect champion and role | Blitz, Porofessor | partial: `champselect.state` reads it from the client (tested against lcu-mock); websocket watcher with reconnects (ADR-044); trusts Riot's CA, verified against a real client |
| Import rune page | Blitz, Porofessor | partial: `build.import` writes Stronk's own page (most played full page unless one is clearly better, ADR-043); tested against lcu-mock and on a real client (2026-10-19) |
| Write item set | Blitz, Porofessor | partial: Stronk's own item set, the player's kept and backed up before each write; tested against lcu-mock and on a real client (2026-10-19) |
| Undo an import | none | partial: settings list the item set backups with their dates and restore one after a confirmation (`item_sets.restore`, current sets backed up first); rune pages and spells have no undo |
| Set summoner spells | Blitz | partial: most played pair, Flash on the player's key; tested against lcu-mock and on a real client (2026-10-19) |
| Auto-import on lock-in | Blitz | partial: a setting, off by default, on the websocket watcher (the watcher checked on a real client 2026-10-19; auto-import itself not yet) |
| Readable names for runes, spells and items | Blitz, Porofessor | partial: `names.get` reads them from the client's own game data, in its language (ADR-047); readable phases and roles; tested against lcu-mock, not yet on a real client |
| Say why part of an import was skipped | none | partial: each skipped part shows as a warning, for example all rune pages in use (ADR-047) |
| Alternatives per slot with their evidence | u.gg, Blitz (win rate and pick rate per option) | partial: the champion select view lists the three most played runes, spells and items per slot (plus Stronk's choice when rarer) from `build.plan`'s `alternatives`, with share of games, win impact, sample size and a confidence marker (clearly better or worse, no clear difference, too few games, fragile), and says when the import falls back to the most played build (ADR-049); clicking an option imports it instead of Stronk's pick (ADR-050); options past the listed ones are counted but can't be picked, and picks are forgotten on restart |
| Cycle alternative builds by hotkey | none | missing |

## App

| Capability | Reference | Status |
|---|---|---|
| Lightweight install and memory use | none (Electron competitors) | missing |
| Works offline with cached data | none | done (ADR-046: verified disk cache, used when the data source can't be reached) |
| Web build viewer for preparation | Coachless | missing |
| Auto-update (app and data) | Blitz | missing |
