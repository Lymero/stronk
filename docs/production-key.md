# Production API key application (draft)

Draft for review before submitting at developer.riotgames.com. Text in **[brackets]** needs a decision or a fact only the owner has. Everything else describes what the code does today (commit references in the "Evidence" section).

## Product name

Stronk

## One-line description

A free desktop app that imports runes, an item set and summoner spells during champion select, chosen from ranked match statistics that are honest about their uncertainty.

## Product description

Stronk helps players set up a build in champion select. It lays out the choices and leaves the decision to the player. When the player hovers or locks a champion, it shows, for that champion and role, from high-elo ranked games on the current patch:

- every published option for the rune page, the summoner spell pair and each item slot, the most played first, each with its share of games, the number of games, its win impact and a confidence marker ("clearly better", "clearly worse", "no clear difference", "too few games");
- an option is marked "clearly better" only when it beats the most played option in a head-to-head comparison and the difference survives a false-discovery-rate correction across the whole patch; impact is coloured only when the difference is clear, so noise never looks like a finding;
- the sample size behind the build, and a flag whenever an estimate cannot be trusted (too few games, or a choice nobody makes in comparable situations).

Stronk proposes a default (the most played combination, unless an option is clearly better), and the player can pick any listed option for any slot instead, including less common ones behind "more options". Picks are remembered per champion and role until the patch changes. One click writes the build into the client: a rune page named "Stronk: <champion> <role>", an item set with the same name, and the summoner spell pair, keeping Flash on the key the player already uses. Writing on lock-in is a setting, off by default, and writes the player's own picks. Stronk only replaces its own page and item set; it never edits or deletes the player's pages or item sets, and when there is no free rune page it says so instead of overwriting one.

The statistics are "win probability added": the change in the team's win probability around each decision, compared with the alternatives chosen in similar game states, with propensity overlap checks, bootstrap intervals and false-discovery control. The method and its tests are public in the repository (docs/wpa-method.md).

## What Stronk does not do

- No in-game overlay, no information during the game, no automation of gameplay.
- No decisions taken away: every option stays visible and pickable, and nothing is written to the client unless the player clicks Import or turns on import at lock-in.
- No information about other players: Stronk never shows, stores or looks up names, ranks or histories of teammates or opponents, and the champion-select data it records for testing is scrubbed of every identifier.
- No accounts, ads or telemetry.

## Riot API usage (server side only)

The desktop app does not use the Riot API and ships no key. A crawler on our server collects ranked match data to compute the statistics:

| Endpoint | Purpose |
|---|---|
| `league-v4` `/lol/league/v4/{challenger,grandmaster,master}leagues/by-queue/RANKED_SOLO_5x5` and `/entries/RANKED_SOLO_5x5/DIAMOND/I` | Seed players at the top of the ladder |
| `match-v5` `/lol/match/v5/matches/by-puuid/{puuid}/ids` | Their recent ranked games |
| `match-v5` `/lol/match/v5/matches/{matchId}` and `/timeline` | Build choices and game state minute by minute |

- **Volume:** about 2.4 requests per stored game (measured: 11,310 requests for 4,700 games). The statistics need roughly ten times the data a development key allows per patch (at 22,954 games, most champion-role decision points have too few games to compare options), so the aim is up to about **[200,000]** games per patch across **[EUW, KR, NA]**: about 480,000 requests over a two-week patch, 0.4 requests per second on average. The crawler honours every rate limit header and backs off on 429s; the standard production limits are enough.
- **Regions:** **[list the platforms to crawl]**.

## Data handling

- Player identifiers never leave the crawler's storage in readable form: PUUIDs are replaced by keyed hashes (HMAC with a secret that is never published), and names and Riot IDs are dropped when a game is stored.
- What is published is aggregate statistics per champion, role and patch (signed JSON files); no player-level data.
- The API key lives in the server's environment, never in code, commits, logs or the app.
- Champion-select recordings used for tests keep an allowlist of fields; a test fails if a committed recording contains anything that looks like an identifier.
- Before the app writes its item set, it saves a local backup of the player's item sets, exactly as the client returns them, so they can be restored from the app's settings after a confirmation. These backups contain the player's account ID (the client includes it), stay in the user's own data folder, are never sent anywhere, and only the 20 most recent are kept. A backup from another account is refused.
- Picks and settings stay on the player's machine.

## Use of the League client (Game Client API)

The app talks only to the local client at `127.0.0.1`, authenticated with the client's lockfile, and trusts only Riot's published client certificate authority (riotgames.pem). It follows the champion-select session over the client's websocket (`OnJsonApiEvent_lol-champ-select_v1_session`).

It reads:

- the champion-select session and the logged-in summoner;
- the rune pages, how many pages the account has room for, and the item sets, before writing;
- names and icons of champions, runes, spells and items from the client's own game data (`/lol-game-data/assets/`), so they match the player's language and patch without any other download.

It writes only:

- its own rune page (`/lol-perks/v1/pages`);
- its own item set (`/lol-item-sets/v1/item-sets/{summonerId}/sets`, every other set written back unchanged);
- the spell selection (`/lol-champ-select/v1/session/my-selection`);
- when the player restores a backup from the settings, the player's own item sets as they were saved (current sets backed up first).

Nothing about other players in the session is stored or shown.

## Status and evidence

- Desktop app (Tauri) checked end to end on Windows against the live client on 2026-10-19 with data built from the full corpus: names and icons, picking a listed and a less common option and keeping them across a restart, import on lock-in (also when the timer locks the hover), and restoring the player's 30 item sets from a backup (commit e32b11e).
- Champion select followed over the client's websocket, reconnecting after a client restart; a real champion select recorded, scrubbed and replayed in tests (commit f418710).
- Imports covered by end-to-end tests against a simulated client: full rune page, an existing Stronk page replaced, the player's pages untouched, no page written when none is free, Flash kept on its key (commit bf0d05b); picks limited to published options (ADR-050).
- Playwright tests drive the UI against the real core on the simulated client (commit ad8f1d4); lock-in to import is timed on every check, p95 67 ms against a 300 ms budget (commit ac17571).
- Statistics pipeline with published method, synthetic-truth tests and quality floors checked in CI; 22,954 games collected with a development key.
- **[Attach screenshots: the champion select view on real data (`real-data/real-leesin.png`) and an import in the client (`icons/core-imported.png`), or fresh ones from a custom game]**

## Monetization

**[Free. No paywall, ads or premium tier planned]** (Riot's policies require a free tier).

## Website and verification

`https://stronk.christophercastel.com` (source in `site/`, ADR-054): the product page, the method description, the published data, a privacy policy and terms of use (Riot reviews both, and does not grant a production key without a verified website; a GitHub repository is not accepted instead). After submitting, Riot gives a text string to put, exactly as given, in `riot.txt` at the site's root; the file can be removed once the site is verified. **[Site deployed on Cloudflare; riot.txt in place after submitting]**.

The Riot legal notice ("Stronk isn't endorsed by Riot Games…", ATTRIBUTION.md) is in every page's footer on the site and in the app's footer, below the settings.

## Before submitting

- **[Register the product in the Developer Portal and note that it uses the League Client API, as Riot asks for LCU apps]**
- **[Site live (privacy policy and terms are written, `site/public/`); domain verified with riot.txt]**
- Legal notice visible in the app (its footer)
- **[Data served from the public location (R2/CDN), not a local folder]**
- Reviews usually take one to three weeks; answers arrive in the Developer Portal's messages.

## Contact

**[Name, email, Discord or other contact Riot can reach]**
