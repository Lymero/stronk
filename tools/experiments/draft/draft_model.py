"""A draft model: how much each pick moves a team's chance of winning, from a partial draft.

One row per game, the blue team's win as the outcome, and a ridge-penalised logistic model of

    logit P(blue wins) = side + skill and practice differences
                       + Σ blue (champion, role) - Σ red (champion, role)        main
                       + Σ roles lane[role](blue champion vs red champion)        lane
                       + duo(blue bottom, blue support) - duo(red …)             duo
                       + cross(blue bottom vs red support) - cross(red … blue)    cross
                       + damage mix(blue's magic-damage count) - (red's)          comp

Each block has its own penalty (a Gaussian prior's width), chosen on validation games, so a
matchup seen 40 times stays near 0 and a champion seen 5,000 times keeps its estimate. Skill and
practice (draft_games.py) take out who plays a champion: main effects are for a player of
average skill on their first game of the champion in the crawl, whatever champion it is.

`score` turns a partial draft into each available champion's effect for the role asked: the
picks known count in full; a slot not picked yet counts as the role's average pick, its
interactions averaged over what is picked there; an enemy pick of unknown role counts in each
role by how often that champion plays it, given the other enemy picks. The effect is against
the average pick of the role among champions still available, in wins per 100 games.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy import optimize, sparse

ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
BOTTOM, UTILITY = 3, 4
BLOCKS = ("cov", "comp", "main", "lane", "duo", "cross")
COMP_LEVELS = (0, 1, 3, 4)
"""Magic-damage champions on a team, against 2 (the reference); 4 stands for 4 or 5."""
MIN_GAMES = 30
"""A champion in a role, or a pair, needs this many games for a column of its own."""

type Floats = NDArray[np.float64]
type Ints = NDArray[np.int64]


@dataclass(frozen=True)
class Games:
    """One row per game; seats are [team (0 blue, 1 red), role]."""

    match_id: NDArray[np.str_]
    champion: Ints  # (n, 2, 5)
    skill: Floats  # (n, 2, 5)
    practice: Floats  # (n, 2, 5)
    blue_win: Floats  # (n,)

    def __len__(self) -> int:
        return len(self.blue_win)

    def take(self, rows: Ints | NDArray[np.bool_]) -> Games:
        return Games(
            self.match_id[rows],
            self.champion[rows],
            self.skill[rows],
            self.practice[rows],
            self.blue_win[rows],
        )


def games_of(frame: pl.DataFrame) -> Games:
    """From draft_games.py's table: games with one player per team and role only."""
    seats = (
        frame.with_columns(
            pl.col("position").replace_strict({r: i for i, r in enumerate(ROLES)}).alias("role"),
            (pl.col("team") == 200).cast(pl.Int64).alias("side"),
        )
        .filter(pl.len().over("match_id", "side", "role") == 1)
        .filter(pl.len().over("match_id") == 10)
        .sort("match_id", "side", "role")
    )
    n = seats.height // 10
    shape = (n, 2, 5)
    win = seats["win"].to_numpy().reshape(n, 10)
    return Games(
        seats["match_id"].to_numpy().reshape(n, 10)[:, 0],
        seats["champion"].to_numpy().reshape(shape).astype(np.int64),
        seats["skill"].to_numpy().reshape(shape),
        seats["practice"].to_numpy().reshape(shape),
        win[:, 0].astype(np.float64),
    )


@dataclass
class Vocab:
    """Which column each champion-role, pair and covariate has."""

    magic: frozenset[int]
    main: dict[tuple[int, int], int] = field(default_factory=dict[tuple[int, int], int])
    lane: dict[tuple[int, int, int], int] = field(default_factory=dict[tuple[int, int, int], int])
    duo: dict[tuple[int, int], int] = field(default_factory=dict[tuple[int, int], int])
    cross: dict[tuple[int, int], int] = field(default_factory=dict[tuple[int, int], int])
    block: list[str] = field(default_factory=list[str])

    @property
    def width(self) -> int:
        return len(self.block)

    def mask(self, *blocks: str) -> NDArray[np.bool_]:
        return np.isin(np.array(self.block), blocks)


def vocab_of(games: Games, magic: Iterable[int], min_games: int = MIN_GAMES) -> Vocab:
    v = Vocab(frozenset(magic))
    v.block = ["cov"] * 3 + ["comp"] * len(COMP_LEVELS)
    main: Counter[tuple[int, int]] = Counter()
    lane: Counter[tuple[int, int, int]] = Counter()
    duo: Counter[tuple[int, int]] = Counter()
    cross: Counter[tuple[int, int]] = Counter()
    c = games.champion.tolist()
    for seats in c:
        for r in range(5):
            a, b = seats[0][r], seats[1][r]
            main[(r, a)] += 1
            main[(r, b)] += 1
            if a != b:  # a mirror matchup cancels out
                lane[(r, min(a, b), max(a, b))] += 1
        for t in (0, 1):
            duo[(seats[t][BOTTOM], seats[t][UTILITY])] += 1
            cross[(seats[t][BOTTOM], seats[1 - t][UTILITY])] += 1

    def add[K](table: dict[K, int], counts: Counter[K], kind: str) -> None:
        for key, n in sorted(counts.items()):
            if n >= min_games:
                table[key] = len(v.block)
                v.block.append(kind)

    add(v.main, main, "main")
    add(v.lane, lane, "lane")
    add(v.duo, duo, "duo")
    add(v.cross, cross, "cross")
    return v


def design(games: Games, v: Vocab) -> sparse.csr_matrix:
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []

    def put(row: int, col: int | None, val: float) -> None:
        if col is not None:
            rows.append(row)
            cols.append(col)
            vals.append(val)

    c = games.champion
    skill = games.skill[:, 0].sum(1) - games.skill[:, 1].sum(1)
    practice = games.practice[:, 0].sum(1) - games.practice[:, 1].sum(1)
    for row in range(len(games)):
        put(row, 0, 1.0)
        put(row, 1, skill[row])
        put(row, 2, practice[row])
        for t, sign in ((0, 1.0), (1, -1.0)):
            level = min(4, sum(int(x) in v.magic for x in c[row, t]))
            if level != 2:
                put(row, 3 + COMP_LEVELS.index(level), sign)
            for r in range(5):
                put(row, v.main.get((r, c[row, t, r])), sign)
            put(row, v.duo.get((c[row, t, BOTTOM], c[row, t, UTILITY])), sign)
            put(row, v.cross.get((c[row, t, BOTTOM], c[row, 1 - t, UTILITY])), sign)
        for r in range(5):
            a, b = c[row, 0, r], c[row, 1, r]
            if a != b:
                put(row, v.lane.get((r, min(a, b), max(a, b))), 1.0 if a < b else -1.0)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(len(games), v.width))


def fit(
    x: sparse.csr_matrix,
    y: Floats,
    penalty: Floats,
    start: Floats | None = None,
    weights: Floats | None = None,
) -> Floats:
    """Coefficients minimising the weighted log loss plus Σ penalty·w²/2."""
    w = np.ones(len(y)) if weights is None else weights
    xt = x.T.tocsr()

    def objective(coef: Floats) -> tuple[float, Floats]:
        eta = x @ coef
        loss = float(w @ (np.logaddexp(0.0, eta) - y * eta)) + 0.5 * float(penalty @ coef**2)
        grad = xt @ (w * (expit(eta) - y)) + penalty * coef
        return loss, grad

    begin = np.zeros(x.shape[1]) if start is None else start
    result = optimize.minimize(
        objective, begin, jac=True, method="L-BFGS-B", options={"maxiter": 5000, "gtol": 1e-7}
    )
    return result.x


def expit(eta: Floats) -> Floats:
    return 1.0 / (1.0 + np.exp(-np.clip(eta, -35.0, 35.0)))


def log_loss(y: Floats, p: Floats) -> Floats:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def penalties(v: Vocab, lam: Mapping[str, float]) -> Floats:
    out = np.array([lam.get(b, 0.0) for b in v.block])
    out[:3] = 1e-4  # side, skill and practice: free
    return out


@dataclass(frozen=True)
class Shares:
    """How often each champion is picked in each role, and plays each role."""

    pick: list[dict[int, float]]
    """Per role, champion to share of that role's picks."""
    role: dict[int, Floats]
    """Per champion, share of their games in each role."""
    magic_rate: Floats
    """Per role, share of picks dealing mostly magic damage."""

    @staticmethod
    def of(games: Games, magic: frozenset[int]) -> Shares:
        counts: list[Counter[int]] = [
            Counter(games.champion[:, :, r].ravel().tolist()) for r in range(5)
        ]
        pick = [{c: k / cs.total() for c, k in cs.items()} for cs in counts]
        champions = {c for cs in counts for c in cs}
        role: dict[int, Floats] = {}
        for c in champions:
            n = np.array([counts[r][c] for r in range(5)], dtype=np.float64)
            role[c] = n / n.sum()
        magic_rate = np.array([sum(s for c, s in p.items() if c in magic) for p in pick])
        return Shares(pick, role, magic_rate)


@dataclass(frozen=True)
class Draft:
    """What is known in champion select: allies by role, enemies with or without a role."""

    role: int
    allies: Mapping[int, int] = field(default_factory=dict[int, int])
    enemies: Sequence[int] = ()
    enemy_roles: Mapping[int, int] = field(default_factory=dict[int, int])
    """Enemies whose role is known, role to champion; the rest are in `enemies`."""
    banned: frozenset[int] = frozenset()

    def taken(self) -> set[int]:
        return {*self.allies.values(), *self.enemies, *self.enemy_roles.values(), *self.banned}


def enemy_positions(draft: Draft, shares: Shares) -> Floats:
    """P(enemy pick i plays role r), for `draft.enemies`, given the roles still open."""
    open_roles = [r for r in range(5) if r not in draft.enemy_roles]
    k = len(draft.enemies)
    out = np.zeros((k, 5))
    if k == 0:
        return out
    total = 0.0
    for roles in itertools.permutations(open_roles, k):
        weight = 1.0
        for i, r in enumerate(roles):
            weight *= shares.role.get(draft.enemies[i], np.full(5, 0.2))[r] + 1e-6
        total += weight
        for i, r in enumerate(roles):
            out[i, r] += weight
    return out / total if total > 0 else out


@dataclass(frozen=True)
class Scored:
    champion: int
    effect: float
    """Wins per 100 games against the average available pick of the role."""
    low: float
    high: float
    share: float
    """Share of the role's picks."""


def score(
    draft: Draft,
    v: Vocab,
    shares: Shares,
    coefs: Floats,
    *,
    min_share: float = 0.002,
) -> list[Scored]:
    """Every available champion for `draft.role` picked by at least `min_share` of the role,
    best first. `coefs` holds one fit per row (the first the point estimate, the rest bootstrap
    fits): intervals are their 2.5% and 97.5% quantiles."""
    coefs = np.atleast_2d(coefs)
    r = draft.role
    taken = draft.taken()
    candidates = [c for c, s in shares.pick[r].items() if s >= min_share and c not in taken]
    weights = np.array([shares.pick[r][c] for c in candidates])
    weights = weights / weights.sum()
    scorer = _Scorer(draft, v, shares, coefs)
    eta = np.array([scorer.own(c) for c in candidates])  # (candidates, fits)
    known = scorer.known()
    effect = 100 * (expit(known + eta - weights @ eta) - expit(known))
    bootstrapped = coefs.shape[0] > 2
    return sorted(
        (
            Scored(
                c,
                float(effect[i, 0]),
                float(np.quantile(effect[i, 1:], 0.025)) if bootstrapped else np.nan,
                float(np.quantile(effect[i, 1:], 0.975)) if bootstrapped else np.nan,
                shares.pick[r][c],
            )
            for i, c in enumerate(candidates)
        ),
        key=lambda s: -s.effect,
    )


@dataclass(frozen=True)
class _Scorer:
    draft: Draft
    v: Vocab
    shares: Shares
    coefs: Floats

    def zero(self) -> Floats:
        return np.zeros(self.coefs.shape[0])

    def at(self, col: int | None) -> Floats:
        return self.zero() if col is None else self.coefs[:, col]

    def own(self, c: int) -> Floats:
        """The candidate's own terms, for each fit: everything that changes with it."""
        r = self.draft.role
        taken = self.draft.taken() | {c}
        out = self.at(self.v.main.get((r, c))) + self.lane(c, taken) + self.comp(c)
        if r in {BOTTOM, UTILITY}:
            out += self.duo(c, taken) + self.cross(c, taken)
        return out

    def known(self) -> Floats:
        """Where the effect is measured from: the ally main effects known, minus the enemy ones
        known by role (enough to place p0 near 0.5)."""
        out = self.zero()
        for r, a in self.draft.allies.items():
            out += self.at(self.v.main.get((r, a)))
        for r, e in self.draft.enemy_roles.items():
            out -= self.at(self.v.main.get((r, e)))
        return out

    def against(self, role: int, value: Callable[[int], Floats], taken: set[int]) -> Floats:
        """`value(d)` for the enemy `d` in `role`: known, likely by how each enemy pick plays
        it, or not picked yet and averaged over the role's available picks."""
        if role in self.draft.enemy_roles:
            return value(self.draft.enemy_roles[role])
        likely = enemy_positions(self.draft, self.shares)
        out = self.zero()
        for i, d in enumerate(self.draft.enemies):
            out += likely[i, role] * value(d)
        unknown = 1.0 - likely[:, role].sum()
        if unknown > 0:
            out += unknown * self.average(role, value, taken)
        return out

    def average(self, role: int, value: Callable[[int], Floats], taken: set[int]) -> Floats:
        picks = {d: s for d, s in self.shares.pick[role].items() if d not in taken}
        total = sum(picks.values())
        out = self.zero()
        for d, s in picks.items():
            out += s / total * value(d)
        return out

    def lane(self, c: int, taken: set[int]) -> Floats:
        r = self.draft.role

        def versus(d: int) -> Floats:
            if c == d:
                return self.zero()
            sign = 1.0 if c < d else -1.0
            return sign * self.at(self.v.lane.get((r, min(c, d), max(c, d))))

        return self.against(r, versus, taken)

    def duo(self, c: int, taken: set[int]) -> Floats:
        bottom = self.draft.role == BOTTOM
        mate = UTILITY if bottom else BOTTOM

        def with_(other: int) -> Floats:
            return self.at(self.v.duo.get((c, other) if bottom else (other, c)))

        if mate in self.draft.allies:
            return with_(self.draft.allies[mate])
        return self.average(mate, with_, taken)

    def cross(self, c: int, taken: set[int]) -> Floats:
        """Bottom against the enemy support, or support against the enemy bottom."""
        bottom = self.draft.role == BOTTOM
        mate = UTILITY if bottom else BOTTOM

        def versus(d: int) -> Floats:
            if bottom:
                return self.at(self.v.cross.get((c, d)))
            return -self.at(self.v.cross.get((d, c)))

        return self.against(mate, versus, taken)

    def comp(self, c: int) -> Floats:
        """The damage mix term of the candidate's team, expected over the roles still open."""
        magic = self.v.magic
        known = sum(int(a in magic) for a in self.draft.allies.values()) + int(c in magic)
        dist = np.zeros(6)
        dist[known] = 1.0
        for r in range(5):  # Poisson-binomial over the open roles
            if r == self.draft.role or r in self.draft.allies:
                continue
            q = self.shares.magic_rate[r]
            dist = np.concatenate([dist[:1] * (1 - q), dist[1:] * (1 - q) + dist[:-1] * q])
        out = self.zero()
        for count, p in enumerate(dist):
            level = min(4, count)
            if level != 2 and p > 0:
                out += p * self.coefs[:, 3 + COMP_LEVELS.index(level)]
        return out
