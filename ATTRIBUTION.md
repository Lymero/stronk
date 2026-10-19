# Attribution

Every third-party asset (images, icons, fonts, data files) used by Stronk gets a line here in the same change that adds it. Code dependencies are tracked by their lockfiles (`uv.lock`, `pnpm-lock.yaml`, `Cargo.lock`) and are not listed.

| Asset | Source | Licence | Used in |
|---|---|---|---|
| Data Dragon champion and item data | Riot Games, ddragon.leagueoflegends.com | Riot Games' [Legal Jibber Jabber](https://www.riotgames.com/en/legal) policy for fan projects | crawl directories, corpus and test recordings (`static/`) |
| League client game data names, a hand-written subset (`game_data.json`) | Riot Games, names as in Data Dragon and the League client's `/lol-game-data/` | Riot Games' [Legal Jibber Jabber](https://www.riotgames.com/en/legal) policy for fan projects | `tools/lcu_mock/`, served by the fake client in tests; the app reads names from the player's own client |
| League client root certificate (`riotgames.pem`) | Riot Games, https://static.developer.riotgames.com/docs/lol/riotgames.pem (downloaded 2026-10-18, sha256 `da884275737f024b33c93ae5d28bdb002768a3cb73752ab40254a32218193521`) | Published by Riot for the Game Client API | `app/core/crates/lcu/certs/`, trusted for connections to the local client |

## Riot Games

Stronk isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
