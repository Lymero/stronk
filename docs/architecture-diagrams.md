# Architecture diagrams

After M3, before M4. Drawn from `main` at `02672bd` (2026-10-20): code, [architecture.md](architecture.md), [roadmap.md](roadmap.md), ADR-001 to ADR-054. The SVGs are in [diagrams/](diagrams/).

Two systems share one signed data contract. The pipeline turns Riot matches into per-champion build statistics; the desktop app reads them and writes runes, items and spells into the League client. No live backend: only static signed files. Section 1 covers the whole system from today to the end of M4; sections 2 to 5 go one level down.

![Legend: colours by language and UML arrow notation](diagrams/legend.svg)

## 1. The whole system, step by step

Deployment view. Each step highlights what it changes. The step order is a suggestion; the roadmap doesn't order M4.

### Step 0: today (M3)

![Deployment today](diagrams/map-0-today.svg)

Today everything runs on your PC: the pipeline in WSL writes signed files to disk, and the app on Windows reads them as a folder. Only the product site is hosted.

- Built: `just data-real` builds 727 signed files in about 8 minutes. The app has 9 commands and reads a folder or HTTP source, verified and cached on disk. The product site is live; the production key is awaiting Riot.
- Missing for players: hosted data; more than one patch (16.20), region (`all`) and elo (`master_plus`); an installer, an updater and a web viewer.

### Step 1: data on R2 and a CDN

![Deployment after step 1](diagrams/map-1-step-1.svg)

One adapter and one setting. `R2Publisher` joins `LocalPublisher` behind the same `Publisher` port and uploads the same signed files to R2; the app's data setting becomes the CDN URL, which `HttpSource` already takes. The pipeline still runs by hand.

- Why first: the smallest change (ADR-017), and steps 3 and 4 need a public URL.
- Done when: the app runs on the CDN from an empty cache, then offline.

### Step 2: pipeline on a VPS

![Deployment after step 2](diagrams/map-2-step-2.svg)

The same pipeline on a VPS timer, with the production key; the signing key lives on the VPS only. Scope grows to all champions, roles, elos and regions; paths already have `{region}/{elo}`.

- Watch: a run below its floors should not publish.
- Done when: a timer run publishes unattended.

### Step 3: web build viewer

![Deployment after step 3](diagrams/map-3-step-3.svg)

The same UI with an `HttpBackend` reading the CDN (ADR-018), hosted with the site. Read-only: no League client in a browser.

- Blockers: ranking runs in the Rust core (section 3); names and icons come from the client, so the viewer needs Data Dragon.

### Step 4: public release (target)

![Deployment at the target](diagrams/map-4-target.svg)

Players install a signed, self-updating app that fetches data from the CDN; a VPS keeps the data fresh; the web viewer serves build preparation. CI builds signed installers and an update manifest for the Tauri updater; the app carries the release public key. App and data update independently.

- Open: the updater key is a third secret; the release host is GitHub Releases or R2.

## 2. Inside the pipeline

First, the order stages run and the files they pass on.

![Pipeline activity](diagrams/pipeline-flow.svg)

wpa reads extract's tables as well as the model; publish rereads the crawl for game counts and the rune page of each keystone. `just pipeline` runs all five; `just pipeline-stage <name>` runs one.

Second, the ports each command requires and their implementations.

![Pipeline commands, ports and implementations](diagrams/pipeline-ports.svg)

Every port has a file or replay implementation, so the pipeline runs offline on the committed fixture. Planned: `R2Publisher` (M4), WPA v2 (M5).

## 3. Inside the desktop app

The UI only calls `Backend.run(id, params)`; every core entry point dispatches through one registry. The web viewer is another backend; an MCP server would be another entry point.

![App components](diagrams/app.svg)

Commands reach the outside only through three ports, so the core runs against the real client or lcu-mock, and a folder or the CDN. src-tauri also runs lcu's `watch()` to push champion select changes to the UI. The UI's command types are generated from the registry (`stronk-core schema`, ADR-053).

> **Open question for the web viewer.** The view renders `build.plan`, whose ranking lives in the Rust core (ADR-049). A browser has no core. Options:
>
> - **Compile `domain` and the plan code to WebAssembly** (recommended): one rule, and `domain` has no I/O.
> - `publish` writes ranked plans: simpler, but the rule is duplicated in Python.
> - Rewrite ranking in TypeScript: undoes ADR-049.
>
> Same for names and icons, which come from the League client.

## 4. One champion select, end to end

The path under the 300 ms budget. The build is fetched and verified on hover, so lock-in is a cache hit plus the writes to the client.

![Lock-in sequence](diagrams/lock-in.svg)

Commands travel UI → TauriBackend → src-tauri → Registry over IPC; that hop is left out. The UI decides when to import; the core only answers commands. The bracket is what `just bench` measures (`lockin_import_cache_hit`: 200 replays on lcu-mock, debug build).

## 5. How data is trusted

The app trusts the public key built into it, not the host. The CDN and `serve-data` go through `HttpSource`, shown here; a folder goes through `DirectorySource`, which runs the same two checks without the HTTP steps.

![Data trust activity](diagrams/trust.svg)

Only `index.json` is unsigned, so the app never lets it move to an older patch (ADR-046). Plain `http://` is accepted only for `127.0.0.1` and `[::1]`.

## What each step changes

| Step | Part | Today | Adds |
|---|---|---|---|
| 1 | `Publisher`, data URL | LocalPublisher; folder or serve-data | R2Publisher; CDN URL |
| 2 | Where it runs, Riot key | WSL by hand; dev key | VPS timer; production key; more regions and elos |
| 3 | `Backend` interface | Tauri, Mock, Core | HttpBackend, plus ranking in the browser |
| 4 | Shell and build | Unsigned dev build | Code signing, updater, release public key |
| Later | Entry points, `Estimator` | Tauri, CLI; WPA v1 | MCP server; WPA v2 |
