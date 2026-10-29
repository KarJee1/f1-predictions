"""Orchestration: keeps the race history up to date, trains models, and on every scheduled tick
publishes whatever the app needs (prediction for the next race, standings, results, accuracy, news)."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import model as models
from . import publish, social
from .sources import timing
from .config import settings
from .dataset import build_history, schedule_frame
from .evaluate import backtest, score_race, summarize
from .explain import explain
from .features import STAGES, build_features
from .jolpica import Jolpica, parse_lap_time
from .news import fetch_news
from .simulate import dnf_probability, simulate
from .storage import Store
from .weather import race_forecast

log = logging.getLogger(__name__)

HISTORY_KEY = "data/history.parquet"
STATE_KEY = "data/state.json"
COLORS_KEY = "data/team_colors.json"

# Fallback colors; replaced by the official ones from live timing whenever a session loads.
DEFAULT_TEAM_COLORS = {
    "mercedes": "#27F4D2",
    "red_bull": "#3671C6",
    "ferrari": "#E8002D",
    "mclaren": "#FF8000",
    "aston_martin": "#229971",
    "alpine": "#FF87BC",
    "williams": "#64C4FF",
    "rb": "#6692FF",
    "sauber": "#52E252",
    "audi": "#BB0A30",
    "haas": "#B6BABD",
    "cadillac": "#A6A6A6",
}

SESSION_DONE_AFTER = timedelta(minutes=75)  # a session counts as done once its data has had time to land
RACE_DONE_AFTER = timedelta(hours=3)


class Pipeline:
    def __init__(self, store: Store | None = None, client: Jolpica | None = None):
        self.store = store or Store()
        self.client = client or Jolpica()
        self._history: pd.DataFrame | None = None

    # -- history -------------------------------------------------------------------------------

    def history(self) -> pd.DataFrame:
        if self._history is None:
            blob = self.store.read_bytes(HISTORY_KEY)
            self._history = pd.read_parquet(io.BytesIO(blob)) if blob else self.refresh_history()
        return self._history

    def refresh_history(self, full: bool = False) -> pd.DataFrame:
        this_year = datetime.now(timezone.utc).year
        seasons = list(range(settings.first_season, this_year + 1))
        blob = None if full else self.store.read_bytes(HISTORY_KEY)
        if blob:
            stored = pd.read_parquet(io.BytesIO(blob))
            keep = stored[stored["season"] < this_year]
            if settings.use_timing:
                # Seasons stored before practice timing was available get rebuilt once with it (OpenF1 starts in 2023).
                recent = keep[keep["season"] >= 2023]
                if "fp_best_gap_pct" in recent:
                    has = recent.groupby("season")["fp_best_gap_pct"].apply(lambda v: v.notna().any())
                    bare = set(has[~has].index)
                else:
                    bare = set(recent["season"])
                keep = keep[~keep["season"].isin(bare)]
            missing = [s for s in seasons if s == this_year or s not in set(keep["season"])]
            history = pd.concat([keep, build_history(self.client, missing, with_timing=settings.use_timing)], ignore_index=True)
        else:
            history = build_history(self.client, seasons, with_timing=settings.use_timing)
        buf = io.BytesIO()
        history.to_parquet(buf, index=False)
        self.store.write_bytes(HISTORY_KEY, buf.getvalue())
        self._history = history
        return history

    # -- training ------------------------------------------------------------------------------

    def train(self, kinds: tuple[str, ...] = models.KINDS, test_seasons: list[int] | None = None) -> dict:
        """Backtest each model type per stage, keep the best by winner log loss, retrain it on everything."""
        df = build_features(self.history())
        latest = int(df["season"].max())
        if test_seasons is None:
            races_this_season = df.loc[df["season"] == latest, "round"].nunique()
            test_seasons = [latest - 1, latest] if races_this_season >= 5 else [latest - 2, latest - 1]

        report = {"trained_at": datetime.now(timezone.utc).isoformat(), "test_seasons": test_seasons, "stages": {}}
        for stage in STAGES:
            if len(kinds) > 1:
                summary = summarize(backtest(df, test_seasons, stages=(stage,), kinds=kinds)).loc[stage]
                candidates = summary.drop(index="baseline", errors="ignore")
                kind = str(candidates["winner_log_loss"].idxmin())
                table = summary.reset_index().replace({np.nan: None}).to_dict(orient="records")
            else:
                kind, table = kinds[0], []
            fitted = models.train_stage(df, stage, kind, latest)
            fitted.metrics = {"backtest": table}
            models.save(fitted, self.store)
            report["stages"][stage] = {"model": kind, "beta": fitted.beta, "backtest": table}
            log.info("Stage %s: chose %s (beta %.3f)", stage, kind, fitted.beta)
        self.store.write_json("v1/model.json", report)
        return report

    # -- prediction ----------------------------------------------------------------------------

    def team_colors(self) -> dict[str, str]:
        return DEFAULT_TEAM_COLORS | (self.store.read_json(COLORS_KEY) or {})

    def _entries(self, race: pd.Series, session_name: str | None) -> pd.DataFrame:
        """Who is racing: the latest session's entry list if there is one, else the last race's lineup."""
        hist = self.history()
        before = hist[(hist["season"] < race["season"]) | ((hist["season"] == race["season"]) & (hist["round"] < race["round"]))]
        last_key = before[["season", "round"]].drop_duplicates().sort_values(["season", "round"]).iloc[-1]
        last = before[(before["season"] == last_key["season"]) & (before["round"] == last_key["round"])]
        cols = ["driver_id", "code", "number", "first_name", "last_name", "constructor_id", "constructor_name"]
        lineup = last[cols].drop_duplicates("code").set_index("code", drop=False)

        try:
            session = timing.session_entries(int(race["season"]), int(race["round"]), session_name) if session_name else pd.DataFrame()
        except Exception:
            log.exception("Entry list failed; using the last race's lineup")
            session = pd.DataFrame()
        if session.empty:
            return lineup.reset_index(drop=True)

        # Map live-timing team names to constructor ids using drivers we already know.
        known = session[session["code"].isin(lineup.index)]
        team_map = (
            known.assign(cid=known["code"].map(lineup["constructor_id"]))
            .groupby("team_name")["cid"].agg(lambda s: s.mode().iloc[0])
            .to_dict()
        )
        names = lineup.drop_duplicates("constructor_id").set_index("constructor_id")["constructor_name"].to_dict()
        rows, colors = [], self.store.read_json(COLORS_KEY) or {}
        for _, e in session.iterrows():
            prior = lineup.loc[e["code"]] if e["code"] in lineup.index else None
            cid = team_map.get(e["team_name"]) or (prior["constructor_id"] if prior is not None else e["team_name"].lower().replace(" ", "_"))
            if isinstance(e["team_color"], str) and len(e["team_color"]) == 7:
                colors[cid] = e["team_color"]
            rows.append(
                {
                    "driver_id": prior["driver_id"] if prior is not None else e["code"].lower(),
                    "code": e["code"],
                    "number": e["number"],
                    "first_name": e["first_name"],
                    "last_name": e["last_name"],
                    "constructor_id": cid,
                    "constructor_name": names.get(cid, e["team_name"]),
                }
            )
        self.store.write_json(COLORS_KEY, colors)
        return pd.DataFrame(rows)

    def _quali(self, season: int, rnd: int) -> pd.DataFrame:
        rows = []
        for q in self.client.round_qualifying(season, rnd):
            times = [t for t in (parse_lap_time(q.get(k)) for k in ("Q1", "Q2", "Q3")) if t]
            rows.append({"code": q["Driver"].get("code"), "quali_pos": int(q["position"]), "quali_best": min(times) if times else np.nan})
        if rows:
            return pd.DataFrame(rows)
        try:
            return timing.quali_results(season, rnd)
        except Exception:
            log.exception("Qualifying from timing failed")
            return pd.DataFrame(columns=["code", "quali_pos", "quali_best"])

    def predict(self, race: pd.Series, stage: str, session_name: str | None, now: datetime) -> dict:
        season, rnd = int(race["season"]), int(race["round"])
        rows = self._entries(race, session_name)
        rows = rows.assign(
            season=season, round=rnd, race_name=race["race_name"], circuit_id=race["circuit_id"], date=race["date"],
            grid=np.nan, position=np.nan, classified=pd.NA, status=None, points=np.nan,
            quali_pos=np.nan, quali_best=np.nan, fp_best_gap_pct=np.nan, fp_longrun_gap_pct=np.nan, rain=np.nan,
        )
        if stage in ("practice", "quali"):
            try:
                fp = timing.practice_features(season, rnd)
            except Exception:
                log.exception("Practice timing failed; predicting without it")
                fp = pd.DataFrame()
            if not fp.empty:
                rows["fp_best_gap_pct"] = rows["code"].map(fp["fp_best_gap_pct"])
                rows["fp_longrun_gap_pct"] = rows["code"].map(fp["fp_longrun_gap_pct"])
        if stage == "quali":
            q = self._quali(season, rnd)
            if not q.empty:
                q = q.dropna(subset=["code"]).drop_duplicates("code").set_index("code")
                rows["quali_pos"] = rows["code"].map(q["quali_pos"])
                rows["quali_best"] = rows["code"].map(q["quali_best"])
            # The official grid (with penalties) is only published with the result.
            rows["grid"] = rows["quali_pos"]
        weather = race_forecast(race["lat"], race["lon"], race["race_start"].to_pydatetime()) if pd.notna(race["race_start"]) else None
        if weather and weather.get("rain_prob") is not None:
            rows["rain"] = weather["rain_prob"]

        hist = self.history()
        prior = hist[(hist["season"] < season) | ((hist["season"] == season) & (hist["round"] < rnd))]
        feats = build_features(pd.concat([prior, rows], ignore_index=True))
        target = feats[(feats["season"] == season) & (feats["round"] == rnd)].reset_index(drop=True)

        fitted = None
        for s in STAGES[: STAGES.index(stage) + 1][::-1]:  # fall back to an earlier stage's model if needed
            fitted = models.load(s, self.store)
            if fitted:
                break
        if fitted is None:
            raise RuntimeError("No trained model found; run `f1pred train` first")

        scores = fitted.scores(target)
        p_dnf = dnf_probability(target["team_dnf_rate"].to_numpy(float), target["driver_dnf_rate"].to_numpy(float))
        sim = simulate(scores, fitted.beta, p_dnf, n=settings.n_simulations)
        reasons = explain(target, fitted.features, fitted.contributions(target))
        return publish.prediction_doc(race, stage, target, sim, reasons, fitted.kind, weather, self.team_colors())

    # -- scheduled tick ------------------------------------------------------------------------

    def schedule(self, season: int) -> pd.DataFrame:
        return schedule_frame(self.client, season)

    @staticmethod
    def stage_for(race: pd.Series, now: datetime) -> tuple[str, str | None]:
        """Which prediction stage applies right now, and the latest session to take the entry list from."""
        def done(col):
            return pd.notna(race[col]) and race[col] + SESSION_DONE_AFTER <= now

        if done("quali_start"):
            return "quali", "Q"
        for name, col in (("FP3", "fp3_start"), ("FP2", "fp2_start"), ("FP1", "fp1_start")):
            if done(col):
                return "practice", name
        return "pre", None

    def run(self, now: datetime | None = None, force: bool = False) -> dict:
        now = now or datetime.now(timezone.utc)
        state = self.store.read_json(STATE_KEY) or {"scored": [], "predictions": {}}
        season = now.year
        sched = self.schedule(season)
        if sched.empty or (sched["race_start"] + RACE_DONE_AFTER < now).all():
            nxt = self.schedule(season + 1)
            if not nxt.empty:
                sched, season = pd.concat([sched, nxt], ignore_index=True), season + 1
        self.store.write_json(f"v1/schedule/{season}.json", [publish.race_info(r) for _, r in sched[sched["season"] == season].iterrows()])
        summary = {"now": now.isoformat(), "actions": []}

        # 1. Score finished races that have results and haven't been scored yet.
        finished = sched[sched["race_start"] + RACE_DONE_AFTER < now]
        newly_scored = False
        for _, race in finished.iterrows():
            key = f"{int(race['season'])}-{int(race['round'])}"
            if key in state["scored"]:
                continue
            results = self.client.round_results(int(race["season"]), int(race["round"]))
            if not results:
                continue
            self._score(race, results)
            state["scored"].append(key)
            newly_scored = True
            summary["actions"].append(f"scored {key}")
        last_race = finished.iloc[-1] if not finished.empty else None

        # Friend groups: score everyone's synced picks for races that finished in the last week.
        if settings.groups:
            done = set(state.setdefault("group_scored", []))
            for _, race in finished[finished["race_start"] > now - timedelta(days=7)].iterrows():
                key = f"{int(race['season'])}-{int(race['round'])}"
                results = self.store.read_json(f"v1/races/{key.replace('-', '/')}/results.json")
                if key in done or not results:
                    continue
                try:
                    n = social.score_race(int(race["season"]), int(race["round"]), results["results"])
                except Exception as exc:  # leave it for the next run
                    log.warning("Scoring group picks for %s failed: %s", key, exc)
                    continue
                state["group_scored"].append(key)
                summary["actions"].append(f"scored {n} group picks for {key}")

        if newly_scored:
            self.refresh_history()
            self.train()
            summary["actions"].append("retrained")

        # A fresh deployment has no accuracy history yet: fill it in with out-of-sample predictions.
        if last_race is not None and self.store.read_json(f"v1/accuracy/{int(last_race['season'])}.json") is None:
            self.backfill_accuracy(int(last_race["season"]))
            summary["actions"].append("backfilled accuracy")

        # 2. Predict the next race.
        upcoming = sched[sched["race_start"] + RACE_DONE_AFTER >= now]
        prediction = None
        if not upcoming.empty:
            race = upcoming.iloc[0]
            stage, session_name = self.stage_for(race, now)
            key = f"{int(race['season'])}-{int(race['round'])}"
            base = f"v1/races/{int(race['season'])}/{int(race['round'])}"
            previous = state["predictions"].get(key, {})
            race_week = race["race_start"] - now < timedelta(days=7)
            stale = previous.get("stage") != stage or previous.get("session") != session_name or (
                race_week and now - datetime.fromisoformat(previous["generated_at"]) > timedelta(hours=6)
            )
            if force or stale or newly_scored:
                prediction = self.predict(race, stage, session_name, now)
                self.store.write_json(f"{base}/prediction.json", prediction)
                self.store.write_json(f"{base}/prediction-{stage}.json", prediction)
                state["predictions"][key] = {"stage": stage, "session": session_name, "generated_at": prediction["generated_at"]}
                summary["actions"].append(f"predicted {key} ({stage})")
            else:
                prediction = self.store.read_json(f"{base}/prediction.json")

            self.store.write_json(
                "v1/meta.json",
                {
                    "generated_at": now.isoformat(),
                    "season": int(race["season"]),
                    "next_race": publish.race_info(race),
                    "prediction_path": f"{base}/prediction.json",
                    "prediction_stage": state["predictions"].get(key, {}).get("stage"),
                    "last_race": publish.race_info(last_race) if last_race is not None else None,
                    "last_results_path": (
                        f"v1/races/{int(last_race['season'])}/{int(last_race['round'])}/results.json" if last_race is not None else None
                    ),
                },
            )

        # 3. Standings with the predicted change.
        standings_season = int(last_race["season"]) if last_race is not None else season
        self.store.write_json(
            "v1/standings.json",
            publish.standings_doc(
                self.client.driver_standings(standings_season),
                self.client.constructor_standings(standings_season),
                prediction if prediction and prediction["race"]["season"] == standings_season else None,
                self.team_colors(),
            ),
        )

        # 4. News from this race weekend and the previous one.
        since = (last_race["race_start"] - timedelta(days=4)) if last_race is not None else now - timedelta(days=14)
        self.store.write_json("v1/news.json", {"generated_at": now.isoformat(), "items": fetch_news(since.to_pydatetime() if hasattr(since, "to_pydatetime") else since)})

        self.store.write_json(STATE_KEY, state)
        return summary

    def backfill_accuracy(self, season: int) -> dict:
        """Fill the accuracy history for races that finished before the app was publishing.
        Each race is predicted by a model trained only on races before it (post-qualifying
        stage), so these are honest out-of-sample numbers, and they're marked as backfilled."""
        df = build_features(self.history())
        meta = self.store.read_json("models/quali.json") or {"kind": "lightgbm"}
        sched = self.schedule(season).set_index("round")
        doc = self.store.read_json(f"v1/accuracy/{season}.json") or {"season": season, "races": []}
        done = {r["round"] for r in doc["races"]}
        for rnd in sorted(df.loc[(df["season"] == season) & df["label"].notna(), "round"].unique()):
            rnd = int(rnd)
            if rnd in done:
                continue
            race_idx = int(df.loc[(df["season"] == season) & (df["round"] == rnd), "race_idx"].iloc[0])
            fitted = models.train_stage(df[df["race_idx"] < race_idx], "quali", meta["kind"], season)
            race = df[df["race_idx"] == race_idx].reset_index(drop=True)
            scores = fitted.scores(race)
            p_dnf = dnf_probability(race["team_dnf_rate"].to_numpy(float), race["driver_dnf_rate"].to_numpy(float))
            sim = simulate(scores, fitted.beta, p_dnf, n=5000)
            order = sorted(range(len(race)), key=lambda i: (-sim["win"][i], -sim["podium"][i], sim["expected_position"][i]))
            ids = race["driver_id"].tolist()
            pred_order = [ids[i] for i in order]
            scored = score_race(pred_order, dict(zip(ids, sim["win"])), race[["driver_id", "position"]])
            code = dict(zip(race["driver_id"], race["code"]))
            actual = race.sort_values("position")["driver_id"].tolist()
            doc["races"].append(
                {
                    "round": rnd,
                    "race_name": sched.loc[rnd, "race_name"] if rnd in sched.index else race["race_name"].iloc[0],
                    "stage": "quali",
                    "backfilled": True,
                    **scored,
                    "predicted_top3": [code[d] for d in pred_order[:3]],
                    "actual_top3": [code[d] for d in actual[:3]],
                }
            )
        self._write_accuracy(doc)
        return doc["summary"]

    def _write_accuracy(self, doc: dict) -> None:
        doc["races"].sort(key=lambda r: r["round"])
        n = len(doc["races"])
        if n:
            doc["summary"] = {
                "races": n,
                "winner_correct_pct": round(100 * sum(r["winner_correct"] for r in doc["races"]) / n, 1),
                "avg_podium_hits": round(sum(r["podium_hits"] for r in doc["races"]) / n, 2),
                "avg_spearman": round(float(np.nanmean([r["spearman"] for r in doc["races"]])), 3),
            }
        self.store.write_json(f"v1/accuracy/{doc['season']}.json", doc)

    def _score(self, race: pd.Series, results: list[dict]) -> None:
        season, rnd = int(race["season"]), int(race["round"])
        base = f"v1/races/{season}/{rnd}"
        self.store.write_json(f"{base}/results.json", publish.results_doc(race, results))
        prediction = self.store.read_json(f"{base}/prediction.json")
        if not prediction:
            return
        actual = pd.DataFrame(
            {
                "driver_id": [r["Driver"]["driverId"] for r in results],
                "position": [int(r["position"]) for r in results],
            }
        )
        order = [d["driver_id"] for d in prediction["drivers"]]
        win = {d["driver_id"]: d["win_pct"] / 100 for d in prediction["drivers"]}
        scored = score_race(order, win, actual)
        actual_sorted = actual.sort_values("position")["driver_id"].tolist()
        code = {d["driver_id"]: d["code"] for d in prediction["drivers"]}
        entry = {
            "round": rnd,
            "race_name": race["race_name"],
            "stage": prediction["stage"],
            **scored,
            "predicted_top3": [code.get(d, d) for d in order[:3]],
            "actual_top3": [code.get(d, d) for d in actual_sorted[:3]],
        }
        doc = self.store.read_json(f"v1/accuracy/{season}.json") or {"season": season, "races": []}
        doc["races"] = [r for r in doc["races"] if r["round"] != rnd] + [entry]
        self._write_accuracy(doc)
