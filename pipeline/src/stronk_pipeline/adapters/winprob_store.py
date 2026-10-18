"""WinProbStore on one JSON file, whichever learner made the model.

{"kind": "logistic", "features": [...], "mean": [...], "scale": [...], "coef": [...]}
{"kind": "lightgbm", "features": [...], "booster": "<LightGBM text model>"}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import lightgbm as lgb
import numpy as np

from stronk_pipeline.adapters.lightgbm_winprob import MINUTE, LightGbmWinProb
from stronk_pipeline.domain.logistic import LogisticModel
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import LogisticWinProb
from stronk_pipeline.ports import StoreError, WinProbModel


class JsonWinProbStore:
    def save(self, model: WinProbModel, path: Path) -> Result[Path, StoreError]:
        features = list(model.feature_names)
        if isinstance(model, LogisticWinProb):
            record: dict[str, object] = {
                "kind": "logistic",
                "features": features,
                "mean": model.model.mean.tolist(),
                "scale": model.model.scale.tolist(),
                "coef": model.model.coef.tolist(),
            }
        elif isinstance(model, LightGbmWinProb):
            booster = model.booster.model_to_string()
            record = {"kind": "lightgbm", "features": features, "booster": booster}
        else:
            return Err(StoreError("invalid", f"cannot save a {type(model).__name__}"))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(path)

    def load(self, path: Path) -> Result[WinProbModel, StoreError]:
        if not path.is_file():
            return Err(StoreError("not_found", f"no win probability model at {path}"))
        try:
            raw: object = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            return Err(StoreError("invalid", f"{path} is not a model file: {e}"))
        record = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
        features = record.get("features")
        names = tuple(cast("list[object]", features)) if isinstance(features, list) else ()
        if not names or not all(isinstance(f, str) for f in names):
            return Err(StoreError("invalid", f"{path}: no feature list"))
        names = cast("tuple[str, ...]", names)
        try:
            match record.get("kind"):
                case "logistic":
                    return Ok(LogisticWinProb(names, _logistic(record, len(names))))
                case "lightgbm":
                    return Ok(LightGbmWinProb(_booster(record, names), names))
                case kind:
                    return Err(StoreError("invalid", f"{path}: unknown model kind {kind!r}"))
        except (KeyError, ValueError, TypeError, lgb.basic.LightGBMError) as e:
            return Err(StoreError("invalid", f"{path}: {e}"))


def _logistic(record: dict[str, object], width: int) -> LogisticModel:
    mean, scale, coef = (np.asarray(record[k], dtype=np.float64) for k in ("mean", "scale", "coef"))
    inputs = 2 * width + 1  # features, minute, features x minute
    if mean.shape != (inputs,) or scale.shape != (inputs,) or coef.shape != (inputs + 1,):
        raise ValueError(f"coefficients don't fit {width} features")
    if not (np.isfinite(mean).all() and np.isfinite(scale).all() and np.isfinite(coef).all()):
        raise ValueError("coefficients must be finite")
    return LogisticModel(mean, scale, coef)


def _booster(record: dict[str, object], names: tuple[str, ...]) -> lgb.Booster:
    text = record.get("booster")
    if not isinstance(text, str):
        raise TypeError("booster must be a string")
    booster = lgb.Booster(model_str=text)
    if tuple(booster.feature_name()) != (*names, MINUTE):
        raise ValueError("booster features don't match the feature list")
    return booster
