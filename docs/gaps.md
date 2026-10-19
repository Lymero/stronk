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
| Import rune page | Blitz, Porofessor | partial: `build.import` writes Stronk's own page (most played full page unless one is clearly better, ADR-043); tested against lcu-mock, not yet on a real client |
| Write item set | Blitz, Porofessor | partial: Stronk's own item set, the player's kept; tested against lcu-mock |
| Set summoner spells | Blitz | partial: most played pair, Flash on the player's key; tested against lcu-mock |
| Auto-import on lock-in | Blitz | partial: a setting, off by default, on the websocket watcher; not yet checked on a real client |
| Cycle alternative builds by hotkey | none | missing |

## App

| Capability | Reference | Status |
|---|---|---|
| Lightweight install and memory use | none (Electron competitors) | missing |
| Works offline with cached data | none | done (ADR-046: verified disk cache, used when the data source can't be reached) |
| Web build viewer for preparation | Coachless | missing |
| Auto-update (app and data) | Blitz | missing |
