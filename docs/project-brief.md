# Project brief

## Problem

Coachless (coachless.gg) ranks League of Legends builds by WPA, which is more trustworthy than raw win rates. It works well for preparing a build in advance, but:

- it is a website: slow, heavy and tied to the browser;
- there is no fast way to get a build into the client during champion select;
- its WPA can still mislead on meta-locked choices. A rune with a 3% pick rate can show a higher WPA than the 97% pick, because the small group taking it is self-selected and has no real comparison group.

## Goals

| Goal | Measure |
|---|---|
| **Free** | No paywall (Riot policy also requires a free tier) |
| **Fast** | Lock-in to runes, items and spells imported: P95 ≤ 300 ms. Cold start: P95 ≤ 1 s. See [architecture.md](architecture.md#7-budgets-and-floors) |
| **Clean** | Clearer UI than existing tools; one screen, no clutter |
| **Honest** | Every number shows its confidence interval or sample size, and a flag when it isn't trustworthy |

## Non-goals (for now)

- In-game overlays (Riot restricts information-advantage overlays)
- Accounts, social features, ads
- Telemetry by default

## Engineering principles

Being a solo project changes the **process**, not the **architecture**.

- **Architecture:** clean, layered, modern patterns, as if a team would join tomorrow. Clear boundaries, dependency rules, typed contracts, tests at every layer. See [architecture.md](architecture.md).
- **Process:** lightweight. No multi-agent coordination, no heavy ceremony. One agent or one human at a time, short session notes, decisions recorded in [decisions.md](decisions.md).
- **Feedback loops:** every feature can be run offline on fixtures, from one command, with inspectable output, in under a minute.
- **Correctness of the statistics comes first.** A fast tool with wrong numbers is worse than no tool.
- **The app never crashes in a lobby.** Outside input is hostile until validated.

## Product decisions

### Product name

- **Stronk** in user-facing text; `stronk` in code, packages, binaries and folders.
- Gaming slang for "strong", not a Riot trademark. Fits a tool about how strong items really are.
- Before public release: confirm the domain and check for conflicting trademarks.

### Naming: "WPA" vs the UI label

- WPA (win probability added) is a decades-old, public sports-analytics concept and a generic statistical method. No known patent applies (not legal advice).
- Do not copy Coachless's branding, design, wording, code or data.
- **Code, docs and the method page:** "WPA" (`wpa`).
- **Main UI:** **"Win impact"** (for example "Win impact: +1.2%"), with the tooltip "Win probability added, adjusted for game state, compared with alternatives."
- Always show the confidence interval or sample size next to the number, and the flag when it isn't trustworthy.

### Riot API key

- The desktop app needs no Riot key; the League client's local API needs none. Only the server-side crawler does.
- **Now:** development key from developer.riotgames.com (instant, expires every 24 h, low rate limits).
- **Before public release:** production key. Requires a working prototype and riot.txt verification on a domain we control; review takes about two weeks.
- The key lives in `.env` as `RIOT_API_KEY`. Never committed, never shipped.

## Costs

A small VPS for crawling and training (about €10–30 per month) plus a free CDN tier.
