import json
from pathlib import Path
from typing import Any

import bench
import check_budgets
import check_floors
import pipeline_metrics
from ratchet import loosened, unjustified

FLOOR = {"metric": "m.error", "source": "out.json", "max": 0.1}
BUDGET = {
    "scenario": "lockin",
    "description": "d",
    "source": "out.json",
    "unit": "ms",
    "p95": 300,
    "enforce": True,
}


def write(tmp_path: Path, values: dict[str, Any]) -> Path:
    (tmp_path / "out.json").write_text(json.dumps(values))
    return tmp_path


def test_floor_met(tmp_path: Path) -> None:
    _, problems = check_floors.check([FLOOR], write(tmp_path, {"m.error": 0.05}))
    assert problems == []


def test_floor_breached(tmp_path: Path) -> None:
    _, problems = check_floors.check([FLOOR], write(tmp_path, {"m.error": 0.2}))
    assert len(problems) == 1


def test_enforced_floor_without_value_fails(tmp_path: Path) -> None:
    _, problems = check_floors.check([FLOOR], tmp_path)
    assert problems == ["m.error: no value in out.json"]


def test_floors_are_checked_by_their_suite(tmp_path: Path) -> None:
    full = {**FLOOR, "metric": "m.full", "suite": "full"}
    root = write(tmp_path, {"m.error": 0.05})
    assert check_floors.check([FLOOR, full], root) == (
        check_floors.check([FLOOR], root)
    )  # `full` isn't measured by `just check`
    _, problems = check_floors.check([FLOOR, full], root, "full")
    assert problems == ["m.full: no value in out.json"]


def test_pending_floor_never_fails(tmp_path: Path) -> None:
    pending = {"metric": "m.later", "source": "out.json", "enforce": False}
    report, problems = check_floors.check([pending], tmp_path)
    assert problems == []
    assert "pending" in report[0]


def test_budget_met_and_breached(tmp_path: Path) -> None:
    _, ok = check_budgets.check([BUDGET], write(tmp_path, {"p50": 80, "p95": 250}))
    _, bad = check_budgets.check([BUDGET], write(tmp_path, {"p50": 80, "p95": 350}))
    assert ok == []
    assert len(bad) == 1


def test_unenforced_budget_without_results_passes(tmp_path: Path) -> None:
    _, problems = check_budgets.check([{**BUDGET, "enforce": False}], tmp_path)
    assert problems == []


def test_malformed_budget_fails(tmp_path: Path) -> None:
    _, problems = check_budgets.check([{"scenario": "x", "enforce": False}], tmp_path)
    assert len(problems) == 1


def test_loosening_is_detected() -> None:
    def changed(**kw: Any) -> list[str]:
        return loosened(
            [FLOOR],
            [{**FLOOR, **kw}],
            key="metric",
            limits={"max": "upper", "min": "lower"},
            enforce_default=True,
        )

    assert changed(max=0.05) == []  # tightened
    assert changed(max=0.2) == ["m.error"]
    assert changed(enforce=False) == ["m.error"]
    assert loosened([FLOOR], [], key="metric", limits={}, enforce_default=True) == ["m.error"]


def test_loosening_needs_a_decision(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions.md"
    decisions.write_text("ADR-099: relax m.error because ...")
    assert unjustified(["m.error", "m.other"], decisions) == ["m.other"]


def test_committed_floors_and_budgets_parse(tmp_path: Path) -> None:
    """Well-formed config only: measured results are `just budgets`' job, after `just bench`."""
    import tomllib

    root = Path(__file__).resolve().parents[3]
    floors = tomllib.loads((root / "metrics/floors.toml").read_text())["floor"]
    budgets = tomllib.loads((root / "perf/budgets.toml").read_text())["budget"]
    assert all({"metric", "source"} <= f.keys() for f in floors)
    _, problems = check_budgets.check(budgets, tmp_path)  # no results there
    enforced = {b["scenario"] for b in budgets if b["enforce"]}
    assert {p.split(":")[0] for p in problems} == enforced
    assert all(p.endswith("over budget or not measured") for p in problems)


def test_pipeline_metrics_read_the_extract_report() -> None:
    report = {"stage": "extract", "result": {"skip_rate": 0.25}}
    assert pipeline_metrics.metrics(report) == {"pipeline.skip_rate": 0.25}


def test_pipeline_metrics_read_the_winprob_report() -> None:
    report = {"stage": "winprob", "result": {"test": {"calibration_error": 0.01, "log_loss": 0.5}}}
    assert pipeline_metrics.metrics(report) == {
        "winprob.calibration_error": 0.01,
        "winprob.log_loss": 0.5,
    }
    assert pipeline_metrics.metrics(report, "ci") == {
        "winprob.ci.calibration_error": 0.01,
        "winprob.ci.log_loss": 0.5,
    }
    extract = {"stage": "extract", "result": {"skip_rate": 0.0}}
    assert pipeline_metrics.metrics(extract, "full") == {"extract.full.skip_rate": 0.0}


def test_bench_reports_median_and_max() -> None:
    ticks = iter([0.0, 1.0, 1.0, 4.0, 4.0, 6.0])  # runs of 1, 3 and 2 s
    runs: list[None] = []
    result = bench.measure(lambda: runs.append(None), repeats=3, clock=lambda: next(ticks))
    assert result == {"p50": 2.0, "max": 3.0}
    assert len(runs) == 3


def test_rust_layers_point_inward() -> None:
    import rust_layers

    def package(name: str, *deps: str) -> rust_layers.Package:
        return {"name": name, "dependencies": [{"name": d, "kind": None} for d in deps]}

    ok = [package("stronk-domain"), package("stronk-service", "stronk-domain", "serde")]
    assert rust_layers.violations(ok) == []
    bad = [package("stronk-domain", "stronk-service"), package("stronk-service")]
    assert rust_layers.violations(bad) == ["stronk-domain must not depend on stronk-service"]


def test_tls_exceptions_live_in_the_lcu_verifier_only(tmp_path: Path) -> None:
    import rust_layers

    home = tmp_path / "crates/lcu/src/tls.rs"
    home.parent.mkdir(parents=True)
    home.write_text("builder.dangerous()")
    assert rust_layers.tls_exceptions(tmp_path) == []
    other = tmp_path / "crates/data/src/http.rs"
    other.parent.mkdir(parents=True)
    other.write_text("Client::builder().danger_accept_invalid_certs(true)")
    assert rust_layers.tls_exceptions(tmp_path) == [
        "crates/data/src/http.rs: danger_accept_invalid outside crates/lcu/src/tls.rs"
    ]
