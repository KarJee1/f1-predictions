"""Code-path tests on synthetic seasons (fake drivers with a hidden skill level). These check the
plumbing and that the model can recover an obvious signal; real accuracy comes from `f1pred backtest`."""

import numpy as np
import pandas as pd
import pytest

from f1pred import model as models
from f1pred.evaluate import backtest, summarize
from f1pred.explain import explain
from f1pred.features import FEATURES_BY_STAGE, build_features
from f1pred.publish import standings_doc
from f1pred.simulate import fit_beta, plackett_luce_loglik, simulate
from f1pred.storage import Store

TEAMS = ["mercedes", "red_bull", "ferrari", "mclaren", "aston_martin", "alpine", "williams", "rb", "sauber", "haas"]


def synthetic_history(seasons=(2022, 2023, 2024), races=12, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    skill = np.linspace(2.0, -2.0, 20)  # driver 0 is the fastest
    rows = []
    for season in seasons:
        for rnd in range(1, races + 1):
            pace = skill + rng.normal(0, 0.6, 20)
            quali_order = np.argsort(-(pace + rng.normal(0, 0.3, 20)))
            quali_pos = np.empty(20, int)
            quali_pos[quali_order] = np.arange(1, 21)
            dnf = rng.random(20) < 0.08
            race_score = np.where(dnf, -99, pace + rng.normal(0, 0.5, 20))
            finish = np.empty(20, int)
            finish[np.argsort(-race_score)] = np.arange(1, 21)
            for d in range(20):
                rows.append(
                    {
                        "season": season, "round": rnd, "race_name": f"GP {rnd}", "circuit_id": f"c{rnd}",
                        "date": f"{season}-01-{rnd:02d}", "driver_id": f"d{d}", "code": f"D{d:02d}", "number": str(d),
                        "first_name": "Test", "last_name": f"Driver{d}", "constructor_id": TEAMS[d // 2],
                        "constructor_name": TEAMS[d // 2].title(), "grid": float(quali_pos[d]), "position": int(finish[d]),
                        "classified": not dnf[d], "status": "Retired" if dnf[d] else "Finished",
                        "points": float([25, 18, 15, 12, 10, 8, 6, 4, 2, 1][finish[d] - 1]) if finish[d] <= 10 and not dnf[d] else 0.0,
                        "quali_pos": float(quali_pos[d]), "quali_best": 80 + quali_pos[d] * 0.1,
                        "fp_best_gap_pct": quali_pos[d] * 0.1, "fp_longrun_gap_pct": quali_pos[d] * 0.08, "rain": 0.0,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def feats():
    return build_features(synthetic_history())


def test_features_only_use_past_races(feats):
    first = feats[(feats["season"] == 2022) & (feats["round"] == 1)]
    assert first["driver_form_ewm"].isna().all()
    assert first["driver_last_finish"].isna().all()
    second = feats[(feats["season"] == 2022) & (feats["round"] == 2)].set_index("driver_id")
    first = first.set_index("driver_id")
    assert (second["driver_last_finish"] == first["position"].reindex(second.index)).all()


def test_labels_rank_classified_finishers(feats):
    race = feats[(feats["season"] == 2023) & (feats["round"] == 3)]
    winner = race.loc[race["position"].idxmin()]
    assert winner["label"] == race["label"].max()
    assert race.loc[~race["classified"].astype(bool), "label"].isna().all()


def test_simulation_probabilities_are_consistent():
    scores = np.linspace(3, -3, 20)
    sim = simulate(scores, beta=1.0, p_dnf=np.full(20, 0.05), n=4000)
    assert sim["win"].sum() == pytest.approx(1.0)
    assert sim["podium"].sum() == pytest.approx(3.0)
    assert sim["distribution"].sum(axis=1) == pytest.approx(np.ones(20))
    assert sim["win"][0] > sim["win"][1] > sim["win"][5]
    assert np.all(np.diff(sim["expected_position"]) > -0.2)


def test_beta_recovers_true_temperature():
    rng = np.random.default_rng(1)
    races = []
    for _ in range(200):
        s = rng.normal(0, 1, 20)
        order = np.argsort(-(2.0 * s + rng.gumbel(size=20)))
        races.append(s[order])
    assert fit_beta(races) == pytest.approx(2.0, rel=0.2)
    assert plackett_luce_loglik(np.array([2.0, 1.0, 0.0]), 1.0) < 0


@pytest.mark.parametrize("kind", models.KINDS)
def test_model_trains_saves_and_loads(feats, kind, tmp_path):
    fitted = models.train_stage(feats, "quali", kind, 2024)
    race = feats[(feats["season"] == 2024) & (feats["round"] == 12)]
    scores = fitted.scores(race)
    # The fastest synthetic driver should score above the slowest.
    by_driver = dict(zip(race["driver_id"], scores))
    assert by_driver["d0"] > by_driver["d19"]
    store = Store(str(tmp_path))
    models.save(fitted, store)
    loaded = models.load("quali", store)
    assert np.allclose(loaded.scores(race), scores, atol=1e-5)
    contrib = loaded.contributions(race)
    assert contrib.shape == (len(race), len(FEATURES_BY_STAGE["quali"]))


def test_backtest_beats_nothing_burger(feats):
    summary = summarize(backtest(feats, [2024], stages=("quali",), kinds=("xgboost",)))
    assert summary.loc[("quali", "xgboost"), "spearman"] > 0.5


def test_explanations_read_naturally(feats):
    fitted = models.train_stage(feats, "quali", "xgboost", 2024)
    race = feats[(feats["season"] == 2024) & (feats["round"] == 12)].reset_index(drop=True)
    reasons = explain(race, fitted.features, fitted.contributions(race))
    assert len(reasons) == len(race)
    assert all(r["summary"].endswith(".") for r in reasons)
    assert all(len(r["factors"]) > 0 for r in reasons)


def test_predicted_standings_apply_points():
    drivers = [
        {"Driver": {"driverId": "a", "code": "AAA", "givenName": "A", "familyName": "A"}, "Constructors": [{"constructorId": "t1", "name": "T1"}], "position": "1", "points": "100", "wins": "3"},
        {"Driver": {"driverId": "b", "code": "BBB", "givenName": "B", "familyName": "B"}, "Constructors": [{"constructorId": "t2", "name": "T2"}], "position": "2", "points": "90", "wins": "2"},
    ]
    teams = [
        {"Constructor": {"constructorId": "t1", "name": "T1"}, "position": "1", "points": "150", "wins": "3"},
        {"Constructor": {"constructorId": "t2", "name": "T2"}, "position": "2", "points": "140", "wins": "2"},
    ]
    prediction = {
        "race": {"season": 2026, "round": 5},
        "drivers": [
            {"driver_id": "b", "team_id": "t2", "predicted_position": 1},
            {"driver_id": "a", "team_id": "t1", "predicted_position": 11},
        ],
    }
    doc = standings_doc(drivers, teams, prediction, {})
    b = next(d for d in doc["drivers"] if d["driver_id"] == "b")
    assert b["predicted_points"] == 115 and b["predicted_position"] == 1 and b["position_change"] == 1
    t2 = next(t for t in doc["constructors"] if t["team_id"] == "t2")
    assert t2["predicted_position"] == 1
