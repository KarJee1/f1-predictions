"""Feature engineering. Every form/history feature only looks at races *before* the row's race,
so the same code builds training rows and rows for an upcoming race without leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .circuits import traits
from .dataset import team_key

STAGES = ("pre", "practice", "quali")

BASE_FEATURES = [
    "career_starts",
    "driver_form_ewm",
    "driver_quali_ewm",
    "driver_last_finish",
    "driver_season_avg",
    "driver_dnf_rate",
    "driver_circuit_avg",
    "driver_circuit_starts",
    "teammate_delta_ewm",
    "driver_champ_rank",
    "driver_points_share",
    "driver_win_ewm",
    "driver_podium_ewm",
    "team_form_ewm",
    "team_quali_ewm",
    "team_dnf_rate",
    "team_points_share",
    "season_races_so_far",
    "overtaking",
    "street",
    "rain",
]
PRACTICE_FEATURES = BASE_FEATURES + ["fp_best_gap_pct", "fp_longrun_gap_pct", "fp_longrun_rank"]
QUALI_FEATURES = PRACTICE_FEATURES + ["grid", "quali_pos", "quali_gap_pct", "pitlane_start", "grid_penalty"]

FEATURES_BY_STAGE = {"pre": BASE_FEATURES, "practice": PRACTICE_FEATURES, "quali": QUALI_FEATURES}


def _shifted_ewm(s: pd.Series, span: int) -> pd.Series:
    return s.shift().ewm(span=span, ignore_na=True).mean()


def build_features(rows: pd.DataFrame) -> pd.DataFrame:
    """rows: history (+ optional upcoming race rows with no result yet). Returns rows plus feature columns."""
    df = rows.copy()
    df = df.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)
    df["race_idx"] = df.groupby(["season", "round"]).ngroup()
    df["team"] = df["constructor_id"].map(team_key)
    has_result = df["position"].notna()
    classified = df["classified"].astype("boolean").fillna(False).astype(bool)
    df["pos_c"] = df["position"].where(classified)
    df["dnf"] = np.where(has_result, (~classified).astype(float), np.nan)
    df["points_f"] = df["points"].fillna(0.0)

    # Driver form ------------------------------------------------------------------------
    g = df.groupby("driver_id", sort=False)
    df["career_starts"] = g.cumcount()
    df["driver_form_ewm"] = g["pos_c"].transform(lambda s: _shifted_ewm(s, 5))
    df["driver_quali_ewm"] = g["quali_pos"].transform(lambda s: _shifted_ewm(s, 5))
    df["driver_last_finish"] = g["position"].shift()
    df["driver_dnf_rate"] = g["dnf"].transform(lambda s: s.shift().rolling(10, min_periods=3).mean())
    df["driver_season_avg"] = df.groupby(["driver_id", "season"])["pos_c"].transform(
        lambda s: s.shift().expanding().mean()
    )
    gc = df.groupby(["driver_id", "circuit_id"], sort=False)
    df["driver_circuit_avg"] = gc["pos_c"].transform(lambda s: s.shift().expanding().mean())
    df["driver_circuit_starts"] = gc.cumcount()

    # Teammate comparison separates the driver from the car.
    team_sum = df.groupby(["race_idx", "team"])["pos_c"].transform("sum")
    team_cnt = df.groupby(["race_idx", "team"])["pos_c"].transform("count")
    mate = (team_sum - df["pos_c"]) / (team_cnt - 1)
    df["teammate_delta"] = (df["pos_c"] - mate).where(team_cnt > 1)
    df["teammate_delta_ewm"] = df.groupby("driver_id", sort=False)["teammate_delta"].transform(lambda s: _shifted_ewm(s, 8))

    season_pts = df.groupby(["driver_id", "season"])["points_f"].transform(lambda s: s.cumsum().shift(fill_value=0))
    df["driver_champ_rank"] = season_pts.groupby(df["race_idx"]).rank(ascending=False, method="min")
    leader_pts = season_pts.groupby(df["race_idx"]).transform("max")
    df["driver_points_share"] = (season_pts / leader_pts).where(leader_pts > 0)
    df["win"] = np.where(has_result, (df["position"] == 1).astype(float), np.nan)
    df["podium"] = np.where(has_result, (df["position"] <= 3).astype(float), np.nan)
    g = df.groupby("driver_id", sort=False)
    df["driver_win_ewm"] = g["win"].transform(lambda s: _shifted_ewm(s, 6))
    df["driver_podium_ewm"] = g["podium"].transform(lambda s: _shifted_ewm(s, 6))

    # Team form --------------------------------------------------------------------------
    team_race = (
        df.groupby(["race_idx", "season", "team"])
        .agg(t_pos=("pos_c", "mean"), t_quali=("quali_pos", "mean"), t_dnf=("dnf", "mean"), t_pts=("points_f", "sum"))
        .reset_index()
        .sort_values("race_idx")
    )
    tg = team_race.groupby("team", sort=False)
    team_race["team_form_ewm"] = tg["t_pos"].transform(lambda s: _shifted_ewm(s, 5))
    team_race["team_quali_ewm"] = tg["t_quali"].transform(lambda s: _shifted_ewm(s, 5))
    team_race["team_dnf_rate"] = tg["t_dnf"].transform(lambda s: s.shift().rolling(10, min_periods=3).mean())
    team_race["team_season_pts"] = team_race.groupby(["team", "season"])["t_pts"].transform(
        lambda s: s.cumsum().shift(fill_value=0)
    )
    leader = team_race.groupby("race_idx")["team_season_pts"].transform("max")
    team_race["team_points_share"] = (team_race["team_season_pts"] / leader).where(leader > 0)
    df = df.merge(
        team_race[["race_idx", "team", "team_form_ewm", "team_quali_ewm", "team_dnf_rate", "team_points_share"]],
        on=["race_idx", "team"],
        how="left",
    )

    # Race context -----------------------------------------------------------------------
    df["season_races_so_far"] = df["round"] - 1
    circuit = df["circuit_id"].map(traits)
    df["overtaking"] = circuit.map(lambda t: t["overtaking"])
    df["street"] = circuit.map(lambda t: t["street"])

    # Practice ---------------------------------------------------------------------------
    df["fp_longrun_rank"] = df.groupby("race_idx")["fp_longrun_gap_pct"].rank(method="min")

    # Qualifying -------------------------------------------------------------------------
    field_size = df.groupby("race_idx")["driver_id"].transform("count")
    df["pitlane_start"] = (df["grid"] == 0).astype(float).where(df["grid"].notna())
    df["grid"] = df["grid"].where(df["grid"] != 0, field_size)
    pole = df.groupby("race_idx")["quali_best"].transform("min")
    df["quali_gap_pct"] = (df["quali_best"] / pole - 1) * 100
    df["grid_penalty"] = df["grid"] - df["quali_pos"]

    # Ranking label: among classified finishers, winner gets the highest relevance.
    finish_rank = df[classified].groupby("race_idx")["position"].rank(method="first")
    n_classified = df[classified].groupby("race_idx")["position"].transform("count")
    df["label"] = np.nan
    df.loc[classified, "label"] = (n_classified - finish_rank).astype(float)

    return df.sort_values(["season", "round", "position"]).reset_index(drop=True)
