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
| Per-slot item ranking | Coachless | partial: per slot in build files, items 1 to 3 each and the late items pooled as "4+" (ADR-067); ranking claims need FDR survivors |
| Elo filters | Coachless, u.gg | missing |
| Matchup-adjusted builds | u.gg, Blitz | missing |
| Starting items | u.gg, Blitz, Coachless | done: the start (items bought before leaving base, potions and wards aside) estimated and ranked like a slot, imported as the item set's first block (ADR-071) |
| First back | u.gg, Blitz | done: the first components, what is bought on the first trip back without supplies, boots or completed items, as one choice (Dark Seal + Amplifying Tome), imported as the second block (ADR-072) |
| Boots | u.gg, Blitz | missing: their own section (ADR-072) |
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
| Champion, rune, spell and item icons | Blitz, Porofessor, u.gg | partial: `icons.get` reads them from the client's own game data and the view shows them next to every name, with a plain stand-in when there is none (ADR-052); tested against lcu-mock, not yet on a real client |
| Say why part of an import was skipped | none | partial: each skipped part shows as a warning, for example all rune pages in use (ADR-047) |
| Alternatives per slot with their evidence | u.gg, Blitz (win rate and pick rate per option) | partial: the champion select view lists the three most played runes, spells and items per slot (plus Stronk's choice when rarer) from `build.plan`'s `alternatives`, with share of games, win impact, sample size and a confidence marker (clearly better or worse, no clear difference, too few games, fragile), and says when the import falls back to the most played build (ADR-049); clicking an option imports it instead of Stronk's pick (ADR-050); every other option of a slot is listed on request and can be picked too, and picks are kept across restarts until the patch changes (ADR-051); the build reads as one line per slot, options behind a click, every estimate with its uncertainty, coloured only for a clear difference (ADR-056); the rune page row by row and the stat shards, each choice with its number, for reading (ADR-057), laid out as the client's rune trees (ADR-058); the whole build on one board of panels, every option an icon with its number, precision and games, a page built rune by rune (ADR-059); every number against its slot's most played option (ADR-060); the build as a sheet of picks by name, one slot open beside it with its options ranked against that baseline (ADR-062); runes and shards as the client's tree with the focused row as a list in the same language (ADR-063, ADR-064) |
| Cycle alternative builds by hotkey | none | missing |

## App

| Capability | Reference | Status |
|---|---|---|
| Lightweight install and memory use | none (Electron competitors) | missing |
| Works offline with cached data | none | done (ADR-046: verified disk cache, used when the data source can't be reached) |
| Web build viewer for preparation | Coachless | missing (a static product site exists, ADR-054, without builds) |
| Auto-update (app and data) | Blitz | missing |
