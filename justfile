# Stronk tasks. Run `mise install` once for toolchains, then `just setup`.
# Everything below runs offline after setup.

set shell := ["bash", "-euo", "pipefail", "-c"]

contracts_rs := "--manifest-path contracts/generated/rust/Cargo.toml"

# List recipes
default:
    @just --list

# Install dependencies and git hooks
setup:
    uv sync --all-packages --locked
    pnpm install --frozen-lockfile
    cargo fetch {{ contracts_rs }} --locked
    if git rev-parse --git-dir >/dev/null 2>&1; then uv run pre-commit install --hook-type pre-commit --hook-type commit-msg; fi

# Format, lint, typecheck, architecture rules, tests, codegen drift, floors, budgets
check: fmt-check lint typecheck arch test gen-check floors budgets
    @echo "check: all green"

# Format all code in place
fmt:
    uv run ruff format .
    uv run ruff check --fix-only --quiet .
    cargo fmt {{ contracts_rs }}

fmt-check:
    uv run ruff format --check .
    cargo fmt --check {{ contracts_rs }}

lint:
    uv run ruff check .
    cargo clippy {{ contracts_rs }} --all-targets --locked --quiet -- -D warnings

typecheck:
    pnpm exec pyright
    pnpm exec tsc -p contracts/generated/ts

# Dependency rules between layers (import-linter)
arch:
    uv run lint-imports

# All tests
test:
    uv run pytest
    cargo test {{ contracts_rs }} --locked --quiet

# Regenerate types from contracts/schemas/
gen:
    uv run python contracts/codegen.py

# Fail if contracts/generated/ is stale
gen-check:
    uv run python contracts/codegen.py --check

# Full pipeline offline on the committed recording (fixtures/riot/euw1), into runs/pipeline/
pipeline out="runs/pipeline":
    rm -rf {{ out }}
    uv run stronk-pipeline run crawl.run --params '{"platform": "euw1", "max_matches": 10, "replay": "fixtures/riot/euw1", "out": "{{ out }}/crawl"}'
    uv run stronk-pipeline run extract.run --params '{"crawl": "{{ out }}/crawl", "out": "{{ out }}/extract"}'
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}/extract/decisions.parquet"}' > {{ out }}/wpa.json

# Crawl ranked games from the Riot API (needs RIOT_API_KEY); rerun to resume
crawl platform="euw1" games="100" out=("runs/crawl/" + platform):
    uv run stronk-pipeline run crawl.run --params '{"platform": "{{ platform }}", "max_matches": {{ games }}, "out": "{{ out }}"}'

# Frames and decision points from a crawl directory; --retry-quarantine re-reads quarantined games first
extract crawl="runs/crawl/euw1" out="runs/extract/euw1" *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    retry=false
    for flag in {{ flags }}; do
        case "$flag" in
            --retry-quarantine) retry=true ;;
            *) echo "unknown flag $flag; known: --retry-quarantine" >&2; exit 2 ;;
        esac
    done
    uv run stronk-pipeline run extract.run --params '{"crawl": "{{ crawl }}", "out": "{{ out }}", "retry_quarantine": '"$retry"'}'

# One pipeline stage by name (crawl, extract, wpa) with JSON parameters
pipeline-stage name params="{}":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ name }}" in
        crawl) id=crawl.run ;;
        extract) id=extract.run ;;
        wpa) id=wpa.estimate ;;
        *) echo "unknown stage {{ name }}; known: crawl, extract, wpa" >&2; exit 2 ;;
    esac
    uv run stronk-pipeline run "$id" --params '{{ params }}'

# Fetch and verify the pinned test corpus (corpus.lock) into corpus/
corpus:
    GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}" uv run python tools/corpus/corpus.py fetch

# Archive a crawl directory for the corpus and print its corpus.lock entry
corpus-pack crawl name:
    uv run python tools/corpus/corpus.py pack {{ crawl }} {{ name }}

# Synthetic-truth metrics against metrics/floors.toml
floors:
    uv run stronk-synth eval --out metrics/out/synthetic.json > /dev/null
    just pipeline > /dev/null
    uv run python tools/checks/pipeline_metrics.py runs/pipeline/extract/report.json metrics/out/pipeline.json
    uv run python tools/checks/check_floors.py

# Benchmark results against perf/budgets.toml
budgets:
    uv run python tools/checks/check_budgets.py

# Run a pipeline command: just pipeline-run wpa.estimate '{"decisions": "runs/synth/decisions.parquet"}'
pipeline-run id params="{}":
    uv run stronk-pipeline run {{ id }} --params '{{ params }}'

# Generate synthetic games and estimate WPA on them
synth out="runs/synth/decisions.parquet":
    uv run stronk-synth generate --out {{ out }}
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}"}'
