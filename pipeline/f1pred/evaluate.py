"""Backtesting: train on earlier seasons, predict every race of a later season, and score it.
Used to choose between model types and to report honest accuracy numbers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .model import KINDS, train_stage
from .simulate import dnf_probability, simulate


def score_race(pred_order: list[str], win_prob: dict[str, float] | None, actual: pd.DataFrame) -> dict:
    """pred_order: driver ids, predicted first to last. actual: rows with driver_id, position, classified."""
    actual = actual.sort_values("position")
    winner = actual.iloc[0]["driver_id"]
    podium = set(actual.head(3)["driver_id"])
    pos = dict(zip(actual["driver_id"], actual["position"]))
    common = [d for d in pred_order if d in pos]
    rho = spearmanr(range(len(common)), [pos[d] for d in common]).statistic if len(common) > 2 else np.nan
    out = {
        "winner_correct": bool(pred_order[0] == winner),
        "podium_hits": len(podium & set(pred_order[:3])),
        "spearman": float(rho),
        "mean_abs_position_error": float(np.mean([abs(i + 1 - pos[d]) for i, d in enumerate(common)])),
    }
    if win_prob is not None:
        out["winner_log_loss"] = float(-np.log(max(win_prob.get(winner, 0.0), 1e-4)))
    return out


def predict_race(model, race: pd.DataFrame, n_sims: int = 5000) -> pd.DataFrame:
    scores = model.scores(race)
    p_dnf = dnf_probability(race["team_dnf_rate"].to_numpy(float), race["driver_dnf_rate"].to_numpy(float))
    sim = simulate(scores, model.beta, p_dnf, n=n_sims)
    out = race[["driver_id"]].copy()
    out["win"], out["podium"], out["expected_position"] = sim["win"], sim["podium"], sim["expected_position"]
    return out.sort_values(["win", "podium", "expected_position"], ascending=[False, False, True])


def _baseline_order(race: pd.DataFrame, stage: str) -> list[str]:
    if stage == "quali":
        key = race["grid"].fillna(99)
    else:
        key = race["driver_champ_rank"].fillna(99)
    return race.assign(_k=key).sort_values("_k")["driver_id"].tolist()


def backtest(df: pd.DataFrame, test_seasons: list[int], stages=("pre", "practice", "quali"), kinds=KINDS) -> pd.DataFrame:
    """One row per (season, round, stage, model) with the race's scores."""
    records = []
    for season in test_seasons:
        test = df[(df["season"] == season) & df["position"].notna()]
        for stage in stages:
            models = {kind: train_stage(df, stage, kind, season - 1) for kind in kinds}
            for rnd, race in test.groupby("round"):
                base = score_race(_baseline_order(race, stage), None, race)
                records.append({"season": season, "round": rnd, "stage": stage, "model": "baseline", **base})
                for kind, model in models.items():
                    pred = predict_race(model, race)
                    win = dict(zip(pred["driver_id"], pred["win"]))
                    records.append(
                        {"season": season, "round": rnd, "stage": stage, "model": kind, **score_race(pred["driver_id"].tolist(), win, race)}
                    )
    return pd.DataFrame(records)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    return (
        results.groupby(["stage", "model"])
        .agg(
            races=("round", "count"),
            winner_correct=("winner_correct", "mean"),
            podium_hits=("podium_hits", "mean"),
            spearman=("spearman", "mean"),
            position_error=("mean_abs_position_error", "mean"),
            winner_log_loss=("winner_log_loss", "mean"),
        )
        .round(3)
    )
