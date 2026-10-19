# Building and running on Windows

The League client runs on Windows, and WSL2 can't reach its `127.0.0.1`, so real-client testing happens on a native Windows build. CI builds and tests the same thing (`.github/workflows/ci.yml`, job `windows`).

## One-time setup

1. **Visual Studio Build Tools** with the "Desktop development with C++" workload (the MSVC linker Rust needs).
2. **Rust** with rustup, MSVC toolchain: `rustup toolchain install 1.99.0` (the version in `.mise.toml`).
3. **Node 24 and pnpm**: `winget install OpenJS.NodeJS.LTS`, then `corepack enable` (pnpm comes from `packageManager` in `package.json`).
4. **WebView2**: preinstalled on Windows 10 and 11.
5. **uv** (`winget install astral-sh.uv`), for lcu-mock and its tests.
6. **just** (`winget install Casey.Just`).

Clone the repository on the Windows file system (for example `C:\src\stronk`), not under `\\wsl$`: builds there are slow and file watching breaks. App work happens in this clone; the pipeline stays in WSL.

## With just

On Windows, `just` runs recipes in Windows PowerShell (`windows-shell` in the `justfile`), because the `bash.exe` on the path is WSL's. The app recipes have Windows versions; the pipeline recipes are for WSL.

| Command | Does |
|---|---|
| `just setup` | uv, pnpm and cargo dependencies, git hooks |
| `just test` | Rust (contracts, core) and UI tests; the Python tests run in WSL |
| `just lcu-mock [session]` | Fake League client, writes `runs\lcu-mock\lockfile` and `root.pem` |
| `just app` | Desktop app on the fixture data, talking to `just lcu-mock` |
| `just app-real [data] [key]` | Desktop app on real data (default `runs\real\data`, from `just data-real` in WSL), talking to the real League client |
| `just app-mock` | UI in the browser against `MockBackend` |
| `just core <command-id> [params]` | Run an app command from the terminal |

Run the app against the mock in two terminals: `just lcu-mock` in one, `just app` in the other. The mock moves to its next step on `POST /mock/step` (user `riot` with the lockfile's password, trusting `runs\lcu-mock\root.pem`; see `tools/lcu_mock/lcu_mock.py`), and the app follows it over the websocket.

Windows PowerShell 5.1 drops double quotes inside arguments to programs, `just` included, so escape them in JSON parameters (PowerShell 7.3 and later don't need this):

```powershell
just core build.plan '{\"champion\": \"LeeSin\", \"role\": \"JUNGLE\"}'
```

`just core` reads the same `STRONK_*` variables as the app; set them in the terminal first (see "Run the desktop app against the real client").

## Build

From the repository root, in PowerShell:

```powershell
pnpm install --frozen-lockfile
pnpm --filter @stronk/ui build
cargo build --manifest-path app/core/Cargo.toml --release -p stronk-cli -p stronk-app
```

This gives `app\core\target\release\stronk-core.exe` (the CLI) and `stronk-app.exe` (the desktop app).

## Record a champion select (for `tools/lcu_mock`)

1. Start the League client and log in.
2. Run the recorder; it waits for a champion select and stops when it ends (or after 15 minutes):

   ```powershell
   app\core\target\release\stronk-core.exe record-champselect --out tools\lcu_mock\sessions\custom-2026-10-19.json
   ```

3. Create a custom game, enter champion select, hover a champion, lock one in, and leave or start the game.
4. The recorder saves only allowlisted fields and refuses to save if anything still looks like an identifier (docs/security.md, "League client"). Check the file anyway, then commit it: `tools/lcu_mock/tests/test_sessions_scrubbed.py` checks every committed session again.

The lockfile is found at `C:\Riot Games\League of Legends\lockfile`; for another install folder, pass `--lockfile <path>` or set `STRONK_LCU_LOCKFILE`.

## Restore your item sets

Every import saves your item sets first (in `%APPDATA%\stronk\backups`). To put a backup back:

```powershell
app\core\target\release\stronk-core.exe restore-item-sets          # lists the backups, newest first
app\core\target\release\stronk-core.exe restore-item-sets <file>   # restores one
```

A restore backs up the current sets first, and refuses a backup from another account.

## If the client's certificate is rejected

The app trusts Riot's League client CA (`app/core/crates/lcu/certs/riotgames.pem`). If the real client's certificate doesn't validate against it, the error says why and names the certificate presented, for example:

```
League client certificate rejected: signature doesn't verify against the root (...) (presented: subject "...", issuer "...", signature ..., sha256 9F3A...)
```

Send that line. The fallback is to pin that certificate: `--lcu-pin <sha256>` (or `STRONK_LCU_PIN`), which accepts exactly that certificate and nothing else; it gets recorded in docs/security.md before it becomes a default.

## Run the desktop app against the real client

`just app-real` reads real data from `runs\real\data` with its public key `runs\real\data.pub`. Build them once in WSL from the full corpus (22,954 games), signed with your own key (`~/.config/stronk/signing.key`), then copy them to this clone. `just data-real` stops when the key is missing: creating it is a deliberate step, once (docs/security.md), and `just keygen` prints the public key the app needs.

```bash
just keygen   # once, if you have no signing key yet
just data-real
mkdir -p /mnt/c/src/stronk/runs/real && cp -r runs/real/data runs/real/data.pub /mnt/c/src/stronk/runs/real/
```

Start League, then:

```powershell
just app-real
```

Then enter a champion select: the app shows the champion and role and, when the data has that champion and role, its build and the alternatives per slot. Other sources: `just app-real fixtures/data fixtures/data.pub` for the test data, or `just serve-data runs/real/data` in WSL and `just app-real http://127.0.0.1:8787 runs\real\data.pub` to fetch over HTTP (WSL2 forwards localhost to Windows). Without the variables, the app reports which setting is missing instead of starting blind.

## Run the tests

```powershell
cargo test --manifest-path app/core/Cargo.toml --locked
pnpm --filter @stronk/ui test
cargo build --manifest-path app/core/Cargo.toml -p stronk-cli
$env:STRONK_CORE_BIN = "$PWD\app\core\target\debug\stronk-core.exe"
uv run pytest tools/lcu_mock
```
