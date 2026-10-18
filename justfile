# Stronk tasks. Run `mise install` once for toolchains, then `just setup`.
# Everything below runs offline after setup.

set shell := ["bash", "-euo", "pipefail", "-c"]

contracts_rs := "--manifest-path contracts/generated/rust/Cargo.toml"
ci_corpus := "crawl-ci-16.20"
full_corpus := "crawl-all-16.20"

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
check: fmt-check lint typecheck arch test gen-check floors bench budgets
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

# Signed build files into dist/data/ from estimates and their crawls (comma-separated)
publish estimates crawl key="~/.config/stronk/signing.key" out="dist/data":
    #!/usr/bin/env bash
    set -euo pipefail
    crawls=$(printf '%s' "{{ crawl }}" | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read().split(",")))')
    uv run stronk-pipeline run publish --params '{"estimates": "{{ estimates }}", "crawl": '"$crawls"', "key": "'"$(eval echo {{ key }})"'", "out": "{{ out }}"}'

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
floors-full: (corpus full_corpus)
    just corpus-floors {{ full_corpus }} full
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
    uv run python tools/checks/bench.py

# Run a pipeline command: just pipeline-run wpa.estimate '{"decisions": "runs/synth/decisions.parquet"}'
pipeline-run id params="{}":
    uv run stronk-pipeline run {{ id }} --params '{{ params }}'

# Generate synthetic games and estimate WPA on them
synth out="runs/synth/decisions.parquet":
    uv run stronk-synth generate --out {{ out }}
    uv run stronk-pipeline run wpa.estimate --params '{"decisions": "{{ out }}"}'
