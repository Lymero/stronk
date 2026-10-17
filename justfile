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

# Synthetic-truth metrics against metrics/floors.toml
floors:
    uv run stronk-synth eval --out metrics/out/synthetic.json > /dev/null
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
