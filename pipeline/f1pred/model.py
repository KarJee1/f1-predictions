"""Learning-to-rank race models (one per prediction stage), their temperature, and persistence."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import settings
from .features import FEATURES_BY_STAGE
from .simulate import fit_beta
from .storage import Store

KINDS = ("xgboost", "lightgbm")


def season_weights(seasons: pd.Series, latest: int) -> np.ndarray:
    """Recent seasons count more; seasons before the latest regulation reset count much less."""
    w = 0.75 ** (latest - seasons.to_numpy())
    resets = [r for r in settings.regulation_resets if r <= latest]
    if resets:
        w = np.where(seasons.to_numpy() < max(resets), w * 0.5, w)
    return w


def _training_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df[df["label"].notna()].sort_values(["race_idx", "label"], ascending=[True, False])
    return rows.reset_index(drop=True)


def _fit_estimator(kind: str, rows: pd.DataFrame, features: list[str]):
    X, y, qid = rows[features], rows["label"].astype(int), rows["race_idx"].to_numpy()
    latest = int(rows["season"].max())
    if kind == "xgboost":
        from xgboost import XGBRanker

        est = XGBRanker(
            objective="rank:pairwise",
            n_estimators=300,
            learning_rate=0.02,
            max_depth=3,
            min_child_weight=10,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method="hist",
            random_state=7,
        )
        group_seasons = rows.groupby("race_idx", sort=False)["season"].first()
        est.fit(X, y, qid=qid, sample_weight=season_weights(group_seasons, latest))
        return est
    if kind == "lightgbm":
        from lightgbm import LGBMRanker

        est = LGBMRanker(
            objective="lambdarank",
            n_estimators=300,
            learning_rate=0.02,
            num_leaves=7,
            min_child_samples=40,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            label_gain=list(range(64)),
            lambdarank_truncation_level=30,
            random_state=7,
            verbose=-1,
        )
        group_sizes = rows.groupby("race_idx", sort=False).size().to_numpy()
        est.fit(X, y, group=group_sizes, sample_weight=season_weights(rows["season"], latest))
        return est
    raise ValueError(kind)


@dataclass
class StageModel:
    stage: str
    kind: str
    features: list[str]
    beta: float = 1.0
    estimator: object = None
    metrics: dict = field(default_factory=dict)

    def scores(self, X: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.estimator.predict(X[self.features]), dtype=float)

    def contributions(self, X: pd.DataFrame) -> np.ndarray:
        """Per-feature contribution to each driver's score (SHAP values), without the bias column."""
        if self.kind == "xgboost":
            from xgboost import DMatrix

            contrib = self.estimator.get_booster().predict(DMatrix(X[self.features]), pred_contribs=True)
        else:
            contrib = self.estimator.predict(X[self.features], pred_contrib=True)
        return np.asarray(contrib)[:, :-1]


def finish_orders(rows: pd.DataFrame, scores: np.ndarray) -> list[np.ndarray]:
    """For each race, the scores of classified finishers listed in finishing order."""
    tmp = rows.assign(_s=scores)
    tmp = tmp[tmp["label"].notna()].sort_values(["race_idx", "label"], ascending=[True, False])
    return [g["_s"].to_numpy() for _, g in tmp.groupby("race_idx", sort=False)]


def train_stage(df: pd.DataFrame, stage: str, kind: str, max_season: int, holdout_races: int = 20) -> StageModel:
    """Fit on seasons <= max_season, then fit the score temperature on the most recent races.
    (Backtests showed fitting it on the final model beats a separate out-of-sample model, which
    misses the most recent, most relevant races.)"""
    features = FEATURES_BY_STAGE[stage]
    rows = _training_rows(df[df["season"] <= max_season])
    fitted = StageModel(stage, kind, features, estimator=_fit_estimator(kind, rows, features))
    recent = rows[rows["race_idx"].isin(np.sort(rows["race_idx"].unique())[-holdout_races:])]
    fitted.beta = fit_beta(finish_orders(recent, fitted.scores(recent)))
    return fitted


# -- persistence ---------------------------------------------------------------------------------


def save(model: StageModel, store: Store, prefix: str = "models") -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.ubj"
        if model.kind == "xgboost":
            model.estimator.save_model(str(path))
        else:
            model.estimator.booster_.save_model(str(path))
        store.write_bytes(f"{prefix}/{model.stage}.model", path.read_bytes())
    meta = {"stage": model.stage, "kind": model.kind, "features": model.features, "beta": model.beta, "metrics": model.metrics}
    store.write_json(f"{prefix}/{model.stage}.json", meta)


class _LgbWrapper:
    def __init__(self, booster):
        self.booster = booster

    def predict(self, X, pred_contrib: bool = False):
        return self.booster.predict(X, pred_contrib=pred_contrib)


def load(stage: str, store: Store, prefix: str = "models") -> StageModel | None:
    meta = store.read_json(f"{prefix}/{stage}.json")
    blob = store.read_bytes(f"{prefix}/{stage}.model")
    if meta is None or blob is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.ubj"
        path.write_bytes(blob)
        if meta["kind"] == "xgboost":
            from xgboost import XGBRanker

            est = XGBRanker()
            est.load_model(str(path))
        else:
            import lightgbm

            est = _LgbWrapper(lightgbm.Booster(model_file=str(path)))
    return StageModel(meta["stage"], meta["kind"], meta["features"], meta["beta"], est, meta.get("metrics", {}))


def model_info(store: Store) -> dict:
    return {s: store.read_json(f"models/{s}.json") for s in FEATURES_BY_STAGE}

