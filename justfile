# Stronk tasks. Run `mise install` once for toolchains, then `just setup`.
# Everything below runs offline after setup.

set shell := ["bash", "-euo", "pipefail", "-c"]

# Windows: PowerShell instead (System32\bash.exe is WSL). App recipes only; the pipeline stays in WSL
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

contracts_rs := "--manifest-path contracts/generated/rust/Cargo.toml"
core_rs := "--manifest-path app/core/Cargo.toml"
ci_corpus := "crawl-ci-16.20"
full_corpus := "crawl-all-16.20"
next_corpus := "crawl-all-16.21"

# List recipes
default:
    @just --list

# Install dependencies and git hooks
[unix]
setup:
    uv sync --all-packages --locked
    pnpm install --frozen-lockfile
    cargo fetch {{ contracts_rs }} --locked
    cargo fetch {{ core_rs }} --locked
    if git rev-parse --git-dir >/dev/null 2>&1; then uv run pre-commit install --hook-type pre-commit --hook-type commit-msg; fi

# Install dependencies and git hooks (Windows: uv for lcu-mock, pnpm, cargo)
[windows]
setup:
    uv sync --all-packages --locked
    pnpm install --frozen-lockfile
    cargo fetch {{ contracts_rs }} --locked
    cargo fetch {{ core_rs }} --locked
    if (git rev-parse --git-dir 2>$null) { uv run pre-commit install --hook-type pre-commit --hook-type commit-msg }

# Format, lint, typecheck, architecture rules, tests, codegen drift, floors, budgets
check: fmt-check lint typecheck arch test core-e2e e2e gen-check floors bench budgets
    @echo "check: all green"

# Format all code in place
fmt:
    uv run ruff format .
    uv run ruff check --fix-only --quiet .
    cargo fmt {{ contracts_rs }}
    cargo fmt {{ core_rs }} --all

fmt-check:
    uv run ruff format --check .
    cargo fmt --check {{ contracts_rs }}
    cargo fmt --check {{ core_rs }} --all

lint:
    uv run ruff check .
    cargo clippy {{ contracts_rs }} --all-targets --locked --quiet -- -D warnings
    cargo clippy {{ core_rs }} --all-targets --locked --quiet -- -D warnings

typecheck:
    pnpm exec pyright
    pnpm exec tsc -p contracts/generated/ts
    pnpm --filter @stronk/ui check

# Dependency rules between layers (import-linter; Cargo crate graph)
arch:
    uv run lint-imports
    uv run python tools/checks/rust_layers.py

# All tests
[unix]
test:
    uv run pytest
    cargo test {{ contracts_rs }} --locked --quiet
    cargo test {{ core_rs }} --locked --quiet
    pnpm --filter @stronk/ui test

# Rust and UI tests (Windows; the Python tests run in WSL)
[windows]
test:
    cargo test {{ contracts_rs }} --locked --quiet
    cargo test {{ core_rs }} --locked --quiet
    pnpm --filter @stronk/ui test

# Regenerate types from contracts/schemas/, and the UI's command types from the core
gen:
    uv run python contracts/codegen.py
    uv run python contracts/commands_codegen.py

# Fail if contracts/generated/ or the UI's command types (from `stronk-core schema`) are stale
gen-check:
    uv run python contracts/codegen.py --check
    uv run python contracts/commands_codegen.py --check

# Full pipeline offline on the committed recording (fixtures/riot/euw1), into runs/pipeline/,
# published under runs/pipeline/dist with a throwaway key (never dist/data)
pipeline out="runs/pipeline":
    rm -rf {{ out }}
    uv run stronk-pipeline run crawl.run --params '{"platform": "euw1", "max_matches": 10, "replay": "fixtures/riot/euw1", "out": "{{ out }}/crawl"}'
    uv run stronk-pipeline run extract.run --params '{"crawl": "{{ out }}/crawl", "out": "{{ out }}/extract"}'
    uv run stronk-pipeline run winprob.train --params '{"frames": "{{ out }}/extract/frames.parquet", "out": "{{ out }}/winprob"}' > /dev/null
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}/extract/decisions.parquet", "winprob": "{{ out }}/winprob/model.json", "out": "{{ out }}/estimates.json"}' > {{ out }}/wpa.json
    uv run stronk-pipeline run signing.keygen --params '{"out": "{{ out }}/throwaway.key"}' > /dev/null
    uv run stronk-pipeline run publish --params '{"estimates": "{{ out }}/estimates.json", "crawl": "{{ out }}/crawl", "key": "{{ out }}/throwaway.key", "out": "{{ out }}/dist"}'

# Create the data signing key, outside the repository; prints the public key for the app
keygen out="~/.config/stronk/signing.key":
    uv run stronk-pipeline run signing.keygen --params '{"out": "'"$(eval echo {{ out }})"'"}'

# Serve dist/data/ locally like the CDN (ETag, CORS): just serve-data [root] [port]
serve-data root="dist/data" port="8787":
    uv run python tools/serve_data/serve_data.py --root {{ root }} --port {{ port }}

# The product site (site/public) on 127.0.0.1, as Cloudflare serves it
site port="8788":
    python3 site/serve.py --port {{ port }}

# Signed build files into dist/data/ from estimates and their crawls (comma-separated)
publish estimates crawl key="~/.config/stronk/signing.key" out="dist/data":
    #!/usr/bin/env bash
    set -euo pipefail
    crawls=$(printf '%s' "{{ crawl }}" | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read().split(",")))')
    uv run stronk-pipeline run publish --params '{"estimates": "{{ estimates }}", "crawl": '"$crawls"', "key": "'"$(eval echo {{ key }})"'", "out": "{{ out }}"}'

# Real data for the app from the full corpus (crawl-all-16.20), signed with your key (stops if
# missing: `just keygen` once): runs/real/data and its public key runs/real/data.pub, for `just app-real`
[unix]
data-real key="~/.config/stronk/signing.key" out="runs/real":
    #!/usr/bin/env bash
    set -euo pipefail
    key=$(eval echo {{ key }})
    if [ ! -f "$key" ]; then echo "no signing key at $key: create it once with just keygen (it prints the public key the app needs)" >&2; exit 1; fi
    just corpus {{ full_corpus }}
    just extract corpus/{{ full_corpus }} {{ out }}/extract > /dev/null
    just winprob {{ out }}/extract/frames.parquet {{ out }}/winprob > /dev/null
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}/extract/decisions.parquet", "winprob": "{{ out }}/winprob/model.json", "out": "{{ out }}/estimates.json"}' > {{ out }}/wpa.json
    rm -rf {{ out }}/data
    just publish {{ out }}/estimates.json corpus/{{ full_corpus }} "$key" {{ out }}/data > /dev/null
    cp "$key.pub" {{ out }}/data.pub
    echo "real data: {{ out }}/data, public key {{ out }}/data.pub"

# One patch's WPA contrasts against the next (ADR-055); metrics for backtest.* in floors.toml
backtest earlier later out="runs/backtest":
    uv run stronk-pipeline run backtest.run --params '{"earlier": "{{ earlier }}", "later": "{{ later }}", "out": "{{ out }}"}'
    uv run python tools/checks/pipeline_metrics.py {{ out }}/report.json metrics/out/backtest.json

# Patch backtest on corpora: WPA on the earlier run (extract and winprob already in <earlier>)
# and on the later corpus (extracted into <out>), then `just backtest`
backtest-corpora earlier later out:
    just extract {{ later }} {{ out }}/extract > /dev/null
    just winprob {{ out }}/extract/frames.parquet {{ out }}/winprob > /dev/null
    for run in {{ earlier }} {{ out }}; do uv run stronk-pipeline run wpa.estimate --params '{"decisions": "'"$run"'/extract/decisions.parquet", "winprob": "'"$run"'/winprob/model.json", "out": "'"$run"'/estimates.json"}' > /dev/null; done
    just backtest {{ earlier }}/estimates.json {{ out }}/estimates.json {{ out }}/backtest > /dev/null

# Win probability model on frames: just winprob runs/extract/euw1/frames.parquet runs/winprob/euw1
winprob frames="runs/extract/euw1/frames.parquet" out="runs/winprob/euw1":
    uv run stronk-pipeline run winprob.train --params '{"frames": "{{ frames }}", "out": "{{ out }}"}'

# Crawl ranked games from the Riot API (needs RIOT_API_KEY); rerun to resume
crawl platform="euw1" games="100" out=("runs/crawl/" + platform):
    uv run stronk-pipeline run crawl.run --params '{"platform": "{{ platform }}", "max_matches": {{ games }}, "out": "{{ out }}"}'

# Frames and decision points from crawl directories (comma-separated for several);
# --retry-quarantine re-reads quarantined games first
extract crawl="runs/crawl/euw1" out="runs/extract/euw1" *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    crawls=$(printf '%s' "{{ crawl }}" | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read().split(",")))')
    retry=false
    for flag in {{ flags }}; do
        case "$flag" in
            --retry-quarantine) retry=true ;;
            *) echo "unknown flag $flag; known: --retry-quarantine" >&2; exit 2 ;;
        esac
    done
    uv run stronk-pipeline run extract.run --params '{"crawl": '"$crawls"', "out": "{{ out }}", "retry_quarantine": '"$retry"'}'

# One pipeline stage by name (crawl, extract, wpa) with JSON parameters
pipeline-stage name params="{}":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ name }}" in
        crawl) id=crawl.run ;;
        extract) id=extract.run ;;
        winprob) id=winprob.train ;;
        wpa) id=wpa.estimate ;;
        *) echo "unknown stage {{ name }}; known: crawl, extract, winprob, wpa" >&2; exit 2 ;;
    esac
    uv run stronk-pipeline run "$id" --params '{{ params }}'

# Fetch and verify corpus.lock entries into corpus/: all, or the ones named
corpus *names:
    GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}" uv run python tools/corpus/corpus.py fetch {{ names }}

# Archive a crawl directory for the corpus and print its corpus.lock entry
# One crawl from several, all games or N stratified by crawl: just corpus-merge <out> "<crawl> <crawl>" [N]
corpus-merge out crawls games="":
    uv run python tools/corpus/corpus.py merge {{ out }} {{ crawls }} {{ if games == "" { "" } else { "--games " + games } }}

corpus-pack crawl name:
    uv run python tools/corpus/corpus.py pack {{ crawl }} {{ name }}

# Synthetic-truth metrics against metrics/floors.toml
floors: (corpus ci_corpus)
    uv run stronk-synth eval --out metrics/out/synthetic.json > /dev/null
    just pipeline > /dev/null
    uv run python tools/checks/pipeline_metrics.py runs/pipeline/extract/report.json metrics/out/pipeline.json
    just corpus-floors {{ ci_corpus }} ci
    uv run python tools/checks/check_floors.py

# Floors on the full corpus (all regions): the weekly CI job, or by hand
floors-full: (corpus full_corpus next_corpus)
    just corpus-floors {{ full_corpus }} full
    just backtest-corpora runs/floors-full corpus/{{ next_corpus }} runs/floors-next
    uv run python tools/checks/check_floors.py --suite full

# Extract and winprob on one corpus entry, metrics named after it: just corpus-floors <name> <tag>
corpus-floors name tag:
    just extract corpus/{{ name }} runs/floors-{{ tag }}/extract > /dev/null
    just winprob runs/floors-{{ tag }}/extract/frames.parquet runs/floors-{{ tag }}/winprob > /dev/null
    uv run python tools/checks/pipeline_metrics.py runs/floors-{{ tag }}/extract/report.json metrics/out/extract-{{ tag }}.json {{ tag }}
    uv run python tools/checks/pipeline_metrics.py runs/floors-{{ tag }}/winprob/report.json metrics/out/winprob-{{ tag }}.json {{ tag }}

# Benchmark results against perf/budgets.toml
budgets:
    uv run python tools/checks/check_budgets.py

# Performance scenarios, results in perf/out/ (checked by `just budgets`)
bench:
    cargo build {{ core_rs }} --locked --quiet -p stronk-cli
    STRONK_CORE_BIN="$PWD/app/core/target/debug/stronk-core" PYTHONPATH=tools/lcu_mock uv run python tools/checks/bench.py

# Run a pipeline command: just pipeline-run wpa.estimate '{"decisions": "runs/synth/decisions.parquet"}'
pipeline-run id params="{}":
    uv run stronk-pipeline run {{ id }} --params '{{ params }}'

# Generate synthetic games and estimate WPA on them
synth out="runs/synth/decisions.parquet":
    uv run stronk-synth generate --out {{ out }}
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}"}'

# Run an app command from the terminal: just core build.get '{"champion": "LeeSin", "role": "JUNGLE"}'
[unix]
core id params="{}":
    cargo run {{ core_rs }} --quiet -p stronk-cli -- run {{ id }} --params '{{ params }}'

# Run an app command from the terminal (Windows PowerShell drops unescaped quotes passed to programs)
[windows]
core id params="{}":
    cargo run {{ core_rs }} --quiet -p stronk-cli -- run {{ id }} --params '{{ replace(params, '"', '\"') }}'

# Refresh fixtures/data (signed fixture pipeline output) and its throwaway public key
fixture-data:
    just pipeline > /dev/null
    rm -rf fixtures/data && mkdir -p fixtures/data
    cp -r runs/pipeline/dist/. fixtures/data/
    cp runs/pipeline/throwaway.key.pub fixtures/data.pub

# The real core against lcu-mock and the signed fixture data, and the recorder's scrubbing
core-e2e:
    cargo build {{ core_rs }} --locked --quiet -p stronk-cli
    STRONK_CORE_BIN="$PWD/app/core/target/debug/stronk-core" uv run pytest -q tools/lcu_mock/tests/test_core_against_mock.py tools/lcu_mock/tests/test_record_against_mock.py tools/lcu_mock/tests/test_import_against_mock.py tools/lcu_mock/tests/test_watch_against_mock.py

# Playwright: the UI in Chromium against MockBackend and against the real core on lcu-mock
# (tools/lcu_mock/core_bridge.py); screenshots in runs/e2e/screenshots/. Needs a Chromium:
# `pnpm --filter @stronk/ui exec playwright install chromium`, or STRONK_CHROMIUM=<path>
[unix]
e2e *args:
    cargo build {{ core_rs }} --locked --quiet -p stronk-cli
    rm -rf runs/e2e
    STRONK_CORE_BIN="$PWD/app/core/target/debug/stronk-core" pnpm --filter @stronk/ui exec playwright test {{ args }}

# Playwright end to end (Windows PowerShell)
[windows]
e2e *args:
    cargo build {{ core_rs }} --locked --quiet -p stronk-cli
    if (Test-Path runs/e2e) { Remove-Item -Recurse -Force runs/e2e }
    $env:STRONK_CORE_BIN = "$PWD/app/core/target/debug/stronk-core.exe"; pnpm --filter @stronk/ui exec playwright test {{ args }}

# The board on real data (ADR-061): every build checked for what a player must not see, then
# Playwright on a few picks against the real core and lcu-mock, screenshots in
# runs/e2e-real/screenshots/. Run after a UI change. Not in `check`: CI has no real data.
[unix]
e2e-real data="runs/real/data" key="runs/real/data.pub" picks="":
    #!/usr/bin/env bash
    set -uo pipefail
    if [ ! -f "{{ key }}" ]; then echo "no {{ key }}: run \`just data-real\` first" >&2; exit 1; fi
    cargo build {{ core_rs }} --locked --quiet -p stronk-cli
    rm -rf runs/e2e-real
    uv run python tools/lcu_mock/real_session.py --data "{{ data }}" --out runs/e2e-real/session.json {{ if picks != "" { "--picks " + picks } else { "" } }} || exit 1
    uv run python tools/checks/board_sanity.py --core app/core/target/debug/stronk-core --data "{{ data }}" --key "{{ key }}"; sane=$?
    STRONK_CORE_BIN="$PWD/app/core/target/debug/stronk-core" STRONK_REAL_DATA="{{ data }}" STRONK_REAL_KEY="{{ key }}" \
        pnpm --filter @stronk/ui exec playwright test --config playwright.real.config.ts; shown=$?
    echo "screenshots: runs/e2e-real/screenshots/"
    exit $(( sane || shown ))

# Fake League client replaying a session: just lcu-mock tools/lcu_mock/sessions/<file>.json
lcu-mock session="tools/lcu_mock/sessions/ranked-jungle-leesin.json":
    uv run python tools/lcu_mock/lcu_mock.py {{ session }}

# UI in the browser against MockBackend: http://127.0.0.1:5173/?scenario=ranked-jungle|pages-full|no-client|bad-data
app-mock:
    pnpm --filter @stronk/ui dev

# Desktop app on the fixture data, talking to `just lcu-mock` (needs WebKitGTK on Linux)
[unix]
app:
    STRONK_DATA_DIR="$PWD/fixtures/data" STRONK_DATA_KEY="$PWD/fixtures/data.pub" \
    STRONK_LCU_LOCKFILE="$PWD/runs/lcu-mock/lockfile" STRONK_LCU_CERT="$PWD/runs/lcu-mock/root.pem" \
    pnpm --filter @stronk/ui exec tauri dev --config ../core/src-tauri/tauri.conf.json

# Desktop app on the fixture data, talking to `just lcu-mock`
[windows]
app:
    $env:STRONK_DATA_DIR = "$PWD/fixtures/data"; $env:STRONK_DATA_KEY = "$PWD/fixtures/data.pub"; \
    $env:STRONK_LCU_LOCKFILE = "$PWD/runs/lcu-mock/lockfile"; $env:STRONK_LCU_CERT = "$PWD/runs/lcu-mock/root.pem"; \
    $env:TAURI_APP_PATH = "$PWD/app/core/src-tauri"; pnpm --filter @stronk/ui exec tauri dev

# Desktop app on real data, talking to the real League client (start League first). Data is a
# folder or a `just serve-data` URL; default runs/real from `just data-real`, or fixtures/data
[unix]
app-real data="runs/real/data" key="runs/real/data.pub":
    #!/usr/bin/env bash
    set -euo pipefail
    data="{{ data }}"; key="{{ key }}"
    case "$data" in http://*|https://*|/*) ;; *) data="$PWD/$data" ;; esac
    case "$key" in /*) ;; *) key="$PWD/$key" ;; esac
    if [ ! -f "$key" ]; then echo "no $key: unzip the real data here, run \`just data-real\` first, or \`just app-real fixtures/data fixtures/data.pub\` for the test data" >&2; exit 1; fi
    STRONK_DATA_DIR="$data" STRONK_DATA_KEY="$key" \
    pnpm --filter @stronk/ui exec tauri dev --config ../core/src-tauri/tauri.conf.json

# Desktop app on real data, talking to the real League client (Windows PowerShell)
[windows]
app-real data="runs/real/data" key="runs/real/data.pub":
    $data = '{{ data }}'; $key = '{{ key }}'; \
    if (-not (Test-Path $key)) { Write-Host -ForegroundColor Red "no ${key}: unzip the real data into this clone, copy runs/real from WSL after ``just data-real``, or run ``just app-real fixtures/data fixtures/data.pub`` for the test data"; exit 1 }; \
    if ($data -notmatch '^https?://') { $data = (Resolve-Path $data).Path }; \
    $env:STRONK_DATA_DIR = $data; $env:STRONK_DATA_KEY = (Resolve-Path $key).Path; \
    $env:TAURI_APP_PATH = "$PWD/app/core/src-tauri"; pnpm --filter @stronk/ui exec tauri dev

# Build and lint the Tauri shell (needs WebKitGTK on Linux; CI's app-shell job)
app-build:
    pnpm --filter @stronk/ui build
    cargo clippy {{ core_rs }} -p stronk-app --all-targets --locked --quiet -- -D warnings
    cargo build {{ core_rs }} -p stronk-app --locked --quiet
