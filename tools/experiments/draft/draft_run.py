"""Fit the draft model on one patch, check it on held-out games and on the next patch.

    uv run python tools/experiments/draft/draft_run.py <games> <next> <static.json.gz> <out>

<games> and <next> are draft_games.py tables. Writes <out>/report.json and <out>/coefs.npy
(the fit on every game of the first patch, then its bootstrap fits) and prints a summary:

- penalties chosen on validation games (10% of the first patch's, by match);
- log loss gained over side alone on test games (another 10%) and on the next patch, block by
  block, each with its standard error over games: does each part predict anything?
- stability: each champion's main effect fitted on the next patch alone against the first;
- how many champions, lane matchups and duos are clear (95% bootstrap interval excluding 0);
- what skill and practice change: main effects with and without them;
- the best picks per role in a blind pick, and a few drafts from the next patch, pick by pick.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from draft_model import (
    BLOCKS,
    ROLES,
    Draft,
    Floats,
    Games,
    Scored,
    Shares,
    Vocab,
    design,
    expit,
    fit,
    games_of,
    log_loss,
    penalties,
    score,
    vocab_of,
)
from scipy import sparse

GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0)
START = {"comp": 100.0, "main": 30.0, "lane": 300.0, "duo": 300.0, "cross": 300.0}
TUNED = ("main", "lane", "duo", "cross", "comp")
OFF = 1e9
BOOTSTRAP = 40
VARIANTS = (
    ("side", ()),
    ("+skill, practice", ()),
    ("+champions", ("main",)),
    ("+lane matchups", ("main", "lane")),
    ("+bottom duo, cross", ("main", "lane", "duo", "cross")),
    ("+damage mix", ("main", "lane", "duo", "cross", "comp")),
)
ORDER = (("b", 0), ("r", 0), ("r", 1), ("b", 1), ("b", 2), ("r", 2), ("r", 3), ("b", 3), ("b", 4))
"""Ranked draft order up to blue's last pick: blue 1, red 1-2, blue 2-3, red 3-4, blue 4-5."""


@dataclass(frozen=True)
class Setup:
    v: Vocab
    names: dict[int, str]
    train: Games
    valid: Games
    test: Games
    later: Games
    x: dict[str, sparse.csr_matrix]


def split(ids: np.ndarray) -> np.ndarray:
    """0 train, 1 validation, 2 test: 80/10/10 by a hash of the match id."""
    h = np.array([int(hashlib.sha256(i.encode()).hexdigest()[:8], 16) % 10 for i in ids])
    return np.where(h < 8, 0, np.where(h == 8, 1, 2))


def auc(y: Floats, p: Floats) -> float:
    ranks = np.empty(len(p))
    ranks[np.argsort(p)] = np.arange(1, len(p) + 1)
    pos = y == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def tune(s: Setup) -> dict[str, float]:
    """Each block's penalty in turn over GRID, twice, by validation log loss."""

    def loss(lam: dict[str, float], start: Floats | None) -> tuple[float, Floats]:
        coef = fit(s.x["train"], s.train.blue_win, penalties(s.v, lam), start)
        return float(log_loss(s.valid.blue_win, expit(s.x["valid"] @ coef)).mean()), coef

    lam = dict(START)
    best, coef = loss(lam, None)
    for _ in range(2):
        for block in TUNED:
            for value in GRID:
                trial_loss, trial = loss({**lam, block: value}, coef)
                if trial_loss < best - 1e-7:
                    best, coef, lam = trial_loss, trial, {**lam, block: value}
        print(f"penalties {lam}: validation log loss {best:.5f}")
    return lam


def variants(s: Setup, lam: dict[str, float]) -> list[dict[str, Any]]:
    """Log loss gained over side alone, block by block, on test games and the next patch."""
    rows: list[dict[str, Any]] = []
    base: dict[str, Floats] = {}
    for name, blocks in VARIANTS:
        pen = penalties(s.v, {b: (lam[b] if b in blocks else OFF) for b in TUNED})
        if name == "side":
            pen[1:3] = OFF
        coef = fit(s.x["train"], s.train.blue_win, pen)
        row: dict[str, Any] = {"variant": name}
        for label, games in (("test", s.test), ("next", s.later)):
            p = expit(s.x[label] @ coef)
            loss = log_loss(games.blue_win, p)
            diff = base.setdefault(label, loss) - loss
            row[label] = {
                "log_loss": float(loss.mean()),
                "gain": float(diff.mean()),
                "gain_se": float(diff.std(ddof=1) / np.sqrt(len(diff))),
                "auc": auc(games.blue_win, p),
            }
        rows.append(row)
        t, n = row["test"], row["next"]
        print(
            f"{name:20} test gain {t['gain'] * 1e3:+.2f}e-3 ± {t['gain_se'] * 1e3:.2f} "
            f"auc {t['auc']:.4f} | next {n['gain'] * 1e3:+.2f}e-3 ± {n['gain_se'] * 1e3:.2f} "
            f"auc {n['auc']:.4f}"
        )
    return rows


def bootstrap(games: Games, x: sparse.csr_matrix, pen: Floats) -> Floats:
    """The fit on every game, then BOOTSTRAP fits on games resampled by match."""
    point = fit(x, games.blue_win, pen)
    rng = np.random.default_rng(7)
    n = len(games)
    fits = [point]
    for _ in range(BOOTSTRAP):
        weights = rng.multinomial(n, np.full(n, 1 / n)).astype(float)
        fits.append(fit(x, games.blue_win, pen, point, weights))
    return np.array(fits)


def clear_counts(v: Vocab, clear: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("main", "lane"):
        per_role: dict[str, dict[str, int]] = {}
        table: dict[tuple[int, int], int] | dict[tuple[int, int, int], int] = (
            v.main if kind == "main" else v.lane
        )
        for key, col in table.items():
            role = per_role.setdefault(ROLES[key[0]], {"columns": 0, "clear": 0})
            role["columns"] += 1
            role["clear"] += int(clear[col])
        out[kind] = per_role
    for kind, pairs in (("duo", v.duo), ("cross", v.cross)):
        cols = list(pairs.values())
        out[kind] = {"columns": len(cols), "clear": int(clear[cols].sum())}
    return out


def role_games(games: Games, v: Vocab) -> dict[tuple[int, int], int]:
    out = dict.fromkeys(v.main, 0)
    for r in range(5):
        ids, n = np.unique(games.champion[:, :, r], return_counts=True)
        for i, k in zip(ids, n, strict=True):
            if (r, int(i)) in out:
                out[(r, int(i))] = int(k)
    return out


def stability(
    s: Setup, lam: dict[str, float], point: Floats, clear: np.ndarray
) -> dict[str, float]:
    """Main effects fitted on the next patch alone, against the first patch's."""
    pen = penalties(s.v, {**lam, "lane": OFF, "duo": OFF, "cross": OFF})
    later = fit(s.x["next"], s.later.blue_win, pen)
    first_n = role_games(s.train, s.v)
    next_n = role_games(s.later, s.v)
    cols = [c for k, c in s.v.main.items() if first_n[k] >= 800 and next_n[k] >= 300]
    a, b, c = point[cols], later[cols], clear[cols]
    return {
        "champions": len(cols),
        "correlation": float(np.corrcoef(a, b)[0, 1]),
        "clear": int(c.sum()),
        "clear_same_sign": int((np.sign(a[c]) == np.sign(b[c])).sum()),
    }


def movers(
    s: Setup, games: Games, x: sparse.csr_matrix, point: Floats, lam: dict[str, float]
) -> dict[str, list[tuple[float, str, str]]]:
    """How much skill and practice move each popular champion's main effect (logit)."""
    pen = penalties(s.v, lam)
    pen[1:3] = OFF
    plain = fit(x, games.blue_win, pen, point)
    n = role_games(games, s.v)
    moved = sorted(
        (float(point[col] - plain[col]), s.names.get(k[1], str(k[1])), ROLES[k[0]])
        for k, col in s.v.main.items()
        if n[k] >= 1000
    )
    return {"up": moved[::-1][:6], "down": moved[:6]}


def row_of(scored: Scored, names: dict[int, str]) -> dict[str, Any]:
    return {
        "champion": names.get(scored.champion, str(scored.champion)),
        "effect": round(scored.effect, 2),
        "low": round(scored.low, 2),
        "high": round(scored.high, 2),
        "share": round(scored.share, 4),
    }


def demo(s: Setup, row: int, shares: Shares, coefs: Floats) -> dict[str, Any]:
    """The blue team's picks of one next-patch game, revealed in ranked order with roles
    drawn at random, each blue pick scored when it comes (enemy roles unknown)."""
    g, names = s.later, s.names
    rng = np.random.default_rng(row)
    roles = {"b": list(rng.permutation(5)), "r": list(rng.permutation(5))}
    allies: dict[int, int] = {}
    enemies: list[int] = []
    steps: list[dict[str, Any]] = []
    for side, i in ORDER:
        r = int(roles[side][i])
        if side == "r":
            enemies.append(int(g.champion[row, 1, r]))
            continue
        picked = int(g.champion[row, 0, r])
        ranked = score(
            Draft(role=r, allies=dict(allies), enemies=list(enemies)), s.v, shares, coefs
        )
        mine = next((x for x in ranked if x.champion == picked), None)
        top = [row_of(x, names) for x in ranked[:5]]
        foes = [names.get(e, str(e)) for e in enemies]
        steps.append(
            {
                "pick": len(allies) + len(enemies) + 1,
                "role": ROLES[r],
                "allies": [names.get(a, str(a)) for a in allies.values()],
                "enemies": foes,
                "top": top,
                "picked": row_of(mine, names) if mine else names.get(picked, str(picked)),
            }
        )
        tops = ", ".join(f"{t['champion']} {t['effect']:+.1f}" for t in top[:4])
        played = f"{mine.effect:+.1f}" if mine else "(rare)"
        print(f"  pick {steps[-1]['pick']} {ROLES[r]} vs {foes}: {tops}")
        print(f"    played {names.get(picked, str(picked))} {played}")
        allies[r] = picked
    return {"match": str(g.match_id[row]), "blue_won": bool(g.blue_win[row]), "steps": steps}


def setup(first_path: str, next_path: str, static_path: str) -> tuple[Setup, Games]:
    static = json.loads(gzip.decompress(Path(static_path).read_bytes()))
    names = {int(k): c["name"] for k, c in static["champions"].items()}
    magic = frozenset(int(k) for k, c in static["champions"].items() if c["magic"] > c["attack"])
    first = games_of(pl.read_parquet(first_path))
    later = games_of(pl.read_parquet(next_path))
    part = split(first.match_id)
    train, valid, test = (first.take(part == k) for k in (0, 1, 2))
    v = vocab_of(train, magic)
    x = {
        name: design(g, v)
        for name, g in (("train", train), ("valid", valid), ("test", test), ("next", later))
    }
    return Setup(v, names, train, valid, test, later, x), first


def main(argv: list[str]) -> None:
    first_path, next_path, static_path, out_dir = argv
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s, first = setup(first_path, next_path, static_path)
    sizes = {k: len(getattr(s, k)) for k in ("train", "valid", "test", "later")}
    columns = {b: int(s.v.mask(b).sum()) for b in BLOCKS}
    print(f"games {sizes}, columns {columns}")

    lam = tune(s)
    gains = variants(s, lam)
    t0 = time.time()
    x_all = design(first, s.v)
    coefs = bootstrap(first, x_all, penalties(s.v, lam))
    print(f"bootstrap: {time.time() - t0:.0f} s")
    low, high = np.quantile(coefs[1:], [0.025, 0.975], axis=0)
    clear = (low > 0) | (high < 0)
    point = coefs[0]
    report: dict[str, Any] = {
        "games": sizes,
        "columns": columns,
        "penalties": lam,
        "variants": gains,
        "clear": clear_counts(s.v, clear),
        "stability": stability(s, lam, point, clear),
        "side": float(point[0]),
        "skill": float(point[1]),
        "practice": float(point[2]),
        "practice_moves": movers(s, first, x_all, point, lam),
    }
    for key in ("clear", "stability", "practice_moves"):
        print(f"{key}: {json.dumps(report[key])}")
    print(f"side {point[0]:+.3f}, skill {point[1]:+.3f}, practice {point[2]:+.3f} (logit)")

    shares = Shares.of(first, s.v.magic)
    report["blind"] = {}
    for r, role in enumerate(ROLES):
        ranked = score(Draft(role=r), s.v, shares, coefs)
        report["blind"][role] = [row_of(x, s.names) for x in ranked]
        top = ", ".join(
            f"{s.names.get(x.champion)} {x.effect:+.1f} [{x.low:+.1f}, {x.high:+.1f}]"
            for x in ranked[:6]
        )
        print(f"blind {role}: {top}")
    report["demos"] = [demo(s, g * 997, shares, coefs) for g in range(3)]
    (out / "report.json").write_text(json.dumps(report, indent=1))
    np.save(out / "coefs.npy", coefs)


if __name__ == "__main__":
    main(sys.argv[1:])
