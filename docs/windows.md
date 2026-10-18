# Building and running on Windows

The League client runs on Windows, and WSL2 can't reach its `127.0.0.1`, so real-client testing happens on a native Windows build. CI builds and tests the same thing (`.github/workflows/ci.yml`, job `windows`).

## One-time setup

1. **Visual Studio Build Tools** with the "Desktop development with C++" workload (the MSVC linker Rust needs).
2. **Rust** with rustup, MSVC toolchain: `rustup toolchain install 1.99.0` (the version in `.mise.toml`).
3. **Node 24 and pnpm**: `winget install OpenJS.NodeJS.LTS`, then `corepack enable` (pnpm comes from `packageManager` in `package.json`).
4. **WebView2**: preinstalled on Windows 10 and 11.
5. Optional, for the mock tests only: **uv** (`winget install astral-sh.uv`).

Clone the repository on the Windows file system (for example `C:\src\stronk`), not under `\\wsl$`: builds there are slow and file watching breaks.

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

## If the client's certificate is rejected

The app trusts Riot's League client CA (`app/core/crates/lcu/certs/riotgames.pem`). If the real client's certificate doesn't validate against it, the error says why and names the certificate presented, for example:

```
League client certificate rejected: signature doesn't verify against the root (...) (presented: subject "...", issuer "...", signature ..., sha256 9F3A...)
```

Send that line. The fallback is to pin that certificate: `--lcu-pin <sha256>` (or `STRONK_LCU_PIN`), which accepts exactly that certificate and nothing else; it gets recorded in docs/security.md before it becomes a default.

## Run the desktop app against the real client

```powershell
$env:STRONK_DATA_DIR = "$PWD\fixtures\data"
$env:STRONK_DATA_KEY = "$PWD\fixtures\data.pub"
pnpm --filter @stronk/ui exec tauri dev --config ../core/src-tauri/tauri.conf.json
```

Then enter a champion select: the app shows the champion and role and, when the fixture data has that champion and role, its build. Without the variables, the app reports which setting is missing instead of starting blind.

## Run the tests

```powershell
cargo test --manifest-path app/core/Cargo.toml --locked
pnpm --filter @stronk/ui test
cargo build --manifest-path app/core/Cargo.toml -p stronk-cli
$env:STRONK_CORE_BIN = "$PWD\app\core\target\debug\stronk-core.exe"
uv run pytest tools/lcu_mock
```
