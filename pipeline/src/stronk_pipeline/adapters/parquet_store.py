"""DecisionStore and FrameStore on Parquet. Decision tables are validated when read.

A table is one file, or a directory of parts written a chunk of games at a time (ADR-080);
Polars reads both the same way. Decisions read a few picks at a time, so a table larger than
memory is never held whole.
"""

from __future__ import annotations

import functools
import shutil
from collections.abc import Callable, Collection
from pathlib import Path

import numpy as np
import polars as pl

from stronk_pipeline.domain.decisions import DecisionTable, InvalidDecisionsError
from stronk_pipeline.domain.frames import FrameTable, InvalidFramesError
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import Pick, StoreError

FEATURE_PREFIX = "f_"
COLUMNS: dict[str, pl.DataType] = {
    "match_id": pl.String(),
    "participant": pl.Int64(),
    "champion": pl.String(),
    "champion_class": pl.String(),
    "role": pl.String(),
    "slot": pl.Int64(),
    "minute": pl.Float64(),
    "option": pl.String(),
    "outcome": pl.Int64(),
}


class ParquetDecisionStore:
    def read_decisions(
        self, path: Path, picks: Collection[tuple[str, str]] | None = None
    ) -> Result[DecisionTable, StoreError]:
        match _scan(path, "decision table", COLUMNS):
            case Err() as e:
                return e
            case Ok(value=(lazy, features)):
                pass
        if picks is not None:
            wanted = [f"{champion}/{role}" for champion, role in picks]
            lazy = lazy.filter(pl.concat_str("champion", "role", separator="/").is_in(wanted))
        try:
            frame = _validated(lazy, path, COLUMNS, features)
            table = DecisionTable.create(
                match_id=frame["match_id"].to_numpy().astype(str),
                participant=frame["participant"].to_numpy(),
                champion=frame["champion"].to_numpy().astype(str),
                champion_class=frame["champion_class"].to_numpy().astype(str),
                role=frame["role"].to_numpy().astype(str),
                slot=frame["slot"].to_numpy(),
                minute=frame["minute"].to_numpy(),
                option=frame["option"].to_numpy().astype(str),
                outcome=frame["outcome"].to_numpy(),
                features=_matrix(frame, features),
                feature_names=tuple(f.removeprefix(FEATURE_PREFIX) for f in features),
            )
        except _InvalidTableError as e:
            return Err(StoreError("invalid", str(e)))
        except (pl.exceptions.PolarsError, InvalidDecisionsError) as e:
            return Err(StoreError("invalid", f"{path}: {e}"))
        return Ok(table)

    def picks(self, path: Path) -> Result[list[Pick], StoreError]:
        match _scan(path, "decision table", COLUMNS):
            case Err() as e:
                return e
            case Ok(value=(lazy, _)):
                pass
        keys = ("champion", "champion_class", "role")
        try:
            counts = lazy.group_by(keys).len().sort(["champion", "role"]).collect()
        except pl.exceptions.PolarsError as e:
            return Err(StoreError("invalid", f"{path}: {e}"))
        return Ok([Pick(str(c), str(k), str(r), int(n)) for c, k, r, n in counts.iter_rows()])

    def write_decisions(
        self, table: DecisionTable, path: Path, part: int | None = None
    ) -> Result[Path, StoreError]:
        columns: dict[str, object] = {
            "match_id": table.match_id,
            "participant": table.participant,
            "champion": table.champion,
            "champion_class": table.champion_class,
            "role": table.role,
            "slot": table.slot,
            "minute": table.minute,
            "option": table.option,
            "outcome": table.outcome,
        }
        for i, name in enumerate(table.feature_names):
            columns[FEATURE_PREFIX + name] = table.features[:, i]
        return _write(pl.DataFrame(columns), path, part)


FRAME_COLUMNS: dict[str, pl.DataType] = {
    "match_id": pl.String(),
    "team": pl.Int64(),
    "minute": pl.Float64(),
    "outcome": pl.Int64(),
}


class ParquetFrameStore:
    def read_frames(self, path: Path) -> Result[FrameTable, StoreError]:
        match _scan(path, "frame table", FRAME_COLUMNS):
            case Err() as e:
                return e
            case Ok(value=(lazy, features)):
                pass
        try:
            frame = _validated(lazy, path, FRAME_COLUMNS, features)
            table = FrameTable(
                match_id=frame["match_id"].to_numpy().astype(str),
                team=frame["team"].to_numpy(),
                minute=frame["minute"].to_numpy(),
                outcome=frame["outcome"].to_numpy(),
                features=_matrix(frame, features),
                feature_names=tuple(f.removeprefix(FEATURE_PREFIX) for f in features),
            )
        except _InvalidTableError as e:
            return Err(StoreError("invalid", str(e)))
        except (pl.exceptions.PolarsError, InvalidFramesError) as e:
            return Err(StoreError("invalid", f"{path}: {e}"))
        return Ok(table)

    def frame_chunks(
        self, path: Path
    ) -> Result[list[Callable[[], Result[FrameTable, StoreError]]], StoreError]:
        if not path.exists():
            return Err(StoreError("not_found", f"no frame table at {path}"))
        parts = sorted(path.glob("*.parquet")) if path.is_dir() else [path]
        if not parts:
            return Err(StoreError("invalid", f"{path} holds no Parquet parts"))
        return Ok([functools.partial(self.read_frames, part) for part in parts])

    def write_frames(
        self, table: FrameTable, path: Path, part: int | None = None
    ) -> Result[Path, StoreError]:
        columns: dict[str, object] = {
            "match_id": table.match_id,
            "team": table.team,
            "minute": table.minute,
            "outcome": table.outcome,
        }
        for i, name in enumerate(table.feature_names):
            columns[FEATURE_PREFIX + name] = table.features[:, i]
        return _write(pl.DataFrame(columns), path, part)


class _InvalidTableError(Exception):
    """A table that reads but breaks the format: a message for `StoreError`."""


def _scan(
    path: Path, what: str, columns: dict[str, pl.DataType]
) -> Result[tuple[pl.LazyFrame, list[str]], StoreError]:
    """The table at `path`, not read yet, and its feature columns, sorted."""
    if not path.exists():
        return Err(StoreError("not_found", f"no {what} at {path}"))
    try:
        lazy = pl.scan_parquet(path)
        names = lazy.collect_schema().names()
    except (pl.exceptions.PolarsError, OSError) as e:
        return Err(StoreError("invalid", f"{path} is not a readable Parquet file: {e}"))
    missing = [c for c in columns if c not in names]
    if missing:
        return Err(StoreError("invalid", f"{path} lacks columns: {', '.join(missing)}"))
    return Ok((lazy, sorted(c for c in names if c.startswith(FEATURE_PREFIX))))


def _validated(
    lazy: pl.LazyFrame, path: Path, columns: dict[str, pl.DataType], features: list[str]
) -> pl.DataFrame:
    frame = lazy.select(
        *(pl.col(c).cast(t, strict=True) for c, t in columns.items()),
        *(pl.col(c).cast(pl.Float64, strict=True) for c in features),
    ).collect()
    if frame.null_count().sum_horizontal().item() > 0:
        raise _InvalidTableError(f"{path} contains nulls")
    return frame


def _matrix(
    frame: pl.DataFrame, features: list[str]
) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
    return frame.select(features).to_numpy().astype(np.float64).reshape(len(frame), len(features))


def _write(frame: pl.DataFrame, path: Path, part: int | None) -> Result[Path, StoreError]:
    """The table as one file at `path`, or as part `part` in the directory `path`; part 0 and a
    whole table first remove what `path` held."""
    try:
        if part is None or part == 0:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        if part is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.write_parquet(path)
            return Ok(path)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"part-{part:05d}.parquet"
        frame.write_parquet(target)
    except OSError as e:
        return Err(StoreError("invalid", f"cannot write {path}: {e}"))
    return Ok(path)
