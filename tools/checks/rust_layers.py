"""Layer rules for the app's Cargo workspace (docs/architecture.md, section 2).

Cargo already refuses undeclared dependencies; this checks the declared ones point inward:
domain depends on no app crate, service only on domain (and the contracts), adapters on service
and domain, and only entry points (cli, src-tauri) on adapters.

It also keeps TLS exceptions in one place (ADR-042): rustls' `.dangerous()` and reqwest's
`danger_accept_invalid_*` may appear only in the LCU verifier, `crates/lcu/src/tls.rs`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
ALLOWED: dict[str, set[str]] = {
    "stronk-domain": set(),
    "stronk-service": {"stronk-domain", "stronk-contracts"},
    "stronk-data": {"stronk-domain", "stronk-service", "stronk-contracts"},
    "stronk-lcu": {"stronk-domain", "stronk-service"},
    "stronk-cli": {"stronk-service", "stronk-data", "stronk-lcu", "stronk-domain"},
    "stronk-app": {"stronk-service", "stronk-data", "stronk-lcu", "stronk-domain"},
}


type Package = dict[str, Any]
"""One `cargo metadata` package: `name` and `dependencies` ({name, kind})."""


def violations(packages: list[Package]) -> list[str]:
    ours = {str(p["name"]) for p in packages} | {"stronk-contracts"}
    out: list[str] = []
    for package in packages:
        name = str(package["name"])
        dependencies = cast("list[dict[str, Any]]", package["dependencies"])
        deps = {
            str(d["name"]) for d in dependencies if d["kind"] is None and str(d["name"]) in ours
        }
        if name not in ALLOWED:
            out.append(f"{name}: no layer rule (add it to tools/checks/rust_layers.py)")
            continue
        out += [f"{name} must not depend on {d}" for d in sorted(deps - ALLOWED[name])]
    return out


TLS_EXCEPTION = ("dangerous()", "danger_accept_invalid")
TLS_EXCEPTION_HOME = Path("crates/lcu/src/tls.rs")


def tls_exceptions(core: Path) -> list[str]:
    """Rust files outside the LCU verifier that loosen TLS verification."""
    out: list[str] = []
    for path in sorted(core.rglob("*.rs")):
        relative = path.relative_to(core)
        if relative.parts[0] == "target" or relative == TLS_EXCEPTION_HOME:
            continue
        text = path.read_text()
        out += [f"{relative}: {m} outside {TLS_EXCEPTION_HOME}" for m in TLS_EXCEPTION if m in text]
    return out


def main() -> int:
    result = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps",
         "--manifest-path", str(ROOT / "app/core/Cargo.toml")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    problems = violations(json.loads(result.stdout)["packages"])
    problems += tls_exceptions(ROOT / "app/core")
    for p in problems:
        print(f"rust layers: {p}", file=sys.stderr)
    print("rust layers: " + ("broken" if problems else "kept"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
