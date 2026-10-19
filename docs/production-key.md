# Production API key application (draft)

Draft for review before submitting at developer.riotgames.com. Text in **[brackets]** needs a decision or a fact only the owner has. Everything else describes what the code does today (commit references in the "Evidence" section).

## Product name

Stronk

## One-line description

A free desktop app that imports runes, an item set and summoner spells during champion select, chosen from ranked match statistics that are honest about their uncertainty.

## Product description

Stronk helps players set up a build in champion select. When the player hovers or locks a champion, it shows, for that champion and role:

- the most played full rune page, summoner spell pair and items per build slot in high-elo ranked games on the current patch;
- an option is shown as "Clearly better" instead only when it beats the most played option in a head-to-head comparison and the difference survives a false-discovery-rate correction across the whole patch; otherwise every choice is labelled "Popular";
- the sample size, the comparison's win impact, and a flag whenever an estimate cannot be trusted (too few games, or a choice nobody makes in comparable situations).

One click (or, if the player turns it on, lock-in) writes the build into the client: a rune page named "Stronk: <champion> <role>", an item set with the same name, and the summoner spell pair, keeping Flash on the key the player already uses. Stronk only replaces its own page and item set; it never edits or deletes the player's pages or item sets, and when there is no free rune page it says so instead of overwriting one.

The statistics are "win probability added": the change in the team's win probability around each decision, compared with the alternatives chosen in similar game states, with propensity overlap checks, bootstrap intervals and false-discovery control. The method and its tests are public in the repository (docs/wpa-method.md).

## What Stronk does not do

- No in-game overlay, no information during the game, no automation of gameplay.
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
- Before the app writes its item set, it saves a local backup of the player's item sets, exactly as the client returns them, so they can be restored. These backups contain the player's account ID (the client includes it), stay in the user's own data folder, are never sent anywhere, and only the 20 most recent are kept.

## Use of the League client (Game Client API)

The app talks only to the local client at `127.0.0.1`, authenticated with the client's lockfile, and trusts only Riot's published client certificate authority (riotgames.pem). It reads the champion-select session and the champion list, and writes only: its own rune page (`/lol-perks/v1/pages`), its own item set (`/lol-item-sets/v1/item-sets/{summonerId}/sets`, every other set written back unchanged), and the spell selection (`/lol-champ-select/v1/session/my-selection`).

## Status and evidence

- Working prototype on Windows against the live client: champion select detected over the client's websocket, a real champion select recorded and replayed in tests (commit f418710).
- Imports covered by end-to-end tests against a simulated client: full rune page, an existing Stronk page replaced, the player's pages untouched, no page written when none is free, Flash kept on its key (commit bf0d05b).
- Statistics pipeline with published method, synthetic-truth tests and quality floors checked in CI; 22,954 games collected with a development key.
- **[Screenshots of the app in a custom game's champion select]**

## Monetization

**[Free. No paywall, ads or premium tier planned]** (Riot's policies require a free tier).

## Website and verification

**[Domain]**: the product page, the method description and the published data. Riot asks for verification with `riot.txt` on that domain; **[set it up before submitting]**.

## Contact

**[Name, email, Discord or other contact Riot can reach]**
