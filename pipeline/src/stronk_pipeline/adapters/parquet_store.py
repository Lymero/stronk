"""DecisionStore and FrameStore on Parquet files. Decision tables are validated when read."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from stronk_pipeline.domain.decisions import DecisionTable, InvalidDecisionsError
from stronk_pipeline.domain.frames import FrameTable, InvalidFramesError
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import StoreError

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
    def read_decisions(self, path: Path) -> Result[DecisionTable, StoreError]:
        if not path.is_file():
            return Err(StoreError("not_found", f"no decision table at {path}"))
        try:
            frame = pl.read_parquet(path)
        except (pl.exceptions.PolarsError, OSError) as e:
            return Err(StoreError("invalid", f"{path} is not a readable Parquet file: {e}"))
        missing = [c for c in COLUMNS if c not in frame.columns]
        if missing:
            return Err(StoreError("invalid", f"{path} lacks columns: {', '.join(missing)}"))
        features = sorted(c for c in frame.columns if c.startswith(FEATURE_PREFIX))
        try:
            frame = frame.select(
                *(pl.col(c).cast(t, strict=True) for c, t in COLUMNS.items()),
                *(pl.col(c).cast(pl.Float64, strict=True) for c in features),
            )
            if frame.null_count().sum_horizontal().item() > 0:
                return Err(StoreError("invalid", f"{path} contains nulls"))
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
                features=frame.select(features)
                .to_numpy()
                .astype(np.float64)
                .reshape(len(frame), len(features)),
                feature_names=tuple(f.removeprefix(FEATURE_PREFIX) for f in features),
            )
        except (pl.exceptions.PolarsError, InvalidDecisionsError) as e:
            return Err(StoreError("invalid", f"{path}: {e}"))
        return Ok(table)

    def write_decisions(self, table: DecisionTable, path: Path) -> Result[Path, StoreError]:
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
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pl.DataFrame(columns).write_parquet(path)
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(path)


FRAME_COLUMNS: dict[str, pl.DataType] = {
    "match_id": pl.String(),
    "team": pl.Int64(),
    "minute": pl.Float64(),
    "outcome": pl.Int64(),
}


class ParquetFrameStore:
    def read_frames(self, path: Path) -> Result[FrameTable, StoreError]:
        if not path.is_file():
            return Err(StoreError("not_found", f"no frame table at {path}"))
        try:
            frame = pl.read_parquet(path)
        except (pl.exceptions.PolarsError, OSError) as e:
            return Err(StoreError("invalid", f"{path} is not a readable Parquet file: {e}"))
        missing = [c for c in FRAME_COLUMNS if c not in frame.columns]
        if missing:
            return Err(StoreError("invalid", f"{path} lacks columns: {', '.join(missing)}"))
        features = sorted(c for c in frame.columns if c.startswith(FEATURE_PREFIX))
        try:
            frame = frame.select(
                *(pl.col(c).cast(t, strict=True) for c, t in FRAME_COLUMNS.items()),
                *(pl.col(c).cast(pl.Float64, strict=True) for c in features),
            )
            if frame.null_count().sum_horizontal().item() > 0:
                return Err(StoreError("invalid", f"{path} contains nulls"))
            table = FrameTable(
                match_id=frame["match_id"].to_numpy().astype(str),
                team=frame["team"].to_numpy(),
                minute=frame["minute"].to_numpy(),
                outcome=frame["outcome"].to_numpy(),
                features=frame.select(features)
                .to_numpy()
                .astype(np.float64)
                .reshape(len(frame), len(features)),
                feature_names=tuple(f.removeprefix(FEATURE_PREFIX) for f in features),
            )
        except (pl.exceptions.PolarsError, InvalidFramesError) as e:
            return Err(StoreError("invalid", f"{path}: {e}"))
        return Ok(table)

    def write_frames(self, table: FrameTable, path: Path) -> Result[Path, StoreError]:
        columns: dict[str, object] = {
            "match_id": table.match_id,
            "team": table.team,
            "minute": table.minute,
            "outcome": table.outcome,
        }
        for i, name in enumerate(table.feature_names):
            columns[FEATURE_PREFIX + name] = table.features[:, i]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pl.DataFrame(columns).write_parquet(path)
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(path)
